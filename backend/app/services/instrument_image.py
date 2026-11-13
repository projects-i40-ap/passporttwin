"""Fotografía del activo físico asociada al pasaporte digital.

La imagen es evidencia visual, no estado metrológico: se guarda junto al resto de
ficheros (como el RAW documental) con un nombre derivado del `public_id`, sin
introducir columnas nuevas en el modelo canónico de PostgreSQL.
"""

import os
from pathlib import Path
from typing import Optional

# Formatos aceptados por la UI y su extensión canónica en disco.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MEDIA_TYPES_BY_SUFFIX: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

MAX_IMAGE_BYTES = int(os.getenv("INSTRUMENT_IMAGE_MAX_BYTES", 5 * 1024 * 1024))


def instrument_image_dir() -> Path:
    """Directorio de fotografías, configurable por entorno (LEGO, sin rutas fijas)."""
    path = Path(os.getenv("INSTRUMENT_IMAGE_DIR", "/app/storage/instruments"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_extension(content_type: Optional[str]) -> Optional[str]:
    """Devuelve la extensión canónica para un `Content-Type` aceptado."""
    normalized = (content_type or "").split(";")[0].strip().lower()

    return ALLOWED_IMAGE_TYPES.get(normalized)


def image_path(public_id) -> Optional[Path]:
    """Ruta de la fotografía del instrumento, si existe."""
    for suffix in MEDIA_TYPES_BY_SUFFIX:
        candidate = instrument_image_dir() / f"{public_id}{suffix}"

        if candidate.is_file():
            return candidate

    return None


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def save_instrument_image(public_id, data: bytes, extension: str) -> Path:
    """Reemplaza la fotografía vigente del instrumento y devuelve su ruta."""
    directory = instrument_image_dir()

    for existing in directory.glob(f"{public_id}.*"):
        existing.unlink(missing_ok=True)

    destination = directory / f"{public_id}{extension}"
    destination.write_bytes(data)

    return destination
