import os
import hashlib
import logging
import re
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.database.session import get_db, SessionLocal
from app.models.document import Document
from datetime import date, datetime
from app.models.document import ExtractedField
from app.models.instrument import InstrumentUnit, InstrumentType
from app.services.pdf_extractor import (
    PDFDatasheetExtractor,
    HybridDocumentExtractor,
)
from app.services.document_normalizer import DocumentNormalizer
from app.services.document_classifier import classify_document
from app.models.calibration import CalibrationEvent, AuditLog
from app.schemas.audit import (
    AuditLogEntryResponse,
    DocumentTraceabilityResponse,
)
from app.schemas.document import (
    ExtractedFieldCorrection,
    DocumentQueryRequest,
    DocumentQueryResponse,
    InstrumentTypeFromDocument,
    LinkInstrumentTypeRequest,
)
from app.services.document_validation import validate_document_fields, validation_reference_date
from app.services.rag_service import DocumentRAGService
from app.services.aas_builder import AASBuilder
from app.services.audit_service import AuditService
from app.services.document_identity import SERIAL_CANDIDATES_FIELD
from app.services.document_original import original_response
from app.services.document_materialization import ingestion_event, materialization_state
from app.services.document_field_status import validate_field_states, invalidate_fields, field_states

router = APIRouter(prefix="/documents", tags=["documents"])

logger = logging.getLogger("passporttwin.documents")

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

@router.get("", summary="Busca documentos por nombre, serie o ubicación")
def list_documents(q: str = Query("", max_length=200), review_only: bool = False,
                   limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db)):
    query = db.query(Document, InstrumentUnit.serial_number, InstrumentUnit.location, InstrumentUnit.public_id).outerjoin(
        InstrumentUnit, Document.instrument_unit_id == InstrumentUnit.id)
    if q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(Document.original_filename.ilike(pattern, escape="\\"),
                                 InstrumentUnit.serial_number.ilike(pattern, escape="\\"),
                                 InstrumentUnit.location.ilike(pattern, escape="\\")))
    if review_only:
        query = query.filter(Document.processing_status.in_(["REVIEW_REQUIRED", "FAILED_EXTRACTION"]))
    rows = query.order_by(Document.uploaded_at.desc(), Document.id.desc()).offset(offset).limit(limit + 1).all()
    return {"items": [{"id": doc.id, "original_filename": doc.original_filename,
                       "processing_status": doc.processing_status, "source_type": doc.source_type,
                       "instrument_serial": serial, "location": location,
                       "instrument_public_id": str(public_id) if public_id else None,
                       "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None}
                      for doc, serial, location, public_id in rows[:limit]],
            "offset": offset, "limit": limit, "has_more": len(rows) > limit}


def _remove_raw_file(file_path: str | None) -> None:
    """Borra el RAW solo si está dentro del almacén; nunca propaga errores."""
    if not file_path:
        return

    try:
        absolute = os.path.realpath(file_path)
        storage = os.path.realpath(STORAGE_RAW_DIR)

        if os.path.commonpath([absolute, storage]) != storage:
            logger.warning("Se omite el borrado de un RAW fuera del almacén: %s", file_path)
            return

        if os.path.exists(absolute):
            os.remove(absolute)
    except Exception as exc:  # Disco, permisos o ruta inválida.
        logger.warning("No se pudo borrar el RAW %s: %s", file_path, exc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Elimina un documento no materializado")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Borra un documento de staging y su RAW.

    Un documento materializado sostiene un `calibration_event` y forma parte del
    pasaporte: se rechaza con 409. La decisión se registra en `audit_log` antes
    del borrado, de modo que la traza sobrevive al documento.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    if ingestion_event(db, doc.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "R-DUP-DELETE: El documento sostiene una calibración ya incorporada "
                "al modelo canónico y no puede eliminarse."
            ),
        )

    file_path = doc.file_path
    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=doc.id,
        action="DOCUMENT_DELETED",
        source="api.documents.delete",
        before={
            "document_id": doc.id,
            "original_filename": doc.original_filename,
            "source_type": doc.source_type,
            "processing_status": doc.processing_status,
            "sha256_hash": doc.sha256_hash,
        },
        details={"sha256_hash": doc.sha256_hash, "reason": "user_request"},
    )

    db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).delete()
    db.delete(doc)
    db.commit()

    _remove_raw_file(file_path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _process_queued_document(document_id: int) -> None:
    """Procesa un documento encolado en la subida, con sesión propia.

    La tarea corre después de responder al cliente: una ficha de 92 páginas con
    un modelo local tarda casi un minuto y no debe bloquear la subida.
    """
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or doc.processing_status != "QUEUED":
            return

        try:
            _extract_and_store(db, doc, "auto", validation_reference_date())
        except HTTPException as exc:
            logger.warning("Proceso automático rechazado (%s): %s", document_id, exc.detail)
        except Exception:
            logger.exception("Falló el proceso automático del documento %s", document_id)
            db.rollback()
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.processing_status = "FAILED_EXTRACTION"
                db.commit()
    finally:
        db.close()


@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Ingesta de archivo RAW con hash SHA-256")
async def upload_raw_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = "AUTO",  # AUTO | CERTIFICATE | DATASHEET | CSV
    doc_type_form: str | None = Form(None, alias="doc_type"),
    db: Session = Depends(get_db)
):
    # El tipo puede venir por query (compatibilidad) o por formulario (UI).
    doc_type = (doc_type_form or doc_type or "AUTO").strip().upper()
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
    elif doc_type == "DATASHEET":
        source_type = "PDF_DATASHEET"
    elif doc_type == "CERTIFICATE":
        source_type = "PDF_CERTIFICATE"
    else:
        # T7: en modo automático manda el contenido, no el nombre del archivo.
        source_type = classify_document(storage_path, file.filename or "")

    new_doc = Document(
        original_filename=file.filename,
        file_path=storage_path,
        sha256_hash=file_hash,
        source_type=source_type,
        # Los PDF se encolan: la extracción corre después de responder (T7).
        processing_status="QUEUED" if source_type.startswith("PDF_") else "RECEIVED"
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

    # 5. Cola de extracción (T7): el PDF se procesa solo, sin segundo botón.
    if new_doc.source_type.startswith("PDF_"):
        background.add_task(_process_queued_document, new_doc.id)

    return {
        "document_id": new_doc.id,
        "filename": new_doc.original_filename,
        "source_type": new_doc.source_type,
        "sha256": new_doc.sha256_hash,
        "status": new_doc.processing_status,
        "storage_path": new_doc.file_path
    }

@router.get("/{document_id}/original", summary="Abre o descarga el RAW verificado del documento")
def get_document_original(document_id: int, download: bool = False, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(404, "Documento no encontrado.")
    return original_response(document, STORAGE_RAW_DIR, download)


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
    reference_date: date = Depends(validation_reference_date),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    return _extract_and_store(db, doc, extractor, reference_date)


def _extract_and_store(db: Session, doc: Document, extractor: str, reference_date: date) -> dict:
    """Extrae, valida y persiste un documento.

    Lo comparten el endpoint manual y la cola automática de la subida (T7), de
    modo que ambos caminos aplican exactamente las mismas reglas.
    """
    # 1. Enrutamiento del extractor según la naturaleza documental.
    #    El extractor híbrido (bloque LEGO 1) degrada al determinista ante
    #    cualquier fallo de `llama.cpp` (RF-LEGO-02).
    full_text = ""

    if doc.source_type == "PDF_DATASHEET":
        # Un datasheet define especificaciones de tipo, no de activo individual.
        # Se normaliza a un esquema canónico declarado (RF-DOC-02): el LLM actúa
        # como adaptador de formato con gramática y degrada al determinista.
        normalizer = DocumentNormalizer()
        normalized = normalizer.normalize(doc.file_path, extractor_mode=extractor)
        extracted = normalized["fields"]
        full_text = normalized["full_text"]
        extractor_used = normalized["extractor_used"]
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
        # Reprocessing must discard any previous automatic link before matching again.
        doc.instrument_unit_id = None

    # RF-DOC-03: un documento legible nunca se descarta. Si no hay campos pero sí
    # texto, queda en revisión con el texto indexado para el bloque RAG.
    if not extracted and not full_text:
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

    target_unit = None
    # 3. Reglas y Matching según el tipo de documento
    if doc.source_type == "PDF_DATASHEET":
        # Un datasheet define especificaciones de tipo, no de activo individual.
        # Toda ficha va a la cola de revisión: el LLM propone, el humano confirma
        # (RF-DOC-03). No se ejecutan reglas metrológicas de certificado.
        rules_failed = []
        doc.processing_status = "REVIEW_REQUIRED"
    else:
        target_unit, rules_failed = validate_document_fields(
            db=db,
            fields=extracted,
            reference_date=reference_date,
        )
        if target_unit:
            doc.instrument_unit_id = target_unit.id

        doc.processing_status = "ACCEPTED" if len(rules_failed) == 0 else "REVIEW_REQUIRED"

    stored_fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
    validate_field_states(db, doc, stored_fields, rules_failed, target_unit)
    AuditService.log_event(db=db, entity_name="document", entity_id=doc.id,
        action="DOCUMENT_PROCESSED", source="api.documents.process",
        after={"processing_status": doc.processing_status, "rules_failed": rules_failed,
               "field_validation": field_states(stored_fields)})
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

    if ingestion_event(db, doc.id) is not None:
        raise HTTPException(409, "R-DUP-ACCEPT: El documento ya fue materializado previamente en el modelo canónico.")

    if doc.source_type != "PDF_CERTIFICATE":
        raise HTTPException(400, "Solo los certificados de calibración se incorporan a este historial.")

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

    flush = getattr(db, "flush", None)
    if callable(flush):
        flush()  # Capture the canonical event ID in the same ingestion transaction.

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
            "calibration_event_id": new_calibration.id,
            "instrument_id": instrument.id,
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
    projection_updated = AASBuilder.sync_dynamic_submodels(
        instrument, calibration_history, document_provenance
    )
    if not projection_updated and AASBuilder.shell_is_missing(instrument):
        projection_updated = AASBuilder.sync_shell_and_nameplate(
            instrument, instrument.instrument_type
        ) and AASBuilder.sync_dynamic_submodels(
            instrument, calibration_history, document_provenance
        )
        if projection_updated:
            previous_status = instrument.aas_sync_status
            instrument.aas_sync_status = "SYNCED"
            AuditService.log_event(
                db=db, entity_name="instrument_unit", entity_id=instrument.id,
                action="AAS_SYNCED", source="api.documents.accept",
                before={"aas_sync_status": previous_status},
                after={"aas_sync_status": "SYNCED"},
                details={"document_id": doc.id, "scope": "missing_shell_recovery"},
            )
            db.commit()

    if not projection_updated:
        previous_status = instrument.aas_sync_status
        instrument.aas_sync_status = "ERROR"
        AuditService.log_event(db=db, entity_name="instrument_unit", entity_id=instrument.id,
            action="AAS_SYNC_FAILED", source="api.documents.accept",
            before={"aas_sync_status": previous_status}, after={"aas_sync_status": "ERROR"},
            details={"document_id": doc.id, "scope": "dynamic_submodels"})
        db.commit()

    return {
        "status": "CANONICAL_COMMITTED",
        "aas_projection": {"status": "UPDATED" if projection_updated else "ERROR"},
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
        "original_filename": getattr(doc, "original_filename", None),
        "processing_status": doc.processing_status,
        "source_type": doc.source_type,
        "matched_instrument_id": doc.instrument_unit_id,
        "instrument_type_id": getattr(doc, "instrument_type_id", None),
        "materialization": materialization_state(db, doc),
        "fields": [
            {
                "field_id": field.id,
                "field_name": field.field_name,
                "raw_value": field.raw_value,
                "normalized_value": field.normalized_value,
                "confidence": field.confidence,
                "validation_status": field.validation_status,
                "read_only": field.field_name == SERIAL_CANDIDATES_FIELD,
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

    if field.field_name in (SERIAL_CANDIDATES_FIELD, FULL_TEXT_FIELD):
        raise HTTPException(status_code=400, detail="La evidencia extraída es de solo lectura.")

    # Saving a correction requires revalidation before canonical acceptance.
    doc.processing_status = "REVIEW_REQUIRED"
    if field.field_name == "serial_number":
        doc.instrument_unit_id = None

    # Human-in-the-loop:
    # raw_value se conserva como evidencia original.
    # normalized_value contiene la corrección humana.
    old_normalized_value = field.normalized_value
    field.normalized_value = correction.normalized_value

    related_fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
    invalidate_fields(related_fields)

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
            "field_validation": field_states(related_fields),
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
        "validation_status": field.validation_status,
        "field_validation": field_states(related_fields)
    }

def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return cleaned or "modelo"


@router.post("/{document_id}/create-type", summary="Crea un modelo a partir de una ficha revisada")
def create_type_from_document(
    document_id: int,
    payload: InstrumentTypeFromDocument,
    db: Session = Depends(get_db),
):
    """Convierte una ficha técnica en un `instrument_type` canónico (T9).

    El modelo es el objeto que agrupa a todos los ejemplares: la ficha describe
    el DS18B20, no el sensor con serial 001. Si el fabricante y el modelo ya
    existen, se reutiliza el tipo en lugar de duplicarlo.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    if doc.source_type != "PDF_DATASHEET":
        raise HTTPException(
            status_code=400,
            detail="Solo las fichas técnicas crean modelos de instrumento.",
        )

    fields = {
        field.field_name: field.normalized_value or field.raw_value
        for field in db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
        if field.field_name != FULL_TEXT_FIELD
    }

    manufacturer = (payload.manufacturer or fields.get("manufacturer") or "").strip()
    model = (payload.model or fields.get("model") or "").strip()
    unit = (payload.unit or fields.get("range_unit") or fields.get("unit") or "").strip()
    magnitude = (
        payload.magnitude
        or fields.get("measurement_variable")
        or fields.get("measurement_principle")
        or ""
    ).strip()

    if not model:
        raise HTTPException(
            status_code=422,
            detail="La ficha no declara un modelo. Corrige el campo «model» antes de crear el tipo.",
        )
    if not unit:
        raise HTTPException(
            status_code=422,
            detail="La ficha no declara unidad de medida. Corrige el campo «range_unit» o «unit».",
        )

    existing = None
    if manufacturer:
        existing = (
            db.query(InstrumentType)
            .filter(
                func.lower(InstrumentType.manufacturer) == manufacturer.lower(),
                func.lower(InstrumentType.model) == model.lower(),
            )
            .first()
        )

    if existing:
        instrument_type, created = existing, False
    else:
        name = payload.name or _slug(f"{manufacturer} {model}")
        base_name, suffix = name, 2
        while db.query(InstrumentType).filter(InstrumentType.name == name).first():
            name = f"{base_name}_{suffix}"
            suffix += 1

        instrument_type = InstrumentType(
            name=name,
            magnitude=magnitude or "Unknown",
            unit=unit,
            manufacturer=manufacturer or None,
            model=model,
        )
        db.add(instrument_type)
        db.commit()
        db.refresh(instrument_type)
        created = True

    before_type = getattr(doc, "instrument_type_id", None)
    doc.instrument_type_id = instrument_type.id
    doc.processing_status = "ACCEPTED"

    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=doc.id,
        action="DOCUMENT_TYPE_LINKED",
        source="api.documents.create_type",
        before={"instrument_type_id": before_type},
        after={"instrument_type_id": instrument_type.id, "created": created},
        details={
            "document_id": doc.id,
            "instrument_type_name": instrument_type.name,
            "manufacturer": instrument_type.manufacturer,
            "model": instrument_type.model,
        },
    )
    db.commit()

    return {
        "document_id": doc.id,
        "created": created,
        "instrument_type": {
            "id": instrument_type.id,
            "name": instrument_type.name,
            "magnitude": instrument_type.magnitude,
            "unit": instrument_type.unit,
            "manufacturer": instrument_type.manufacturer,
            "model": instrument_type.model,
        },
    }


@router.patch("/{document_id}/link-type", summary="Asocia una ficha a un modelo existente")
def link_document_type(
    document_id: int,
    payload: LinkInstrumentTypeRequest,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    if doc.source_type != "PDF_DATASHEET":
        raise HTTPException(
            status_code=400,
            detail="Solo las fichas técnicas se asocian a un modelo.",
        )

    instrument_type = (
        db.query(InstrumentType).filter(InstrumentType.id == payload.instrument_type_id).first()
    )
    if not instrument_type:
        raise HTTPException(status_code=404, detail="Tipo de instrumento no encontrado.")

    before_type = getattr(doc, "instrument_type_id", None)
    doc.instrument_type_id = instrument_type.id
    doc.processing_status = "ACCEPTED"

    AuditService.log_event(
        db=db,
        entity_name="document",
        entity_id=doc.id,
        action="DOCUMENT_TYPE_LINKED",
        source="api.documents.link_type",
        before={"instrument_type_id": before_type},
        after={"instrument_type_id": instrument_type.id, "created": False},
        details={"document_id": doc.id, "instrument_type_name": instrument_type.name},
    )
    db.commit()

    return {
        "document_id": doc.id,
        "instrument_type_id": instrument_type.id,
        "instrument_type_name": instrument_type.name,
    }


@router.post("/{document_id}/revalidate", summary="Revalida un documento después de la revisión humana")
def revalidate_document(
    document_id: int,
    db: Session = Depends(get_db),
    reference_date: date = Depends(validation_reference_date),
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

    # Estado previo a la revalidación (RF-AUDIT-03). Se captura antes de mutar
    # el documento para que la auditoría refleje el cambio real.
    before_state = {
        "processing_status": doc.processing_status,
        "matched_instrument_id": doc.instrument_unit_id,
        "rules_failed": getattr(doc, "rules_failed", None),
        "field_validation": field_states(fields),
    }

    if doc.source_type == "PDF_DATASHEET":
        # Una ficha técnica no tiene reglas metrológicas: no hay serial de activo
        # ni fecha de calibración que exigir (RF-DOC-12). La revisión humana
        # confirma los campos y el documento sale de la cola sin matching.
        target_unit, rules_failed = None, []
        doc.instrument_unit_id = None
        doc.processing_status = "ACCEPTED"
    else:
        target_unit, rules_failed = validate_document_fields(
            db=db,
            fields=normalized_fields,
            reference_date=reference_date,
        )

        # Evita conservar un matching anterior si deja de ser válido.
        doc.instrument_unit_id = target_unit.id if target_unit else None

        if len(rules_failed) == 0:
            doc.processing_status = "ACCEPTED"
        else:
            doc.processing_status = "REVIEW_REQUIRED"

    validate_field_states(db, doc, fields, rules_failed, target_unit)

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
            "field_validation": field_states(fields),
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