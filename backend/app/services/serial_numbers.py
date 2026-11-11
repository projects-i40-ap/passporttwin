"""
Regla única de número de serie (Spec 001 — T14).

Un serial es una clave de identidad, no un texto libre: se imprime en la
etiqueta, viaja al identificador de la AAS y se empareja con los certificados.
Se admite letras, números, guion y guion bajo, entre 2 y 40 caracteres, y se
normaliza a mayúsculas para que `ds-001` y `DS-001` no creen dos activos.
"""

import re

SERIAL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")
SERIAL_HINT = "Letras, números, guion y guion bajo (2–40 caracteres). Ejemplo: DS18B20-001"


class InvalidSerial(ValueError):
    """El número de serie no cumple el formato canónico."""


def normalize_serial(value: str) -> str:
    """Recorta, pasa a mayúsculas y valida. Lanza `InvalidSerial` si no cumple."""
    serial = str(value or "").strip().upper()
    if not SERIAL_PATTERN.match(serial):
        raise InvalidSerial(
            "Número de serie no válido. Usa letras, números, guion y guion bajo, "
            "entre 2 y 40 caracteres (ejemplo: DS18B20-001)."
        )
    return serial
