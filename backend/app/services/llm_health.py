"""
Detección en caliente de `llama.cpp` (Spec 001 — T7).

El proyecto no debe depender de que alguien recuerde poner `AI_LEGO_ENABLED=true`:
si el servidor de inferencia responde, los bloques LEGO lo prefieren; si no,
degradan al determinista. La sonda se cachea para no golpear el servidor en cada
documento y su coste es un `GET /models` con timeout corto.
"""

import logging
import time
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger("passporttwin.llm_health")

_cache = {"checked_at": 0.0, "available": False, "base_url": None}


def llama_cpp_available(force: bool = False, timeout: Optional[float] = None) -> bool:
    """True si `AI_BASE_URL` responde con modelos disponibles."""
    if not settings.ai_probe_enabled:
        return False

    now = time.monotonic()
    ttl = settings.ai_probe_cache_seconds

    if (
        not force
        and _cache["base_url"] == settings.ai_base_url
        and now - _cache["checked_at"] < ttl
    ):
        return _cache["available"]

    url = f"{settings.ai_base_url.rstrip('/')}/models"
    available = False

    try:
        response = requests.get(
            url,
            timeout=settings.ai_probe_timeout_seconds if timeout is None else timeout,
        )
        available = response.status_code == 200
    except Exception as exc:  # Red, DNS, timeout o servidor apagado.
        logger.info("llama.cpp no disponible en %s (%s)", url, exc)

    _cache.update(checked_at=now, available=available, base_url=settings.ai_base_url)

    return available


def reset_availability_cache() -> None:
    """Invalida la caché (tests y cambios de configuración en caliente)."""
    _cache.update(checked_at=0.0, available=False, base_url=None)
