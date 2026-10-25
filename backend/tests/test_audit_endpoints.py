"""Tests de los endpoints de consulta de trazabilidad (RF-AUDIT-06).

Validan los árboles de auditoría de instrumentos y documentos sin requerir una
instancia real de PostgreSQL: la sesión SQLAlchemy se sustituye por un fake
compatible con el subconjunto de consultas que usan los endpoints.
"""

from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog, CalibrationEvent
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit


class FakeQuery:
    """Consulta mínima que ignora filtros y devuelve el dataset del fake."""

    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is InstrumentUnit:
            return self.session.instrument

        if self.model is Document:
            return self.session.document

        return None

    def all(self):
        if self.model is Document:
            return self.session.documents

        if self.model is CalibrationEvent:
            return self.session.calibration_events

        if self.model is ExtractedField:
            return self.session.fields

        if self.model is AuditLog:
            return self.session.audit_logs

        return []


class FakeSession:
    """Sesión fake con los agregados de instrumento y documento."""

    def __init__(
        self,
        instrument_exists=True,
        document_exists=True,
        audit_logs=None,
    ):
        self.instrument = (
            SimpleNamespace(
                id=7,
                serial_number="PT-001",
                instrument_type_id=1,
                lifecycle_state="operational",
                aas_sync_status="SYNCED",
            )
            if instrument_exists
            else None
        )

        self.document = (
            SimpleNamespace(
                id=1,
                instrument_unit_id=7,
                original_filename="current_certificate.pdf",
                source_type="PDF_CERTIFICATE",
                sha256_hash="test-sha256",
                processing_status="REVIEW_REQUIRED",
                uploaded_at=None,
            )
            if document_exists
            else None
        )

        self.documents = [
            self.document,
            SimpleNamespace(
                id=2,
                instrument_unit_id=7,
                original_filename="previous_certificate.pdf",
                source_type="PDF_CERTIFICATE",
                sha256_hash="previous-sha256",
                processing_status="ACCEPTED",
                uploaded_at=None,
            ),
            SimpleNamespace(
                id=3,
                instrument_unit_id=99,
                original_filename="foreign_certificate.pdf",
                source_type="PDF_CERTIFICATE",
                sha256_hash="foreign-sha256",
                processing_status="ACCEPTED",
                uploaded_at=None,
            ),
        ]

        self.calibration_events = [
            SimpleNamespace(id=41, instrument_unit_id=7),
            SimpleNamespace(id=42, instrument_unit_id=99),
        ]

        self.fields = [
            SimpleNamespace(
                id=10,
                document_id=1,
                field_name="serial_number",
                raw_value="WRONG-SERIAL",
                normalized_value="WRONG-SERIAL",
                confidence="1.0",
                validation_status="STAGING",
            ),
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
                id=99,
                document_id=2,
                field_name="serial_number",
                raw_value="PT-002",
                normalized_value="PT-002",
                confidence="1.0",
                validation_status="STAGING",
            ),
        ]

        self.audit_logs = list(audit_logs or [])

    def query(self, model):
        return FakeQuery(model=model, session=self)

    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


def _audit_log(
    log_id,
    entity_name,
    entity_id,
    action,
    created_at,
    details=None,
):
    return SimpleNamespace(
        id=log_id,
        entity_name=entity_name,
        entity_id=entity_id,
        action=action,
        details=details or {},
        created_at=created_at,
    )


def _instrument_audit_logs():
    """Eventos del instrumento 7, sus documentos y calibraciones, más ruido ajeno."""
    return [
        _audit_log(
            1,
            "instrument_unit",
            7,
            "INSTRUMENT_CREATED",
            datetime(2026, 1, 10, 9, 0, 0),
            {"instrument_unit_id": 7},
        ),
        _audit_log(
            2,
            "document",
            1,
            "DOCUMENT_UPLOADED",
            datetime(2026, 1, 11, 9, 0, 0),
            {"document_id": 1},
        ),
        _audit_log(
            3,
            "document",
            1,
            "FIELD_CORRECTED",
            datetime(2026, 1, 12, 9, 0, 0),
            {
                "document_id": 1,
                "field_id": 10,
                "actor": "alexander",
                "before": {"normalized_value": "WRONG-SERIAL"},
                "after": {"normalized_value": "PT-001"},
            },
        ),
        _audit_log(
            4,
            "instrument_unit",
            7,
            "CALIBRATION_INGESTED",
            datetime(2026, 1, 13, 9, 0, 0),
            {"document_id": 1, "certificate_sha256": "test-sha256"},
        ),
        _audit_log(
            5,
            "calibration_event",
            41,
            "CALIBRATION_RECORDED",
            datetime(2026, 1, 14, 9, 0, 0),
            {},
        ),
        # Ruido: documento y calibración de otro instrumento.
        _audit_log(
            6,
            "document",
            3,
            "DOCUMENT_UPLOADED",
            datetime(2026, 1, 15, 9, 0, 0),
            {"document_id": 3},
        ),
        _audit_log(
            7,
            "instrument_unit",
            99,
            "AAS_SYNCED",
            datetime(2026, 1, 16, 9, 0, 0),
            {"instrument_unit_id": 99},
        ),
        _audit_log(
            8,
            "calibration_event",
            42,
            "CALIBRATION_RECORDED",
            datetime(2026, 1, 17, 9, 0, 0),
            {},
        ),
    ]


def _document_audit_logs():
    """Eventos del documento 1 y sus campos, más ruido ajeno."""
    return [
        _audit_log(
            101,
            "document",
            1,
            "DOCUMENT_UPLOADED",
            datetime(2026, 2, 1, 9, 0, 0),
            {"document_id": 1},
        ),
        _audit_log(
            102,
            "extracted_field",
            10,
            "FIELD_CORRECTED",
            datetime(2026, 2, 2, 9, 0, 0),
            {
                "document_id": 1,
                "field_id": 10,
                "before": {"normalized_value": "WRONG-SERIAL"},
                "after": {"normalized_value": "PT-001"},
            },
        ),
        _audit_log(
            103,
            "instrument_unit",
            7,
            "CALIBRATION_INGESTED",
            datetime(2026, 2, 3, 9, 0, 0),
            {"document_id": 1},
        ),
        # Ruido: eventos de otro documento, de sus campos y del activo.
        _audit_log(
            104,
            "document",
            2,
            "DOCUMENT_UPLOADED",
            datetime(2026, 2, 4, 9, 0, 0),
            {"document_id": 2},
        ),
        _audit_log(
            105,
            "extracted_field",
            99,
            "FIELD_CORRECTED",
            datetime(2026, 2, 5, 9, 0, 0),
            {"document_id": 2, "field_id": 99},
        ),
        _audit_log(
            106,
            "instrument_unit",
            7,
            "AAS_SYNCED",
            datetime(2026, 2, 6, 9, 0, 0),
            {"instrument_unit_id": 7},
        ),
    ]


client = TestClient(app)


def _bind_db(monkeypatch, db):
    """Inyecta la sesión fake restaurando el override previo al terminar."""

    def override_get_db():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)


def test_get_instrument_audit_returns_descending_traceability(monkeypatch):
    fake_db = FakeSession(audit_logs=_instrument_audit_logs())
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/7/audit")

    assert response.status_code == 200

    data = response.json()

    assert data["instrument_id"] == 7
    assert data["serial_number"] == "PT-001"
    assert data["total_events"] == 5

    # Orden cronológico descendente: el evento más reciente primero.
    assert [event["id"] for event in data["events"]] == [5, 4, 3, 2, 1]
    assert [
        event["action"] for event in data["events"]
    ] == [
        "CALIBRATION_RECORDED",
        "CALIBRATION_INGESTED",
        "FIELD_CORRECTED",
        "DOCUMENT_UPLOADED",
        "INSTRUMENT_CREATED",
    ]

    # El diferencial before/after se desnormaliza desde el JSONB `details`.
    correction = data["events"][2]

    assert correction["entity_name"] == "document"
    assert correction["entity_id"] == 1
    assert correction["actor"] == "alexander"
    assert correction["before"] == {"normalized_value": "WRONG-SERIAL"}
    assert correction["after"] == {"normalized_value": "PT-001"}

    # La evidencia del certificado materializado viaja en `details`.
    ingested = data["events"][1]

    assert ingested["details"]["document_id"] == 1
    assert ingested["details"]["certificate_sha256"] == "test-sha256"

    # Ningún evento de otro instrumento se cuela en el árbol.
    assert all(
        event["entity_id"] != 99
        for event in data["events"]
    )


def test_get_instrument_audit_returns_404_when_not_found(monkeypatch):
    fake_db = FakeSession(
        instrument_exists=False,
        audit_logs=_instrument_audit_logs(),
    )
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/404/audit")

    assert response.status_code == 404
    assert response.json()["detail"] == "Instrumento no encontrado."


def test_get_document_audit_returns_descending_traceability(monkeypatch):
    fake_db = FakeSession(audit_logs=_document_audit_logs())
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/documents/1/audit")

    assert response.status_code == 200

    data = response.json()

    assert data["document_id"] == 1
    assert data["original_filename"] == "current_certificate.pdf"
    assert data["sha256_hash"] == "test-sha256"
    assert data["processing_status"] == "REVIEW_REQUIRED"
    assert data["total_events"] == 3

    assert [event["id"] for event in data["events"]] == [103, 102, 101]
    assert [
        event["action"] for event in data["events"]
    ] == [
        "CALIBRATION_INGESTED",
        "FIELD_CORRECTED",
        "DOCUMENT_UPLOADED",
    ]

    # El evento canónico referencia el documento vía details.document_id.
    assert data["events"][0]["entity_name"] == "instrument_unit"
    assert data["events"][0]["details"]["document_id"] == 1

    # El evento del campo extraído conserva su diferencial.
    field_event = data["events"][1]

    assert field_event["entity_name"] == "extracted_field"
    assert field_event["entity_id"] == 10
    assert field_event["before"] == {"normalized_value": "WRONG-SERIAL"}
    assert field_event["after"] == {"normalized_value": "PT-001"}

    # Ni el otro documento, ni sus campos, ni la sincronización AAS aparecen.
    assert all(
        event["id"] not in (104, 105, 106)
        for event in data["events"]
    )


def test_get_document_audit_returns_404_when_not_found(monkeypatch):
    fake_db = FakeSession(
        document_exists=False,
        audit_logs=_document_audit_logs(),
    )
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/documents/404/audit")

    assert response.status_code == 404
    assert response.json()["detail"] == "Documento no encontrado."
