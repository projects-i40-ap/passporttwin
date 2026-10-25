"""Tests del adaptador CSV de mantenimiento y consulta de historial (RF-MAINT-02/04).

La sesión SQLAlchemy real se sustituye por un fake compatible con el subconjunto
de operaciones que usan los endpoints (`query`, `filter`, `order_by`, `add`,
`commit`, `refresh`, `flush`), de modo que la suite no requiere PostgreSQL.
"""

import hashlib
import os
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import instruments as instruments_api
from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog
from app.models.document import Document
from app.models.instrument import InstrumentUnit
from app.models.maintenance import MaintenanceEvent


# ---------------------------------------------------------------------------
# Fake de la sesión SQLAlchemy
# ---------------------------------------------------------------------------
def _filter_values(criteria):
    """Extrae los valores literales de las expresiones `columna == valor`."""
    values = []

    for criterion in criteria:
        bind_parameter = getattr(criterion, "right", None)
        value = getattr(bind_parameter, "value", None)

        if value is not None:
            values.append(value)

    return values


class FakeQuery:
    """Consulta mínima que emula el filtrado y el orden solicitados por la API."""

    def __init__(self, model, session):
        self.model = model
        self.session = session
        self.filter_values = []
        self.ordered = False

    def filter(self, *criteria):
        self.filter_values.extend(_filter_values(criteria))
        return self

    def order_by(self, *criteria):
        self.ordered = True
        return self

    def first(self):
        if self.model is Document:
            for document in self.session.documents:
                if not self.filter_values:
                    return document

                if document.sha256_hash in self.filter_values:
                    return document

            return None

        if self.model is InstrumentUnit:
            for instrument in self.session.instruments:
                if not self.filter_values:
                    return instrument

                for value in self.filter_values:
                    if value == instrument.id or value == instrument.serial_number:
                        return instrument

            return None

        return None

    def all(self):
        if self.model is MaintenanceEvent:
            events = [
                event
                for event in self.session.maintenance_events
                if not self.filter_values
                or event.instrument_unit_id in self.filter_values
            ]

            if self.ordered:
                return sorted(
                    events,
                    key=lambda event: (event.event_date, event.id or 0),
                    reverse=True,
                )

            return events

        return []


class FakeSession:
    """Sesión fake con los agregados canónicos que tocan los endpoints."""

    def __init__(self, instruments=None, documents=None, maintenance_events=None):
        self.instruments = list(instruments or [])
        self.documents = list(documents or [])
        self.maintenance_events = list(maintenance_events or [])
        self.audit_logs = []
        self._next_document_id = 100
        self._next_event_id = 1000

    def query(self, model):
        return FakeQuery(model=model, session=self)

    def add(self, obj):
        if isinstance(obj, Document):
            self.documents.append(obj)
        elif isinstance(obj, MaintenanceEvent):
            self.maintenance_events.append(obj)
        elif isinstance(obj, AuditLog):
            self.audit_logs.append(obj)

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        if isinstance(obj, Document):
            if obj.id is None:
                self._next_document_id += 1
                obj.id = self._next_document_id
        elif isinstance(obj, MaintenanceEvent):
            if obj.id is None:
                self._next_event_id += 1
                obj.id = self._next_event_id

            if obj.created_at is None:
                obj.created_at = datetime(2026, 1, 1, 12, 0, 0)

    def close(self):
        pass


def make_instrument(instrument_id=1, serial_number="PT-001"):
    return SimpleNamespace(
        id=instrument_id,
        instrument_type_id=1,
        serial_number=serial_number,
        manufacturer="Demo Instruments",
        model="PT-100",
        lifecycle_state="operational",
        aas_sync_status="SYNCED",
    )


def make_event(event_id, instrument_id, event_date, description="Intervención"):
    return SimpleNamespace(
        id=event_id,
        instrument_unit_id=instrument_id,
        event_date=event_date,
        description=description,
        cost_estimate=Decimal("10.00"),
        created_at=datetime(2026, 1, 1, 9, 0, 0),
    )


client = TestClient(app)


def _bind_db(monkeypatch, db):
    """Inyecta la sesión fake y garantiza la restauración del override."""

    def override_get_db():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)


def _upload(filename, content):
    return client.post(
        "/api/v1/instruments/maintenance/upload-csv",
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )


def _maintenance_csv(rows):
    header = "serial_number,event_date,description,cost_estimate\n"
    return header + "".join(rows)


# ---------------------------------------------------------------------------
# Ingesta CSV (RF-MAINT-02)
# ---------------------------------------------------------------------------
def test_upload_maintenance_csv_persists_events_document_and_audit(
    monkeypatch,
    tmp_path,
):
    fake_db = FakeSession(
        instruments=[
            make_instrument(1, "PT-001"),
            make_instrument(2, "PT-002"),
        ]
    )

    monkeypatch.setattr(
        instruments_api,
        "STORAGE_RAW_DIR",
        str(tmp_path),
    )
    _bind_db(monkeypatch, fake_db)

    csv_content = _maintenance_csv(
        [
            "PT-001,2026-01-15,Sustitución de membrana,150.50\n",
            "PT-002,2026-02-20,Lubricación de válvula,25\n",
        ]
    )
    expected_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

    response = _upload("maintenance.csv", csv_content)

    assert response.status_code == 201

    data = response.json()

    assert data["sha256"] == expected_hash
    assert data["total_rows_evaluated"] == 2
    assert data["total_logged"] == 2
    assert data["skipped_records"] == []
    assert [event["serial_number"] for event in data["logged_events"]] == [
        "PT-001",
        "PT-002",
    ]

    # 1. Evidencia RAW inmutable byte a byte.
    raw_path = os.path.join(str(tmp_path), f"{expected_hash}.csv")
    assert os.path.exists(raw_path)
    with open(raw_path, "rb") as raw_file:
        assert raw_file.read() == csv_content.encode("utf-8")

    # 2. Registro de procedencia con la fuente MAINTENANCE_CSV.
    assert len(fake_db.documents) == 1
    raw_document = fake_db.documents[0]
    assert raw_document.source_type == "MAINTENANCE_CSV"
    assert raw_document.sha256_hash == expected_hash
    assert raw_document.id == data["raw_document_id"]

    # 3. Persistencia canónica en maintenance_event.
    assert len(fake_db.maintenance_events) == 2
    first_event = fake_db.maintenance_events[0]
    assert first_event.instrument_unit_id == 1
    assert first_event.event_date == date(2026, 1, 15)
    assert first_event.description == "Sustitución de membrana"
    assert first_event.cost_estimate == Decimal("150.50")

    # 4. Auditoría MAINTENANCE_LOGGED por cada evento insertado.
    assert len(fake_db.audit_logs) == 2
    for audit_entry, event in zip(fake_db.audit_logs, fake_db.maintenance_events):
        assert audit_entry.action == "MAINTENANCE_LOGGED"
        assert audit_entry.entity_name == "maintenance_event"
        assert audit_entry.entity_id == event.id
        assert audit_entry.details["instrument_unit_id"] == event.instrument_unit_id
        assert audit_entry.details["document_id"] == raw_document.id
        assert audit_entry.details["sha256"] == expected_hash
        assert audit_entry.details["source"] == (
            "api.instruments.maintenance.upload_csv"
        )


def test_upload_maintenance_csv_rejects_duplicate_sha256_with_409(
    monkeypatch,
    tmp_path,
):
    fake_db = FakeSession(instruments=[make_instrument(1, "PT-001")])
    monkeypatch.setattr(instruments_api, "STORAGE_RAW_DIR", str(tmp_path))
    _bind_db(monkeypatch, fake_db)

    csv_content = _maintenance_csv(
        ["PT-001,2026-01-15,Cambio de filtro,40\n"]
    )

    first_response = _upload("maintenance.csv", csv_content)
    assert first_response.status_code == 201

    events_after_first = list(fake_db.maintenance_events)
    audit_after_first = list(fake_db.audit_logs)

    second_response = _upload("maintenance_again.csv", csv_content)

    assert second_response.status_code == 409
    detail = second_response.json()["detail"]
    assert "R-DUP-01" in detail
    assert first_response.json()["sha256"] in detail

    # Ningún efecto adicional: ni documentos, ni eventos, ni auditoría.
    assert len(fake_db.documents) == 1
    assert fake_db.maintenance_events == events_after_first
    assert fake_db.audit_logs == audit_after_first


def test_upload_maintenance_csv_skips_unknown_serial_and_invalid_rows(
    monkeypatch,
    tmp_path,
):
    fake_db = FakeSession(instruments=[make_instrument(1, "PT-001")])
    monkeypatch.setattr(instruments_api, "STORAGE_RAW_DIR", str(tmp_path))
    _bind_db(monkeypatch, fake_db)

    csv_content = _maintenance_csv(
        [
            "PT-001,2026-03-01,Calibración interna,10\n",
            "PT-UNKNOWN,2026-03-02,Revisión de lazo,10\n",
            "PT-001,not-a-date,Fecha corrupta,10\n",
        ]
    )

    response = _upload("maintenance.csv", csv_content)

    assert response.status_code == 201

    data = response.json()

    assert data["total_rows_evaluated"] == 3
    assert data["total_logged"] == 1
    assert len(fake_db.maintenance_events) == 1
    assert len(fake_db.audit_logs) == 1

    assert [record["row"] for record in data["skipped_records"]] == [3, 4]
    assert data["skipped_records"][0]["serial_number"] == "PT-UNKNOWN"
    assert "instrument_unit" in data["skipped_records"][0]["reason"]
    assert data["skipped_records"][1]["serial_number"] == "PT-001"
    assert "event_date" in data["skipped_records"][1]["reason"]


# ---------------------------------------------------------------------------
# Consulta REST del historial (RF-MAINT-04)
# ---------------------------------------------------------------------------
def test_get_instrument_maintenance_returns_descending_history(monkeypatch):
    fake_db = FakeSession(
        instruments=[make_instrument(1, "PT-001")],
        maintenance_events=[
            make_event(11, 1, date(2026, 1, 10), "Intervención antigua"),
            make_event(12, 1, date(2026, 3, 5), "Intervención reciente"),
            make_event(13, 1, date(2026, 2, 1), "Intervención intermedia"),
            # Ruido: evento de otro instrumento que no debe aparecer.
            make_event(14, 2, date(2026, 4, 1), "Evento ajeno"),
        ],
    )
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/1/maintenance")

    assert response.status_code == 200

    data = response.json()

    # Orden cronológico descendente estricto.
    assert [event["id"] for event in data] == [12, 13, 11]
    assert [event["event_date"] for event in data] == [
        "2026-03-05",
        "2026-02-01",
        "2026-01-10",
    ]
    assert data[0]["instrument_unit_id"] == 1
    assert data[0]["description"] == "Intervención reciente"


def test_get_instrument_maintenance_returns_404_when_instrument_missing(
    monkeypatch,
):
    fake_db = FakeSession(instruments=[])
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/404/maintenance")

    assert response.status_code == 404
    assert response.json()["detail"] == "Instrumento no encontrado."
