# ingestion/ingest_docs.py
import os
import re
import time
import uuid
import hashlib
from pathlib import Path
from typing import Callable, Optional, Generator
from qdrant_client.http import models

from backend.config import settings
from backend.database import SessionLocal, DocumentoNormativo
from ingestion.document_parser import extraer_markdown_de_pdf
from backend.search_service import (
    eliminar_documento_por_ruta,
    indexar_chunks_documento,
    get_embedding_model,
)


def calcular_hash_md5(ruta_archivo: Path) -> str:
    """Calcula el hash MD5 de un archivo leyendo en bloques."""
    hasher = hashlib.md5()
    with open(ruta_archivo, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def forzar_hidratacion_onedrive(ruta_pdf: Path, timeout_segundos: int = 45) -> bool:
    """Fuerza la descarga de archivos 'Files On-Demand' de OneDrive."""
    if os.name == "nt":
        os.system(f'attrib -U "{ruta_pdf}" >nul 2>&1')

    inicio = time.time()
    while time.time() - inicio < timeout_segundos:
        try:
            with open(ruta_pdf, "rb") as f:
                primeros_bytes = f.read(1024)
                if len(primeros_bytes) > 0 and ruta_pdf.stat().st_size > 0:
                    return True
        except (PermissionError, OSError):
            time.sleep(1)

    return False


def limpiar_texto(texto: str) -> str:
    """Normaliza espacios en blanco conservando la estructura de párrafos."""
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


def dividir_en_chunks(texto: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
    """Divide texto en fragmentos respetando palabras y solapamiento."""
    palabras = texto.split()
    if not palabras:
        return []
    chunks = []
    i = 0
    while i < len(palabras):
        chunk = " ".join(palabras[i : i + chunk_size])
        chunks.append(chunk)
        i += max(1, chunk_size - overlap)
    return chunks


def auditar_directorio(directorio_raiz: Path, region: str = "mexico") -> dict:
    """
    Escanea la carpeta de OneDrive buscando únicamente PDFs dentro de '2025-2026',
    compara contra SQLite y clasifica en nuevos, modificados, sin_cambios y eliminados.
    """
    db = SessionLocal()
    try:
        registros_bd = {
            doc.ruta_relativa: doc
            for doc in db.query(DocumentoNormativo).filter(DocumentoNormativo.region == region).all()
        }

        nuevos = []
        modificados = []
        sin_cambios = []
        encontrados_en_disco = set()

        for pdf in directorio_raiz.rglob("*"):
            if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                continue
            if pdf.name.startswith("~") or pdf.name.startswith("."):
                continue

            # Filtro estricto de periodo de vigencia
            if settings.CARPETA_VIGENCIA.lower() not in str(pdf).lower():
                continue

            ruta_rel = str(pdf.relative_to(directorio_raiz))
            encontrados_en_disco.add(ruta_rel)

            if not forzar_hidratacion_onedrive(pdf):
                print(f"[WARN] No se pudo asegurar la hidratación de: {pdf.name}")
                continue

            hash_actual = calcular_hash_md5(pdf)

            if ruta_rel not in registros_bd:
                nuevos.append((pdf, ruta_rel, hash_actual))
            elif registros_bd[ruta_rel].hash_md5 != hash_actual:
                modificados.append((pdf, ruta_rel, hash_actual))
            else:
                sin_cambios.append(ruta_rel)

        eliminados = [r for r in registros_bd.keys() if r not in encontrados_en_disco]

        return {
            "nuevos": nuevos,
            "modificados": modificados,
            "sin_cambios": sin_cambios,
            "eliminados": eliminados,
        }
    finally:
        db.close()


def procesar_e_indexar_archivo(
    ruta_pdf: Path,
    ruta_rel: str,
    hash_md5: str,
    region: str,
    embedding_model
) -> int:
    """Extrae texto con PyMuPDF/PaddleOCR, vectoriza con BGE-small y sube a Qdrant."""
    paginas = extraer_markdown_de_pdf(ruta_pdf)
    puntos_qdrant = []
    total_chunks = 0

    textos_chunk = []
    metadatos_chunk = []

    for item in paginas:
        num_pag = item["pagina"]
        texto_limpio = limpiar_texto(item["texto"])
        chunks = dividir_en_chunks(texto_limpio)

        for idx, chunk in enumerate(chunks):
            total_chunks += 1
            textos_chunk.append(chunk)
            metadatos_chunk.append({
                "pagina": num_pag,
                "sub_idx": idx,
                "texto": chunk,
            })

    if not textos_chunk:
        return 0

    # Inferencia de embeddings local en lote
    vectores = list(embedding_model.embed(textos_chunk))

    for meta, vector in zip(metadatos_chunk, vectores):
        # UUID determinista basado en ruta y fragmento
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{ruta_rel}_{meta['pagina']}_{meta['sub_idx']}"))
        puntos_qdrant.append(
            models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "documento": ruta_pdf.name,
                    "ruta_relativa": ruta_rel,
                    "pagina": meta["pagina"],
                    "contenido": meta["texto"],
                    "region": region.lower(),
                },
            )
        )

    # Inserción en Qdrant
    indexar_chunks_documento(puntos_qdrant)

    # Actualizar registro en SQLite
    db = SessionLocal()
    try:
        doc = db.query(DocumentoNormativo).filter(DocumentoNormativo.ruta_relativa == ruta_rel).first()
        stat = ruta_pdf.stat()
        if not doc:
            doc = DocumentoNormativo(
                id=hash_md5,
                nombre_archivo=ruta_pdf.name,
                ruta_absoluta=str(ruta_pdf.resolve()),
                ruta_relativa=ruta_rel,
                region=region.lower(),
                hash_md5=hash_md5,
                tamanio_bytes=stat.st_size,
                mtime=stat.st_mtime,
                total_paginas=len(paginas),
                total_chunks=total_chunks,
                esta_indexado=True,
            )
            db.add(doc)
        else:
            doc.hash_md5 = hash_md5
            doc.tamanio_bytes = stat.st_size
            doc.mtime = stat.st_mtime
            doc.total_paginas = len(paginas)
            doc.total_chunks = total_chunks
            doc.esta_indexado = True

        db.commit()
    finally:
        db.close()

    return total_chunks


def sincronizar_directorio(
    directorio: str | Path,
    region: str = "mexico",
    callback_progreso: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """
    Sincroniza una carpeta de OneDrive:
    1. Audita cambios
    2. Purga eliminados y modificados en Qdrant
    3. Procesa e indexa únicamente nuevos y modificados
    """
    directorio_raiz = Path(directorio).expanduser().resolve()
    if not directorio_raiz.exists():
        raise FileNotFoundError(f"La ruta no existe: {directorio_raiz}")

    auditoria = auditar_directorio(directorio_raiz, region=region)
    db = SessionLocal()

    # 1. Purgar eliminados
    try:
        for ruta_rel in auditoria["eliminados"]:
            eliminar_documento_por_ruta(ruta_rel)
            db.query(DocumentoNormativo).filter(DocumentoNormativo.ruta_relativa == ruta_rel).delete()
        db.commit()
    finally:
        db.close()

    # 2. Purgar modificados en Qdrant antes de reindexar
    for _, ruta_rel, _ in auditoria["modificados"]:
        eliminar_documento_por_ruta(ruta_rel)

    # 3. Procesar nuevos y modificados
    a_procesar = auditoria["nuevos"] + auditoria["modificados"]
    total = len(a_procesar)
    modelo_embedding = get_embedding_model()

    chunks_totales = 0
    for idx, (pdf, ruta_rel, hash_md5) in enumerate(a_procesar, start=1):
        if callback_progreso:
            callback_progreso(idx, total, pdf.name)

        chunks = procesar_e_indexar_archivo(pdf, ruta_rel, hash_md5, region, modelo_embedding)
        chunks_totales += chunks

    return {
        "nuevos_procesados": len(auditoria["nuevos"]),
        "modificados_procesados": len(auditoria["modificados"]),
        "eliminados": len(auditoria["eliminados"]),
        "sin_cambios": len(auditoria["sin_cambios"]),
        "chunks_generados": chunks_totales,
    }


if __name__ == "__main__":
    carpeta_prueba = Path("./data")
    print(f"Probando escaneo en {carpeta_prueba.resolve()}...")
    if carpeta_prueba.exists():
        res = sincronizar_directorio(carpeta_prueba, region="mexico")
        print(f"Resultado de sincronización: {res}")