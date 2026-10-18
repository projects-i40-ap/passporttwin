"""
Bloque LEGO 2: servicio RAG documental (Spec 001 — T3).

Recupera evidencias verificables desde PostgreSQL (documentos, campos extraídos y
eventos de calibración), las puntúa mediante coincidencia léxica ligera (sin
dependencias pesadas) e invoca opcionalmente a `llama.cpp` (`AI_BASE_URL` /
`AI_MODEL_NAME`) para sintetizar una respuesta fundamentada.

Arquitectura LEGO con fallback limpio (Constitución, RF-RAG-03): si `llama.cpp`
está apagado, inaccesible o agota el timeout, el servicio devuelve la evidencia
recuperada con `answer=None` y `llm_status="OFFLINE_RETRIEVAL_ONLY"` sin lanzar
excepción ni romper la API.
"""

import logging
import re
from collections import defaultdict
from typing import Any, Optional

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.calibration import CalibrationEvent
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit

logger = logging.getLogger("passporttwin.rag")

# Tokenización ligera: palabras, números y símbolos de unidad (°, µ, %).
_TOKEN_PATTERN = re.compile(r"[0-9a-záéíóúñü°µ%]+", re.IGNORECASE)

# Longitud máxima del fragmento (`snippet`) devuelto como evidencia.
_SNIPPET_LENGTH = 280


class DocumentRAGService:
    """Fase Retrieval en SQL + Fase Generation en `llama.cpp` (patrón LEGO)."""

    SYSTEM_PROMPT = (
        "Eres un asistente técnico de metrología de PassportTwin. Responde "
        "ÚNICAMENTE con la información presente en el contexto recuperado de la "
        "base de datos (documentos, campos y calibraciones). Si el contexto no "
        "contiene la respuesta, indícalo explícitamente sin inventar datos. "
        "Sé conciso y cita el nombre de archivo o serial cuando sea relevante."
    )

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = base_url or settings.ai_base_url
        self.model_name = model_name or settings.ai_model_name
        self.timeout = settings.ai_timeout_seconds if timeout is None else timeout

    def query_documents(
        self,
        db: Session,
        question: str,
        serial_number: Optional[str] = None,
        document_id: Optional[int] = None,
        top_k: int = 4,
        use_llm: bool = True,
    ) -> dict:
        """
        Recupera evidencias relevantes y, si procede, genera una respuesta.

        Siempre devuelve un diccionario compatible con `DocumentQueryResponse`.
        Nunca propaga errores de red de `llama.cpp` (RF-RAG-03).
        """
        question = (question or "").strip()
        tokens = self._tokenize(question)
        limit = self._normalize_top_k(top_k)

        ranked = self._retrieve(
            db=db,
            question_tokens=tokens,
            serial_number=serial_number,
            document_id=document_id,
        )
        top = ranked[:limit]

        sources = [entry["source"] for entry in top]
        context_chunks = [entry["chunk"] for entry in top]

        response: dict[str, Any] = {
            "question": question,
            "serial_number": serial_number,
            "answer": None,
            "llm_status": "OFFLINE_RETRIEVAL_ONLY",
            "model_used": None,
            "sources": sources,
            "context_chunks": context_chunks,
        }

        if use_llm and context_chunks:
            try:
                response["answer"] = self._generate_answer(question, context_chunks)
                response["llm_status"] = "ONLINE_GENERATED"
                response["model_used"] = self.model_name
            except Exception as exc:  # Red, timeout, HTTP o payload inválido.
                logger.warning(
                    "Bloque LEGO 2 (RAG) no disponible (%s); modo OFFLINE_RETRIEVAL_ONLY.",
                    exc,
                )

        return response

    # --- Fase Retrieval (100%% SQL / léxico) ---------------------------------

    def _retrieve(
        self,
        db: Session,
        question_tokens: list[str],
        serial_number: Optional[str],
        document_id: Optional[int],
    ) -> list[dict]:
        """Carga documentos, campos y calibraciones y los puntúa léxicamente."""
        documents = self._fetch_all(db, Document)
        fields = self._fetch_all(db, ExtractedField)
        calibrations = self._fetch_all(db, CalibrationEvent)

        fields_by_doc: dict[Any, list] = defaultdict(list)
        for field in fields:
            fields_by_doc[getattr(field, "document_id", None)].append(field)

        calibrations_by_unit: dict[Any, list] = defaultdict(list)
        for event in calibrations:
            calibrations_by_unit[getattr(event, "instrument_unit_id", None)].append(event)

        allowed_unit_ids = self._resolve_serial_unit_ids(db, serial_number)
        serial_normalized = serial_number.strip().lower() if serial_number else None

        ranked: list[dict] = []

        for document in documents:
            doc_fields = fields_by_doc.get(getattr(document, "id", None), [])

            if document_id is not None and getattr(document, "id", None) != document_id:
                continue

            if serial_number and not self._matches_serial(
                document, doc_fields, allowed_unit_ids, serial_normalized
            ):
                continue

            doc_calibrations = calibrations_by_unit.get(
                getattr(document, "instrument_unit_id", None), []
            )

            matched_fields, haystack_text, full_text = self._build_payload(
                document, doc_fields, doc_calibrations
            )

            score = self._score(question_tokens, haystack_text)

            ranked.append(
                {
                    "score": score,
                    "document": document,
                    "fields": doc_fields,
                    "calibrations": doc_calibrations,
                    "matched_fields": matched_fields,
                    "full_text": full_text,
                }
            )

        ranked.sort(key=lambda entry: entry["score"], reverse=True)

        return [
            {
                "source": self._build_source(entry),
                "chunk": self._build_chunk(entry),
            }
            for entry in ranked
        ]

    def _fetch_all(self, db: Session, model) -> list:
        """Ejecuta `query(model).all()` de forma tolerante a FakeSession de tests."""
        try:
            return list(db.query(model).all() or [])
        except Exception as exc:  # pragma: no cover - defensivo ante mocks incompletos.
            logger.warning("No se pudo recuperar %s: %s", getattr(model, "__name__", model), exc)
            return []

    def _resolve_serial_unit_ids(self, db: Session, serial_number: Optional[str]) -> set:
        """Traduce un serial a los `instrument_unit_id` canónicos asociados."""
        if not serial_number:
            return set()

        try:
            instrument = (
                db.query(InstrumentUnit)
                .filter(InstrumentUnit.serial_number == serial_number)
                .first()
            )
        except Exception:  # pragma: no cover - FakeSession sin soporte InstrumentUnit.
            instrument = None

        unit_id = getattr(instrument, "id", None)

        return {unit_id} if unit_id is not None else set()

    @staticmethod
    def _matches_serial(
        document,
        doc_fields: list,
        allowed_unit_ids: set,
        serial_normalized: Optional[str],
    ) -> bool:
        """Un documento pertenece al serial si su activo coincide o un campo lo declara."""
        unit_id = getattr(document, "instrument_unit_id", None)

        if unit_id is not None and unit_id in allowed_unit_ids:
            return True

        for field in doc_fields:
            if getattr(field, "field_name", None) != "serial_number":
                continue

            raw = getattr(field, "normalized_value", None) or getattr(field, "raw_value", None)

            if raw and str(raw).strip().lower() == serial_normalized:
                return True

        return False

    def _build_payload(self, document, doc_fields: list, calibrations: list) -> tuple[dict, str, str]:
        """Construye campos emparejables, texto para puntuar y `__full_text__`."""
        matched_fields: dict = {}
        parts: list[str] = []
        full_text = ""

        for field in doc_fields:
            name = getattr(field, "field_name", "") or ""
            raw = getattr(field, "raw_value", None)
            normalized = getattr(field, "normalized_value", None)
            value = normalized if normalized not in (None, "") else raw

            if name == "__full_text__":
                full_text = str(value) if value else ""
                parts.append(full_text)
                continue

            matched_fields[name] = value
            parts.append(f"{name} {value if value is not None else ''}")

        for event in calibrations:
            parts.append(self._calibration_text(event))

        haystack = " ".join(part for part in parts if part)

        return matched_fields, haystack, full_text

    @staticmethod
    def _calibration_text(event) -> str:
        return (
            f"calibration date={getattr(event, 'calibration_date', None)} "
            f"error={getattr(event, 'error_value', None)} "
            f"tolerance={getattr(event, 'tolerance', None)} "
            f"result={getattr(event, 'result', None)} "
            f"next_due={getattr(event, 'next_due_date', None)}"
        )

    def _score(self, question_tokens: list[str], haystack_text: str) -> float:
        """Puntúa por número de tokens distintos de la pregunta presentes en el texto."""
        if not question_tokens:
            return 0.0

        haystack_tokens = set(self._tokenize(haystack_text))
        unique_question_tokens = set(question_tokens)

        return float(len(unique_question_tokens & haystack_tokens))

    # --- Fase Generation (LEGO `llama.cpp`) ---------------------------------

    def _generate_answer(self, question: str, context_chunks: list[str]) -> str:
        """Invoca `POST {AI_BASE_URL}/chat/completions` y devuelve la respuesta."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        context = "\n\n".join(context_chunks)
        payload = {
            "model": self.model_name,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Pregunta: {question}\n\n"
                        f"Contexto recuperado de PostgreSQL:\n{context}"
                    ),
                },
            ],
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        if content is None or not str(content).strip():
            raise ValueError("Respuesta vacía del LLM")

        return str(content).strip()

    # --- Utilidades ----------------------------------------------------------

    def _build_source(self, entry: dict) -> dict:
        document = entry["document"]

        return {
            "document_id": getattr(document, "id", None),
            "original_filename": getattr(document, "original_filename", "") or "",
            "sha256_hash": getattr(document, "sha256_hash", "") or "",
            "source_type": getattr(document, "source_type", None),
            "processing_status": getattr(document, "processing_status", None),
            "score": entry["score"],
            "matched_fields": entry["matched_fields"],
            "snippet": self._build_snippet(entry),
        }

    @staticmethod
    def _build_snippet(entry: dict) -> str:
        full_text = entry.get("full_text") or ""

        if full_text:
            return full_text[:_SNIPPET_LENGTH].strip()

        matched = entry.get("matched_fields") or {}
        pairs = [
            f"{name}={value}"
            for name, value in matched.items()
            if value not in (None, "")
        ]

        return "; ".join(pairs)[:_SNIPPET_LENGTH]

    @staticmethod
    def _build_chunk(entry: dict) -> str:
        """Fragmento compacto y trazable (con hash) para el prompt del LLM."""
        document = entry["document"]
        matched = entry.get("matched_fields") or {}
        fields_text = "; ".join(
            f"{name}={value}"
            for name, value in matched.items()
            if value not in (None, "")
        )

        calibration_text = " | ".join(
            DocumentRAGService._calibration_text(event) for event in entry["calibrations"]
        )

        chunk = (
            f"Documento #{getattr(document, 'id', None)} "
            f"({getattr(document, 'original_filename', '')}) "
            f"sha256={getattr(document, 'sha256_hash', '')} "
            f"estado={getattr(document, 'processing_status', None)}\n"
            f"Campos: {fields_text or 'sin campos'}"
        )

        if calibration_text:
            chunk += f"\nCalibraciones: {calibration_text}"

        full_text = entry.get("full_text")
        if full_text:
            chunk += f"\nTexto: {full_text[:_SNIPPET_LENGTH].strip()}"

        return chunk

    def _tokenize(self, text: Any) -> list[str]:
        if not text:
            return []

        return [
            token
            for token in _TOKEN_PATTERN.findall(str(text).lower())
            if len(token) >= 2
        ]

    @staticmethod
    def _normalize_top_k(top_k: Any) -> int:
        try:
            return max(int(top_k), 0)
        except (TypeError, ValueError):
            return 4
