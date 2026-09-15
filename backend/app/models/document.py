from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database.session import Base

class Document(Base):
    __tablename__ = "document"

    id = Column(Integer, primary_key=True, index=True)
    instrument_unit_id = Column(Integer, ForeignKey("instrument_unit.id"), nullable=True)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    source_type = Column(String, default="MANUAL_UPLOAD")  # PDF_CERTIFICATE | INVENTORY_CSV
    sha256_hash = Column(String(64), unique=True, nullable=False, index=True)
    processing_status = Column(String, default="RECEIVED")  # RECEIVED | EXTRACTED | VALIDATED | ACCEPTED | REJECTED
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    extracted_fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")

class ExtractedField(Base):
    __tablename__ = "extracted_field"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("document.id"), nullable=False)
    field_name = Column(String, nullable=False)        # e.g., 'serial_number', 'calibration_date'
    raw_value = Column(Text, nullable=True)           # e.g., 'S/N: PT-WIKA-001'
    normalized_value = Column(Text, nullable=True)    # e.g., 'PT-WIKA-001'
    confidence = Column(String, default="1.0")
    validation_status = Column(String, default="STAGING") # STAGING | ACCEPTED | REVIEW_REQUIRED | REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="extracted_fields")