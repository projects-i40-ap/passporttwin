"""Tests del adaptador ERP simulado y gestión de incidencias (RF-MAINT-03/04/05).

La sesión SQLAlchemy real se sustituye por un fake compatible con el subconjunto
de operaciones que usan los endpoints (`query`, `filter`, `order_by`, `add`,
`commit`, `refresh`, `flush`), de modo que la suite no requiere PostgreSQL ni
un servidor Eclipse BaSyx en ejecución.
"""

from datetime import date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import instruments as instruments_api
from app.database.session import get_db
from app.main import app
from app.models.calibration import AuditLog
from app.models.instrument import InstrumentUnit
from app.models.maintenance import Incident


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
        if self.model is Incident:
            incidents = [
                incident
                for incident in self.session.incidents
                if not self.filter_values
                or incident.instrument_unit_id in self.filter_values
            ]

            if self.ordered:
                return sorted(
                    incidents,
                    key=lambda incident: (incident.incident_date, incident.id or 0),
                    reverse=True,
                )

            return incidents

        return []


class FakeSession:
    """Sesión fake con los agregados canónicos que tocan los endpoints."""

    def __init__(self, instruments=None, incidents=None):
        self.instruments = list(instruments or [])
        self.incidents = list(incidents or [])
        self.audit_logs = []
        self._next_incident_id = 500

    def query(self, model):
        return FakeQuery(model=model, session=self)

    def add(self, obj):
        if isinstance(obj, Incident):
            self.incidents.append(obj)
        elif isinstance(obj, AuditLog):
            self.audit_logs.append(obj)

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        if isinstance(obj, Incident):
            if obj.id is None:
                self._next_incident_id += 1
                obj.id = self._next_incident_id

            if obj.created_at is None:
                obj.created_at = datetime(2026, 4, 1, 8, 0, 0)

    def close(self):
        pass


def make_instrument(instrument_id=1, serial_number="PT-001"):
    return SimpleNamespace(
        id=instrument_id,
        instrument_type_id=1,
        serial_number=serial_number,
        manufacturer="Demo Instruments",
        model="PT-100",
        location="Plant-A/Area-1",
        criticality="MEDIUM",
        lifecycle_state="operational",
        aas_sync_status="PENDING",
    )


def make_incident(incident_id, instrument_id, incident_date, description="Incidencia"):
    return SimpleNamespace(
        id=incident_id,
        instrument_unit_id=instrument_id,
        incident_date=incident_date,
        description=description,
        severity="HIGH",
        resolved_at=None,
        created_at=datetime(2026, 1, 1, 9, 0, 0),
    )


client = TestClient(app)


def _bind_db(monkeypatch, db):
    """Inyecta la sesión fake y garantiza la restauración del override."""

    def override_get_db():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)


def _erp_sync(records):
    return client.post("/api/v1/instruments/erp-sync", json={"records": records})


# ---------------------------------------------------------------------------
# Sincronización ERP (RF-MAINT-03/05)
# ---------------------------------------------------------------------------
def test_erp_sync_updates_asset_audits_and_projects_to_aas(monkeypatch):
    instrument = make_instrument(1, "PT-001")
    fake_db = FakeSession(instruments=[instrument])
    _bind_db(monkeypatch, fake_db)

    projected = []

    def fake_sync_operational_state(target):
        projected.append(target)
        return True

    monkeypatch.setattr(
        instruments_api.AASBuilder,
        "sync_operational_state",
        staticmethod(fake_sync_operational_state),
    )

    response = _erp_sync(
        [
            {
                "serial_number": "PT-001",
                "location": "Plant-B/Area-2",
                "criticality": "HIGH",
                "lifecycle_state": "maintenance",
            },
            {
                "serial_number": "PT-UNKNOWN",
                "location": "Plant-C/Area-3",
            },
        ]
    )

    assert response.status_code == 200

    data = response.json()
    assert data["processed"] == 2
    assert data["updated"] == 1
    assert data["skipped"] == 1
    assert [result["status"] for result in data["results"]] == [
        "UPDATED",
        "NOT_FOUND",
    ]

    # 1. El activo canónico refleja el estado recibido del ERP.
    assert instrument.location == "Plant-B/Area-2"
    assert instrument.criticality == "HIGH"
    assert instrument.lifecycle_state == "maintenance"
    assert instrument.aas_sync_status == "SYNCED"
    assert data["results"][0]["aas_sync_status"] == "SYNCED"
    assert data["results"][0]["before"] == {
        "location": "Plant-A/Area-1",
        "criticality": "MEDIUM",
        "lifecycle_state": "operational",
    }
    assert data["results"][0]["after"] == {
        "location": "Plant-B/Area-2",
        "criticality": "HIGH",
        "lifecycle_state": "maintenance",
    }

    # 2. Proyección hacia el submodelo OperationalState con el estado ya mutado.
    assert projected == [instrument]

    # 3. Auditoría inmutable ERP_SYNCED con before/after.
    assert len(fake_db.audit_logs) == 1
    audit_entry = fake_db.audit_logs[0]
    assert audit_entry.action == "ERP_SYNCED"
    assert audit_entry.entity_name == "instrument_unit"
    assert audit_entry.entity_id == 1
    assert audit_entry.details["source"] == "api.instruments.erp_sync"
    assert audit_entry.details["instrument_unit_id"] == 1
    assert audit_entry.details["serial_number"] == "PT-001"
    assert audit_entry.details["before"]["location"] == "Plant-A/Area-1"
    assert audit_entry.details["after"]["location"] == "Plant-B/Area-2"
    assert audit_entry.details["after"]["aas_sync_status"] == "SYNCED"


def test_erp_sync_tolerates_basyx_failure_marking_pending(monkeypatch):
    instrument = make_instrument(1, "PT-001")
    fake_db = FakeSession(instruments=[instrument])
    _bind_db(monkeypatch, fake_db)

    monkeypatch.setattr(
        instruments_api.AASBuilder,
        "sync_operational_state",
        staticmethod(lambda target: False),
    )

    response = _erp_sync(
        [
            {
                "serial_number": "PT-001",
                "location": "Plant-D/Area-4",
            }
        ]
    )

    # RF-MAINT-05: sin pérdida de datos y con HTTP 200 aunque BaSyx falle.
    assert response.status_code == 200

    data = response.json()
    assert data["updated"] == 1
    assert data["results"][0]["aas_sync_status"] == "PENDING"
    assert instrument.location == "Plant-D/Area-4"
    assert instrument.aas_sync_status == "PENDING"
    assert len(fake_db.audit_logs) == 1
    assert fake_db.audit_logs[0].action == "ERP_SYNCED"
    assert fake_db.audit_logs[0].details["after"]["aas_sync_status"] == "PENDING"


def test_erp_sync_tolerates_basyx_exception_marking_error(monkeypatch):
    instrument = make_instrument(1, "PT-001")
    fake_db = FakeSession(instruments=[instrument])
    _bind_db(monkeypatch, fake_db)

    def raising_sync(target):
        raise RuntimeError("BaSyx no disponible")

    monkeypatch.setattr(
        instruments_api.AASBuilder,
        "sync_operational_state",
        staticmethod(raising_sync),
    )

    response = _erp_sync(
        [
            {
                "serial_number": "PT-001",
                "criticality": "CRITICAL",
            }
        ]
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert instrument.criticality == "CRITICAL"
    assert instrument.aas_sync_status == "ERROR"
    assert fake_db.audit_logs[0].details["after"]["aas_sync_status"] == "ERROR"


# ---------------------------------------------------------------------------
# Alta de incidencias (RF-MAINT-04)
# ---------------------------------------------------------------------------
def test_create_incident_persists_and_logs_audit(monkeypatch):
    fake_db = FakeSession(instruments=[make_instrument(1, "PT-001")])
    _bind_db(monkeypatch, fake_db)

    response = client.post(
        "/api/v1/instruments/1/incidents",
        json={
            "incident_date": "2026-04-10",
            "description": "Pérdida de señal en lazo 4-20 mA",
            "severity": "high",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["instrument_unit_id"] == 1
    assert data["incident_date"] == "2026-04-10"
    assert data["description"] == "Pérdida de señal en lazo 4-20 mA"
    assert data["severity"] == "HIGH"
    assert data["resolved_at"] is None

    # 1. Persistencia canónica en incident.
    assert len(fake_db.incidents) == 1
    incident = fake_db.incidents[0]
    assert incident.instrument_unit_id == 1
    assert incident.incident_date == date(2026, 4, 10)
    assert incident.severity == "HIGH"
    assert data["id"] == incident.id

    # 2. Auditoría inmutable de la incidencia.
    assert len(fake_db.audit_logs) == 1
    audit_entry = fake_db.audit_logs[0]
    assert audit_entry.action == "INCIDENT_LOGGED"
    assert audit_entry.entity_name == "incident"
    assert audit_entry.entity_id == incident.id
    assert audit_entry.details["source"] == "api.instruments.incidents.create"
    assert audit_entry.details["instrument_unit_id"] == 1
    assert audit_entry.details["after"]["severity"] == "HIGH"
    assert audit_entry.details["after"]["incident_date"] == "2026-04-10"


def test_create_incident_returns_404_when_instrument_missing(monkeypatch):
    fake_db = FakeSession(instruments=[])
    _bind_db(monkeypatch, fake_db)

    response = client.post(
        "/api/v1/instruments/404/incidents",
        json={
            "incident_date": "2026-04-10",
            "description": "Incidencia huérfana",
            "severity": "LOW",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Instrumento no encontrado."
    assert fake_db.incidents == []
    assert fake_db.audit_logs == []


# ---------------------------------------------------------------------------
# Consulta de incidencias (RF-MAINT-04)
# ---------------------------------------------------------------------------
def test_get_instrument_incidents_returns_descending_history(monkeypatch):
    fake_db = FakeSession(
        instruments=[make_instrument(1, "PT-001")],
        incidents=[
            make_incident(21, 1, date(2026, 1, 10), "Incidencia antigua"),
            make_incident(22, 1, date(2026, 5, 5), "Incidencia reciente"),
            make_incident(23, 1, date(2026, 3, 1), "Incidencia intermedia"),
            # Ruido: incidencia de otro instrumento que no debe aparecer.
            make_incident(24, 2, date(2026, 6, 1), "Incidencia ajena"),
        ],
    )
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/1/incidents")

    assert response.status_code == 200

    data = response.json()
    assert [incident["id"] for incident in data] == [22, 23, 21]
    assert [incident["incident_date"] for incident in data] == [
        "2026-05-05",
        "2026-03-01",
        "2026-01-10",
    ]
    assert all(incident["instrument_unit_id"] == 1 for incident in data)


def test_get_instrument_incidents_returns_404_when_instrument_missing(
    monkeypatch,
):
    fake_db = FakeSession(instruments=[])
    _bind_db(monkeypatch, fake_db)

    response = client.get("/api/v1/instruments/404/incidents")

    assert response.status_code == 404
    assert response.json()["detail"] == "Instrumento no encontrado."
