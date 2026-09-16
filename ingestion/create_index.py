# ingestion/create_index.py
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile
)
from backend.config import settings

def crear_indice(dimension_vector: int = 768):
    client = SearchIndexClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(settings.AZURE_SEARCH_KEY)
    )

    campos = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="contenido", type=SearchFieldDataType.String),
        SearchableField(name="documento", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="pagina", type=SearchFieldDataType.Int32, filterable=True),
        SearchField(
            name="vector_contenido",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dimension_vector,
            vector_search_profile_name="perfil-hibrido"
        )
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="perfil-hibrido", algorithm_configuration_name="hnsw-config")]
    )

    index_name = settings.AZURE_SEARCH_INDEX
    indice = SearchIndex(name=index_name, fields=campos, vector_search=vector_search)

    print(f"Creando índice '{index_name}' en Azure AI Search...")
    client.create_or_update_index(indice)
    print(f"¡Índice '{index_name}' creado exitosamente!")

if __name__ == "__main__":
    crear_indice(dimension_vector=3072)