import json
import re
from datetime import datetime
import pdfplumber
import logging
import requests

from app.core.config import settings

logger = logging.getLogger("passporttwin.extractor")

class PDFCertificateExtractor:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """Lee el texto completo de un PDF digital con `pdfplumber`."""
        raw_text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n"
        except Exception as e:
            logger.error(f"Error leyendo PDF con pdfplumber: {str(e)}")
            return ""

        return raw_text

    @staticmethod
    def _parse_text(raw_text: str) -> dict:
        """Recupera campos clave de un certificado a partir de su texto limpio."""
        fields = {}

        # 1. Extracción de Número de Serie (ej. S/N: PT-WIKA-001 o Serial: PT-WIKA-001)
        serial_match = re.search(r"(?:S/N|Serial|Número de Serie)[:\s]+([A-Za-z0-9\-_]+)", raw_text, re.IGNORECASE)
        if serial_match:
            fields["serial_number"] = serial_match.group(1).strip()

        # 2. Extracción de Fecha de Calibración (Formatos ISO YYYY-MM-DD o DD/MM/YYYY)
        cal_date_match = re.search(r"(?:Calibration Date|Fecha de Calibración)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", raw_text, re.IGNORECASE)
        if cal_date_match:
            raw_date = cal_date_match.group(1).strip()
            fields["calibration_date"] = PDFCertificateExtractor._normalize_date(raw_date)

        # 3. Extracción de Fecha de Próximo Vencimiento
        due_date_match = re.search(r"(?:Due Date|Próxima Calibración)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", raw_text, re.IGNORECASE)
        if due_date_match:
            raw_date = due_date_match.group(1).strip()
            fields["next_due_date"] = PDFCertificateExtractor._normalize_date(raw_date)

        # 4. Extracción de Error Máximo y Tolerancia
        error_match = re.search(r"(?:Max Error|Error Máximo)[:\s]+([+\-]?\d+(?:\.\d+)?)", raw_text, re.IGNORECASE)
        if error_match:
            fields["error_value"] = float(error_match.group(1).strip())

        tol_match = re.search(r"(?:Tolerance|Tolerancia)[:\s]+([+\-]?\d+(?:\.\d+)?)", raw_text, re.IGNORECASE)
        if tol_match:
            fields["tolerance"] = float(tol_match.group(1).strip())

        # 5. Extracción de Unidad de medida (ej. Unidad: bar / Unit: kPa)
        unit_match = re.search(r"(?:Unidad|Unit)[:\s]+([A-Za-z°ºµ%]+)", raw_text, re.IGNORECASE)
        if unit_match:
            fields["unit"] = unit_match.group(1).strip()

        # 6. Extracción de Rango Operativo (ej. Rango: 0-10 bar / Range: 0 - 10 kPa)
        range_match = re.search(
            r"(?:Operating Range|Rango(?: Operativo)?|Range)[:\s]+"
            r"([0-9]+(?:[.,][0-9]+)?\s*(?:-|–|—|\ba\b|\bto\b)\s*"
            r"[0-9]+(?:[.,][0-9]+)?(?:\s*[A-Za-z°ºµ%]+)?)",
            raw_text,
            re.IGNORECASE,
        )
        if range_match:
            fields["operating_range"] = range_match.group(1).strip()

        return fields

    @staticmethod
    def extract_and_parse(file_path: str, include_full_text: bool = False) -> dict:
        """Extrae texto de un PDF digital y recupera campos clave mediante expresiones regulares."""
        raw_text = PDFCertificateExtractor.extract_text(file_path)

        if not raw_text:
            return {}

        fields = PDFCertificateExtractor._parse_text(raw_text)

        # Texto limpio opcional para el bloque RAG (RF-RAG-01).
        if include_full_text:
            fields["__full_text__"] = raw_text.strip()

        return fields

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convierte fechas a estándar canónico ISO-8601 (YYYY-MM-DD)."""
        if "/" in date_str:
            parts = date_str.split("/")
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return date_str

class PDFDatasheetExtractor:
    @staticmethod
    def extract_technical_data(file_path: str) -> dict:
        """Extrae especificaciones técnicas básicas de un datasheet PDF digital."""
        raw_text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n"
        except Exception as e:
            logger.error(f"Error leyendo Datasheet con pdfplumber: {str(e)}")
            return {}

        fields = {}
        # Extracción de Modelo y Rango Operativo
        model_match = re.search(r"(?:Model|Modelo)[:\s]+([A-Za-z0-9\-_\/]+)", raw_text, re.IGNORECASE)
        if model_match:
            fields["model"] = model_match.group(1).strip()

        range_match = re.search(r"(?:Range|Rango)[:\s]+([0-9\.\-]+\s*(?:bar|kPa|°C|pH))", raw_text, re.IGNORECASE)
        if range_match:
            fields["operating_range"] = range_match.group(1).strip()

        return fields

class LLMOCRDocumentExtractor:
    """
    Bloque LEGO 1: extractor híbrido determinista + LLM/OCR.

    Si el modo solicitado requiere la IA (`extractor_mode="llm"`, o `"auto"` con
    el bloque habilitado) envía el texto del PDF a `llama.cpp`
    (`gemma-4-e4b` / `gemma-4-e2b`). Ante cualquier error de red, timeout o JSON
    inválido, degrada de forma transparente al extractor determinista
    (`deterministic_fallback`) sin propagar la excepción (RF-LEGO-02).
    """

    CANONICAL_FIELDS = (
        "serial_number",
        "calibration_date",
        "next_due_date",
        "error_value",
        "tolerance",
        "unit",
        "operating_range",
    )

    SYSTEM_PROMPT = (
        "Eres un extractor de datos de certificados de calibración industriales. "
        "Devuelve EXCLUSIVAMENTE un objeto JSON válido, sin texto adicional ni "
        'explicaciones, con las claves "serial_number", "calibration_date", '
        '"next_due_date", "error_value", "tolerance", "unit" y "operating_range". '
        "Usa null cuando un dato no aparezca en el documento. Las fechas deben "
        "estar en formato ISO-8601 (YYYY-MM-DD)."
    )

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ):
        self.base_url = base_url or settings.ai_base_url
        self.model_name = model_name or settings.ai_model_name
        self.timeout = settings.ai_timeout_seconds if timeout is None else timeout
        self.enabled = settings.ai_lego_enabled if enabled is None else enabled

    def should_use_llm(self, extractor_mode: str = "auto") -> bool:
        """Decide si el bloque LEGO debe invocarse para el modo solicitado."""
        mode = (extractor_mode or "auto").strip().lower()

        if mode == "llm":
            return True

        if mode == "auto":
            return bool(self.enabled)

        return False

    def extract_and_parse(
        self,
        file_path: str,
        extractor_mode: str = "auto",
        include_full_text: bool = False,
    ) -> dict:
        """Extrae campos del documento con fallback determinista garantizado."""
        raw_text = PDFCertificateExtractor.extract_text(file_path)
        deterministic = PDFCertificateExtractor._parse_text(raw_text) if raw_text else {}

        if include_full_text and raw_text:
            deterministic["__full_text__"] = raw_text.strip()

        if not self.should_use_llm(extractor_mode):
            deterministic["extractor_used"] = "deterministic"
            return deterministic

        try:
            llm_fields = self._extract_with_llama_cpp(raw_text)
        except Exception as exc:  # Red, timeout, HTTP o JSON inválido.
            logger.warning(
                "Bloque LEGO 1 no disponible (%s); degradando a extractor determinista.",
                exc,
            )
            deterministic["extractor_used"] = "deterministic_fallback"
            return deterministic

        merged = dict(deterministic)
        merged.update(llm_fields)
        merged["extractor_used"] = "llm"
        return merged

    def _extract_with_llama_cpp(self, raw_text: str) -> dict:
        """Invoca `POST {AI_BASE_URL}/chat/completions` y parsea el JSON devuelto."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model_name,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Texto del documento:\n{raw_text}"},
            ],
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        return self._parse_llm_json(content)

    def _parse_llm_json(self, content: str) -> dict:
        """Limpia bloques Markdown ```json y valida el JSON canónico del LLM."""
        if content is None or not str(content).strip():
            raise ValueError("Respuesta vacía del LLM")

        text = str(content).strip()

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("El LLM no devolvió un objeto JSON válido")

        parsed = json.loads(text[start : end + 1])

        if not isinstance(parsed, dict):
            raise ValueError("El JSON del LLM no es un objeto")

        return {
            key: value
            for key, value in parsed.items()
            if key in self.CANONICAL_FIELDS and value not in (None, "")
        }

class HybridDocumentExtractor(LLMOCRDocumentExtractor):
    """Alias semántico del extractor híbrido (bloque LEGO 1) de la Spec 001."""

    pass
