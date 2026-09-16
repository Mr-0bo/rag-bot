# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import user, chat

app = FastAPI(title="Asistente de Normativas Técnicas")

app.mount("/frontend", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def home():
    return FileResponse("frontend/index.html")

app.include_router(user.router)
app.include_router(chat.router)