from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.database.session import get_db
from app.models.instrument import InstrumentUnit
from app.services.health_context import load_context
from app.services.lifecycle_health import calculate_lifecycle_health

router=APIRouter(prefix='/instruments',tags=['lifecycle health'])


@router.get('/{instrument_id}/health-score')
def get_lifecycle_health(instrument_id:int,as_of:date|None=None,db:Session=Depends(get_db)):
    reference=as_of or date.today()
    if reference>date.today(): raise HTTPException(422,'La fecha no puede ser futura.')
    instrument=db.query(InstrumentUnit).filter(InstrumentUnit.id==instrument_id).first()
    if instrument is None: raise HTTPException(404,'Instrumento no encontrado.')
    return {'instrument_id':instrument.id,**calculate_lifecycle_health(instrument,
        as_of=reference,weights=settings.lifecycle_health_weights,**load_context(db,instrument.id,reference))}
