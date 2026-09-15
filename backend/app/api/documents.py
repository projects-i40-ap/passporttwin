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
    
    # 3. Matching Determinista por Serial Number (Regla primaria)
    matched_serial = extracted.get("serial_number")
    target_unit = None
    if matched_serial:
        target_unit = db.query(InstrumentUnit).filter(InstrumentUnit.serial_number == matched_serial).first()

    # 4. Motor de Reglas y Calidad de Datos (R-ID-01, R-DATE-01, R-DATE-02)
    rules_failed = []
    
    # Regla R-ID-01: Concordancia de activo
    if not target_unit:
        rules_failed.append("R-ID-01: Serial no coincide con ningún activo canónico registrado.")
    else:
        doc.instrument_unit_id = target_unit.id

    # Reglas R-DATE-01 y R-DATE-02: Coherencia temporal
    cal_date_str = extracted.get("calibration_date")
    due_date_str = extracted.get("next_due_date")

    if cal_date_str:
        cal_date = datetime.strptime(cal_date_str, "%Y-%m-%d").date()
        if cal_date > datetime.utcnow().date():
            rules_failed.append("R-DATE-01: La fecha de calibración es futura.")
        
        if due_date_str:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            if due_date <= cal_date:
                rules_failed.append("R-DATE-02: La fecha de vencimiento es anterior o igual a la de calibración.")

    # 5. Determinación de Estado Canónico
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