# ingestion/ingest_docs.py
import os
import re
import uuid
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.search.documents import SearchClient

from backend.config import settings
from backend.llm_orchestrator import generar_embedding

def limpiar_texto(texto: str) -> str:
    """Normaliza espacios en blanco y saltos de línea."""
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def dividir_en_chunks(texto: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Divide el texto extraído en fragmentos con solapamiento."""
    palabras = texto.split()
    chunks = []
    i = 0
    while i < len(palabras):
        chunk = " ".join(palabras[i:i + chunk_size])
        chunks.append(chunk)
        i += max(1, chunk_size - overlap)
    return chunks

def extraer_con_document_intelligence(ruta_pdf: str, doc_client: DocumentIntelligenceClient) -> list[tuple[int, str]]:
    """Extrae texto página por página usando el modelo prebuilt-layout de Azure."""
    print(f"  Analizando con Azure Document Intelligence...")
    with open(ruta_pdf, "rb") as f:
        contenido_bytes = f.read()

    poller = doc_client.begin_analyze_document(
        "prebuilt-layout",
        contenido_bytes,
        content_type="application/pdf"
    )
    resultado = poller.result()

    paginas_texto = []
    if resultado.pages:
        for pagina in resultado.pages:
            num_pag = pagina.page_number
            lineas = [linea.content for linea in pagina.lines] if pagina.lines else []
            texto_pag = " ".join(lineas)
            if texto_pag.strip():
                paginas_texto.append((num_pag, texto_pag))
    return paginas_texto

def indexar_carpeta(ruta_carpeta: str = "data"):
    if not os.path.exists(ruta_carpeta):
        os.makedirs(ruta_carpeta)
        print(f"Directorio '{ruta_carpeta}/' creado. Coloca los PDFs normativos allí.")
        return

    archivos_pdf = [f for f in os.listdir(ruta_carpeta) if f.lower().endswith(".pdf")]
    if not archivos_pdf:
        print(f"No hay archivos PDF en la carpeta '{ruta_carpeta}/'.")
        return

    # Clientes de Azure
    doc_client = DocumentIntelligenceClient(
        endpoint=settings.AZURE_DOC_INTEL_ENDPOINT,
        credential=AzureKeyCredential(settings.AZURE_DOC_INTEL_KEY),
        api_version="2024-11-30"
    )
    search_client = SearchClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT,
        index_name=settings.AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(settings.AZURE_SEARCH_KEY)
    )

    documentos_a_subir = []

    for archivo in archivos_pdf:
        ruta_archivo = os.path.join(ruta_carpeta, archivo)
        print(f"\nProcesando archivo: {archivo}")

        paginas = extraer_con_document_intelligence(ruta_archivo, doc_client)

        for num_pagina, texto_pagina in paginas:
            texto_limpio = limpiar_texto(texto_pagina)
            chunks = dividir_en_chunks(texto_limpio)

            for idx, chunk in enumerate(chunks):
                vector = generar_embedding(chunk)
                if not vector:
                    print(f"  Fallo de embedding: {archivo} (pág {num_pagina}, fragmento {idx})")
                    continue

                doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{archivo}_{num_pagina}_{idx}"))
                documentos_a_subir.append({
                    "id": doc_id,
                    "contenido": chunk,
                    "documento": archivo,
                    "pagina": num_pagina,
                    "vector_contenido": vector
                })

    if documentos_a_subir:
        print(f"\nSubiendo {len(documentos_a_subir)} fragmentos a Azure AI Search...")
        lote_tamano = 50
        for i in range(0, len(documentos_a_subir), lote_tamano):
            lote = documentos_a_subir[i:i + lote_tamano]
            res = search_client.upload_documents(documents=lote)
            subidos = sum(1 for r in res if r.succeeded)
            print(f"  Lote {i // lote_tamano + 1}: {subidos}/{len(lote)} indexados exitosamente.")
        print("\n¡Ingesta de normativas finalizada!")
    else:
        print("No se encontraron fragmentos procesables.")

if __name__ == "__main__":
    indexar_carpeta("data/raw_pdfs")