"""Esquemas Pydantic para la consulta de auditoría y trazabilidad.

Cubren el contrato de salida de los eventos canónicos de `audit_log`
(RF-AUDIT-01) y de los árboles de trazabilidad de instrumentos y documentos
(RF-AUDIT-06). El JSONB `details` se desnormaliza en campos explícitos para
facilitar su consumo desde la vista React de auditoría.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Claves del JSONB `details` que se exponen como campos de primer nivel.
_DETAIL_KEYS: tuple[str, ...] = (
    "actor",
    "source",
    "rule_or_model",
    "before",
    "after",
)


class AuditLogEntryResponse(BaseModel):
    """Evento inmutable de auditoría con su diferencial `before` / `after`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_name: str
    entity_id: int
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    # Campos desnormalizados desde `details` para la tabla de trazabilidad.
    actor: Optional[str] = None
    source: Optional[str] = None
    rule_or_model: Optional[str] = None
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _expand_details(cls, data: Any) -> Any:
        """Extrae `actor`, `source`, `rule_or_model`, `before` y `after` del JSONB."""
        if isinstance(data, dict):
            payload = dict(data)
        else:
            payload = {
                field_name: getattr(data, field_name, None)
                for field_name in (
                    "id",
                    "entity_name",
                    "entity_id",
                    "action",
                    "details",
                    "created_at",
                )
            }

        details = payload.get("details")

        if not isinstance(details, dict):
            return payload

        for key in _DETAIL_KEYS:
            if payload.get(key) is None and details.get(key) is not None:
                payload[key] = details[key]

        return payload


class _TraceabilityBase(BaseModel):
    """Base común de los árboles de trazabilidad ordenados por fecha."""

    total_events: int = 0
    events: list[AuditLogEntryResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_total_events(self) -> "_TraceabilityBase":
        """Mantiene `total_events` coherente con la lista de eventos."""
        if not self.total_events:
            self.total_events = len(self.events)

        return self


class InstrumentTraceabilityResponse(_TraceabilityBase):
    """Historial de auditoría de un activo y de sus documentos/calibraciones."""

    instrument_id: int
    serial_number: Optional[str] = None


class DocumentTraceabilityResponse(_TraceabilityBase):
    """Historial de auditoría asociado a un documento y su evidencia RAW."""

    document_id: int
    original_filename: Optional[str] = None
    sha256_hash: Optional[str] = None
    processing_status: Optional[str] = None
