# backend/llm_orchestrator.py
import re
import google.generativeai as genai
from backend.config import settings

if settings and settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)


def generar_embedding(texto: str) -> list[float]:

    try:
        resultado = genai.embed_content(
            model="models/gemini-embedding-001",
            content=texto,
            task_type="retrieval_query"
        )
        return resultado["embedding"]
    except Exception as e:
        print(f"[ERROR GEMINI EMBEDDING] {e}")
        return []


def clasificar_intencion(mensaje: str) -> str:

    msg_limpio = mensaje.strip().lower()

    saludos_directos = {
        "hola", "hola!", "hola.", "buenos dias", "buenos días", "buenas tardes",
        "buenas noches", "que tal", "qué tal", "como estas", "cómo estás",
        "gracias", "muchas gracias", "adios", "adiós", "bye", "hasta luego"
    }
    msg_sin_signos = re.sub(r"[^\w\s]", "", msg_limpio)
    if msg_sin_signos in saludos_directos:
        return "CONVERSACIONAL"

    prompt_router = f"""Clasifica la intención del usuario.
Responde ÚNICAMENTE con una palabra: "CONVERSACIONAL" o "TECNICA".

- CONVERSACIONAL: Saludos, despedidas, agradecimientos, halagos o charla trivial.
- TECNICA: Preguntas sobre especificaciones, normas, conceptos, materiales, procesos o cualquier consulta de información o seguimiento técnico.

Entrada: "{mensaje}"
Clasificación:"""

    try:
        modelo = genai.GenerativeModel("gemini-3.1-flash-lite")
        respuesta = modelo.generate_content(
            prompt_router,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=5
            )
        )
        etiqueta = respuesta.text.strip().upper()
        return "CONVERSACIONAL" if "CONVERSACIONAL" in etiqueta else "TECNICA"
    except Exception as e:
        print(f"[WARN ROUTER] Falló clasificación automática, asumiendo TECNICA: {e}")
        return "TECNICA"


def reformular_pregunta_con_historial(historial_mensajes: list[dict], pregunta_actual: str) -> str:

    if not historial_mensajes:
        return pregunta_actual

    ultimos_turnos = historial_mensajes[-4:]
    resumen_chat = "\n".join([f"{m['rol'].upper()}: {m['contenido']}" for m in ultimos_turnos])

    prompt = f"""Historial reciente de la conversación:
{resumen_chat}

Pregunta de seguimiento del colaborador: "{pregunta_actual}"

Instrucción: Reescribe la pregunta para que sea una consulta de búsqueda documental independiente y específica, incorporando el sujeto o concepto técnico del que venían hablando. Si la pregunta ya es autónoma y clara por sí misma, devuélvela exactamente igual.
Responde ÚNICAMENTE con la consulta reescrita, sin introducciones ni comillas."""

    try:
        modelo = genai.GenerativeModel("gemini-3.1-flash-lite")
        resp = modelo.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=45
            )
        )
        consulta_optimizada = resp.text.strip()
        return consulta_optimizada if consulta_optimizada else pregunta_actual
    except Exception:
        return pregunta_actual


def generar_respuesta_chat(system_prompt: str, user_prompt: str, historial: list[dict] = None) -> str:

    try:
        modelo = genai.GenerativeModel(
            model_name="gemini-3.1-flash-lite",
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0
            )
        )

        chat_history = []
        if historial:
            for h in historial:
                rol_gemini = "user" if h["rol"] == "user" else "model"
                chat_history.append({
                    "role": rol_gemini,
                    "parts": [h["contenido"]]
                })

        chat = modelo.start_chat(history=chat_history)
        respuesta = chat.send_message(user_prompt)
        return respuesta.text
    except Exception as e:
        print(f"[ERROR GEMINI CHAT] {e}")
        return "Hubo un error de comunicación con el motor de IA."