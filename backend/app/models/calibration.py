from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Date, Numeric, ForeignKey, JSON
from app.database.session import Base

class CalibrationEvent(Base):
    __tablename__ = "calibration_event"

    id = Column(Integer, primary_key=True, index=True)
    instrument_unit_id = Column(Integer, ForeignKey("instrument_unit.id"), nullable=False)
    calibration_date = Column(Date, nullable=False)
    error_value = Column(Numeric, nullable=False)
    tolerance = Column(Numeric, nullable=False)
    result = Column(String, nullable=False)  # pass | out_of_tolerance
    next_due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)