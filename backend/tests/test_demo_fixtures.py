from tests.test_analytics_snapshots import setup
from app.models.instrument import InstrumentUnit
from app.models.calibration import CalibrationEvent
from app.models.document import Document
from app.models.analytics_snapshot import AnalyticsSnapshot
from scripts.seed_demo import seed_demo
from scripts import seed_demo as demo_module
from uuid import uuid4


def test_demo_is_additive_repeatable_and_preserves_manual_corrections(setup,monkeypatch,tmp_path):
    client,db,other=setup
    monkeypatch.setenv('STORAGE_RAW_DIR',str(tmp_path))
    suffix=uuid4().hex
    monkeypatch.setattr(demo_module,'CASES',tuple((serial+'-'+suffix,title,due,status) for serial,title,due,status in demo_module.CASES))
    first=seed_demo(db)
    assert len(first)==4
    demo=db.query(InstrumentUnit).filter(InstrumentUnit.serial_number=='PTWIN-DEMO-SANO-'+suffix).first()
    doc=db.query(Document).filter(Document.instrument_unit_id==demo.id).first()
    doc.original_filename='Nombre corregido por el equipo.pdf';db.commit()
    calibrations=db.query(CalibrationEvent).count();documents=db.query(Document).count()
    second=seed_demo(db)
    assert {r['passport_url'] for r in first}=={r['passport_url'] for r in second}
    assert db.query(CalibrationEvent).count()==calibrations
    assert db.query(Document).count()==documents
    assert db.get(Document,doc.id).original_filename=='Nombre corregido por el equipo.pdf'
    assert db.get(InstrumentUnit,other.id) is not None
    assert db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.instrument_unit_id==demo.id).count()==2
    review=db.query(InstrumentUnit).filter(InstrumentUnit.serial_number=='PTWIN-DEMO-REVISION-'+suffix).first()
    context=client.get(f'/api/v1/instruments/{review.id}/passport-context').json()
    assert context['documents'][0]['processing_status']=='REVIEW_REQUIRED'
