"""Tests unitarios de los modelos ORM y esquemas Pydantic de mantenimiento (RF-MAINT-01)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import Date, Numeric, Text
from sqlalchemy.orm import configure_mappers

from app.models import Incident, InstrumentUnit, MaintenanceEvent
from app.schemas.maintenance import (
    ERPSyncRecord,
    ERPSyncRequest,
    ERPSyncResponse,
    ERPSyncRecordResult,
    IncidentCreate,
    IncidentResponse,
    MaintenanceEventCreate,
    MaintenanceEventResponse,
)


def make_instrument_unit(serial_number: str = "PT-TEST-001") -> InstrumentUnit:
    return InstrumentUnit(
        id=1,
        instrument_type_id=1,
        serial_number=serial_number,
        manufacturer="TEST",
        model="TEST-MODEL",
        lifecycle_state="operational",
    )


def make_maintenance_event() -> MaintenanceEvent:
    return MaintenanceEvent(
        id=1,
        instrument_unit_id=1,
        event_date=date(2026, 1, 15),
        description="Sustitución de membrana",
        cost_estimate=Decimal("150.50"),
        created_at=datetime(2026, 1, 15, 10, 30, 0),
    )


def make_incident() -> Incident:
    return Incident(
        id=1,
        instrument_unit_id=1,
        incident_date=date(2026, 2, 3),
        description="Deriva en lectura de presión",
        severity="HIGH",
        created_at=datetime(2026, 2, 3, 8, 0, 0),
    )


# ---------------------------------------------------------------------------
# Modelos ORM
# ---------------------------------------------------------------------------
def test_mappers_configure_without_errors():
    configure_mappers()


def test_maintenance_event_table_matches_schema():
    table = MaintenanceEvent.__table__

    assert table.name == "maintenance_event"
    assert set(table.columns.keys()) == {
        "id",
        "instrument_unit_id",
        "event_date",
        "description",
        "cost_estimate",
        "created_at",
    }
    assert isinstance(table.c.event_date.type, Date)
    assert isinstance(table.c.description.type, Text)
    assert isinstance(table.c.cost_estimate.type, Numeric)
    assert table.c.event_date.nullable is False
    assert table.c.description.nullable is False


def test_incident_table_matches_schema():
    table = Incident.__table__

    assert table.name == "incident"
    assert set(table.columns.keys()) == {
        "id",
        "instrument_unit_id",
        "incident_date",
        "description",
        "severity",
        "resolved_at",
        "created_at",
    }
    assert isinstance(table.c.incident_date.type, Date)
    assert table.c.incident_date.nullable is False
    assert table.c.description.nullable is False
    assert table.c.resolved_at.nullable is True
    assert table.c.severity.default.arg == "LOW"


def test_models_reference_instrument_unit_foreign_key():
    for model in (MaintenanceEvent, Incident):
        fk = next(iter(model.__table__.c.instrument_unit_id.foreign_keys))
        assert fk.target_fullname == "instrument_unit.id"
        assert model.__table__.c.instrument_unit_id.nullable is False


def test_maintenance_event_instance_and_relationship():
    event = make_maintenance_event()
    unit = make_instrument_unit()

    event.instrument_unit = unit

    assert event.event_date == date(2026, 1, 15)
    assert event.description == "Sustitución de membrana"
    assert event.cost_estimate == Decimal("150.50")
    assert event.instrument_unit is unit


def test_incident_instance_and_relationship():
    incident = make_incident()
    unit = make_instrument_unit()

    incident.instrument_unit = unit

    assert incident.incident_date == date(2026, 2, 3)
    assert incident.severity == "HIGH"
    assert incident.resolved_at is None
    assert incident.instrument_unit is unit


# ---------------------------------------------------------------------------
# Esquemas Pydantic v2
# ---------------------------------------------------------------------------
def test_maintenance_event_response_validates_orm_object():
    response = MaintenanceEventResponse.model_validate(make_maintenance_event())

    assert response.id == 1
    assert response.instrument_unit_id == 1
    assert response.event_date == date(2026, 1, 15)
    assert response.cost_estimate == Decimal("150.50")
    assert response.created_at == datetime(2026, 1, 15, 10, 30, 0)


def test_maintenance_event_response_serializes_to_json():
    response = MaintenanceEventResponse.model_validate(make_maintenance_event())
    payload = response.model_dump(mode="json")

    assert payload["event_date"] == "2026-01-15"
    assert payload["created_at"].startswith("2026-01-15T10:30:00")
    assert Decimal(payload["cost_estimate"]) == Decimal("150.50")


def test_maintenance_event_create_defaults_cost_to_none():
    event = MaintenanceEventCreate(
        event_date=date(2026, 1, 15),
        description="Lubricación de válvula",
    )

    assert event.cost_estimate is None


def test_maintenance_event_create_rejects_empty_description():
    with pytest.raises(ValidationError):
        MaintenanceEventCreate(event_date=date(2026, 1, 15), description="")


def test_incident_response_validates_orm_object_and_serializes():
    response = IncidentResponse.model_validate(make_incident())
    payload = response.model_dump(mode="json")

    assert response.severity == "HIGH"
    assert response.resolved_at is None
    assert payload["incident_date"] == "2026-02-03"


def test_incident_create_defaults_severity_to_low():
    incident = IncidentCreate(
        incident_date=date(2026, 2, 3),
        description="Parada puntual del lazo de control",
    )

    assert incident.severity == "LOW"
    assert incident.resolved_at is None


def test_incident_create_requires_description_and_date():
    with pytest.raises(ValidationError):
        IncidentCreate(description="Sin fecha")

    with pytest.raises(ValidationError):
        IncidentCreate(incident_date=date(2026, 2, 3), description="")


def test_erp_sync_request_parses_batch():
    request = ERPSyncRequest(
        records=[
            {
                "serial_number": "PT-TEST-001",
                "location": "Plant-B/Area-2",
                "criticality": "HIGH",
                "lifecycle_state": "maintenance",
            },
            {"serial_number": "PT-TEST-002"},
        ]
    )

    assert len(request.records) == 2
    assert request.records[0].location == "Plant-B/Area-2"
    assert request.records[1].criticality is None
    assert request.records[1].lifecycle_state is None


def test_erp_sync_request_requires_at_least_one_record():
    with pytest.raises(ValidationError):
        ERPSyncRequest(records=[])


def test_erp_sync_record_requires_serial_number():
    with pytest.raises(ValidationError):
        ERPSyncRecord(serial_number="")


def test_erp_sync_response_serializes_before_after():
    response = ERPSyncResponse(
        processed=1,
        updated=1,
        skipped=0,
        results=[
            ERPSyncRecordResult(
                serial_number="PT-TEST-001",
                status="UPDATED",
                before={"location": "Plant-A/Area-1"},
                after={"location": "Plant-B/Area-2"},
                aas_sync_status="SYNCED",
            )
        ],
    )
    payload = response.model_dump(mode="json")

    assert payload["updated"] == 1
    assert payload["results"][0]["before"] == {"location": "Plant-A/Area-1"}
    assert payload["results"][0]["after"] == {"location": "Plant-B/Area-2"}
    assert payload["results"][0]["aas_sync_status"] == "SYNCED"
