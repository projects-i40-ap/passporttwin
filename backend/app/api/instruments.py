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
from decimal import Decimal, InvalidOperation
from fastapi import UploadFile, File
from app.models.document import Document
from app.models.maintenance import Incident, MaintenanceEvent
from app.schemas.maintenance import (
    ERPSyncRecordResult,
    ERPSyncRequest,
    ERPSyncResponse,
    IncidentCreate,
    IncidentResponse,
    MaintenanceEventResponse,
)

import logging

logger = logging.getLogger("passporttwin.instruments")

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

######## Endpoints de Ingesta de Mantenimiento (CSV) y consulta de historial
MAINTENANCE_REQUIRED_COLUMNS = {"serial_number", "event_date", "description"}


def _parse_maintenance_date(value):
    """Normaliza `event_date` del CSV (`YYYY-MM-DD` o ISO 8601) a `date`.

    Devuelve `None` cuando la celda está vacía o no representa una fecha válida,
    de modo que la fila se reporte en `skipped_records` sin romper el lote.
    """
    if value is None:
        return None

    if not isinstance(value, str) and pd.isna(value):
        return None

    try:
        parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    except (TypeError, ValueError):
        return None

    if parsed is None or pd.isna(parsed):
        return None

    return parsed.date()


def _parse_maintenance_cost(value):
    """Convierte `cost_estimate` a `Decimal`, devolviendo `None` si no es válido."""
    if value is None:
        return None

    if not isinstance(value, str) and pd.isna(value):
        return None

    text = str(value).strip().replace(",", ".")
    if not text:
        return None

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


@router.post(
    "/maintenance/upload-csv",
    status_code=status.HTTP_201_CREATED,
    summary="Ingesta de órdenes de mantenimiento vía CSV (R-DUP-01)",
)
async def upload_maintenance_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Ingesta de órdenes de trabajo de mantenimiento (RF-MAINT-02).

    Pipeline:
    1. RAW: calcula el SHA-256 de los bytes crudos y rechaza duplicados
       (HTTP 409, R-DUP-01) antes de persistir cualquier efecto.
    2. RAW STORAGE: guarda el fichero inmutable en
       `/app/storage/raw/{sha256}.csv` y crea el `Document` con
       `source_type="MAINTENANCE_CSV"`.
    3. NORMALIZE & MATCH: parsea con pandas y empareja cada fila con
       `instrument_unit` por `serial_number` exacto. Las filas sin serial
       canónico se reportan en `skipped_records`.
    4. CANONICAL COMMIT: inserta en `maintenance_event` y registra
       `MAINTENANCE_LOGGED` en `audit_log` por cada evento persistido.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="El formato del archivo debe ser estrictamente .csv"
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=400,
            detail="El archivo CSV proporcionado está vacío."
        )

    # 1. Regla de Integridad RAW (R-DUP-01): unicidad del SHA-256.
    file_hash = hashlib.sha256(contents).hexdigest()
    existing_document = (
        db.query(Document)
        .filter(Document.sha256_hash == file_hash)
        .first()
    )
    if existing_document:
        raise HTTPException(
            status_code=409,
            detail=(
                "El fichero ya fue ingerido (R-DUP-01): ya existe el "
                f"documento {existing_document.id} con SHA-256 {file_hash}."
            )
        )

    # 2. Persistencia RAW inmutable + registro de procedencia.
    storage_path = os.path.join(STORAGE_RAW_DIR, f"{file_hash}.csv")
    with open(storage_path, "wb") as f:
        f.write(contents)

    raw_doc = Document(
        original_filename=file.filename,
        file_path=storage_path,
        sha256_hash=file_hash,
        source_type="MAINTENANCE_CSV",
        processing_status="ACCEPTED"
    )
    db.add(raw_doc)
    db.commit()
    db.refresh(raw_doc)

    # 3. Parsing con pandas.
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Error al estructurar el CSV de mantenimiento: {str(e)}"
        )

    if not MAINTENANCE_REQUIRED_COLUMNS.issubset(df.columns):
        missing = MAINTENANCE_REQUIRED_COLUMNS - set(df.columns)
        raise HTTPException(
            status_code=400,
            detail=(
                "Faltan columnas requeridas en la cabecera del CSV: "
                f"{sorted(missing)}"
            )
        )

    logged_events = []
    skipped_records = []

    # 4. Procesamiento fila a fila con matching exacto por serial.
    for idx, row in df.iterrows():
        row_number = idx + 2  # +2: cabecera y base 0 de pandas.

        serial = row["serial_number"]
        serial = "" if serial is None or pd.isna(serial) else str(serial).strip()

        if not serial:
            skipped_records.append({
                "row": row_number,
                "serial_number": None,
                "reason": "La fila no informa de serial_number."
            })
            continue

        instrument = (
            db.query(InstrumentUnit)
            .filter(InstrumentUnit.serial_number == serial)
            .first()
        )
        if not instrument:
            skipped_records.append({
                "row": row_number,
                "serial_number": serial,
                "reason": "El serial_number no existe en instrument_unit."
            })
            continue

        description = row["description"]
        description = (
            "" if description is None or pd.isna(description)
            else str(description).strip()
        )
        if not description:
            skipped_records.append({
                "row": row_number,
                "serial_number": serial,
                "reason": "La fila no informa de description."
            })
            continue

        event_date = _parse_maintenance_date(row["event_date"])
        if event_date is None:
            skipped_records.append({
                "row": row_number,
                "serial_number": serial,
                "reason": "event_date vacía o con formato inválido."
            })
            continue

        cost_estimate = None
        if "cost_estimate" in df.columns:
            cost_estimate = _parse_maintenance_cost(row["cost_estimate"])

        event = MaintenanceEvent(
            instrument_unit_id=instrument.id,
            event_date=event_date,
            description=description,
            cost_estimate=cost_estimate,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        # 5. Trazabilidad inmutable de la intervención.
        AuditService.log_event(
            db=db,
            entity_name="maintenance_event",
            entity_id=event.id,
            action="MAINTENANCE_LOGGED",
            source="api.instruments.maintenance.upload_csv",
            after={
                "instrument_unit_id": instrument.id,
                "event_date": event_date.isoformat(),
                "description": description,
                "cost_estimate": (
                    str(cost_estimate) if cost_estimate is not None else None
                ),
            },
            details={
                "instrument_unit_id": instrument.id,
                "document_id": raw_doc.id,
                "sha256": file_hash,
                "row": row_number,
            },
        )
        db.commit()

        logged_events.append({
            "id": event.id,
            "instrument_unit_id": instrument.id,
            "serial_number": serial,
            "event_date": event_date.isoformat(),
            "description": description,
            "cost_estimate": (
                str(cost_estimate) if cost_estimate is not None else None
            ),
        })

    return {
        "raw_document_id": raw_doc.id,
        "sha256": file_hash,
        "total_rows_evaluated": len(df),
        "total_logged": len(logged_events),
        "logged_events": logged_events,
        "skipped_records": skipped_records,
    }


@router.get(
    "/{id}/maintenance",
    response_model=List[MaintenanceEventResponse],
    summary="Historial cronológico descendente de mantenimiento",
)
def get_instrument_maintenance(id: int, db: Session = Depends(get_db)):
    """Listado de eventos de mantenimiento del instrumento (RF-MAINT-04).

    Devuelve las intervenciones ordenadas de la más reciente a la más antigua
    (`event_date` descendente, desempate por `id` descendente).
    """
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    return (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.instrument_unit_id == id)
        .order_by(MaintenanceEvent.event_date.desc(), MaintenanceEvent.id.desc())
        .all()
    )


######## Adaptador HTTP del ERP simulado e incidencias operativas (RF-MAINT-03/04/05)
ERP_SYNC_FIELDS = ("location", "criticality", "lifecycle_state")


@router.post(
    "/erp-sync",
    response_model=ERPSyncResponse,
    summary="Sincronización del estado operacional desde el ERP simulado",
)
def sync_instruments_from_erp(
    payload: ERPSyncRequest,
    db: Session = Depends(get_db),
):
    """Sincroniza lotes de activos provenientes del ERP simulado (RF-MAINT-03).

    Para cada registro:
    1. Localiza el activo por `serial_number` exacto.
    2. Captura el estado previo (`before`) y aplica los nuevos valores (`after`).
    3. Confirma la transacción canónica en PostgreSQL.
    4. Registra `ERP_SYNCED` en `audit_log` con la evidencia del cambio.
    5. Proyecta de forma resiliente el nuevo estado hacia `OperationalState`
       en Eclipse BaSyx (RF-MAINT-05): si la proyección falla, el activo queda
       con `aas_sync_status="PENDING"` y la respuesta sigue siendo HTTP 200.
    """
    results: List[ERPSyncRecordResult] = []
    updated = 0
    skipped = 0

    for record in payload.records:
        serial = (record.serial_number or "").strip()
        instrument = (
            db.query(InstrumentUnit)
            .filter(InstrumentUnit.serial_number == serial)
            .first()
        )

        if not instrument:
            skipped += 1
            results.append(
                ERPSyncRecordResult(
                    serial_number=serial,
                    status="NOT_FOUND",
                )
            )
            continue

        # 1. Estado previo y aplicación de los valores informados por el ERP.
        before = {
            field: getattr(instrument, field, None)
            for field in ERP_SYNC_FIELDS
        }
        for field in ERP_SYNC_FIELDS:
            new_value = getattr(record, field, None)
            if new_value is not None:
                setattr(instrument, field, new_value)

        after = {
            field: getattr(instrument, field, None)
            for field in ERP_SYNC_FIELDS
        }
        previous_sync_status = getattr(instrument, "aas_sync_status", None)

        # 2. Frontera transaccional: PostgreSQL es la fuente de verdad y se
        #    confirma antes de intentar la proyección interoperable.
        db.commit()

        # 3. Proyección resiliente hacia Eclipse BaSyx (patrón LEGO).
        try:
            projected = AASBuilder.sync_operational_state(instrument)
            sync_status = "SYNCED" if projected else "PENDING"
        except Exception:
            logger.exception(
                "Fallo inesperado proyectando OperationalState del activo %s",
                serial,
            )
            sync_status = "ERROR"

        instrument.aas_sync_status = sync_status

        # 4. Trazabilidad inmutable de la actualización externa (ERP_SYNCED).
        AuditService.log_event(
            db=db,
            entity_name="instrument_unit",
            entity_id=instrument.id,
            action="ERP_SYNCED",
            source="api.instruments.erp_sync",
            before={**before, "aas_sync_status": previous_sync_status},
            after={**after, "aas_sync_status": sync_status},
            details={
                "instrument_unit_id": instrument.id,
                "serial_number": serial,
            },
        )
        db.commit()
        db.refresh(instrument)

        updated += 1
        results.append(
            ERPSyncRecordResult(
                serial_number=serial,
                status="UPDATED",
                before=before,
                after=after,
                aas_sync_status=sync_status,
            )
        )

    return ERPSyncResponse(
        processed=len(payload.records),
        updated=updated,
        skipped=skipped,
        results=results,
    )


@router.post(
    "/{id}/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta directa de una incidencia operativa",
)
def create_instrument_incident(
    id: int,
    payload: IncidentCreate,
    db: Session = Depends(get_db),
):
    """Registra una incidencia operativa con auditoría inmutable (RF-MAINT-04)."""
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    incident = Incident(
        instrument_unit_id=instrument.id,
        incident_date=payload.incident_date,
        description=payload.description,
        severity=str(payload.severity or "LOW").strip().upper(),
        resolved_at=payload.resolved_at,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    AuditService.log_event(
        db=db,
        entity_name="incident",
        entity_id=incident.id,
        action="INCIDENT_LOGGED",
        source="api.instruments.incidents.create",
        after={
            "instrument_unit_id": instrument.id,
            "incident_date": payload.incident_date.isoformat(),
            "description": payload.description,
            "severity": incident.severity,
            "resolved_at": (
                payload.resolved_at.isoformat()
                if payload.resolved_at is not None
                else None
            ),
        },
        details={"instrument_unit_id": instrument.id},
    )
    db.commit()
    db.refresh(incident)

    return incident


@router.get(
    "/{id}/incidents",
    response_model=List[IncidentResponse],
    summary="Historial cronológico descendente de incidencias",
)
def get_instrument_incidents(id: int, db: Session = Depends(get_db)):
    """Listado de incidencias del instrumento (RF-MAINT-04).

    Devuelve las incidencias de la más reciente a la más antigua
    (`incident_date` descendente, desempate por `id` descendente).
    """
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")

    return (
        db.query(Incident)
        .filter(Incident.instrument_unit_id == id)
        .order_by(Incident.incident_date.desc(), Incident.id.desc())
        .all()
    )