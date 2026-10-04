from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.document import Document
from app.models.instrument import InstrumentType, InstrumentUnit
from app.services.aas_builder import AASBuilder


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is InstrumentUnit:
            if self.session.instrument_exists:
                return self.session.instrument
            return None

        if self.model is InstrumentType:
            return self.session.instrument_type

        if self.model is Document:
            return self.session.document

        return None

    def all(self):
        if self.model is InstrumentType:
            return [self.session.instrument_type]

        return []


class FakeSession:
    def __init__(self, instrument_exists=False):
        self.instrument_exists = instrument_exists

        self.instrument_type = SimpleNamespace(
            id=1,
            name="pressure_transmitter",
            magnitude="Pressure",
            unit="bar",
        )

        self.instrument = None
        self.document = None

        if instrument_exists:
            self.instrument = SimpleNamespace(
                id=1,
                public_id=uuid4(),
                instrument_type_id=1,
                serial_number="PT-EXISTING-001",
                manufacturer="Demo Instruments",
                model="PT-100",
                location="Plant-A/Area-1",
                criticality="MEDIUM",
                installed_at=None,
                lifecycle_state="operational",
                aas_sync_status="PENDING",
                created_at=datetime.utcnow(),
            )

    def query(self, model):
        return FakeQuery(
            model=model,
            session=self,
        )

    def add(self, obj):
        if isinstance(obj, InstrumentUnit):
            self.instrument = obj
            self.instrument_exists = True

        if isinstance(obj, Document):
            self.document = obj

    def commit(self):
        pass

    def refresh(self, obj):
        if isinstance(obj, InstrumentUnit):
            if obj.id is None:
                obj.id = 1

            if obj.public_id is None:
                obj.public_id = uuid4()

            if obj.lifecycle_state is None:
                obj.lifecycle_state = "operational"

            if obj.aas_sync_status is None:
                obj.aas_sync_status = "PENDING"

            if obj.created_at is None:
                obj.created_at = datetime.utcnow()

        if isinstance(obj, Document):
            if obj.id is None:
                obj.id = 10

    def close(self):
        pass


client = TestClient(app)


def test_register_instrument_syncs_nameplate_and_operational_state(monkeypatch):
    fake_db = FakeSession()

    def override_get_db():
        try:
            yield fake_db
        finally:
            pass

    sync_call = {}

    def fake_sync_shell_and_nameplate(instrument, instrument_type):
        sync_call["nameplate_instrument"] = instrument
        sync_call["instrument_type"] = instrument_type
        return True

    def fake_sync_operational_state(instrument):
        sync_call["operational_instrument"] = instrument
        return True

    monkeypatch.setattr(
        AASBuilder,
        "sync_shell_and_nameplate",
        fake_sync_shell_and_nameplate,
    )

    monkeypatch.setattr(
        AASBuilder,
        "sync_operational_state",
        fake_sync_operational_state,
    )

    app.dependency_overrides[get_db] = override_get_db

    try:
        response = client.post(
            "/api/v1/instruments",
            json={
                "instrument_type_id": 1,
                "serial_number": "PT-NEW-001",
                "manufacturer": "Demo Instruments",
                "model": "PT-100",
                "location": "Plant-A/Area-1",
                "criticality": "MEDIUM",
                "installed_at": "2026-10-04",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201

    data = response.json()

    assert data["serial_number"] == "PT-NEW-001"
    assert data["lifecycle_state"] == "operational"
    assert data["aas_sync_status"] == "SYNCED"

    assert sync_call["nameplate_instrument"] is fake_db.instrument
    assert sync_call["instrument_type"] is fake_db.instrument_type
    assert sync_call["operational_instrument"] is fake_db.instrument


def test_force_sync_syncs_nameplate_and_operational_state(monkeypatch):
    fake_db = FakeSession(instrument_exists=True)

    def override_get_db():
        try:
            yield fake_db
        finally:
            pass

    sync_call = {}

    def fake_sync_shell_and_nameplate(instrument, instrument_type):
        sync_call["nameplate_instrument"] = instrument
        sync_call["instrument_type"] = instrument_type
        return True

    def fake_sync_operational_state(instrument):
        sync_call["operational_instrument"] = instrument
        return True

    monkeypatch.setattr(
        AASBuilder,
        "sync_shell_and_nameplate",
        fake_sync_shell_and_nameplate,
    )

    monkeypatch.setattr(
        AASBuilder,
        "sync_operational_state",
        fake_sync_operational_state,
    )

    app.dependency_overrides[get_db] = override_get_db

    try:
        response = client.post(
            "/api/v1/instruments/1/sync"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200

    data = response.json()

    assert data["serial_number"] == "PT-EXISTING-001"
    assert data["aas_sync_status"] == "SYNCED"

    assert sync_call["nameplate_instrument"] is fake_db.instrument
    assert sync_call["instrument_type"] is fake_db.instrument_type
    assert sync_call["operational_instrument"] is fake_db.instrument


def test_upload_csv_syncs_nameplate_and_operational_state(monkeypatch):
    fake_db = FakeSession()

    def override_get_db():
        try:
            yield fake_db
        finally:
            pass

    sync_call = {}

    def fake_sync_shell_and_nameplate(instrument, instrument_type):
        sync_call["nameplate_instrument"] = instrument
        sync_call["instrument_type"] = instrument_type
        return True

    def fake_sync_operational_state(instrument):
        sync_call["operational_instrument"] = instrument
        return True

    monkeypatch.setattr(
        AASBuilder,
        "sync_shell_and_nameplate",
        fake_sync_shell_and_nameplate,
    )

    monkeypatch.setattr(
        AASBuilder,
        "sync_operational_state",
        fake_sync_operational_state,
    )

    app.dependency_overrides[get_db] = override_get_db

    csv_content = (
        "serial_number,type_name,manufacturer,model,"
        "location,criticality,installed_at\n"
        "PT-CSV-001,pressure_transmitter,Demo Instruments,"
        "PT-200,Plant-A/Area-2,HIGH,2026-10-04\n"
    )

    try:
        response = client.post(
            "/api/v1/instruments/upload-csv",
            files={
                "file": (
                    "instruments.csv",
                    csv_content.encode("utf-8"),
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201

    data = response.json()

    assert data["total_rows_evaluated"] == 1
    assert data["total_created"] == 1
    assert data["created_instruments"][0]["serial_number"] == "PT-CSV-001"
    assert data["created_instruments"][0]["aas_sync_status"] == "SYNCED"

    assert sync_call["nameplate_instrument"] is fake_db.instrument
    assert sync_call["instrument_type"] is fake_db.instrument_type
    assert sync_call["operational_instrument"] is fake_db.instrument