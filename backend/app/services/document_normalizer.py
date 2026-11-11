"""
Bloque LEGO 1b: normalizador de fichas técnicas a esquema canónico (Spec 001 — T5).

Convierte un documento heterogéneo (ficha de sensor de cualquier fabricante) en el
JSON canónico que el resto del sistema determinista ya consume. La generación usa
decodificación restringida (`response_format` con JSON Schema): el modelo no puede
emitir otro formato que el declarado.

Reglas de diseño:
- El LLM es un adaptador de formato, nunca una fuente de verdad. Escribe en
  `extracted_field` (staging) y un humano lo acepta.
- Todo valor se ancla al texto: si no aparece literalmente en su trozo, se
  descarta a `null` en lugar de propagarse.
- Cualquier fallo (red, timeout, esquema no soportado, JSON inválido) degrada al
  extractor determinista sin lanzar excepción (RF-DOC-05 / RF-LEGO-02).
"""

import json
import logging
import re
from typing import Any, Optional

import pdfplumber
import requests

from app.core.config import settings
from app.services.llm_health import llama_cpp_available
from app.services.pdf_extractor import PDFDatasheetExtractor

logger = logging.getLogger("passporttwin.normalizer")

# Esquema canónico de ficha técnica. `nullable` explícito: "no aparece" es un
# valor legítimo y debe distinguirse de "no lo he podido leer".
DATASHEET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "manufacturer": {"type": ["string", "null"]},
        "model": {"type": ["string", "null"]},
        "measurement_principle": {"type": ["string", "null"]},
        "measurement_variable": {"type": ["string", "null"]},
        "range_min": {"type": ["number", "null"]},
        "range_max": {"type": ["number", "null"]},
        "range_unit": {"type": ["string", "null"]},
        "accuracy": {"type": ["string", "null"]},
        "output_signal": {"type": ["string", "null"]},
        "protection_class": {"type": ["string", "null"]},
    },
    "required": [
        "manufacturer",
        "model",
        "measurement_principle",
        "measurement_variable",
        "range_min",
        "range_max",
        "range_unit",
        "accuracy",
        "output_signal",
        "protection_class",
    ],
    "additionalProperties": False,
}

SCHEMA_VERSION = "datasheet-v1"

SYSTEM_PROMPT = (
    "Eres un normalizador de fichas técnicas de instrumentación industrial. "
    "Rellena el esquema con los datos que aparecen literalmente en el documento. "
    "Usa null cuando el dato no aparezca. No inventes cifras, unidades ni modelos. "
    "Si el rango se expresa como '0 ... 1600 bar', range_min=0, range_max=1600, "
    "range_unit='bar'. Responde solo con el objeto JSON del esquema."
)

_NUMERIC_FIELDS = ("range_min", "range_max")


class DocumentNormalizer:
    """Adaptador LLM + gramática de un datasheet hacia el esquema canónico."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        enabled: Optional[bool] = None,
        disable_thinking: Optional[bool] = None,
        max_chars: Optional[int] = None,
        max_chunks: Optional[int] = None,
    ):
        self.base_url = base_url or settings.ai_base_url
        self.model_name = model_name or settings.ai_model_name
        self.timeout = settings.ai_timeout_seconds if timeout is None else timeout
        self.enabled = settings.ai_lego_enabled if enabled is None else enabled
        self.disable_thinking = (
            settings.ai_disable_thinking if disable_thinking is None else disable_thinking
        )
        self.max_chars = max_chars or settings.ai_normalizer_max_chars
        self.max_chunks = max_chunks or settings.ai_normalizer_max_chunks

    def should_use_llm(self, extractor_mode: str = "auto") -> bool:
        """Mismo contrato que el Bloque LEGO 1: `llm`, `auto` o determinista."""
        mode = (extractor_mode or "auto").strip().lower()
        if mode == "llm":
            return True
        if mode == "auto":
            return bool(self.enabled) or llama_cpp_available()
        return False

    def normalize(self, file_path: str, extractor_mode: str = "auto") -> dict:
        """Devuelve `fields`, `full_text`, `extractor_used` y `evidence`."""
        deterministic = PDFDatasheetExtractor.extract_technical_data(file_path) or {}
        pages = self._read_pages(file_path)
        full_text = "\n".join(pages).strip()

        if not self.should_use_llm(extractor_mode) or not full_text:
            fields = self._derive_range(dict(deterministic))
            return {
                "fields": {name: value for name, value in fields.items() if value is not None},
                "full_text": full_text,
                "extractor_used": "deterministic",
                "evidence": {},
                "schema_version": SCHEMA_VERSION,
            }

        try:
            extracted: dict[str, Any] = {}
            evidence: dict[str, str] = {}

            for chunk in self._chunks(pages):
                data = self._call_llm(chunk)
                for name, value in data.items():
                    if name in extracted and extracted[name] is not None:
                        continue
                    if name not in DATASHEET_SCHEMA["properties"]:
                        continue
                    if value is None:
                        continue
                    if self._is_anchored(value, chunk):
                        extracted[name] = value
                        evidence[name] = "anchored"
                    else:
                        evidence[name] = "not_anchored"

            # El LLM manda donde aporta valor; el determinista rellena huecos.
            merged = {**deterministic, **extracted}
            merged = self._derive_range(merged)
            merged = {name: value for name, value in merged.items() if value is not None}

            if not extracted and not deterministic:
                raise ValueError("La normalización no produjo campos anclados")

            return {
                "fields": merged,
                "full_text": full_text,
                "extractor_used": "llm_schema",
                "evidence": evidence,
                "schema_version": SCHEMA_VERSION,
            }
        except Exception as exc:  # Red, timeout, HTTP, JSON o esquema rechazado.
            logger.warning(
                "Bloque LEGO 1b no disponible (%s); degradando a extractor determinista.",
                exc,
            )
            return {
                "fields": self._derive_range(dict(deterministic)),
                "full_text": full_text,
                "extractor_used": "deterministic_fallback",
                "evidence": {"error": str(exc)},
                "schema_version": SCHEMA_VERSION,
            }

    # --- Lectura y troceado --------------------------------------------------

    def _read_pages(self, file_path: str) -> list[str]:
        try:
            with pdfplumber.open(file_path) as pdf:
                return [(page.extract_text() or "") for page in pdf.pages]
        except Exception as exc:
            logger.error("No se pudo leer el PDF para normalizar: %s", exc)
            return []

    def _chunks(self, pages: list[str]) -> list[str]:
        """Agrupa páginas completas hasta el presupuesto de caracteres."""
        chunks: list[str] = []
        current: list[str] = []
        size = 0

        for page in pages:
            if size and size + len(page) > self.max_chars:
                chunks.append("\n".join(current))
                current, size = [], 0
                if len(chunks) >= self.max_chunks:
                    break
            current.append(page)
            size += len(page)

        if current and len(chunks) < self.max_chunks:
            chunks.append("\n".join(current))

        return [chunk for chunk in chunks if chunk.strip()]

    # --- Generación ----------------------------------------------------------

    def _call_llm(self, text: str) -> dict:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "temperature": 0.0,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Documento:\n{text}"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "datasheet",
                    "schema": DATASHEET_SCHEMA,
                    "strict": True,
                },
            },
        }

        if self.disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        response = requests.post(url, json=payload, timeout=self.timeout)

        # Servidor sin soporte de gramática: un reintento sin `response_format`
        # y validación estricta posterior. Si también falla, se degrada.
        if response.status_code in (400, 422) and "response_format" in payload:
            logger.info(
                "El servidor rechazó la gramática (HTTP %s); reintentando sin esquema.",
                response.status_code,
            )
            payload.pop("response_format")
            response = requests.post(url, json=payload, timeout=self.timeout)

        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        if content is None or not str(content).strip():
            raise ValueError("Respuesta vacía del LLM")

        return self._parse_json(str(content))

    @staticmethod
    def _parse_json(content: str) -> dict:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("El JSON del LLM no es un objeto")
        return parsed

    # --- Evidencia y derivados ----------------------------------------------

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower().replace("\u00a0", " "))

    def _is_anchored(self, value: Any, text: str) -> bool:
        """Un valor solo se conserva si su literal aparece en el trozo."""
        haystack = self._normalize_text(text)

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return any(candidate in haystack for candidate in self._number_forms(value))

        if isinstance(value, str):
            needle = self._normalize_text(value)
            if len(needle) >= 2 and needle in haystack:
                return True
            # Cadenas compuestas ("IP65/67", "±0.5 %"): exige que sus cifras
            # aparezcan también, para no colar un valor inventado.
            numbers = re.findall(r"\d+(?:[.,]\d+)?", needle)
            return bool(numbers) and all(
                any(form in haystack for form in self._number_forms(n)) for n in numbers
            )

        return False

    @staticmethod
    def _number_forms(value: Any) -> set[str]:
        """Variantes de escritura de un número: 1600 / 1.600 / 1,600 / 1600.0."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return set()

        forms = {str(value)}
        if number.is_integer():
            integer = int(number)
            forms.update(
                {
                    str(integer),
                    f"{integer:,}",
                    f"{integer:,}".replace(",", "."),
                    f"{integer:,}".replace(",", " "),
                }
            )
        else:
            forms.add(f"{number}")

        return {form for form in forms if form}

    @staticmethod
    def _derive_range(fields: dict) -> dict:
        """Reconstruye `operating_range` y `unit` para las reglas metrológicas."""
        low = fields.get("range_min")
        high = fields.get("range_max")
        unit = fields.get("range_unit")

        if low is not None and high is not None:
            suffix = f" {unit}" if unit else ""
            # El rango del esquema manda sobre la regex: si el LLM aporta
            # min/max/unit, el valor determinista se considera obsoleto.
            fields["operating_range"] = f"{low} - {high}{suffix}"

        if unit and not fields.get("unit"):
            fields["unit"] = unit

        return fields
