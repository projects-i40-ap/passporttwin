"""
Tests TDD de integración de la API (Spec 001 — T4).

Cubren:
- `POST /api/v1/documents/query` con `llama.cpp` online (Gemma-4-E4B mockeado),
  devolviendo `answer`, `llm_status="ONLINE_GENERATED"` y `sources` con hash.
- `POST /api/v1/documents/query` con `llama.cpp` apagado (fallback sin GPU),
  devolviendo HTTP 200, `answer=None`, `llm_status="OFFLINE_RETRIEVAL_ONLY"` y
  `sources` intactas (RF-RAG-03).
- `POST /api/v1/documents/{id}/process?extractor=llm` usando el extractor híbrido,
  devolviendo `extractor_used` y persistiendo `__full_text__` sin exponerlo.
- Idempotencia de `POST /api/v1/documents/{id}/accept` (R-DUP-ACCEPT / RF-RULE-04).
"""

from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog, CalibrationEvent
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit
from app.services import pdf_extractor
from app.services import rag_service
from app.services.aas_builder import AASBuilder

SAMPLE_CERTIFICATE_TEXT = (
    "Certificate of Calibration\n"
    "S/N: PT-WIKA-001\n"
    "Calibration Date: 2026-01-15\n"
    "Due Date: 2027-01-15\n"
    "Max Error: 0.5\n"
    "Tolerance: 1.0\n"
    "Unidad: bar\n"
    "Rango: 0-10 bar\n"
)

LLM_JSON_CONTENT = (
    '{"serial_number": "PT-WIKA-001", '
    '"calibration_date": "2026-01-15", '
    '"next_due_date": "2027-01-15", '
    '"error_value": 0.5, '
    '"tolerance": 1.0, '
    '"unit": "bar", '
    '"operating_range": "0 - 10 bar"}'
)


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        if self.model is ExtractedField:
            self.session.fields = []
        return 0

    def first(self):
        if self.model is Document:
            return self.session.document

        if self.model is ExtractedField:
            return self.session.fields[0] if self.session.fields else None

        if self.model is InstrumentUnit:
            return self.session.instrument

        if self.model is AuditLog:
            return self.session.audit_logs[0] if self.session.audit_logs else None

        return None

    def all(self):
        if self.model is Document:
            return self.session.documents

        if self.model is ExtractedField:
            return self.session.fields

        if self.model is CalibrationEvent:
            return self.session.calibration_events

        if self.model is AuditLog:
            return self.session.audit_logs

        if self.model is InstrumentUnit:
            return [self.session.instrument] if self.session.instrument else []

        return []


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=1,
            processing_status="ACCEPTED",
            instrument_unit_id=7,
            original_filename="certificate.pdf",
            source_type="PDF_CERTIFICATE",
            sha256_hash="test-sha256",
            uploaded_at=None,
            file_path="/tmp/certificate.pdf",
        )

        self.documents = [self.document]

        self.instrument = SimpleNamespace(
            id=7,
            serial_number="PT-001",
            lifecycle_state="operational",
        )

        self.fields = [
            SimpleNamespace(
                id=10,
                document_id=1,
                field_name="serial_number",
                raw_value="PT-001",
                normalized_value="PT-001",
                confidence="1.0",
                validation_status="STAGING",
            ),
            SimpleNamespace(
                id=11,
                document_id=1,
                field_name="__full_text__",
                raw_value=SAMPLE_CERTIFICATE_TEXT,
                normalized_value=SAMPLE_CERTIFICATE_TEXT,
                confidence="1.0",
                validation_status="STAGING",
            ),
        ]

        self.calibration_events = []
        self.audit_logs = []

    def query(self, model):
        return FakeQuery(model=model, session=self)

    def add(self, obj):
        if isinstance(obj, ExtractedField):
            if getattr(obj, "id", None) is None:
                obj.id = 100 + len(self.fields)
            self.fields.append(obj)

        if isinstance(obj, CalibrationEvent):
            obj.id = 99
            self.calibration_events.append(obj)

        if isinstance(obj, AuditLog):
            self.audit_logs.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


fake_db = FakeSession()


def override_get_db():
    try:
        yield fake_db
    finally:
        pass


@pytest.fixture(autouse=True)
def _bind_fake_db():
    """Aísla el override de `get_db` para no contaminar otros módulos de test."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


class FakeHTTPResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def llama_cpp_response(content):
    """Construye una respuesta OpenAI-compatible de `llama.cpp`."""
    return FakeHTTPResponse(
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        }
    )


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePDF:
    def __init__(self, text):
        self.pages = [FakePage(text)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def patch_pdf_text(monkeypatch, text=SAMPLE_CERTIFICATE_TEXT):
    monkeypatch.setattr(
        pdf_extractor.pdfplumber,
        "open",
        lambda path: FakePDF(text),
    )


def patch_aas_builder(monkeypatch):
    monkeypatch.setattr(AASBuilder, "sync_calibration_submodel", lambda *a, **k: True)
    monkeypatch.setattr(AASBuilder, "sync_document_provenance", lambda *a, **k: True)
    monkeypatch.setattr(AASBuilder, "sync_operational_state", lambda *a, **k: True)


# --- POST /api/v1/documents/query (RAG, RF-RAG-02 / RF-RAG-03) -------------


def test_rag_query_online_generates_answer_with_llama_cpp(monkeypatch):
    fake_db.reset()

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return llama_cpp_response("El serial PT-001 corresponde al certificado.pdf.")

    monkeypatch.setattr(rag_service.requests, "post", fake_post)

    response = client.post(
        "/api/v1/documents/query",
        json={"question": "¿Cuál es el serial del certificado?", "serial_number": "PT-001"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["llm_status"] == "ONLINE_GENERATED"
    assert data["answer"] == "El serial PT-001 corresponde al certificado.pdf."
    assert data["model_used"] == "gemma-4-e4b"
    assert captured["url"].endswith("/chat/completions")

    assert len(data["sources"]) >= 1

    source = data["sources"][0]

    assert source["document_id"] == 1
    assert source["sha256_hash"] == "test-sha256"
    assert source["original_filename"] == "certificate.pdf"


def test_rag_query_offline_returns_retrieval_only(monkeypatch):
    fake_db.reset()

    def fake_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("llama.cpp apagado")

    monkeypatch.setattr(rag_service.requests, "post", fake_post)

    response = client.post(
        "/api/v1/documents/query",
        json={"question": "¿Cuál es el serial del certificado?"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["answer"] is None
    assert data["llm_status"] == "OFFLINE_RETRIEVAL_ONLY"
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["sha256_hash"] == "test-sha256"


# --- POST /api/v1/documents/{id}/process (RF-LEGO-01 / RF-RAG-01) ----------


def test_process_document_with_llm_extractor_persists_full_text(monkeypatch):
    fake_db.reset()
    fake_db.fields = []
    fake_db.document.source_type = "PDF_CERTIFICATE"

    patch_pdf_text(monkeypatch)

    monkeypatch.setattr(
        pdf_extractor.requests,
        "post",
        lambda *args, **kwargs: llama_cpp_response(LLM_JSON_CONTENT),
    )

    response = client.post("/api/v1/documents/1/process?extractor=llm")

    assert response.status_code == 200

    data = response.json()

    assert data["extractor_used"] == "llm"
    assert "__full_text__" not in data["extracted_fields"]
    assert data["extracted_fields"]["serial_number"] == "PT-WIKA-001"

    stored_names = [field.field_name for field in fake_db.fields]

    assert "__full_text__" in stored_names

    # GET /fields no debe exponer el campo interno `__full_text__`.
    fields_response = client.get("/api/v1/documents/1/fields")

    assert fields_response.status_code == 200

    visible_names = [
        field["field_name"] for field in fields_response.json()["fields"]
    ]

    assert "__full_text__" not in visible_names
    assert "serial_number" in visible_names


# --- POST /api/v1/documents/{id}/accept (R-DUP-ACCEPT / RF-RULE-04) --------


def _accepted_document_fields():
    return [
        SimpleNamespace(
            id=11,
            document_id=1,
            field_name="calibration_date",
            raw_value="2026-01-15",
            normalized_value="2026-01-15",
            confidence="1.0",
            validation_status="STAGING",
        ),
        SimpleNamespace(
            id=12,
            document_id=1,
            field_name="next_due_date",
            raw_value="2027-01-15",
            normalized_value="2027-01-15",
            confidence="1.0",
            validation_status="STAGING",
        ),
    ]


def test_accept_document_is_idempotent(monkeypatch):
    fake_db.reset()
    fake_db.document.processing_status = "ACCEPTED"
    fake_db.document.instrument_unit_id = 7
    fake_db.fields = _accepted_document_fields()

    patch_aas_builder(monkeypatch)

    first = client.post("/api/v1/documents/1/accept")

    assert first.status_code == 200
    assert first.json()["status"] == "CANONICAL_COMMITTED"
    assert len(fake_db.calibration_events) == 1
    assert len(fake_db.audit_logs) == 1

    second = client.post("/api/v1/documents/1/accept")

    assert second.status_code == 409
    assert "R-DUP-ACCEPT" in second.json()["detail"]

    # No se duplica el evento de calibración.
    assert len(fake_db.calibration_events) == 1
    assert len(fake_db.audit_logs) == 1
