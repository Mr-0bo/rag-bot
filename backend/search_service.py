# backend/search_service.py
from typing import List, Dict, Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastembed import TextEmbedding
from backend.config import settings

# Instancias singleton para reutilizar memoria
_qdrant_client: Optional[QdrantClient] = None
_embedding_model: Optional[TextEmbedding] = None


def get_embedding_model() -> TextEmbedding:
    """Carga de forma perezosa el modelo de embeddings local."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name=settings.EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_qdrant_client() -> QdrantClient:
    """Inicializa la base de datos vectorial local en la ruta de usuario segura."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path=str(settings.qdrant_path))
        _inicializar_coleccion(_qdrant_client)
    return _qdrant_client


def _inicializar_coleccion(client: QdrantClient):
    """Crea la colección si no existe."""
    if not client.collection_exists(settings.QDRANT_COLLECTION_NAME):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_DIMENSION,
                distance=models.Distance.COSINE
            )
        )


def generar_embedding_local(texto: str) -> List[float]:
    """Genera vector de 384 dimensiones en CPU local."""
    modelo = get_embedding_model()
    vectores = list(modelo.embed([texto]))
    return vectores[0].tolist()


def buscar_fragmentos(
        consultas: Union[str, List[str]],
        region: str = "mexico",
        top_k: int = 10,
        max_por_doc: int = 3,
        max_por_pagina: int = 2
) -> List[Dict]:
    """
    Busca semánticamente en Qdrant con distribución equitativa por subconsulta (Round-Robin)
    y diversificación estricta por documento y página.
    """
    try:
        client = get_qdrant_client()

        if isinstance(consultas, str):
            lista_consultas = [consultas]
        else:
            lista_consultas = consultas if consultas else [""]

        filtro_region = models.Filter(
            must=[
                models.FieldCondition(
                    key="region",
                    match=models.MatchValue(value=region.lower())
                )
            ]
        )

        # 1. Recuperar y filtrar candidatos por cada subconsulta (recall amplio a 40)
        puntos_por_consulta = []
        print(f"\n[DEBUG SEARCH] Subconsultas recibidas ({len(lista_consultas)}): {lista_consultas}")

        for idx, sub_query in enumerate(lista_consultas):
            sub_query_limpia = sub_query.strip()
            if not sub_query_limpia:
                continue

            print(f"[DEBUG SEARCH] Ejecutando subconsulta {idx + 1}/{len(lista_consultas)}: '{sub_query_limpia}'")
            vector_query = generar_embedding_local(sub_query_limpia)
            respuesta = client.query_points(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                query=vector_query,
                query_filter=filtro_region,
                limit=40,
                with_payload=True
            )

            # Pre-deduplicar respetando max_por_pagina para no descartar chunks hermanos de páginas densas
            pts_filtrados = []
            conteo_paginas_subquery: Dict[str, int] = {}
            for p in sorted(respuesta.points, key=lambda x: float(x.score), reverse=True):
                pl = p.payload or {}
                # Casteo a string obligatorio para evitar errores de tipo int vs str
                doc_str = str(pl.get('documento', 'Desconocido'))
                pag_str = str(pl.get('pagina', 'N/A'))
                clave = f"{doc_str}_{pag_str}"

                if conteo_paginas_subquery.get(clave, 0) < max_por_pagina:
                    conteo_paginas_subquery[clave] = conteo_paginas_subquery.get(clave, 0) + 1
                    pts_filtrados.append(p)

            print(
                f"[DEBUG SEARCH] -> Puntos recuperados para subconsulta {idx + 1} (máx {max_por_pagina} por pág): {len(pts_filtrados)}")
            puntos_por_consulta.append(pts_filtrados)

        # 2. Mezcla Round-Robin: garantizar representación de cada subconsulta
        candidatos_intercalados = []
        max_longitud = max((len(pts) for pts in puntos_por_consulta), default=0)
        for i in range(max_longitud):
            for pts in puntos_por_consulta:
                if i < len(pts):
                    candidatos_intercalados.append(pts[i])

        print(f"[DEBUG SEARCH] Total candidatos intercalados pre-filtro final: {len(candidatos_intercalados)}")

        # 3. Diversificación y deduplicación global final
        conteo_doc: Dict[str, int] = {}
        conteo_pagina: Dict[str, int] = {}
        ids_vistos = set()
        fragmentos_diversificados = []

        print(f"\n--- [EVALUACIÓN QDRANT LOCAL ({region.upper()})] ---")
        for punto in candidatos_intercalados:
            if punto.id in ids_vistos:
                continue

            payload = punto.payload or {}
            # Casteo a string obligatorio para el conteo global
            doc = str(payload.get("documento", "Desconocido"))
            pag = str(payload.get("pagina", "N/A"))
            score = float(punto.score)

            clave_pag = f"{doc}_{pag}"

            if conteo_pagina.get(clave_pag, 0) >= max_por_pagina:
                continue

            if conteo_doc.get(doc, 0) >= max_por_doc:
                continue

            ids_vistos.add(punto.id)
            conteo_pagina[clave_pag] = conteo_pagina.get(clave_pag, 0) + 1
            conteo_doc[doc] = conteo_doc.get(doc, 0) + 1

            print(f"Doc: {doc} | Pág: {pag} | Similitud: {score:.4f}")
            fragmentos_diversificados.append({
                "documento": doc,
                "ruta_relativa": payload.get("ruta_relativa", ""),
                "pagina": payload.get("pagina", "N/A"),
                "contenido": payload.get("contenido", ""),
                "region": payload.get("region", region),
                "score": score
            })

            if len(fragmentos_diversificados) >= top_k:
                break

        return fragmentos_diversificados

    except Exception as e:
        print(f"[ERROR BÚSQUEDA QDRANT LOCAL] {e}")
        return []


def eliminar_documento_por_ruta(ruta_relativa: str):
    """Elimina todos los vectores asociados a un archivo modificado o borrado."""
    client = get_qdrant_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="ruta_relativa",
                        match=models.MatchValue(value=ruta_relativa)
                    )
                ]
            )
        )
    )


def indexar_chunks_documento(puntos: List[models.PointStruct]):
    """Inserta o actualiza un lote de fragmentos vectorizados en Qdrant."""
    if not puntos:
        return
    client = get_qdrant_client()
    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points=puntos
    )