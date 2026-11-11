"""
Clasificación documental por contenido (Spec 001 — T7).

El nombre del archivo no basta: `ds18b20.pdf` es una ficha técnica y
`certificado_2026.pdf` puede ser un certificado. La decisión se toma por
marcadores del texto de las primeras páginas; el nombre solo desempata.

Los marcadores de certificado pesan más porque son específicos del acto
metrológico ("certificate of calibration", "due date"), mientras que una ficha
puede contener la palabra "specifications" sin ser un certificado.
"""

import logging

import pdfplumber

logger = logging.getLogger("passporttwin.classifier")

CERTIFICATE_MARKERS = (
    "certificate of calibration",
    "calibration certificate",
    "certificado de calibración",
    "calibration date",
    "fecha de calibración",
    "next calibration",
    "próxima calibración",
    "due date",
    "max error",
    "error máximo",
    "measurement uncertainty",
    "incertidumbre de medida",
)

DATASHEET_MARKERS = (
    "data sheet",
    "datasheet",
    "technical data",
    "technical information",
    "ficha técnica",
    "absolute maximum ratings",
    "ordering information",
    "pin configuration",
    "pinout",
    "electrical characteristics",
    "block diagram",
)

FILENAME_DATASHEET_HINTS = ("datasheet", "data-sheet", "data_sheet", "ficha", "technical")


def _read_text(file_path: str, max_chars: int = 8000) -> str:
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages[:3]:
                text += (page.extract_text() or "") + "\n"
                if len(text) >= max_chars:
                    break
        return text.lower()
    except Exception as exc:
        logger.warning("No se pudo leer el PDF para clasificarlo: %s", exc)
        return ""


def classify_document(file_path: str, filename: str = "") -> str:
    """Devuelve `PDF_DATASHEET` o `PDF_CERTIFICATE` para un PDF.

    Ante la duda mantiene `PDF_CERTIFICATE`, que es el comportamiento histórico:
    un certificado mal clasificado perdería sus reglas metrológicas, mientras que
    una ficha mal clasificada sigue llegando a la cola de revisión.
    """
    name = (filename or "").lower()
    text = _read_text(file_path)

    certificate_hits = sum(1 for marker in CERTIFICATE_MARKERS if marker in text)
    datasheet_hits = sum(1 for marker in DATASHEET_MARKERS if marker in text)

    if certificate_hits and certificate_hits >= datasheet_hits:
        return "PDF_CERTIFICATE"

    if datasheet_hits:
        return "PDF_DATASHEET"

    if any(hint in name for hint in FILENAME_DATASHEET_HINTS):
        return "PDF_DATASHEET"

    return "PDF_CERTIFICATE"
