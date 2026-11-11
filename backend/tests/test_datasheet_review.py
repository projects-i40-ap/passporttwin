"""
Tests de la revalidación de fichas técnicas (Spec 001 — T8).

Una ficha no tiene reglas metrológicas: no exige serial de activo ni fecha de
calibración, y confirmar sus campos no debe disparar `R-MISSING-01` ni `R-ID-01`.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog
from app.models.document import Document, ExtractedField


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
        if self.model is ExtractedField:
            return self.session.fields
        return []


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=11,
            original_filename="ds18b20.pdf",
            source_type="PDF_DATASHEET",
            processing_status="REVIEW_REQUIRED",
            instrument_unit_id=None,
            sha256_hash="c" * 64,
        )
        self.fields = [
            SimpleNamespace(id=1, document_id=11, field_name="model",
                            raw_value="DS18B20", normalized_value="DS18B20",
                            validation_status="STAGING"),
            SimpleNamespace(id=2, document_id=11, field_name="manufacturer",
                            raw_value="Maxim Integrated", normalized_value="Maxim Integrated",
                            validation_status="STAGING"),
        ]
        self.audit_logs = []

    def query(self, model):
        return FakeQuery(model, self)

    def add(self, obj):
        if isinstance(obj, AuditLog):
            self.audit_logs.append(obj)

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
def client():
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


def test_datasheet_revalidation_does_not_apply_certificate_rules(client, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("una ficha no debe pasar por las reglas de certificado")

    monkeypatch.setattr(documents_api, "validate_document_fields", must_not_run)

    response = client.post("/api/v1/documents/11/revalidate")

    assert response.status_code == 200
    data = response.json()
    assert data["rules_failed"] == []
    assert data["processing_status"] == "ACCEPTED"
    assert data["matched_instrument_id"] is None


def test_datasheet_revalidation_is_audited(client):
    response = client.post("/api/v1/documents/11/revalidate")

    assert response.status_code == 200
    actions = [getattr(entry, "action", None) for entry in fake_db.audit_logs]
    assert "DOCUMENT_REVALIDATED" in actions


def test_certificate_revalidation_still_runs_metrological_rules(client, monkeypatch):
    fake_db.document.source_type = "PDF_CERTIFICATE"
    called = {}

    monkeypatch.setattr(
        documents_api,
        "validate_document_fields",
        lambda db, fields, reference_date: called.update(fields=fields) or (None, ["R-ID-01: sin activo"]),
    )

    response = client.post("/api/v1/documents/11/revalidate")

    assert called["fields"]["model"] == "DS18B20"
    assert response.status_code == 200
    assert response.json()["rules_failed"] == ["R-ID-01: sin activo"]
    assert response.json()["processing_status"] == "REVIEW_REQUIRED"
