"""Esquemas Pydantic v2 para mantenimiento, incidencias y sincronización ERP (RF-MAINT-01)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Eventos de mantenimiento
# ---------------------------------------------------------------------------
class MaintenanceEventBase(BaseModel):
    """Atributos comunes de una intervención de mantenimiento."""

    event_date: date
    description: str = Field(min_length=1)
    cost_estimate: Optional[Decimal] = None


class MaintenanceEventCreate(MaintenanceEventBase):
    """Payload de alta de una intervención (el instrumento se resuelve por ruta)."""


class MaintenanceEventResponse(MaintenanceEventBase):
    """Representación REST de un evento persistido en `maintenance_event`."""

    id: int
    instrument_unit_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Incidencias operativas
# ---------------------------------------------------------------------------
class IncidentBase(BaseModel):
    """Atributos comunes de una incidencia operativa."""

    incident_date: date
    description: str = Field(min_length=1)
    severity: str = "LOW"
    resolved_at: Optional[datetime] = None


class IncidentCreate(IncidentBase):
    """Payload de alta directa de una incidencia (`POST /{id}/incidents`)."""


class IncidentResponse(IncidentBase):
    """Representación REST de una incidencia persistida en `incident`."""

    id: int
    instrument_unit_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Sincronización ERP simulada
# ---------------------------------------------------------------------------
class ERPSyncRecord(BaseModel):
    """Activo recibido del ERP simulado para sincronizar su estado operacional."""

    serial_number: str = Field(min_length=1)
    location: Optional[str] = None
    criticality: Optional[str] = None
    lifecycle_state: Optional[str] = None


class ERPSyncRequest(BaseModel):
    """Lote de sincronización ERP (`POST /erp-sync`)."""

    records: list[ERPSyncRecord] = Field(min_length=1)


class ERPSyncRecordResult(BaseModel):
    """Resultado individual de la sincronización de un activo."""

    serial_number: str
    status: str  # UPDATED | NOT_FOUND
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    aas_sync_status: Optional[str] = None


class ERPSyncResponse(BaseModel):
    """Resumen del lote de sincronización ERP."""

    processed: int
    updated: int
    skipped: int
    results: list[ERPSyncRecordResult] = Field(default_factory=list)
