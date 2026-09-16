# backend/database.py
import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///./normativas_chat.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(String, primary_key=True, index=True)
    nombre = Column(String, nullable=True)
    pronombre = Column(String, nullable=True)
    nombre_agente = Column(String, default="Asistente Técnico")
    disclaimer_aceptado = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    sesiones = relationship("SesionChat", back_populates="usuario")


class SesionChat(Base):
    __tablename__ = "sesiones_chat"
    id = Column(String, primary_key=True, index=True)
    usuario_id = Column(String, ForeignKey("usuarios.id"))
    titulo = Column(String, default="Nueva consulta")
    fijado = Column(Boolean, default=False)
    fijado_en = Column(DateTime, nullable=True)
    actualizado_en = Column(DateTime, default=datetime.datetime.utcnow)
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    usuario = relationship("Usuario", back_populates="sesiones")
    mensajes = relationship("Mensaje", back_populates="sesion", cascade="all, delete-orphan")


class Mensaje(Base):
    __tablename__ = "mensajes"
    id = Column(String, primary_key=True, index=True)
    sesion_id = Column(String, ForeignKey("sesiones_chat.id"))
    rol = Column(String)
    contenido = Column(Text)
    fuentes = Column(Text, nullable=True)
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    sesion = relationship("SesionChat", back_populates="mensajes")


Base.metadata.create_all(bind=engine)