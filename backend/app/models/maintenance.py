#########################################################
# Mapeo SQLAlchemy 2.0 de las tablas maintenance_event e incident
# definidas en infra/postgres/schema.sql (RF-MAINT-01).
#########################################################

from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.session import Base


class MaintenanceEvent(Base):
    """Intervención de mantenimiento registrada sobre una unidad de instrumento."""

    __tablename__ = "maintenance_event"

    id = Column(Integer, primary_key=True, index=True)
    instrument_unit_id = Column(
        Integer,
        ForeignKey("instrument_unit.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    cost_estimate = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    instrument_unit = relationship("InstrumentUnit", foreign_keys=[instrument_unit_id])


class Incident(Base):
    """Incidencia operativa asociada a una unidad de instrumento."""

    __tablename__ = "incident"

    id = Column(Integer, primary_key=True, index=True)
    instrument_unit_id = Column(
        Integer,
        ForeignKey("instrument_unit.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    incident_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, default="LOW")
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    instrument_unit = relationship("InstrumentUnit", foreign_keys=[instrument_unit_id])
