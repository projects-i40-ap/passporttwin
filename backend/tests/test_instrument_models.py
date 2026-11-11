"""
Tests de modelos de instrumento y alta de dispositivos (Spec 001 — T9).

Cubren:
- Crear un `instrument_type` desde una ficha revisada y asociarla al documento.
- Reutilizar el modelo existente por fabricante + modelo en lugar de duplicarlo.
- Rechazar la creación de modelos desde un certificado.
- Heredar fabricante y modelo del tipo al dar de alta un dispositivo.
- Comprobar un serial en vivo para el formulario.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.api import instruments as instruments_api
from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentType, InstrumentUnit


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is Document:
            return self.session.document
        if self.model is InstrumentType:
            return self.session.type_result
        if self.model is InstrumentUnit:
            return self.session.unit_result
        return None

    def all(self):
        if self.model is ExtractedField:
            return self.session.fields
        if self.model is InstrumentType:
            return self.session.types
        if self.model is InstrumentUnit:
            return self.session.units
        return []


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=21,
            original_filename="ds18b20.pdf",
            source_type="PDF_DATASHEET",
            processing_status="REVIEW_REQUIRED",
            instrument_unit_id=None,
            instrument_type_id=None,
            sha256_hash="d" * 64,
        )
        self.fields = [
            SimpleNamespace(field_name="manufacturer", raw_value="Maxim Integrated", normalized_value="Maxim Integrated"),
            SimpleNamespace(field_name="model", raw_value="DS18B20", normalized_value="DS18B20"),
            SimpleNamespace(field_name="measurement_variable", raw_value="Temperature", normalized_value="Temperature"),
            SimpleNamespace(field_name="range_unit", raw_value="°C", normalized_value="°C"),
        ]
        self.types = []
        self.type_result = None
        self.units = []
        self.unit_result = None
        self.audit_logs = []

    def query(self, model):
        return FakeQuery(model, self)

    def add(self, obj):
        if isinstance(obj, InstrumentType):
            obj.id = 5 if obj.id is None else obj.id
            self.types.append(obj)
            self.type_result = obj
        if isinstance(obj, InstrumentUnit):
            obj.id = 9
            obj.public_id = uuid.uuid4()
            obj.lifecycle_state = "operational"
            obj.aas_sync_status = "PENDING"
            obj.created_at = datetime.utcnow()
            self.units.append(obj)
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


def test_create_type_from_datasheet_links_document(client):
    response = client.post("/api/v1/documents/21/create-type", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["created"] is True
    assert data["instrument_type"]["manufacturer"] == "Maxim Integrated"
    assert data["instrument_type"]["model"] == "DS18B20"
    assert data["instrument_type"]["magnitude"] == "Temperature"
    assert data["instrument_type"]["unit"] == "°C"
    assert fake_db.document.instrument_type_id == data["instrument_type"]["id"]
    assert fake_db.document.processing_status == "ACCEPTED"


def test_create_type_reuses_existing_model(client):
    fake_db.type_result = SimpleNamespace(
        id=3, name="maxim_integrated_ds18b20", magnitude="Temperature",
        unit="°C", manufacturer="Maxim Integrated", model="DS18B20",
    )

    response = client.post("/api/v1/documents/21/create-type", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["created"] is False
    assert data["instrument_type"]["id"] == 3
    assert fake_db.types == []


def test_create_type_rejects_certificates(client):
    fake_db.document.source_type = "PDF_CERTIFICATE"

    response = client.post("/api/v1/documents/21/create-type", json={})

    assert response.status_code == 400


def test_register_instrument_inherits_manufacturer_and_model(client, monkeypatch):
    fake_db.type_result = SimpleNamespace(
        id=4, name="maxim_integrated_ds18b20", magnitude="Temperature",
        unit="°C", manufacturer="Maxim Integrated", model="DS18B20",
    )
    monkeypatch.setattr(instruments_api.AASBuilder, "sync_shell_and_nameplate", lambda *a, **k: True)
    monkeypatch.setattr(instruments_api.AASBuilder, "sync_operational_state", lambda *a, **k: True)

    response = client.post(
        "/api/v1/instruments",
        json={"instrument_type_id": 4, "serial_number": "DS-001", "location": "Lab A"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["manufacturer"] == "Maxim Integrated"
    assert data["model"] == "DS18B20"
    assert data["serial_number"] == "DS-001"


def test_register_instrument_without_identity_fails(client):
    fake_db.type_result = SimpleNamespace(
        id=4, name="legacy", magnitude="Temperature", unit="°C",
        manufacturer=None, model=None,
    )

    response = client.post(
        "/api/v1/instruments",
        json={"instrument_type_id": 4, "serial_number": "DS-002"},
    )

    assert response.status_code == 422
    assert "manufacturer" in response.json()["detail"]


def test_check_serial_reports_existing_instrument(client):
    fake_db.unit_result = SimpleNamespace(id=9, public_id=uuid.uuid4())

    response = client.get("/api/v1/instruments/check-serial?serial=DS-001")

    assert response.status_code == 200
    assert response.json()["exists"] is True
    assert response.json()["instrument_id"] == 9


def test_register_instrument_rejects_invalid_serial(client):
    fake_db.type_result = SimpleNamespace(
        id=4, name="maxim_integrated_ds18b20", magnitude="Temperature",
        unit="°C", manufacturer="Maxim Integrated", model="DS18B20",
    )

    response = client.post(
        "/api/v1/instruments",
        json={"instrument_type_id": 4, "serial_number": "DS 18/20"},
    )

    assert response.status_code == 422
    assert "Número de serie" in response.json()["detail"]


def test_register_instrument_normalizes_serial_to_uppercase(client, monkeypatch):
    fake_db.type_result = SimpleNamespace(
        id=4, name="maxim_integrated_ds18b20", magnitude="Temperature",
        unit="°C", manufacturer="Maxim Integrated", model="DS18B20",
    )
    monkeypatch.setattr(instruments_api.AASBuilder, "sync_shell_and_nameplate", lambda *a, **k: True)
    monkeypatch.setattr(instruments_api.AASBuilder, "sync_operational_state", lambda *a, **k: True)

    response = client.post(
        "/api/v1/instruments",
        json={"instrument_type_id": 4, "serial_number": "ds18b20-002"},
    )

    assert response.status_code == 201
    assert response.json()["serial_number"] == "DS18B20-002"
