# backend/search_service.py
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from backend.config import settings
from backend.llm_orchestrator import generar_embedding

search_credential = AzureKeyCredential(settings.AZURE_SEARCH_KEY)
search_client = SearchClient(
    endpoint=settings.AZURE_SEARCH_ENDPOINT,
    index_name=settings.AZURE_SEARCH_INDEX,
    credential=search_credential
)


def buscar_fragmentos(pregunta: str, top_k: int = 4) -> list[dict]:

    try:
        # 1. Convertir la pregunta a vector numérico
        vector_pregunta = generar_embedding(pregunta)
        if not vector_pregunta:
            return []

        # 2. Configurar la consulta vectorial
        vector_query = VectorizedQuery(
            vector=vector_pregunta,
            k_nearest_neighbors=top_k,
            fields="vector_contenido"
        )

        # 3. Ejecutar la búsqueda híbrida
        resultados = search_client.search(
            search_text=pregunta,
            vector_queries=[vector_query],
            select=["documento", "pagina", "contenido"],
            top=top_k
        )

        # 4. Limpiar y estructurar la salida incluyendo el score
        fragmentos = []
        for doc in resultados:
            fragmentos.append({
                "documento": doc.get("documento", "Desconocido"),
                "pagina": doc.get("pagina", "N/A"),
                "contenido": doc.get("contenido", ""),
                "score": float(doc.get("@search.score", 0.0))  # Captura de relevancia
            })

        return fragmentos
    except Exception as e:
        print(f"[ERROR BÚSQUEDA AZURE] Verifica tus credenciales o el nombre del índice. Detalle: {e}")
        return []