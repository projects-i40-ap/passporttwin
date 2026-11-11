#########################################################
#Refleja las tablas existentes en infra/postgres/schema.sql añadiendo el identificador 
# public_id para desacoplar el QR del serial según la decisión ADR-009
##########################################################

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.session import Base

class InstrumentType(Base):
    __tablename__ = "instrument_type"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True) # e.g., 'pressure_transmitter'
    magnitude = Column(String, nullable=False)         # e.g., 'Pressure'
    unit = Column(String, nullable=False)              # e.g., 'bar'
    manufacturer = Column(String, nullable=True)       # identidad del modelo (T9)
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    units = relationship("InstrumentUnit", back_populates="instrument_type")

class InstrumentUnit(Base):
    __tablename__ = "instrument_unit"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    instrument_type_id = Column(Integer, ForeignKey("instrument_type.id"), nullable=False)
    serial_number = Column(String, unique=True, nullable=False, index=True)
    technical_name = Column(String, nullable=True)
    plant_tag = Column(String, nullable=True)
    manufacturer = Column(String, nullable=False)
    model = Column(String, nullable=False)
    location = Column(String, nullable=True)
    criticality = Column(String, default="MEDIUM")
    installed_at = Column(Date, nullable=True)
    lifecycle_state = Column(String, default="operational")
    aas_sync_status = Column(String, default="PENDING") # PENDING | SYNCED | ERROR  HAY QUE REVISAR ESTE NO APARECE EN LA BASE DE DATOS
    created_at = Column(DateTime, default=datetime.utcnow)

    instrument_type = relationship("InstrumentType", back_populates="units")
