from datetime import date
from pathlib import Path
from sqlalchemy import text

from tests.test_analytics_snapshots import setup,seed
from app.models.maintenance import Incident,MaintenanceEvent
from app.models.document import Document


def test_lifecycle_inputs_invalidate_bi_and_refresh_matches_api(setup):
    client,db,instrument=setup;seed(db,instrument)
    root=Path(__file__).resolve().parents[2]
    for path in ('bi/sql/fleet_overview.sql','bi/sql/fleet_analytics.sql'):
        db.connection().exec_driver_sql((root/path).read_text())
    path=f'/api/v1/instruments/{instrument.id}/analytics-snapshots'
    first=client.post(path).json()
    def status():
        return db.execute(text('SELECT analytics_status,current_health_score FROM passporttwin_bi.fleet_analytics WHERE instrument_id=:id'),{'id':instrument.id}).one()
    assert status()==('CURRENT',first['health_score'])
    db.add(Incident(instrument_unit_id=instrument.id,incident_date=date.today(),description='test',severity='HIGH'));db.flush()
    assert status()==('STALE_INPUTS',None)
    second=client.post(path).json()
    assert second['health_score']==first['health_score']-20
    assert status()[0]=='CURRENT'
    doc=db.query(Document).filter(Document.instrument_unit_id==instrument.id).first()
    doc.processing_status='REVIEW_REQUIRED';db.flush()
    assert status()==('STALE_INPUTS',None)
    third=client.post(path).json()
    assert third['health_score']<second['health_score']
    db.add(MaintenanceEvent(instrument_unit_id=instrument.id,event_date=date.today(),description='test'));db.flush()
    assert status()==('STALE_INPUTS',None)
    final=client.post(path).json()
    assert final['health_score'] is None
    assert final['risk_result']['reason']=='INSUFFICIENT_POST_MAINTENANCE_HISTORY'
    assert client.get(f'/api/v1/instruments/{instrument.id}/health-score').json()['health_score'] is None
    assert status()==('CURRENT',None)
