##############################################
#Asegura el tipado estricto para las operaciones de la API REST
###############################################

from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime, date

class InstrumentTypeBase(BaseModel):
    name: str
    magnitude: str
    unit: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None

class InstrumentTypeCreate(InstrumentTypeBase):
    pass

class InstrumentTypeResponse(InstrumentTypeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class InstrumentUnitCreate(BaseModel):
    instrument_type_id: int
    serial_number: str
    technical_name: Optional[str] = None
    plant_tag: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = "Plant-A/Area-1"
    criticality: Optional[str] = "MEDIUM"
    installed_at: Optional[date] = None

class InstrumentUnitUpdate(BaseModel):
    instrument_type_id: Optional[int] = None
    serial_number: Optional[str] = None
    technical_name: Optional[str] = None
    plant_tag: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    criticality: Optional[str] = None
    installed_at: Optional[date] = None
    lifecycle_state: Optional[str] = None

class InstrumentUnitResponse(BaseModel):
    id: int
    public_id: UUID
    instrument_type_id: Optional[int] = None
    serial_number: str
    technical_name: Optional[str] = None
    plant_tag: Optional[str] = None
    manufacturer: str
    model: str
    location: Optional[str]
    criticality: Optional[str]
    lifecycle_state: str
    aas_sync_status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InstrumentInventoryResponse(InstrumentUnitResponse):
    calibration_status: Literal["CURRENT", "DUE_SOON", "OVERDUE", "NO_HISTORY", "NO_DUE_DATE"]
