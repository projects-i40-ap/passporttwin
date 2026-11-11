"""
Tests TDD del borrado documental (Spec 001 — T6).

Cubren:
- 404 cuando el documento no existe.
- 409 cuando el documento sostiene una calibración materializada (RF-DOC-07).
- 204 con auditoría `DOCUMENT_DELETED`, borrado de campos y del RAW.
- Un fallo al borrar el archivo no rompe la respuesta ya confirmada.
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
        if self.model is AuditLog:
            return self.session.audit_logs
        if self.model is ExtractedField:
            return self.session.fields
        return []

    def delete(self):
        if self.model is ExtractedField:
            self.session.fields.clear()


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=7,
            original_filename="datasheet.pdf",
            source_type="PDF_DATASHEET",
            processing_status="REVIEW_REQUIRED",
            sha256_hash="b" * 64,
            file_path="",
            uploaded_at=None,
        )
        self.documents = [self.document]
        self.fields = [SimpleNamespace(id=1, document_id=7, field_name="model")]
        self.audit_logs = []
        self.deleted = []

    def query(self, model):
        if model is Document and self.document is None:
            return FakeQuery(model, self)
        return FakeQuery(model, self)

    def add(self, obj):
        if isinstance(obj, AuditLog):
            self.audit_logs.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)
        if obj is self.document:
            self.document = None

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


def test_delete_missing_document_returns_404(client):
    fake_db.document = None

    response = client.delete("/api/v1/documents/7")

    assert response.status_code == 404


def test_delete_materialized_document_returns_409(client):
    fake_db.audit_logs.append(
        SimpleNamespace(
            id=1,
            action="CALIBRATION_INGESTED",
            entity_name="instrument_unit",
            details={"document_id": 7},
        )
    )

    response = client.delete("/api/v1/documents/7")

    assert response.status_code == 409
    assert "R-DUP-DELETE" in response.json()["detail"]
    assert fake_db.deleted == []
    assert fake_db.fields


def test_delete_document_removes_fields_file_and_audits(client, tmp_path, monkeypatch):
    monkeypatch.setattr(documents_api, "STORAGE_RAW_DIR", str(tmp_path))
    raw = tmp_path / f"{'b' * 64}.pdf"
    raw.write_bytes(b"%PDF-1.4 demo")
    fake_db.document.file_path = str(raw)

    response = client.delete("/api/v1/documents/7")

    assert response.status_code == 204
    assert not raw.exists()
    assert fake_db.fields == []
    assert fake_db.deleted and fake_db.deleted[0] is not None

    actions = [getattr(entry, "action", None) for entry in fake_db.audit_logs]
    assert "DOCUMENT_DELETED" in actions

    event = next(entry for entry in fake_db.audit_logs if entry.action == "DOCUMENT_DELETED")
    assert event.details["before"]["sha256_hash"] == "b" * 64


def test_delete_survives_file_removal_failure(client, tmp_path, monkeypatch):
    monkeypatch.setattr(documents_api, "STORAGE_RAW_DIR", str(tmp_path))
    raw = tmp_path / "locked.pdf"
    raw.write_bytes(b"%PDF-1.4 demo")
    fake_db.document.file_path = str(raw)

    def broken_remove(path):
        raise OSError("disco bloqueado")

    monkeypatch.setattr(documents_api.os, "remove", broken_remove)

    response = client.delete("/api/v1/documents/7")

    assert response.status_code == 204
    assert fake_db.deleted
