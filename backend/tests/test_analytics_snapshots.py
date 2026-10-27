from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.database.session import engine, get_db
from app.main import app
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.document import Document
from app.models.calibration import CalibrationEvent, AuditLog
from app.models.instrument import InstrumentType, InstrumentUnit


@pytest.fixture
def setup():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode='create_savepoint')
    family = InstrumentType(name=f'snapshot-{uuid4()}', magnitude='Pressure', unit='bar')
    db.add(family); db.flush()
    instrument = InstrumentUnit(instrument_type_id=family.id,serial_number=f'SNAP-{uuid4()}',manufacturer='TEST',model='TEST',location='Lab A')
    db.add(instrument); db.flush()
    def override(): yield db
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), db, instrument
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
        db.close(); transaction.rollback(); connection.close()


def seed(db, instrument):
    for i,error in enumerate([0.1,0.23,0.29,0.47]):
        db.add(CalibrationEvent(instrument_unit_id=instrument.id,
            calibration_date=date.today()-timedelta(days=(3-i)*30),error_value=error,tolerance=1,result='pass',next_due_date=date.today()+timedelta(days=100)))
    db.add(Document(instrument_unit_id=instrument.id,original_filename='test',file_path='test',sha256_hash=uuid4().hex,processing_status='ACCEPTED'))
    db.flush()


def test_refresh_persists_both_methods_and_append_only_history(setup):
    client,db,instrument=setup;seed(db,instrument)
    path=f'/api/v1/instruments/{instrument.id}/analytics-snapshots'
    snapshots=db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.instrument_unit_id==instrument.id)
    assert snapshots.count() == 0
    result=client.post(path)
    assert result.status_code == 201
    first=result.json()
    assert first['health_score'] == 99.8
    live=client.get(f'/api/v1/instruments/{instrument.id}/health-score').json()
    assert first['score_result'] == live['health_score_details']
    assert first['risk_result'] == {
        k:v for k,v in client.get(f'/api/v1/instruments/{instrument.id}/tolerance-risk').json().items()
        if k not in ('instrument_id','serial_number')
    }
    assert first['risk_result']['validation_status'] == 'EXPERIMENTAL_UNCALIBRATED'
    stored=db.get(AnalyticsSnapshot,first['snapshot_id'])
    assert stored.probability_90 == first['risk_result']['horizons']['90_days']['probability_out_of_tolerance']
    assert first['weights'] == {'calibration_status':.3,'predicted_risk':.3,'recent_incidents':.2,'data_quality':.2}
    second=client.post(path).json()
    assert first['snapshot_id'] != second['snapshot_id']
    assert first['input_hash'] == second['input_hash']
    assert snapshots.count() == 2
    assert db.query(AuditLog).filter(AuditLog.action=='ANALYTICS_SNAPSHOT_CREATED', AuditLog.entity_id.in_([first['snapshot_id'],second['snapshot_id']])).count() == 2
    # Existing read endpoints still do not persist snapshots.
    assert client.get(f'/api/v1/instruments/{instrument.id}/predictions').status_code == 200
    assert snapshots.count() == 2


def test_empty_history_is_null_for_bi_not_fallback_50(setup):
    client,db,instrument=setup
    result=client.post(f'/api/v1/instruments/{instrument.id}/analytics-snapshots').json()
    assert result['health_score'] is None
    assert result['score_status']=='NOT_CALCULATED'
    assert result['score_result']['fallback'] is False
    assert result['risk_status']=='NOT_ESTIMABLE'


def test_reference_date_and_input_hash(setup):
    client,db,instrument=setup;seed(db,instrument)
    path=f'/api/v1/instruments/{instrument.id}/analytics-snapshots'
    result=client.post(path,params={'as_of':(date.today()-timedelta(days=1)).isoformat()}).json()
    assert result['risk_result']['calibrations_used']==3
    first=client.post(path).json()
    instrument.lifecycle_state='out_of_tolerance';db.flush()
    second=client.post(path).json()
    assert first['input_hash'] != second['input_hash']
    assert first['health_score'] != second['health_score']
    assert client.post(path,params={'as_of':(date.today()+timedelta(days=1)).isoformat()}).status_code == 422
    assert client.post('/api/v1/instruments/2147483647/analytics-snapshots').status_code == 404


def test_invalid_tolerance_does_not_emit_score_or_probability(setup):
    client,db,instrument=setup;seed(db,instrument)
    db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id==instrument.id).update({'tolerance':0})
    result=client.post(f'/api/v1/instruments/{instrument.id}/analytics-snapshots').json()
    assert result['health_score'] is None
    assert 'calibration_status' in result['score_result']['missing_components']
    assert result['risk_result']['reason']=='INVALID_CALIBRATION_VALUES'
