"""
Configuración centralizada de IA (Spec 001) y Health Score.

Centraliza las variables de entorno de los módulos de IA local (LLM/OCR/RAG
servidos por `llama.cpp`). Los valores por defecto son seguros para el servidor
privado sin GPU: la IA queda desactivada salvo que se habilite explícitamente
mediante `AI_LEGO_ENABLED=true`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, Field, field_validator

from app.schemas.health_score import HealthScoreWeights


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

    # JSON environment variable HEALTH_SCORE_WEIGHTS; invalid values fail startup.
    health_score_weights: HealthScoreWeights = Field(default_factory=HealthScoreWeights)

    public_api_base_url: AnyHttpUrl = "http://localhost:8000"
    passport_frontend_base_url: AnyHttpUrl = "http://localhost:5173"

    @field_validator("public_api_base_url", "passport_frontend_base_url")
    @classmethod
    def validate_base_url(cls, value):
        if value.query or value.fragment or value.username or value.password:
            raise ValueError("Base URLs cannot contain credentials, query or fragment")
        return value


settings = Settings()
