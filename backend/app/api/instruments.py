from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.models.instrument import InstrumentType, InstrumentUnit
from app.schemas.instrument import (
    InstrumentTypeCreate,
    InstrumentTypeResponse,
    InstrumentUnitCreate,
    InstrumentUnitResponse)
from app.schemas.audit import (
    AuditLogEntryResponse,
    InstrumentTraceabilityResponse,
)
from app.services.aas_builder import AASBuilder
from app.services.audit_service import AuditService

##### LIBRERIAS qr code AND Metabase
import io
import qrcode
from fastapi import Response, status
from fastapi.responses import RedirectResponse
from uuid import UUID

##### Librerias calibration and predictions
from app.models.calibration import AuditLog, CalibrationEvent
from app.services.analytics import DriftAnalyticsService

#### Ingestion masiva de sensores
import io
import os
import hashlib
import pandas as pd
from datetime import datetime
from fastapi import UploadFile, File
from app.models.document import Document

STORAGE_RAW_DIR = os.getenv("STORAGE_RAW_DIR", "/app/storage/raw")
os.makedirs(STORAGE_RAW_DIR, exist_ok=True)

router = APIRouter(prefix="/instruments", tags=["instruments"])

@router.post("/types", response_model=InstrumentTypeResponse, status_code=status.HTTP_201_CREATED)
def create_instrument_type(payload: InstrumentTypeCreate, db: Session = Depends(get_db)):
    existing = db.query(InstrumentType).filter(InstrumentType.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="El tipo de instrumento ya existe.")
    new_type = InstrumentType(**payload.model_dump())
    db.add(new_type)
    db.commit()
    db.refresh(new_type)
    return new_type

@router.get("/types", response_model=List[InstrumentTypeResponse])
def list_instrument_types(db: Session = Depends(get_db)):
    return db.query(InstrumentType).all()

@router.post("", response_model=InstrumentUnitResponse, status_code=status.HTTP_201_CREATED)
def register_instrument(payload: InstrumentUnitCreate, db: Session = Depends(get_db)):
    # 1. Comprobar unicidad de serial
    if db.query(InstrumentUnit).filter(InstrumentUnit.serial_number == payload.serial_number).first():
        raise HTTPException(status_code=400, detail="El número de serie ya está registrado.")

    # 2. Comprobar existencia de tipo
    inst_type = db.query(InstrumentType).filter(InstrumentType.id == payload.instrument_type_id).first()
    if not inst_type:
        raise HTTPException(status_code=404, detail="Tipo de instrumento no encontrado.")

    # 3. Persistencia Canónica Operacional
    new_instrument = InstrumentUnit(**payload.model_dump())
    db.add(new_instrument)
    db.commit()
    db.refresh(new_instrument)

    # 4. Proyección Interoperable AAS (Southbound sync)
    nameplate_synced = AASBuilder.sync_shell_and_nameplate(new_instrument, inst_type)
    operational_synced = AASBuilder.sync_operational_state(new_instrument)
    synced = nameplate_synced and operational_synced

    new_instrument.aas_sync_status = "SYNCED" if synced else "PENDING"

    # 5. Trazabilidad del alta del activo (RF-AUDIT-04).
    AuditService.log_event(
        db=db,
        entity_name="instrument_unit",
        entity_id=new_instrument.id,
        action="INSTRUMENT_CREATED",
        source="api.instruments.create",
        after={
            "serial_number": new_instrument.serial_number,
            "lifecycle_state": new_instrument.lifecycle_state,
            "aas_sync_status": new_instrument.aas_sync_status,
        },
        details={"instrument_unit_id": new_instrument.id},
    )

    db.commit()
    db.refresh(new_instrument)

    return new_instrument

@router.get("", response_model=List[InstrumentUnitResponse])
def list_instruments(db: Session = Depends(get_db)):
    return db.query(InstrumentUnit).all()

@router.get("/{id}", response_model=InstrumentUnitResponse)
def get_instrument_by_id(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    return instrument

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

@router.get(
    "/{id}/audit",
    response_model=InstrumentTraceabilityResponse,
    summary="Trazabilidad de auditoría del instrumento y sus documentos",
)
def get_instrument_audit(id: int, db: Session = Depends(get_db)):
    """Árbol de trazabilidad del activo (RF-AUDIT-06).

    Agrega los eventos del propio instrumento, de sus documentos vinculados y
    de sus calibraciones canónicas, ordenados descendentemente por `created_at`.
    """
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    # Documentos y calibraciones directamente asociados al activo. El filtro
    # en Python mantiene el comportamiento con los `FakeSession` de los tests.
    documents = [
        document
        for document in db.query(Document).filter(
            Document.instrument_unit_id == id
        ).all()
        if getattr(document, "instrument_unit_id", None) == id
    ]
    document_ids = {document.id for document in documents}

    calibrations = [
        calibration
        for calibration in db.query(CalibrationEvent).filter(
            CalibrationEvent.instrument_unit_id == id
        ).all()
        if getattr(calibration, "instrument_unit_id", None) == id
    ]
    calibration_ids = {calibration.id for calibration in calibrations}

    audit_entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_name.in_(
                ("instrument_unit", "document", "calibration_event")
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

        belongs_to_instrument = (
            (entity_name == "instrument_unit" and entity_id == id)
            or (
                entity_name == "document"
                and (
                    entity_id in document_ids
                    or details.get("document_id") in document_ids
                )
            )
            or (
                entity_name == "calibration_event"
                and entity_id in calibration_ids
            )
            or details.get("instrument_unit_id") == id
        )

        if belongs_to_instrument:
            events.append(_serialize_audit_entry(entry))

    return InstrumentTraceabilityResponse(
        instrument_id=instrument.id,
        serial_number=getattr(instrument, "serial_number", None),
        total_events=len(events),
        events=events,
    )

@router.post("/{id}/sync", response_model=InstrumentUnitResponse)
def force_sync_aas(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    inst_type = (
        db.query(InstrumentType)
        .filter(InstrumentType.id == instrument.instrument_type_id)
        .first()
    )

    calibration_history = (
        db.query(CalibrationEvent)
        .filter(CalibrationEvent.instrument_unit_id == instrument.id)
        .order_by(CalibrationEvent.id.asc())
        .all()
    )

    document_provenance = (
        db.query(Document)
        .filter(
            Document.instrument_unit_id == instrument.id,
            Document.processing_status == "ACCEPTED"
        )
        .order_by(Document.id.asc())
        .all()
    )

    nameplate_synced = AASBuilder.sync_shell_and_nameplate(
        instrument,
        inst_type
    )

    calibration_synced = AASBuilder.sync_calibration_submodel(
        instrument,
        calibration_history
    )

    document_provenance_synced = AASBuilder.sync_document_provenance(
        instrument,
        document_provenance
    )

    operational_synced = AASBuilder.sync_operational_state(
        instrument
    )

    synced = (
        nameplate_synced
        and calibration_synced
        and document_provenance_synced
        and operational_synced
    )

    previous_sync_status = instrument.aas_sync_status
    instrument.aas_sync_status = "SYNCED" if synced else "ERROR"

    # Trazabilidad de la sincronización AAS (RF-AUDIT-05).
    AuditService.log_event(
        db=db,
        entity_name="instrument_unit",
        entity_id=instrument.id,
        action="AAS_SYNCED",
        source="api.instruments.sync",
        before={"aas_sync_status": previous_sync_status},
        after={"aas_sync_status": instrument.aas_sync_status},
        details={"instrument_unit_id": instrument.id},
    )

    db.commit()
    db.refresh(instrument)
    return instrument

######## QR y Metabase endpoints
@router.get("/{public_id}/qr", summary="Genera la imagen QR física del pasaporte")
def get_instrument_qr(public_id: UUID, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.public_id == public_id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    # URL canónica estable según arquitectura ADR-009 y Sección 3.5
    passport_url = f"http://localhost:8000/api/v1/instruments/passport/{public_id}"

    # Generación matricial del código QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(passport_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(content=buf.getvalue(), media_type="image/png")

@router.get("/passport/{public_id}", tags=["passport"], summary="Punto de resolución canónica del QR")
def resolve_passport(public_id: UUID, db: Session = Depends(get_db)):
    """Punto de entrada al escanear el QR: resuelve el activo y redirige a la vista de pasaporte."""
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.public_id == public_id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Pasaporte no encontrado para el identificador escaneado.")

    # Redirige a la tarjeta del pasaporte en Metabase pasando el parámetro public_id
    metabase_dashboard_url = f"http://localhost:3003/question/1?public_id={public_id}"
    return RedirectResponse(url=metabase_dashboard_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

####### Endpoints de Calibración y Predicciones
@router.get("/{id}/calibrations", summary="Historial de calibraciones del instrumento")
def get_instrument_calibrations(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    return (
        db.query(CalibrationEvent)
        .filter(CalibrationEvent.instrument_unit_id == id)
        .order_by(CalibrationEvent.calibration_date.asc())
        .all()
    )

@router.get("/{id}/predictions", summary="Predicción de deriva, riesgo 30/60/90 y Health Score")
def get_instrument_predictions(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()

    if not instrument:
        raise HTTPException(
            status_code=404,
            detail="Instrumento no encontrado."
        )

    # Historial del activo objetivo para B0 y M1.
    calibrations = (
        db.query(CalibrationEvent)
        .filter(
            CalibrationEvent.instrument_unit_id == instrument.id
        )
        .order_by(
            CalibrationEvent.calibration_date.asc()
        )
        .all()
    )

    # Instrumentos pertenecientes a la misma familia/tipo.
    family_instrument_ids = [
        instrument_id
        for (instrument_id,) in (
            db.query(InstrumentUnit.id)
            .filter(
                InstrumentUnit.instrument_type_id
                == instrument.instrument_type_id
            )
            .all()
        )
    ]

    # Historial agregado de la familia para calcular B1.
    family_calibrations = []

    if family_instrument_ids:
        family_calibrations = (
            db.query(CalibrationEvent)
            .filter(
                CalibrationEvent.instrument_unit_id.in_(
                    family_instrument_ids
                )
            )
            .order_by(
                CalibrationEvent.instrument_unit_id.asc(),
                CalibrationEvent.calibration_date.asc()
            )
            .all()
        )

    return DriftAnalyticsService.calculate_drift_and_risk(
        instrument=instrument,
        calibrations=calibrations,
        family_calibrations=family_calibrations,
    )

######## Endpoints de Ingesta Masiva de Documentos CSV
@router.post("/upload-csv", status_code=status.HTTP_201_CREATED, summary="Ingesta masiva de inventario de flota vía CSV")
async def upload_instruments_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Pipeline canónico de importación de flota:
    1. RAW: Persiste el archivo inmutable byte a byte con hash SHA-256.
    2. NORMALIZE & VALIDATE: Parsea mediante pandas y verifica integridad fila a fila.
    3. CANONICAL COMMIT: Inserta en instrument_unit con public_id.
    4. AAS PROJECTION: Proyecta la Shell, Nameplate y OperationalState hacia Eclipse BaSyx.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="El formato del archivo debe ser estrictamente .csv")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo CSV proporcionado está vacío.")

    # 1. Regla de Integridad RAW (R-DUP-01): Cómputo SHA-256
    file_hash = hashlib.sha256(contents).hexdigest()
    storage_path = os.path.join(STORAGE_RAW_DIR, f"{file_hash}.csv")
    with open(storage_path, "wb") as f:
        f.write(contents)

    # Registrar procedencia RAW inmutable
    raw_doc = db.query(Document).filter(Document.sha256_hash == file_hash).first()
    if not raw_doc:
        raw_doc = Document(
            original_filename=file.filename,
            file_path=storage_path,
            sha256_hash=file_hash,
            source_type="INVENTORY_CSV",
            processing_status="ACCEPTED"
        )
        db.add(raw_doc)
        db.commit()
        db.refresh(raw_doc)

    # 2. Parsing con pandas
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al estructurar el CSV: {str(e)}")

    required_columns = {"serial_number", "type_name", "manufacturer", "model"}
    if not required_columns.issubset(df.columns):
        missing = required_columns - set(df.columns)
        raise HTTPException(
            status_code=400,
            detail=f"Faltan columnas requeridas en la cabecera del CSV: {list(missing)}"
        )

    created_instruments = []
    skipped_records = []

    # Cache de tipos de instrumentos para optimizar consultas en memoria
    type_cache = {t.name: t for t in db.query(InstrumentType).all()}

    # 3. Procesamiento fila a fila
    for idx, row in df.iterrows():
        serial = str(row["serial_number"]).strip()
        type_str = str(row["type_name"]).strip()

        # Validación: unicidad de serial
        if db.query(InstrumentUnit).filter(InstrumentUnit.serial_number == serial).first():
            skipped_records.append({
                "row": idx + 2,
                "serial_number": serial,
                "reason": "Número de serie ya registrado en la base de datos."
            })
            continue

        # Validación: existencia del tipo metrológico
        inst_type = type_cache.get(type_str)
        if not inst_type:
            skipped_records.append({
                "row": idx + 2,
                "serial_number": serial,
                "reason": f"El tipo '{type_str}' no existe en el catálogo canónico (instrument_type)."
            })
            continue

        # Normalización de fecha de instalación
        install_date = None
        if "installed_at" in row and pd.notna(row["installed_at"]):
            try:
                install_date = datetime.strptime(str(row["installed_at"]).strip(), "%Y-%m-%d").date()
            except ValueError:
                install_date = None

        new_unit = InstrumentUnit(
            instrument_type_id=inst_type.id,
            serial_number=serial,
            manufacturer=str(row["manufacturer"]).strip(),
            model=str(row["model"]).strip(),
            location=str(row.get("location", "Main Plant / Unassigned")).strip(),
            criticality=str(row.get("criticality", "MEDIUM")).strip().upper(),
            installed_at=install_date,
            lifecycle_state="operational",
            aas_sync_status="PENDING"
        )
        db.add(new_unit)
        db.commit()
        db.refresh(new_unit)

        # 4. Proyección Interoperable hacia Eclipse BaSyx
        nameplate_synced = AASBuilder.sync_shell_and_nameplate(new_unit, inst_type)
        operational_synced = AASBuilder.sync_operational_state(new_unit)
        synced = nameplate_synced and operational_synced

        new_unit.aas_sync_status = "SYNCED" if synced else "PENDING"
        db.commit()
        db.refresh(new_unit)

        created_instruments.append({
            "id": new_unit.id,
            "public_id": str(new_unit.public_id),
            "serial_number": new_unit.serial_number,
            "manufacturer": new_unit.manufacturer,
            "model": new_unit.model,
            "aas_sync_status": new_unit.aas_sync_status
        })

    return {
        "raw_document_id": raw_doc.id,
        "sha256": raw_doc.sha256_hash,
        "total_rows_evaluated": len(df),
        "total_created": len(created_instruments),
        "created_instruments": created_instruments,
        "skipped_records": skipped_records
    }