from datetime import date,timedelta,datetime
from types import SimpleNamespace as N
import pytest
from pydantic import ValidationError
from app.schemas.health_score_v2 import LifecycleHealthWeights
from app.services.lifecycle_health import calculate_lifecycle_health,risk_after_maintenance

DAY=date(2026,10,27)


def context():
    return dict(instrument=N(serial_number='TEST',manufacturer='TEST',model='TEST',location='LAB',lifecycle_state='operational'),
        calibrations=[N(id=i+1,calibration_date=DAY-timedelta(days=30*(3-i)),error_value=e,tolerance=1,
                        next_due_date=DAY+timedelta(days=100),result='pass') for i,e in enumerate([.1,.12,.09,.11])],
        documents=[N(id=1,processing_status='ACCEPTED')],incidents=[],maintenance=[],as_of=DAY,
        weights=LifecycleHealthWeights())


def test_four_components_and_reconstruction():
    r=calculate_lifecycle_health(**context());d=r['health_score_details']
    assert r['health_score']==100
    assert set(d['components'])=={'calibration_status','predicted_risk','recent_incidents','data_quality'}
    assert round(100-sum(c['penalty_points'] for c in d['components'].values()),1)==r['health_score']


@pytest.mark.parametrize('severity,penalty', [('LOW',.25),('MEDIUM',.5),('HIGH',1),('CRITICAL',1)])
def test_recent_incident_penalties(severity,penalty):
    c=context();c['incidents']=[N(incident_date=DAY,severity=severity,resolved_at=None)]
    r=calculate_lifecycle_health(**c)
    assert r['health_score']==100-20*penalty


def test_resolved_old_and_future_incidents_do_not_penalize():
    c=context();c['incidents']=[N(incident_date=DAY-timedelta(days=91),severity='HIGH',resolved_at=None),
        N(incident_date=DAY,severity='HIGH',resolved_at=datetime(2026,10,27)),
        N(incident_date=DAY+timedelta(days=1),severity='HIGH',resolved_at=None)]
    assert calculate_lifecycle_health(**c)['health_score']==100


def test_data_quality_and_due_date_penalize_without_changing_risk():
    c=context();baseline=calculate_lifecycle_health(**c)
    c['documents'][0].processing_status='REVIEW_REQUIRED'
    c['calibrations'][-1].result='fail'
    r=calculate_lifecycle_health(**c)
    assert r['health_score']==66.7
    assert r['tolerance_risk']==baseline['tolerance_risk']


def test_missing_inputs_and_unknown_severity_do_not_invent_score():
    c=context();c['calibrations']=[]
    assert calculate_lifecycle_health(**c)['health_score'] is None
    c=context();c['incidents']=[N(incident_date=DAY,severity='UNKNOWN',resolved_at=None)]
    assert calculate_lifecycle_health(**c)['health_score'] is None


def test_maintenance_requires_new_baseline_and_old_history_is_ignored():
    c=context();c['maintenance']=[N(event_date=DAY)]
    risk=risk_after_maintenance(c['calibrations'],c['maintenance'],DAY)
    assert risk['reason']=='INSUFFICIENT_POST_MAINTENANCE_HISTORY'
    assert calculate_lifecycle_health(**c)['health_score'] is None
    c['maintenance']=[N(event_date=DAY-timedelta(days=65))]
    risk=risk_after_maintenance(c['calibrations'],c['maintenance'],DAY)
    assert risk['calibrations_used']==3 and risk['status']=='ESTIMATED'


@pytest.mark.parametrize('weights',[{'predicted_risk':-1},{'data_quality':float('nan')},{'calibration_status':.9},{'other':1}])
def test_bad_config(weights):
    with pytest.raises(ValidationError): LifecycleHealthWeights(**weights)


def test_due_and_overdue_and_predicted_risk_have_expected_direction():
    c=context();c['calibrations'][-1].next_due_date=DAY+timedelta(days=30)
    assert calculate_lifecycle_health(**c)['health_score']==85
    c=context()
    for calibration in c['calibrations']:calibration.calibration_date-=timedelta(days=30)
    c['calibrations'][-1].next_due_date=DAY-timedelta(days=1)
    assert calculate_lifecycle_health(**c)['health_score']==70
    c=context()
    for calibration,value in zip(c['calibrations'],[.1,.4,.6,.9]):calibration.error_value=value
    r=calculate_lifecycle_health(**c)
    assert r['health_score_details']['components']['predicted_risk']['value']>.8
    assert r['health_score']<80


def test_identity_quality_and_environment_configuration(monkeypatch):
    from app.core.config import Settings
    c=context();c['instrument'].manufacturer=''
    assert calculate_lifecycle_health(**c)['health_score']==96.7
    monkeypatch.setenv('LIFECYCLE_HEALTH_WEIGHTS','{"calibration_status":0.4,"predicted_risk":0.3,"recent_incidents":0.2,"data_quality":0.1}')
    assert Settings(_env_file=None).lifecycle_health_weights.calibration_status==.4
