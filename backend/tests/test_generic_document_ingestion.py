"""
Tests TDD del Bloque LEGO 1b (Spec 001 — T5): normalización de fichas técnicas.

Cubren:
- La petición a `llama.cpp` con decodificación restringida (`response_format`)
  y razonamiento desactivado (`enable_thinking=false`).
- El anclaje de evidencia: un valor que no aparece en el texto se descarta.
- La derivación de `operating_range`/`unit` para las reglas metrológicas.
- El fallback determinista cuando el servidor no responde (RF-DOC-05).
- Que un datasheet sin campos pero con texto termina en `REVIEW_REQUIRED`
  con `__full_text__` persistido, sin 422 (RF-DOC-03).
"""

from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.database.session import get_db
from app.main import app
from app.models.document import Document, ExtractedField
from app.services import document_normalizer
from app.services.document_normalizer import DocumentNormalizer

DATASHEET_TEXT = (
    "WIKA data sheet PE 81.61\n"
    "Pressure transmitter\n"
    "Model S-20\n"
    "Measuring ranges 0 ... 1600 bar\n"
    "Output signal 4 ... 20 mA\n"
    "Ingress protection IP68\n"
)

LLM_FIELDS = {
    "manufacturer": "WIKA",
    "model": "S-20",
    "measurement_principle": "Pressure",
    "measurement_variable": "Pressure",
    "range_min": 0,
    "range_max": 1600,
    "range_unit": "bar",
    "accuracy": None,
    "output_signal": "4 ... 20 mA",
    "protection_class": "IP68",
}


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePDF:
    def __init__(self, pages):
        self.pages = [FakePage(text) for text in pages]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def patch_pdf(monkeypatch, pages=(DATASHEET_TEXT,)):
    monkeypatch.setattr(
        document_normalizer.pdfplumber,
        "open",
        lambda path: FakePDF(list(pages)),
    )


class FakeHTTPResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def llm_response(fields):
    return FakeHTTPResponse(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": __import__("json").dumps(fields),
                    }
                }
            ]
        }
    )


def make_normalizer(**overrides):
    options = {
        "base_url": "http://localhost:8080/v1",
        "model_name": "Gemma-4-E4B",
        "timeout": 5.0,
        "enabled": True,
        "disable_thinking": True,
        "max_chars": 4000,
        "max_chunks": 4,
    }
    options.update(overrides)
    return DocumentNormalizer(**options)


# --- Generación restringida -------------------------------------------------


def test_normalizer_requests_json_schema_without_thinking(monkeypatch):
    patch_pdf(monkeypatch)
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return llm_response(LLM_FIELDS)

    monkeypatch.setattr(document_normalizer.requests, "post", fake_post)

    result = make_normalizer().normalize("datasheet.pdf", extractor_mode="auto")

    payload = captured["payload"]
    assert captured["url"] == "http://localhost:8080/v1/chat/completions"
    assert payload["model"] == "Gemma-4-E4B"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}

    assert result["extractor_used"] == "llm_schema"
    assert result["schema_version"] == "datasheet-v1"
    assert result["fields"]["manufacturer"] == "WIKA"
    assert result["fields"]["range_max"] == 1600


def test_normalizer_retries_without_grammar_when_rejected(monkeypatch):
    patch_pdf(monkeypatch)
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(dict(json))
        if "response_format" in json:
            return FakeHTTPResponse({"detail": "unsupported"}, status_code=400)
        return llm_response(LLM_FIELDS)

    monkeypatch.setattr(document_normalizer.requests, "post", fake_post)

    result = make_normalizer().normalize("datasheet.pdf", extractor_mode="auto")

    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    assert result["fields"]["model"] == "S-20"


# --- Anclaje de evidencia ---------------------------------------------------


def test_normalizer_drops_value_not_present_in_text(monkeypatch):
    patch_pdf(monkeypatch)
    invented = dict(LLM_FIELDS, range_max=9999)

    monkeypatch.setattr(
        document_normalizer.requests,
        "post",
        lambda *args, **kwargs: llm_response(invented),
    )

    result = make_normalizer().normalize("datasheet.pdf", extractor_mode="auto")

    assert result["fields"].get("range_max") != 9999
    assert result["evidence"]["range_max"] == "not_anchored"


def test_normalizer_derives_operating_range_and_unit(monkeypatch):
    patch_pdf(monkeypatch)

    monkeypatch.setattr(
        document_normalizer.requests,
        "post",
        lambda *args, **kwargs: llm_response(LLM_FIELDS),
    )

    result = make_normalizer().normalize("datasheet.pdf", extractor_mode="auto")

    assert result["fields"]["operating_range"] == "0 - 1600 bar"
    assert result["fields"]["unit"] == "bar"


def test_derive_range_overrides_stale_deterministic_value():
    fields = {
        "operating_range": "40 bar",
        "range_min": 0,
        "range_max": 1600,
        "range_unit": "bar",
    }

    derived = DocumentNormalizer._derive_range(fields)

    assert derived["operating_range"] == "0 - 1600 bar"


# --- Fallback determinista --------------------------------------------------


def test_normalizer_falls_back_when_server_is_down(monkeypatch):
    patch_pdf(monkeypatch)

    def fake_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("llama.cpp apagado")

    monkeypatch.setattr(document_normalizer.requests, "post", fake_post)

    result = make_normalizer().normalize("datasheet.pdf", extractor_mode="auto")

    assert result["extractor_used"] == "deterministic_fallback"
    assert result["fields"]["model"] == "S-20"
    assert result["full_text"].startswith("WIKA data sheet")


def test_normalizer_keeps_text_when_llm_disabled(monkeypatch):
    patch_pdf(monkeypatch)
    monkeypatch.setattr(document_normalizer, "llama_cpp_available", lambda: False)

    def fake_post(*args, **kwargs):
        raise AssertionError("no debe invocarse llama.cpp si está desactivado")

    monkeypatch.setattr(document_normalizer.requests, "post", fake_post)

    result = make_normalizer(enabled=False).normalize("datasheet.pdf", extractor_mode="auto")

    assert result["extractor_used"] == "deterministic"
    assert result["full_text"].strip()


def test_normalizer_uses_model_when_probe_reports_available(monkeypatch):
    """T7: la sonda manda sobre el flag estático cuando llama.cpp responde."""
    patch_pdf(monkeypatch)
    monkeypatch.setattr(document_normalizer, "llama_cpp_available", lambda: True)
    monkeypatch.setattr(
        document_normalizer.requests,
        "post",
        lambda *args, **kwargs: llm_response(LLM_FIELDS),
    )

    result = make_normalizer(enabled=False).normalize("datasheet.pdf", extractor_mode="auto")

    assert result["extractor_used"] == "llm_schema"
    assert result["fields"]["model"] == "S-20"


# --- Integración con la API (RF-DOC-03) ------------------------------------


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.session.document if self.model is Document else None

    def all(self):
        return self.session.fields if self.model is ExtractedField else []

    def delete(self):
        if self.model is ExtractedField:
            self.session.fields.clear()


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=1,
            processing_status="RECEIVED",
            instrument_unit_id=None,
            original_filename="sensor-datasheet.pdf",
            source_type="PDF_DATASHEET",
            file_path="/app/storage/raw/datasheet.pdf",
            sha256_hash="a" * 64,
            uploaded_at=None,
        )
        self.fields = []

    def query(self, model):
        return FakeQuery(model, self)

    def add(self, obj):
        if isinstance(obj, ExtractedField):
            obj.id = len(self.fields) + 1
            self.fields.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def flush(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


fake_db = FakeSession()


def override_get_db():
    yield fake_db


@pytest.fixture
def api_client():
    """Aísla el override por test y restaura el que hubiera antes."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    fake_db.reset()
    try:
        yield TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


class FakeNormalizer:
    def __init__(self, *args, **kwargs):
        pass

    def normalize(self, file_path, extractor_mode="auto"):
        return {
            "fields": {},
            "full_text": DATASHEET_TEXT,
            "extractor_used": "deterministic_fallback",
            "evidence": {},
            "schema_version": "datasheet-v1",
        }


def test_datasheet_without_fields_goes_to_review_with_full_text(monkeypatch, api_client):
    monkeypatch.setattr(documents_api, "DocumentNormalizer", FakeNormalizer)

    response = api_client.post("/api/v1/documents/1/process")

    assert response.status_code == 200
    data = response.json()
    assert data["processing_status"] == "REVIEW_REQUIRED"
    assert data["extractor_used"] == "deterministic_fallback"

    stored = {field.field_name: field for field in fake_db.fields}
    assert stored["__full_text__"].validation_status == "EVIDENCE"
    assert "WIKA data sheet" in stored["__full_text__"].raw_value


def test_datasheet_without_text_still_fails_extraction(monkeypatch, api_client):
    monkeypatch.setattr(documents_api, "DocumentNormalizer", FakeNormalizer)
    monkeypatch.setattr(
        FakeNormalizer,
        "normalize",
        lambda self, file_path, extractor_mode="auto": {
            "fields": {},
            "full_text": "",
            "extractor_used": "deterministic",
            "evidence": {},
            "schema_version": "datasheet-v1",
        },
    )

    response = api_client.post("/api/v1/documents/1/process")

    assert response.status_code == 422
    assert fake_db.document.processing_status == "FAILED_EXTRACTION"
