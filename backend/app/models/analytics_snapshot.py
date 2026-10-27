"""Append-only application snapshots for BI; refreshes create new rows."""
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, func

from app.database.session import Base


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshot"

    id = Column(Integer, primary_key=True)
    instrument_unit_id = Column(Integer, ForeignKey("instrument_unit.id"), nullable=False, index=True)
    as_of = Column(Date, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    input_hash = Column(String(64), nullable=False)
    input_manifest = Column(JSON, nullable=False)
    weights = Column(JSON, nullable=False)
    score_method_version = Column(String, nullable=False)
    risk_method_version = Column(String, nullable=False)
    score_status = Column(String, nullable=False)
    risk_status = Column(String, nullable=False)
    health_score = Column(Float, nullable=True)
    probability_30 = Column(Float, nullable=True)
    probability_60 = Column(Float, nullable=True)
    probability_90 = Column(Float, nullable=True)
    score_result = Column(JSON, nullable=False)
    risk_result = Column(JSON, nullable=False)
