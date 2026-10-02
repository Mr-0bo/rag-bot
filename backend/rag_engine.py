# backend/rag_engine.py
import re
import uuid
import json
from typing import List
from sqlalchemy.orm import Session

from backend.database import Usuario, SesionChat, Mensaje, ConfiguracionApp
from backend.search_service import buscar_fragmentos
from backend.llm_orchestrator import (
    generar_respuesta_chat,
    clasificar_intencion,
    reformular_pregunta_con_historial
)
from backend.prompts import (
    generar_system_prompt,
    generar_prompt_consulta,
    generar_prompt_conversacional
)

# Umbral de corte para similitud coseno en Qdrant con BGE-small
UMBRAL_SIMILITUD_MINIMO = 0.40


def extraer_fuentes_citadas(texto_respuesta: str) -> List[str]:
    """
    Busca patrones de citación en el texto generado como:
    [Diodos.pdf, Pág. 3] o [Diodos.pdf]
    Devuelve las citas preservando el formato de corchetes, orden y sin duplicados.
    """
    patron = r'\[([^\]]+\.pdf(?:,\s*Pág\.\s*\d+)?)\]'
    coincidencias = re.findall(patron, texto_respuesta, re.IGNORECASE)

    citas_unicas = []
    for cita in coincidencias:
        formato_corchete = f"[{cita.strip()}]"
        if formato_corchete not in citas_unicas:
            citas_unicas.append(formato_corchete)

    return citas_unicas


def ejecutar_consulta(user_id: str, session_id: str, pregunta: str, db: Session) -> dict:
    """
    Pipeline RAG optimizado con desacoplamiento de modelos:
    - Clasificación de intención 100% local en CPU (BGE-small + reglas).
    - Reformulación y descomposición de subconsultas vía Gemini 3.1 Flash Lite.
    - Búsqueda semántica diversificada en Qdrant (top_k=10, deduplicación de páginas y control por doc).
    - Síntesis técnica y citas normativas con Gemini 3.5 Flash Lite.
    """
    # 1. Validar existencia de usuario y sesión
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    sesion = db.query(SesionChat).filter(SesionChat.id == session_id).first()

    if not usuario or not sesion:
        raise ValueError("Usuario o sesión no encontrados en la base de datos.")

    # 2. Obtener la región activa configurada en la aplicación
    config = db.query(ConfiguracionApp).first()
    region_activa = config.region if config and config.region else "mexico"

    # 3. Recuperar historial de turnos previos
    mensajes_anteriores = (
        db.query(Mensaje)
        .filter(Mensaje.sesion_id == sesion.id)
        .order_by(Mensaje.creado_en.asc())
        .all()
    )
    historial_lista = [{"rol": m.rol, "contenido": m.contenido} for m in mensajes_anteriores]

    # 4. Guardar mensaje entrante del usuario
    msg_usuario = Mensaje(
        id=str(uuid.uuid4()),
        sesion_id=sesion.id,
        rol="user",
        contenido=pregunta
    )
    db.add(msg_usuario)

    # 5. Generar título preliminar si es el primer turno
    if len(historial_lista) == 0:
        sesion.titulo = pregunta[:32] + ("..." if len(pregunta) > 32 else "")

    # 6. Construir system prompt adaptado al estilo del usuario
    system_prompt = generar_system_prompt(
        nombre_agente=usuario.nombre_agente or "Copiloto Técnico",
        nombre_usuario=usuario.nombre or "Colaborador",
        pronombre=usuario.pronombre or "neutro"
    )

    # 7. Clasificar intención en local (0 llamadas de API)
    intencion = clasificar_intencion(pregunta)
    print(f"\n[ROUTER INTENCIÓN LOCAL] '{pregunta}' -> Clasificado como: {intencion}")

    if intencion == "CONVERSACIONAL":
        prompt_conversacion = generar_prompt_conversacional(pregunta)
        respuesta_texto = generar_respuesta_chat(
            system_prompt=system_prompt,
            user_prompt=prompt_conversacion,
            historial=historial_lista
        )
        fuentes_unicas = []
    else:
        # Reformulación y desglose de subconsultas técnicas con Gemini 3.1 Flash Lite
        subconsultas = reformular_pregunta_con_historial(historial_lista, pregunta)
        print(f"[REFORMULACIÓN / DESGLOSE (3.1-FLASH-LITE)] -> {subconsultas}")

        # Búsqueda semántica en Qdrant con diversificación ampliada
        # max_por_doc=3 y max_por_pagina=2 evitan que páginas ricas en contenido
        # compitan consigo mismas y sean excluidas prematuramente.
        todos_los_fragmentos = buscar_fragmentos(
            consultas=subconsultas,
            region=region_activa,
            top_k=10,
            max_por_doc=3,
            max_por_pagina=2
        )

        fragmentos_validos = [f for f in todos_los_fragmentos if f.get("score", 0.0) >= UMBRAL_SIMILITUD_MINIMO]
        print(f"Fragmentos sobre umbral ({UMBRAL_SIMILITUD_MINIMO}): {len(fragmentos_validos)}/{len(todos_los_fragmentos)}")

        # Monitoreo detallado del contexto documental entregado
        print("\n" + "=" * 65)
        print(f"[RAG ENGINE] FRAGMENTOS ENVIADOS A GEMINI 3.5 ({len(fragmentos_validos)}):")
        for idx, f in enumerate(fragmentos_validos):
            print(f" [{idx + 1}] {f.get('documento')} | Pág: {f.get('pagina')} | Score: {f.get('score', 0):.4f}")
        print("=" * 65 + "\n")

        if fragmentos_validos:
            prompt_usuario = generar_prompt_consulta(pregunta, fragmentos_validos)

            # Generación técnica con Gemini 3.5 Flash Lite
            respuesta_texto = generar_respuesta_chat(
                system_prompt=system_prompt,
                user_prompt=prompt_usuario,
                historial=historial_lista
            )

            # Extraer las citas explícitas que el modelo generó en su texto
            fuentes_unicas = extraer_fuentes_citadas(respuesta_texto)

            # Si el modelo respondió usando el contexto pero omitió los corchetes
            if not fuentes_unicas:
                indicadores_negativos_totales = [
                    "no se encuentra disponible en los documentos",
                    "no aparece en los documentos indexados",
                    "no está disponible en la base técnica"
                ]
                resp_low = respuesta_texto.lower()
                if not any(ind in resp_low for ind in indicadores_negativos_totales):
                    fuentes_unicas = list({f"[{f['documento']}, Pág. {f['pagina']}]" for f in fragmentos_validos})
        else:
            print("\n[AVISO] No se superó el umbral documental.\n")
            prompt_usuario = (
                f"El colaborador consulta: '{pregunta}'. "
                "Esta información técnica específica no se encuentra en los documentos indexados para la región seleccionada. "
                "Indica brevemente en una sola oración que la especificación o dato no está disponible en la base técnica actual."
            )
            respuesta_texto = generar_respuesta_chat(
                system_prompt=system_prompt,
                user_prompt=prompt_usuario,
                historial=historial_lista
            )
            fuentes_unicas = []

    # 8. Persistir intercambio en SQLite
    msg_asistente = Mensaje(
        id=str(uuid.uuid4()),
        sesion_id=sesion.id,
        rol="assistant",
        contenido=respuesta_texto,
        fuentes=json.dumps(fuentes_unicas) if fuentes_unicas else None
    )
    db.add(msg_asistente)
    db.commit()

    return {
        "respuesta": respuesta_texto,
        "fuentes": fuentes_unicas
    }