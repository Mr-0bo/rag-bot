# backend/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Google Gemini
    GEMINI_API_KEY: str

    # Azure AI Search
    AZURE_SEARCH_ENDPOINT: str
    AZURE_SEARCH_KEY: str
    AZURE_SEARCH_INDEX: str = "indice-normativas"

    # Azure Document Intelligence
    AZURE_DOC_INTEL_ENDPOINT: str = ""
    AZURE_DOC_INTEL_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instancia global para importar en los demás módulos
try:
    settings = Settings()
except Exception as e:
    print(f"[ERROR DE CONFIGURACIÓN] Faltan variables en el archivo .env: {e}")
    settings = None