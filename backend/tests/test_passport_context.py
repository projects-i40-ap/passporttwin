from datetime import date,timedelta,datetime
from tests.test_analytics_snapshots import setup,seed
from app.models.maintenance import Incident


def test_unit_documents_and_analytics_dates_do_not_persist_on_read(setup):
    client,db,instrument=setup;seed(db,instrument)
    path=f'/api/v1/instruments/{instrument.id}/passport-context'
    context=client.get(path).json()
    assert context['unit']=='bar'
    assert context['saved_analytics']['status']=='MISSING'
    assert context['calibration_data_through']==date.today().isoformat()
    assert len(context['documents'])==1
    assert 'file_path' not in context['documents'][0]
    live=client.get(f'/api/v1/instruments/{instrument.id}/health-score').json()
    assert datetime.fromisoformat(live['calculated_at']).tzinfo is not None
    assert live['calibration_data_through']==date.today().isoformat()
    client.post(f'/api/v1/instruments/{instrument.id}/analytics-snapshots')
    assert client.get(path).json()['saved_analytics']['status']=='CURRENT'
    db.add(Incident(instrument_unit_id=instrument.id,incident_date=date.today(),description='test',severity='HIGH'));db.flush()
    assert client.get(path).json()['saved_analytics']['status']=='STALE_INPUTS'


def test_empty_history_and_context_404(setup):
    client,db,instrument=setup
    context=client.get(f'/api/v1/instruments/{instrument.id}/passport-context').json()
    assert context['calibration_data_through'] is None
    assert context['documents']==[]
    assert client.get('/api/v1/instruments/2147483647/passport-context').status_code==404
