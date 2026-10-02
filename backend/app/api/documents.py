import os
import hashlib
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.document import Document
from datetime import datetime
from app.models.document import ExtractedField
from app.models.instrument import InstrumentUnit
from app.services.pdf_extractor import PDFCertificateExtractor
from app.models.calibration import CalibrationEvent, AuditLog
from app.schemas.document import ExtractedFieldCorrection
from app.services.document_validation import validate_document_fields

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_RAW_DIR = os.getenv("STORAGE_RAW_DIR", "/app/storage/raw")
os.makedirs(STORAGE_RAW_DIR, exist_ok=True)

@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Ingesta de archivo RAW con hash SHA-256")
async def upload_raw_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

    # 1. Regla de Integridad R-DUP-01: Cálculo estricto de SHA-256
    file_hash = hashlib.sha256(contents).hexdigest()
    
    existing = db.query(Document).filter(Document.sha256_hash == file_hash).first()
    if existing:
        raise HTTPException(
            status_code=409, 
            detail=f"Documento duplicado (Regla R-DUP-01). ID existente: {existing.id}"
        )

    # 2. Persistencia en Almacenamiento RAW Inmutable
    file_extension = os.path.splitext(file.filename)[1]
    storage_path = os.path.join(STORAGE_RAW_DIR, f"{file_hash}{file_extension}")
    
    with open(storage_path, "wb") as f:
        f.write(contents)

    # 3. Registro Canónico de Procedencia (Provenance)
    new_doc = Document(
        original_filename=file.filename,
        file_path=storage_path,
        sha256_hash=file_hash,
        source_type="PDF_CERTIFICATE" if file_extension.lower() == ".pdf" else "CSV_DATA",
        processing_status="RECEIVED"
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return {
        "document_id": new_doc.id,
        "filename": new_doc.original_filename,
        "sha256": new_doc.sha256_hash,
        "status": new_doc.processing_status,
        "storage_path": new_doc.file_path
    }

@router.post("/{document_id}/process", summary="Ejecuta Extracción, Matching y Motor de Reglas")
def process_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    # 1. Extracción de campos crudos
    extracted = PDFCertificateExtractor.extract_and_parse(doc.file_path)
    if not extracted:
        doc.processing_status = "FAILED_EXTRACTION"
        db.commit()
        raise HTTPException(status_code=422, detail="No se pudieron extraer campos estructurados del PDF.")

    # Línea a añadir para evitar duplicados en Staging:
    db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).delete()   

    # 2. Persistencia en Zona de Staging (extracted_field)
    for field_name, val in extracted.items():
        field_entry = ExtractedField(
            document_id=doc.id,
            field_name=field_name,
            raw_value=str(val),
            normalized_value=str(val),
            confidence="1.0",
            validation_status="STAGING"
        )
        db.add(field_entry)
    
    # 3. Matching Determinista y Motor de Reglas compartido
    target_unit, rules_failed = validate_document_fields(
        db=db,
        fields=extracted
    )

    if target_unit:
        doc.instrument_unit_id = target_unit.id

    # 4. Determinación de Estado Canónico
    if len(rules_failed) == 0:
        doc.processing_status = "ACCEPTED"
    else:
        doc.processing_status = "REVIEW_REQUIRED"

    db.commit()
    db.refresh(doc)

    return {
        "document_id": doc.id,
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "extracted_fields": extracted,
        "rules_failed": rules_failed
    }

from app.models.calibration import CalibrationEvent, AuditLog

@router.post("/{document_id}/accept", summary="Materializa campos aceptados en el Modelo Canónico y AAS")
def accept_document_to_canonical(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    
    if doc.processing_status != "ACCEPTED":
        raise HTTPException(
            status_code=400, 
            detail=f"El documento está en estado '{doc.processing_status}'. Solo se pueden materializar documentos en estado 'ACCEPTED'."
        )

    if not doc.instrument_unit_id:
        raise HTTPException(status_code=400, detail="El documento no tiene un activo canónico asociado.")

    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == doc.instrument_unit_id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento canónico vinculado no existe.")

    # 1. Recuperar campos de la zona de staging (extracted_field)
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
    field_dict = {f.field_name: f.normalized_value for f in fields}

    cal_date_str = field_dict.get("calibration_date")
    due_date_str = field_dict.get("next_due_date")
    error_val = float(field_dict.get("error_value", 0.0))
    tolerance_val = float(field_dict.get("tolerance", 0.1))

    if not cal_date_str:
        raise HTTPException(status_code=422, detail="Falta el campo 'calibration_date' en staging.")

    cal_date = datetime.strptime(cal_date_str, "%Y-%m-%d").date()
    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

    # 2. Regla Metrológica R-TOL-01: Evaluación de tolerancia
    is_out_of_tol = abs(error_val) > tolerance_val
    result_status = "out_of_tolerance" if is_out_of_tol else "pass"

    # 3. Transacción Canónica: Crear evento de calibración
    new_calibration = CalibrationEvent(
        instrument_unit_id=instrument.id,
        calibration_date=cal_date,
        error_value=error_val,
        tolerance=tolerance_val,
        result=result_status,
        next_due_date=due_date
    )
    db.add(new_calibration)

    # 4. Actualizar estado operativo del activo en instrument_unit
    instrument.lifecycle_state = "out_of_tolerance" if is_out_of_tol else "operational"

    # 5. Registrar trazabilidad inmutable en audit_log
    audit_entry = AuditLog(
        entity_name="instrument_unit",
        entity_id=instrument.id,
        action="CALIBRATION_INGESTED",
        details={
            "document_id": doc.id,
            "certificate_sha256": doc.sha256_hash,
            "error_value": error_val,
            "tolerance": tolerance_val,
            "result": result_status,
            "previous_state": "operational",
            "new_state": instrument.lifecycle_state
        }
    )
    db.add(audit_entry)

    # Confirmar transacción en PostgreSQL (Source of Truth)
    db.commit()
    db.refresh(new_calibration)
    db.refresh(instrument)

    return {
        "status": "CANONICAL_COMMITTED",
        "calibration_event_id": new_calibration.id,
        "instrument_id": instrument.id,
        "serial_number": instrument.serial_number,
        "lifecycle_state": instrument.lifecycle_state,
        "result": new_calibration.result,
        "next_due_date": new_calibration.next_due_date
    }

@router.get("/{document_id}/fields", summary="Consulta los campos extraídos de un documento")
def get_extracted_fields(
    document_id: int,
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    fields = db.query(ExtractedField).filter(
        ExtractedField.document_id == document_id
    ).order_by(ExtractedField.id).all()

    return {
        "document_id": doc.id,
        "processing_status": doc.processing_status,
        "fields": [
            {
                "field_id": field.id,
                "field_name": field.field_name,
                "raw_value": field.raw_value,
                "normalized_value": field.normalized_value,
                "confidence": field.confidence,
                "validation_status": field.validation_status
            }
            for field in fields
        ]
    }

@router.patch("/{document_id}/fields/{field_id}", summary="Corrige manualmente un campo extraído")
def correct_extracted_field(
    document_id: int,
    field_id: int,
    correction: ExtractedFieldCorrection,
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    field = db.query(ExtractedField).filter(
        ExtractedField.id == field_id,
        ExtractedField.document_id == document_id
    ).first()

    if not field:
        raise HTTPException(
            status_code=404,
            detail="Campo extraído no encontrado para este documento."
        )

    # Human-in-the-loop:
    # raw_value se conserva como evidencia original.
    # normalized_value contiene la corrección humana.
    field.normalized_value = correction.normalized_value

    db.commit()
    db.refresh(field)

    return {
        "field_id": field.id,
        "document_id": field.document_id,
        "field_name": field.field_name,
        "raw_value": field.raw_value,
        "normalized_value": field.normalized_value,
        "validation_status": field.validation_status
    }

@router.post("/{document_id}/revalidate", summary="Revalida un documento después de la revisión humana")
def revalidate_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    fields = db.query(ExtractedField).filter(
        ExtractedField.document_id == document_id
    ).order_by(ExtractedField.id).all()

    if not fields:
        raise HTTPException(
            status_code=422,
            detail="El documento no tiene campos extraídos para revalidar."
        )

    normalized_fields = {
        field.field_name: field.normalized_value
        for field in fields
    }

    target_unit, rules_failed = validate_document_fields(
        db=db,
        fields=normalized_fields
    )

    # Evita conservar un matching anterior si deja de ser válido.
    doc.instrument_unit_id = target_unit.id if target_unit else None

    if len(rules_failed) == 0:
        doc.processing_status = "ACCEPTED"
    else:
        doc.processing_status = "REVIEW_REQUIRED"

    db.commit()
    db.refresh(doc)

    return {
        "document_id": doc.id,
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "rules_failed": rules_failed
    }