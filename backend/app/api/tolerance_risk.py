from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.calibration import CalibrationEvent
from app.models.instrument import InstrumentUnit
from app.services.lifecycle_health import risk_after_maintenance
from app.models.maintenance import MaintenanceEvent

router = APIRouter(prefix="/instruments", tags=["risk"])


@router.get("/{instrument_id}/tolerance-risk", summary="Riesgo experimental a 30/60/90 días")
def get_tolerance_risk(
    instrument_id: int, as_of: date | None = None, db: Session = Depends(get_db),
):
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    reference_date = as_of if as_of is not None else date.today()
    history = db.query(CalibrationEvent).filter(
        CalibrationEvent.instrument_unit_id == instrument_id,
        CalibrationEvent.calibration_date <= reference_date,
    ).all()
    return {
        "instrument_id": instrument.id,
        "serial_number": instrument.serial_number,
        **risk_after_maintenance(history, db.query(MaintenanceEvent).filter(
            MaintenanceEvent.instrument_unit_id == instrument_id,
            MaintenanceEvent.event_date <= reference_date,
        ).all(), reference_date),
    }
