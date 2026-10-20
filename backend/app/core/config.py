"""
Configuración centralizada de los bloques LEGO de IA (Spec 001).

Centraliza las variables de entorno de los módulos de IA local (LLM/OCR/RAG
servidos por `llama.cpp`). Los valores por defecto son seguros para el servidor
privado sin GPU: la IA queda desactivada salvo que se habilite explícitamente
mediante `AI_LEGO_ENABLED=true`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída desde variables de entorno (y `.env` si existe)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bloque LEGO de IA: desactivado por defecto (fallback determinista).
    ai_lego_enabled: bool = False

    # Endpoint compatible OpenAI servido por `llama.cpp`.
    ai_base_url: str = "http://host.docker.internal:8080/v1"

    # Modelo local intercambiable: `gemma-4-e4b` (calidad) o `gemma-4-e2b`.
    ai_model_name: str = "gemma-4-e4b"

    # Tiempo máximo de espera antes de degradar al motor determinista.
    ai_timeout_seconds: float = 12.0


settings = Settings()
