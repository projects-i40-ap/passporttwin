from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.instrument import InstrumentUnit,InstrumentType
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.services.health_context import load_context
from app.services.analytics_snapshots import build_manifest

router=APIRouter(prefix='/instruments',tags=['passport'])


@router.get('/{instrument_id}/passport-context')
def passport_context(instrument_id:int,db:Session=Depends(get_db)):
    instrument=db.query(InstrumentUnit).filter(InstrumentUnit.id==instrument_id).first()
    if instrument is None:raise HTTPException(404,'Instrumento no encontrado.')
    family=db.query(InstrumentType).filter(InstrumentType.id==instrument.instrument_type_id).first()
    today=date.today();context=load_context(db,instrument.id,today)
    snapshot=db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.instrument_unit_id==instrument.id,
        AnalyticsSnapshot.as_of<=today).order_by(AnalyticsSnapshot.as_of.desc(),AnalyticsSnapshot.computed_at.desc(),AnalyticsSnapshot.id.desc()).first()
    saved={'status':'MISSING','computed_at':None,'as_of':None}
    if snapshot:
        manifest=build_manifest(instrument,load_context(db,instrument.id,snapshot.as_of))
        status='STALE_DATE' if snapshot.as_of<today else 'STALE_INPUTS' if manifest!=snapshot.input_manifest else 'CURRENT'
        saved={'status':status,'computed_at':snapshot.computed_at,'as_of':snapshot.as_of,'snapshot_id':snapshot.id}
    return {'instrument_id':instrument.id,'family':family.name if family else None,
        'unit':family.unit if family else None,
        'calibration_data_through':max((c.calibration_date for c in context['calibrations']),default=None),
        'saved_analytics':saved,
        'documents':[{'id':d.id,'original_filename':d.original_filename,'processing_status':d.processing_status} for d in context['documents']]}
