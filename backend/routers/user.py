# backend/routers/user.py
import uuid
import json
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import case

from backend.database import SessionLocal, Usuario, SesionChat, Mensaje

router = APIRouter(prefix="/api", tags=["Usuarios y Sesiones"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OnboardingRequest(BaseModel):
    user_id: str
    nombre: str = Field(..., min_length=1, max_length=30)
    pronombre: str
    nombre_agente: Optional[str] = Field("Asistente Técnico", max_length=25)


class DisclaimerRequest(BaseModel):
    user_id: str
    no_volver_a_mostrar: bool


class RenameRequest(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=45)


class UserStatusResponse(BaseModel):
    registrado: bool
    nombre: Optional[str] = None
    pronombre: Optional[str] = None
    nombre_agente: Optional[str] = "Asistente Técnico"
    disclaimer_aceptado: bool = False


class SessionResponse(BaseModel):
    id: str
    titulo: str
    fijado: bool = False


class MessageResponse(BaseModel):
    rol: str
    contenido: str
    fuentes: list[str] = []


@router.get("/user/{user_id}", response_model=UserStatusResponse)
def consultar_usuario(user_id: str, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        return UserStatusResponse(registrado=False, disclaimer_aceptado=False)

    return UserStatusResponse(
        registrado=bool(usuario.nombre),
        nombre=usuario.nombre,
        pronombre=usuario.pronombre,
        nombre_agente=usuario.nombre_agente or "Asistente Técnico",
        disclaimer_aceptado=bool(usuario.disclaimer_aceptado)
    )


@router.post("/user/disclaimer")
def registrar_disclaimer(data: DisclaimerRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.id == data.user_id).first()
    if not usuario:
        usuario = Usuario(id=data.user_id)
        db.add(usuario)

    usuario.disclaimer_aceptado = data.no_volver_a_mostrar
    db.commit()
    return {"status": "ok"}


@router.post("/user/onboarding")
def guardar_onboarding(data: OnboardingRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.id == data.user_id).first()
    if not usuario:
        usuario = Usuario(id=data.user_id)
        db.add(usuario)
    usuario.nombre = data.nombre.strip()
    usuario.pronombre = data.pronombre
    usuario.nombre_agente = data.nombre_agente.strip() if data.nombre_agente else "Asistente Técnico"
    db.commit()
    return {"status": "ok"}


@router.get("/sessions/{user_id}", response_model=list[SessionResponse])
def obtener_sesiones(user_id: str, db: Session = Depends(get_db)):
    sesiones = (
        db.query(SesionChat)
        .filter(SesionChat.usuario_id == user_id)
        .order_by(
            case((SesionChat.fijado == True, 0), else_=1),
            SesionChat.fijado_en.desc(),
            SesionChat.actualizado_en.desc(),
            SesionChat.creado_en.desc()
        )
        .all()
    )
    return [SessionResponse(id=s.id, titulo=s.titulo, fijado=bool(s.fijado)) for s in sesiones]


@router.post("/sessions/{user_id}", response_model=SessionResponse)
def crear_nueva_sesion(user_id: str, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        usuario = Usuario(id=user_id)
        db.add(usuario)
        db.commit()

    ahora = datetime.datetime.utcnow()
    nueva = SesionChat(
        id=str(uuid.uuid4()),
        usuario_id=user_id,
        titulo="Nueva consulta",
        actualizado_en=ahora,
        creado_en=ahora
    )
    db.add(nueva)
    db.commit()
    return SessionResponse(id=nueva.id, titulo=nueva.titulo, fijado=False)


@router.patch("/sessions/{session_id}/pin")
def alternar_fijar_sesion(session_id: str, db: Session = Depends(get_db)):
    sesion = db.query(SesionChat).filter(SesionChat.id == session_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    if sesion.fijado:
        sesion.fijado = False
        sesion.fijado_en = None
    else:
        fijados_actuales = (
            db.query(SesionChat)
            .filter(SesionChat.usuario_id == sesion.usuario_id, SesionChat.fijado == True)
            .count()
        )
        if fijados_actuales >= 3:
            raise HTTPException(
                status_code=400,
                detail="Límite alcanzado: solo puedes fijar hasta 3 chats simultáneamente."
            )
        sesion.fijado = True
        sesion.fijado_en = datetime.datetime.utcnow()

    db.commit()
    return {"status": "ok", "fijado": sesion.fijado}


@router.patch("/sessions/{session_id}/rename")
def renombrar_sesion(session_id: str, data: RenameRequest, db: Session = Depends(get_db)):
    sesion = db.query(SesionChat).filter(SesionChat.id == session_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    sesion.titulo = data.titulo.strip()
    db.commit()
    return {"status": "ok", "titulo": sesion.titulo}


@router.delete("/sessions/single/{session_id}")
def eliminar_sesion_individual(session_id: str, db: Session = Depends(get_db)):
    sesion = db.query(SesionChat).filter(SesionChat.id == session_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    db.delete(sesion)
    db.commit()
    return {"status": "ok", "id": session_id}


@router.delete("/sessions/{user_id}/clear-all")
def eliminar_todas_las_sesiones(user_id: str, db: Session = Depends(get_db)):
    sesiones = db.query(SesionChat).filter(SesionChat.usuario_id == user_id).all()
    for s in sesiones:
        db.delete(s)
    db.commit()
    return {"status": "ok", "eliminadas": len(sesiones)}


@router.get("/messages/{session_id}", response_model=list[MessageResponse])
def obtener_historial_sesion(session_id: str, db: Session = Depends(get_db)):
    mensajes = (
        db.query(Mensaje)
        .filter(Mensaje.sesion_id == session_id)
        .order_by(Mensaje.creado_en.asc())
        .all()
    )

    salida = []
    for m in mensajes:
        fuentes_lista = []
        if getattr(m, "fuentes", None):
            try:
                fuentes_lista = json.loads(m.fuentes)
            except Exception:
                fuentes_lista = []
        salida.append(
            MessageResponse(
                rol=m.rol,
                contenido=m.contenido,
                fuentes=fuentes_lista
            )
        )
    return salida