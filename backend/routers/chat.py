# backend/routers/chat.py
import json
import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import SessionLocal, Mensaje, SesionChat
from backend.rag_engine import ejecutar_consulta

router = APIRouter(prefix="/api", tags=["Chat"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    pregunta: str


class ChatResponse(BaseModel):
    respuesta: str
    fuentes: list[str]


@router.post("/chat", response_model=ChatResponse)
def endpoint_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    try:

        sesion = db.query(SesionChat).filter(SesionChat.id == payload.session_id).first()
        if sesion:
            sesion.actualizado_en = datetime.datetime.utcnow()
            db.commit()

        resultado = ejecutar_consulta(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pregunta=payload.pregunta,
            db=db
        )
        return ChatResponse(
            respuesta=resultado["respuesta"],
            fuentes=resultado["fuentes"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[ERROR CHAT] {e}")
        raise HTTPException(status_code=500, detail="Error interno procesando la consulta.")


@router.get("/messages/{session_id}")
def obtener_mensajes_sesion(session_id: str, db: Session = Depends(get_db)):
    mensajes = (
        db.query(Mensaje)
        .filter(Mensaje.sesion_id == session_id)
        .order_by(Mensaje.creado_en.asc())
        .all()
    )
    salida = []
    for m in mensajes:
        fuentes_lista = []
        if m.fuentes:
            try:
                fuentes_lista = json.loads(m.fuentes)
            except Exception:
                fuentes_lista = []
        salida.append({
            "id": m.id,
            "rol": m.rol,
            "contenido": m.contenido,
            "fuentes": fuentes_lista
        })
    return salida