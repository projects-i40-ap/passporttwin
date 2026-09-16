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
from app.services.aas_builder import AASBuilder

##### LIBRERIAS qr code AND Metabase
import io
import qrcode
from fastapi import Response, status
from fastapi.responses import RedirectResponse
from uuid import UUID

##### Librerias calibration and predictions
from app.models.calibration import CalibrationEvent
from app.services.analytics import DriftAnalyticsService

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
    synced = AASBuilder.sync_shell_and_nameplate(new_instrument, inst_type)
    new_instrument.aas_sync_status = "SYNCED" if synced else "PENDING"
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

@router.post("/{id}/sync", response_model=InstrumentUnitResponse)
def force_sync_aas(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    
    inst_type = db.query(InstrumentType).filter(InstrumentType.id == instrument.instrument_type_id).first()
    synced = AASBuilder.sync_shell_and_nameplate(instrument, inst_type)
    instrument.aas_sync_status = "SYNCED" if synced else "ERROR"
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

@router.get("/{id}/calibrations", summary="Historial de calibraciones del instrumento")
def get_instrument_calibrations(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    return db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == id).order_by(CalibrationEvent.calibration_date.asc()).all()

@router.get("/{id}/predictions", summary="Predicción de deriva, riesgo 30/60/90 y Health Score")
def get_instrument_predictions(id: int, db: Session = Depends(get_db)):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    cals = db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == id).all()
    return DriftAnalyticsService.calculate_drift_and_risk(instrument, cals)