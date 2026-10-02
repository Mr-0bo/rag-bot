# backend/routers/sync.py
import json
import hashlib
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from qdrant_client.http import models
import fitz  # PyMuPDF

from backend.database import get_db, SessionLocal, ConfiguracionApp, DocumentoNormativo
from backend.search_service import (
    get_embedding_model,
    indexar_chunks_documento,
    eliminar_documento_por_ruta
)

router = APIRouter(prefix="/api/sync", tags=["Sincronización"])


def recopilar_archivos_pdf(carpetas: List[str]) -> List[Path]:
    """Busca recursivamente archivos .pdf en las carpetas seleccionadas."""
    pdfs = []
    for c in carpetas:
        if not c:
            continue
        p = Path(c).expanduser().resolve()
        if p.exists() and p.is_dir():
            for archivo in p.rglob("*.pdf"):
                if not archivo.name.startswith("._") and archivo.is_file():
                    pdfs.append(archivo)
    return pdfs


def calcular_hash_archivo(ruta: Path) -> str:
    """Calcula el hash MD5 para control de cambios e indexación incremental."""
    hasher = hashlib.md5()
    with open(ruta, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@router.get("/check")
def verificar_cambios_pendientes(db: Session = Depends(get_db)):
    """Verifica en segundo plano si hay PDFs nuevos, modificados o eliminados."""
    config = db.query(ConfiguracionApp).first()
    if not config or not config.directorio_obligatorio:
        return {"requiere_sincronizacion": False, "total_pendientes": 0}

    directorios = [
        config.directorio_obligatorio,
        config.directorio_opcional_1,
        config.directorio_opcional_2
    ]
    archivos_disco = recopilar_archivos_pdf(directorios)
    registrados = {doc.ruta_absoluta: doc for doc in db.query(DocumentoNormativo).all()}

    nuevos = 0
    modificados = 0

    for f in archivos_disco:
        ruta_str = str(f.resolve())
        if ruta_str not in registrados:
            nuevos += 1
        else:
            try:
                if f.stat().st_mtime > (registrados[ruta_str].mtime or 0):
                    modificados += 1
            except Exception:
                pass

    eliminados = max(0, len(registrados) - len(archivos_disco))
    total = nuevos + modificados + eliminados

    return {
        "requiere_sincronizacion": total > 0,
        "total_pendientes": total,
        "nuevos": nuevos,
        "modificados": modificados,
        "eliminados": eliminados
    }


def procesar_e_indexar_pdf(archivo: Path, region: str, db: Session):
    """Extrae texto con PyMuPDF, genera vectores y almacena en SQLite + Qdrant."""
    ruta_abs = str(archivo.resolve())
    nombre = archivo.name
    hash_actual = calcular_hash_archivo(archivo)
    stat = archivo.stat()

    doc_db = db.query(DocumentoNormativo).filter(DocumentoNormativo.ruta_absoluta == ruta_abs).first()

    # Si ya está indexado y no cambió su contenido, omitir reprocesamiento
    if doc_db and doc_db.hash_md5 == hash_actual and doc_db.esta_indexado:
        return

    # Limpiar vectores previos en Qdrant por ruta antes de re-indexar
    eliminar_documento_por_ruta(ruta_abs)

    doc_fitz = fitz.open(archivo)
    total_paginas = len(doc_fitz)
    modelo = get_embedding_model()

    puntos_qdrant = []
    chunk_index = 0

    for num_pag in range(total_paginas):
        pagina = doc_fitz[num_pag]
        texto = pagina.get_text("text").strip()

        if not texto:
            continue

        # Segmentación en bloques de ~1000 caracteres con solapamiento
        sub_chunks = [texto[i:i + 1000] for i in range(0, len(texto), 850)]

        for sub_chunk in sub_chunks:
            chunk_limpio = sub_chunk.strip()
            if len(chunk_limpio) < 20:
                continue

            vector = list(modelo.embed([chunk_limpio]))[0].tolist()

            puntos_qdrant.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "documento": nombre,
                        "ruta_relativa": ruta_abs,  # Usamos ruta_abs para unicidad estricta al borrar
                        "ruta_absoluta": ruta_abs,
                        "pagina": num_pag + 1,
                        "contenido": chunk_limpio,
                        "region": region.lower()
                    }
                )
            )
            chunk_index += 1

    doc_fitz.close()

    # Guardar vectores en Qdrant
    if puntos_qdrant:
        indexar_chunks_documento(puntos_qdrant)

    # Actualizar registro en SQLite
    if not doc_db:
        doc_db = DocumentoNormativo(
            id=str(uuid.uuid4()),
            ruta_absoluta=ruta_abs,
            nombre_archivo=nombre,
            ruta_relativa=ruta_abs,
            region=region.lower()
        )
        db.add(doc_db)

    doc_db.hash_md5 = hash_actual
    doc_db.mtime = stat.st_mtime
    doc_db.tamanio_bytes = stat.st_size
    doc_db.total_paginas = total_paginas
    doc_db.total_chunks = chunk_index
    doc_db.esta_indexado = True
    db.commit()


def generador_indexacion_sse():
    """Generador que procesa los documentos y emite eventos SSE al frontend."""
    db = SessionLocal()
    try:
        config = db.query(ConfiguracionApp).first()
        if not config or not config.directorio_obligatorio:
            yield f"data: {json.dumps({'tipo': 'error', 'mensaje': 'No hay directorios configurados.'})}\n\n"
            return

        directorios = [
            config.directorio_obligatorio,
            config.directorio_opcional_1,
            config.directorio_opcional_2
        ]
        archivos = recopilar_archivos_pdf(directorios)
        total = len(archivos)

        if total == 0:
            yield f"data: {json.dumps({'tipo': 'progreso', 'progreso': 100, 'archivo': 'Sin archivos PDF', 'mensaje': 'No se encontraron PDFs en las carpetas seleccionadas.'})}\n\n"
            yield f"data: {json.dumps({'tipo': 'fin'})}\n\n"
            return

        for i, archivo in enumerate(archivos, 1):
            nombre = archivo.name
            porcentaje = int((i / total) * 100)

            payload_progreso = {
                "tipo": "progreso",
                "progreso": porcentaje,
                "archivo": nombre,
                "mensaje": f"Procesando {i} de {total}"
            }
            yield f"data: {json.dumps(payload_progreso)}\n\n"

            try:
                procesar_e_indexar_pdf(archivo, region=config.region or "mexico", db=db)
            except Exception as e:
                print(f"[WARN INDEX] Error al indexar {nombre}: {e}")

        yield f"data: {json.dumps({'tipo': 'fin'})}\n\n"

    except Exception as e:
        print(f"[ERROR SSE] {e}")
        yield f"data: {json.dumps({'tipo': 'error', 'mensaje': str(e)})}\n\n"
    finally:
        db.close()


@router.get("/stream")
def stream_indexacion():
    """Endpoint Server-Sent Events (SSE) consumido por EventSource en app.js."""
    return StreamingResponse(
        generador_indexacion_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )