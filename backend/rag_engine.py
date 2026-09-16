# backend/rag_engine.py
import uuid
import json
from sqlalchemy.orm import Session

from backend.database import Usuario, SesionChat, Mensaje
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

# Umbral de calibración para RRF en Azure AI Search (filtrar ruidos basales <= 0.033)
UMBRAL_RELEVANCIA_MINIMO = 0.034


def ejecutar_consulta(user_id: str, session_id: str, pregunta: str, db: Session) -> dict:
    """
    Controla el flujo completo con memoria conversacional y Router:
    - Recupera turnos previos (usuario y modelo) de SQLite.
    - Contextualiza la búsqueda en Azure si es una duda de seguimiento.
    - Filtra fuentes espurias si no se supera el umbral o si la respuesta es negativa.
    - Persiste entradas, respuestas y fuentes asociadas en SQLite.
    """
    # 1. Validar existencia de usuario y sesión
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    sesion = db.query(SesionChat).filter(SesionChat.id == session_id).first()

    if not usuario or not sesion:
        raise ValueError("Usuario o sesión no encontrados en la base de datos.")

    # 2. Recuperar el historial previo antes de agregar el nuevo turno
    mensajes_anteriores = (
        db.query(Mensaje)
        .filter(Mensaje.sesion_id == sesion.id)
        .all()
    )
    historial_lista = [{"rol": m.rol, "contenido": m.contenido} for m in mensajes_anteriores]

    # 3. Guardar el nuevo mensaje del usuario
    msg_usuario = Mensaje(
        id=str(uuid.uuid4()),
        sesion_id=sesion.id,
        rol="user",
        contenido=pregunta
    )
    db.add(msg_usuario)

    # 4. Asignar título a la sesión si es el primer mensaje
    if len(historial_lista) == 0:
        sesion.titulo = pregunta[:32] + ("..." if len(pregunta) > 32 else "")

    # 5. Generar system prompt con identidades claras
    system_prompt = generar_system_prompt(
        nombre_agente=usuario.nombre_agente or "Asistente Técnico",
        nombre_usuario=usuario.nombre or "Colaborador",
        pronombre=usuario.pronombre or "neutro"
    )

    # 6. Clasificación de Intención (Router)
    intencion = clasificar_intencion(pregunta)
    print(f"\n[ROUTER INTENCIÓN] Mensaje: '{pregunta}' -> Clasificado como: {intencion}")

    # 7. Ejecutar bifurcación según la intención
    if intencion == "CONVERSACIONAL":
        print("[ROUTER] Omitiendo Azure AI Search (modo conversacional directo).")
        prompt_conversacion = generar_prompt_conversacional(pregunta)
        respuesta_texto = generar_respuesta_chat(
            system_prompt=system_prompt,
            user_prompt=prompt_conversacion,
            historial=historial_lista
        )
        fuentes_unicas = []
    else:
        # Contextualizar consulta con historial si aplica
        consulta_busqueda = reformular_pregunta_con_historial(historial_lista, pregunta)
        if consulta_busqueda != pregunta:
            print(f"[REFORMULACIÓN RAG] '{pregunta}' -> '{consulta_busqueda}'")

        todos_los_fragmentos = buscar_fragmentos(consulta_busqueda, top_k=4)

        print("--- [EVALUACIÓN DE RELEVANCIA AZURE] ---")
        for f in todos_los_fragmentos:
            print(f"Doc: {f['documento']} | Pág: {f['pagina']} | Score: {f['score']:.5f}")

        fragmentos_validos = [f for f in todos_los_fragmentos if f.get("score", 0.0) >= UMBRAL_RELEVANCIA_MINIMO]
        print(f"Fragmentos que superan el umbral ({UMBRAL_RELEVANCIA_MINIMO}): {len(fragmentos_validos)}/{len(todos_los_fragmentos)}")

        if fragmentos_validos:
            prompt_usuario = generar_prompt_consulta(pregunta, fragmentos_validos)
            respuesta_texto = generar_respuesta_chat(
                system_prompt=system_prompt,
                user_prompt=prompt_usuario,
                historial=historial_lista
            )

            # Si el LLM dictamina que no encontró el dato, no incluir fuentes
            indicadores_negativos = [
                "no se encuentra disponible",
                "no está disponible",
                "no se menciona",
                "no contiene información",
                "no aparece en los documentos",
                "no se especifica"
            ]

            respuesta_lower = respuesta_texto.lower()
            if any(indicador in respuesta_lower for indicador in indicadores_negativos):
                fuentes_unicas = []
            else:
                fuentes_unicas = list({f"[{f['documento']}, Pág. {f['pagina']}]" for f in fragmentos_validos})
        else:
            print("\n[AVISO] No se superó el umbral documental.\n")
            prompt_usuario = (
                f"El usuario consulta: '{pregunta}'. "
                "Esta información técnica específica no se encuentra en los documentos indexados. "
                "Indica brevemente en una sola oración que la especificación o dato no está disponible en la base técnica indexada."
            )
            respuesta_texto = generar_respuesta_chat(
                system_prompt=system_prompt,
                user_prompt=prompt_usuario,
                historial=historial_lista
            )
            fuentes_unicas = []

    # 8. Guardar respuesta del asistente en SQLite con sus fuentes
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