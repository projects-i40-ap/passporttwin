"""Tests unitarios del servicio centralizado de auditoría (RF-AUDIT-01).

Validan la persistencia en la sesión, el formateo del JSONB `details` con el
diferencial `before` / `after` y la serialización de los schemas de
trazabilidad. No requieren una instancia real de PostgreSQL.
"""

from datetime import datetime
from types import SimpleNamespace

from app.models.calibration import AuditLog
from app.schemas.audit import (
    AuditLogEntryResponse,
    DocumentTraceabilityResponse,
    InstrumentTraceabilityResponse,
)
from app.services.audit_service import AuditService


class FakeSession:
    """Sesión mínima compatible con `AuditService.log_event`."""

    def __init__(self):
        self.added = []
        self.flushed = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1


class FailingSession:
    """Sesión que fuerza un fallo de persistencia para validar el fallback."""

    def add(self, obj):
        raise RuntimeError("database is down")


def _audit_row(**overrides):
    """Construye una fila de `audit_log` desacoplada de SQLAlchemy."""
    defaults = {
        "id": 5,
        "entity_name": "document",
        "entity_id": 1,
        "action": "FIELD_CORRECTED",
        "details": {
            "document_id": 1,
            "field_id": 10,
            "actor": "alexander",
            "source": "api.patch",
            "rule_or_model": "R-MATCH-01",
            "before": {"normalized_value": "WRONG-SERIAL"},
            "after": {"normalized_value": "PT-001"},
            "metadata": {"sha256": "test-sha256"},
        },
        "created_at": datetime(2026, 1, 15, 12, 0, 0),
    }
    defaults.update(overrides)

    return SimpleNamespace(**defaults)


def test_log_event_persists_full_details_payload():
    db = FakeSession()

    entry = AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=1,
        action="FIELD_CORRECTED",
        actor="alexander",
        source="api.patch",
        rule_or_model="R-MATCH-01",
        before={"normalized_value": "WRONG-SERIAL"},
        after={"normalized_value": "PT-001"},
        details={"document_id": 1, "field_id": 10},
        metadata={"sha256": "test-sha256"},
    )

    assert isinstance(entry, AuditLog)
    assert db.added == [entry]
    assert db.flushed == 1

    assert entry.entity_name == "document"
    assert entry.entity_id == 1
    assert entry.action == "FIELD_CORRECTED"

    # El JSONB `details` conserva los metadatos y el diferencial before/after.
    assert entry.details["document_id"] == 1
    assert entry.details["field_id"] == 10
    assert entry.details["actor"] == "alexander"
    assert entry.details["source"] == "api.patch"
    assert entry.details["rule_or_model"] == "R-MATCH-01"
    assert entry.details["before"] == {"normalized_value": "WRONG-SERIAL"}
    assert entry.details["after"] == {"normalized_value": "PT-001"}
    assert entry.details["metadata"] == {"sha256": "test-sha256"}


def test_log_event_applies_defaults_and_does_not_mutate_caller_details():
    db = FakeSession()
    caller_details = {"document_id": 1}

    entry = AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=1,
        action="DOCUMENT_REVALIDATED",
        details=caller_details,
    )

    assert entry.details["actor"] == "system"
    assert entry.details["document_id"] == 1

    # Sin `before`/`after` explícitos no se inventan claves en el JSONB.
    assert "before" not in entry.details
    assert "after" not in entry.details
    assert "source" not in entry.details

    # El diccionario del llamador permanece intacto (copia defensiva).
    assert caller_details == {"document_id": 1}


def test_log_event_tolerates_sessions_without_flush():
    added = []
    db = SimpleNamespace(add=added.append)

    entry = AuditService.log_event(
        db=db,
        entity_name="instrument_unit",
        entity_id=7,
        action="AAS_SYNCED",
        after={"aas_sync_status": "SYNCED"},
    )

    assert added == [entry]
    assert entry.details["after"] == {"aas_sync_status": "SYNCED"}


def test_log_event_does_not_break_master_operation_on_persistence_error():
    db = FailingSession()

    entry = AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=1,
        action="DOCUMENT_UPLOADED",
        metadata={"sha256": "test-sha256"},
    )

    # El fallo de auditoría se registra en el logger, no se propaga.
    assert isinstance(entry, AuditLog)
    assert entry.action == "DOCUMENT_UPLOADED"


def test_audit_log_entry_response_serializes_before_after():
    response = AuditLogEntryResponse.model_validate(_audit_row())

    assert response.id == 5
    assert response.entity_name == "document"
    assert response.action == "FIELD_CORRECTED"
    assert response.actor == "alexander"
    assert response.source == "api.patch"
    assert response.rule_or_model == "R-MATCH-01"
    assert response.before == {"normalized_value": "WRONG-SERIAL"}
    assert response.after == {"normalized_value": "PT-001"}

    payload = response.model_dump(mode="json")

    assert payload["details"]["document_id"] == 1
    assert payload["before"] == {"normalized_value": "WRONG-SERIAL"}
    assert payload["after"] == {"normalized_value": "PT-001"}
    assert payload["created_at"] == "2026-01-15T12:00:00"


def test_traceability_responses_count_events():
    entry = AuditLogEntryResponse.model_validate(_audit_row())

    instrument_trace = InstrumentTraceabilityResponse(
        instrument_id=7,
        serial_number="PT-001",
        events=[entry],
    )

    document_trace = DocumentTraceabilityResponse(
        document_id=1,
        original_filename="current_certificate.pdf",
        sha256_hash="test-sha256",
        processing_status="ACCEPTED",
        events=[entry],
    )

    assert instrument_trace.total_events == 1
    assert instrument_trace.events[0].action == "FIELD_CORRECTED"
    assert document_trace.total_events == 1
    assert document_trace.sha256_hash == "test-sha256"
