from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.instrument import InstrumentUnit
from app.services.analytics_snapshots import create_snapshot

router = APIRouter(prefix="/instruments", tags=["analytics snapshots"])


@router.post("/{instrument_id}/analytics-snapshots", status_code=201)
def refresh_snapshot(instrument_id: int, as_of: date | None = None, db: Session = Depends(get_db)):
    reference = as_of or date.today()
    if reference > date.today():
        raise HTTPException(status_code=422, detail="La fecha de referencia no puede ser futura.")
    instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == instrument_id).first()
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado.")
    result = create_snapshot(db, instrument, reference)
    return {"snapshot_id": result.id, "instrument_id": result.instrument_unit_id,
            "as_of": result.as_of, "computed_at": result.computed_at,
            "input_hash": result.input_hash, "weights": result.weights,
            "score_method_version": result.score_method_version,
            "risk_method_version": result.risk_method_version,
            "score_status": result.score_status, "risk_status": result.risk_status,
            "health_score": result.health_score,
            "score_result": result.score_result, "risk_result": result.risk_result}
