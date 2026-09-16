# ingestion/document_parser.py
import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from backend.config import settings

try:
    doc_intel_client = DocumentIntelligenceClient(
        endpoint=settings.AZURE_DOC_INTEL_ENDPOINT,
        credential=AzureKeyCredential(settings.AZURE_DOC_INTEL_KEY)
    )
except Exception as e:
    print(f"[ERROR] No se pudo inicializar Document Intelligence. Verifica el .env: {e}")
    doc_intel_client = None


def extraer_markdown_de_pdf(ruta_pdf: str) -> str:
    """
    Toma un archivo PDF local, lo envía a Azure Document Intelligence usando
    el modelo 'prebuilt-layout' y solicita la salida en formato Markdown.
    """
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"El archivo {ruta_pdf} no existe.")

    print(f"Analizando documento: {ruta_pdf} ...")

    with open(ruta_pdf, "rb") as f:
        poller = doc_intel_client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=f,
            content_type="application/octet-stream",
            output_content_format="markdown"
        )

    result = poller.result()

    print("¡Análisis completado exitosamente!")
    return result.content