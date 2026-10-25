import os
import hashlib
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.document import Document
from datetime import datetime
from app.models.document import ExtractedField
from app.models.instrument import InstrumentUnit
from app.services.pdf_extractor import (
    PDFDatasheetExtractor,
    HybridDocumentExtractor,
)
from app.models.calibration import CalibrationEvent, AuditLog
from app.schemas.audit import (
    AuditLogEntryResponse,
    DocumentTraceabilityResponse,
)
from app.schemas.document import (
    ExtractedFieldCorrection,
    DocumentQueryRequest,
    DocumentQueryResponse,
)
from app.services.document_validation import validate_document_fields
from app.services.rag_service import DocumentRAGService
from app.services.aas_builder import AASBuilder
from app.services.audit_service import AuditService

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_RAW_DIR = os.getenv("STORAGE_RAW_DIR", "/app/storage/raw")
os.makedirs(STORAGE_RAW_DIR, exist_ok=True)

# Campo interno de staging que almacena el texto limpio para el bloque RAG
# (RF-RAG-01). Nunca se expone en las respuestas de edición humana.
FULL_TEXT_FIELD = "__full_text__"

def _normalize_audit_timestamp(value):
    """Normaliza `created_at` para ordenar de forma segura (naive/aware)."""
    if value is None:
        return datetime.min
    if getattr(value, "tzinfo", None) is not None:
        return value.replace(tzinfo=None)
    return value

def _sort_audit_entries_desc(entries):
    """Ordena los eventos de auditoría del más reciente al más antiguo."""
    return sorted(
        entries,
        key=lambda entry: (
            _normalize_audit_timestamp(getattr(entry, "created_at", None)),
            getattr(entry, "id", 0) or 0,
        ),
        reverse=True,
    )

def _serialize_audit_entry(entry):
    """Adapta una fila de `audit_log` (ORM o fake) al schema de respuesta."""
    details = getattr(entry, "details", None)

    return AuditLogEntryResponse(
        id=getattr(entry, "id", 0),
        entity_name=getattr(entry, "entity_name", ""),
        entity_id=getattr(entry, "entity_id", 0),
        action=getattr(entry, "action", ""),
        details=dict(details) if isinstance(details, dict) else {},
        created_at=getattr(entry, "created_at", None),
    )

@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Ingesta de archivo RAW con hash SHA-256")
async def upload_raw_document(
    file: UploadFile = File(...),
    doc_type: str = "AUTO",  # AUTO | CERTIFICATE | DATASHEET | CSV
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
    file_extension = os.path.splitext(file.filename)[1].lower()
    storage_path = os.path.join(STORAGE_RAW_DIR, f"{file_hash}{file_extension}")
    
    with open(storage_path, "wb") as f:
        f.write(contents)

    # 3. Clasificación de procedencia documental (Provenance)
    if file_extension == ".csv":
        source_type = "INVENTORY_CSV"
    elif doc_type == "DATASHEET" or "datasheet" in file.filename.lower():
        source_type = "PDF_DATASHEET"
    else:
        source_type = "PDF_CERTIFICATE"

    new_doc = Document(
        original_filename=file.filename,
        file_path=storage_path,
        sha256_hash=file_hash,
        source_type=source_type,
        processing_status="RECEIVED"
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # 4. Trazabilidad de la ingesta RAW (RF-AUDIT-04): el hash SHA-256 queda
    #    como evidencia inmutable del byte a byte almacenado.
    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=new_doc.id,
        action="DOCUMENT_UPLOADED",
        source="api.documents.upload",
        details={
            "document_id": new_doc.id,
            "original_filename": new_doc.original_filename,
            "source_type": new_doc.source_type,
            "processing_status": new_doc.processing_status,
        },
        metadata={"sha256": new_doc.sha256_hash},
    )
    db.commit()

    return {
        "document_id": new_doc.id,
        "filename": new_doc.original_filename,
        "source_type": new_doc.source_type,
        "sha256": new_doc.sha256_hash,
        "status": new_doc.processing_status,
        "storage_path": new_doc.file_path
    }

@router.post(
    "/query",
    response_model=DocumentQueryResponse,
    summary="Consulta RAG documental sobre PostgreSQL (RF-RAG-02 / RF-RAG-03)",
)
def query_documents(
    payload: DocumentQueryRequest,
    db: Session = Depends(get_db),
):
    # Bloque LEGO 2: retrieval 100% SQL + generación opcional vía `llama.cpp`.
    # Si el servidor de inferencia está apagado, degrada a OFFLINE_RETRIEVAL_ONLY
    # sin lanzar excepción (RF-RAG-03).
    service = DocumentRAGService()

    return service.query_documents(
        db=db,
        question=payload.question,
        serial_number=payload.serial_number,
        document_id=payload.document_id,
        top_k=payload.top_k,
        use_llm=payload.use_llm,
    )


@router.post("/{document_id}/process", summary="Ejecuta Extracción, Matching y Motor de Reglas")
def process_document(
    document_id: int,
    extractor: str = "auto",
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    # 1. Enrutamiento del extractor según la naturaleza documental.
    #    El extractor híbrido (bloque LEGO 1) degrada al determinista ante
    #    cualquier fallo de `llama.cpp` (RF-LEGO-02).
    full_text = ""

    if doc.source_type == "PDF_DATASHEET":
        # Un datasheet define especificaciones de tipo, no de activo individual.
        extracted = PDFDatasheetExtractor.extract_technical_data(doc.file_path)
        extractor_used = "datasheet_deterministic"
    else:
        hybrid_extractor = HybridDocumentExtractor()
        parsed = hybrid_extractor.extract_and_parse(
            doc.file_path,
            extractor_mode=extractor,
            include_full_text=True,
        )
        extractor_used = parsed.pop("extractor_used", "deterministic")
        full_text = parsed.pop(FULL_TEXT_FIELD, "")
        extracted = parsed

    if not extracted:
        doc.processing_status = "FAILED_EXTRACTION"
        db.commit()
        raise HTTPException(status_code=422, detail="No se pudieron extraer campos estructurados del PDF.")

    # 2. Persistencia idempotente en Zona de Staging (extracted_field)
    db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).delete()

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

    # Texto limpio indexado para el bloque RAG (RF-RAG-01). Se conserva en
    # staging pero queda excluido de la vista de edición humana.
    if full_text:
        db.add(
            ExtractedField(
                document_id=doc.id,
                field_name=FULL_TEXT_FIELD,
                raw_value=full_text,
                normalized_value=full_text,
                confidence="1.0",
                validation_status="STAGING",
            )
        )

    # 3. Reglas y Matching según el tipo de documento
    if doc.source_type == "PDF_DATASHEET":
        # Un datasheet define especificaciones de tipo, no de activo individual
        rules_failed = []
        doc.processing_status = "ACCEPTED"
    else:
        target_unit, rules_failed = validate_document_fields(
            db=db,
            fields=extracted
        )
        if target_unit:
            doc.instrument_unit_id = target_unit.id

        doc.processing_status = "ACCEPTED" if len(rules_failed) == 0 else "REVIEW_REQUIRED"

    db.commit()
    db.refresh(doc)

    return {
        "document_id": doc.id,
        "source_type": doc.source_type,
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "extracted_fields": extracted,
        "rules_failed": rules_failed,
        "extractor_used": extractor_used
    }

@router.post("/{document_id}/accept", summary="Materializa campos aceptados en el Modelo Canónico y AAS")
def accept_document_to_canonical(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    # R-DUP-ACCEPT (RF-RULE-04): idempotencia de la materialización.
    # Se recorre la auditoría de la sesión (compatible con SQLAlchemy y con los
    # `FakeSession` de los tests) para detectar una ingesta previa del documento.
    for audit_entry in db.query(AuditLog).filter(
        AuditLog.action == "CALIBRATION_INGESTED"
    ).all():
        details = getattr(audit_entry, "details", None) or {}

        if (
            getattr(audit_entry, "action", None) == "CALIBRATION_INGESTED"
            and details.get("document_id") == doc.id
        ):
            raise HTTPException(
                status_code=409,
                detail="R-DUP-ACCEPT: El documento ya fue materializado previamente en el modelo canónico."
            )

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
    previous_lifecycle_state = instrument.lifecycle_state
    instrument.lifecycle_state = "out_of_tolerance" if is_out_of_tol else "operational"

    # 5. Registrar trazabilidad inmutable en audit_log (RF-AUDIT-07). El
    #    `details.document_id` es la clave que consume R-DUP-ACCEPT.
    AuditService.log_event(
        db=db,
        entity_name="instrument_unit",
        entity_id=instrument.id,
        action="CALIBRATION_INGESTED",
        source="api.documents.accept",
        before={"lifecycle_state": previous_lifecycle_state},
        after={"lifecycle_state": instrument.lifecycle_state},
        details={
            "document_id": doc.id,
            "certificate_sha256": doc.sha256_hash,
            "error_value": error_val,
            "tolerance": tolerance_val,
            "result": result_status,
        },
    )

    # 6. Confirmar transacción en PostgreSQL (Source of Truth)
    db.commit()
    db.refresh(new_calibration)
    db.refresh(instrument)

    # 7. Recuperar el historial canónico completo del instrumento.
    calibration_history = (
        db.query(CalibrationEvent)
        .filter(CalibrationEvent.instrument_unit_id == instrument.id)
        .order_by(CalibrationEvent.id.asc())
        .all()
    )

    # 8. Recuperar la procedencia documental aceptada del instrumento.
    document_provenance = (
        db.query(Document)
        .filter(
            Document.instrument_unit_id == instrument.id,
            Document.processing_status == "ACCEPTED"
        )
        .order_by(Document.id.asc())
        .all()
    )

    # 9. Proyectar los submodelos dinámicos hacia Eclipse BaSyx.
    # PostgreSQL sigue siendo Source of Truth aunque la proyección AAS falle.
    AASBuilder.sync_calibration_submodel(
        instrument,
        calibration_history
    )

    AASBuilder.sync_document_provenance(
        instrument,
        document_provenance
    )

    AASBuilder.sync_operational_state(
        instrument
    )

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

    # El texto limpio para RAG (`__full_text__`) nunca se expone en la edición.
    visible_fields = [field for field in fields if field.field_name != FULL_TEXT_FIELD]

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
            for field in visible_fields
        ]
    }

@router.get(
    "/{document_id}/audit",
    response_model=DocumentTraceabilityResponse,
    summary="Trazabilidad de auditoría del documento y sus campos extraídos",
)
def get_document_audit(document_id: int, db: Session = Depends(get_db)):
    """Árbol de trazabilidad documental (RF-AUDIT-06).

    Recupera los eventos del documento y de sus campos extraídos, incluyendo
    las mutaciones canónicas que referencian el documento vía
    `details->>'document_id'`, ordenados descendentemente por `created_at`.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    fields = [
        field
        for field in db.query(ExtractedField).filter(
            ExtractedField.document_id == document_id
        ).all()
        if getattr(field, "document_id", None) == document_id
    ]
    field_ids = {field.id for field in fields}

    audit_entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_name.in_(
                ("document", "extracted_field", "instrument_unit")
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )

    events = []

    for entry in _sort_audit_entries_desc(audit_entries):
        entity_name = getattr(entry, "entity_name", None)
        entity_id = getattr(entry, "entity_id", None)
        details = getattr(entry, "details", None)
        details = details if isinstance(details, dict) else {}

        belongs_to_document = (
            (entity_name == "document" and entity_id == document_id)
            or (entity_name == "extracted_field" and entity_id in field_ids)
            or details.get("document_id") == document_id
        )

        if belongs_to_document:
            events.append(_serialize_audit_entry(entry))

    return DocumentTraceabilityResponse(
        document_id=doc.id,
        original_filename=getattr(doc, "original_filename", None),
        sha256_hash=getattr(doc, "sha256_hash", None),
        processing_status=getattr(doc, "processing_status", None),
        total_events=len(events),
        events=events,
    )

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
    old_normalized_value = field.normalized_value
    field.normalized_value = correction.normalized_value

    # Trazabilidad del diferencial de la corrección (RF-AUDIT-02).
    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=doc.id,
        action="FIELD_CORRECTED",
        source="api.documents.correct_field",
        before={"normalized_value": old_normalized_value},
        after={"normalized_value": field.normalized_value},
        details={
            "document_id": doc.id,
            "field_id": field.id,
            "field_name": field.field_name,
        },
    )

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

    # El texto limpio para RAG no participa en la validación metrológica.
    fields = [field for field in fields if field.field_name != FULL_TEXT_FIELD]

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

    # Estado previo a la revalidación (RF-AUDIT-03).
    before_state = {
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "rules_failed": getattr(doc, "rules_failed", None),
    }

    # Evita conservar un matching anterior si deja de ser válido.
    doc.instrument_unit_id = target_unit.id if target_unit else None

    if len(rules_failed) == 0:
        doc.processing_status = "ACCEPTED"
    else:
        doc.processing_status = "REVIEW_REQUIRED"

    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=doc.id,
        action="DOCUMENT_REVALIDATED",
        source="api.documents.revalidate",
        before=before_state,
        after={
            "processing_status": doc.processing_status,
            "matched_instrument_id": doc.instrument_unit_id,
            "rules_failed": rules_failed,
        },
        details={"document_id": doc.id},
    )

    db.commit()
    db.refresh(doc)

    return {
        "document_id": doc.id,
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "rules_failed": rules_failed
    }