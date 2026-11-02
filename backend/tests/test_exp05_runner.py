from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import random

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('exp05_runner',ROOT/'experiments/run_risk_exp05.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def cases():
    return runner.generate_cases(runner.protocol_for(1))


def snapshot(rows):
    return [(r['head'],r['horizon'],r['probability'],r['baseline_probability'],r['gaussian_baseline_shared_sigma'],r['predicted_error'],r['predictive_std']) for r in rows]


def test_bundle_is_deterministic_and_rng_is_unchanged(tmp_path):
    state=random.getstate()
    runner.prepare(tmp_path/'a',1);runner.prepare(tmp_path/'b',1)
    assert (tmp_path/'a/dataset.json').read_bytes()==(tmp_path/'b/dataset.json').read_bytes()
    assert (tmp_path/'a/manifest.json').read_bytes()==(tmp_path/'b/manifest.json').read_bytes()
    assert state==random.getstate()
    manifest,items,_=runner.load_bundle(tmp_path/'a')
    assert manifest['cases']==len(items)==54
    with pytest.raises(FileExistsError):runner.prepare(tmp_path/'a',1)


def test_future_labels_tolerances_history_and_maintenance_do_not_enter_predictions():
    case=next(c for c in cases() if c['scenario']=='linear')
    expected=snapshot(runner.evaluate_case(case))
    modified=deepcopy(case)
    for target in modified['targets']:
        target['error']+=100
        target['tolerance']*=2
    future=(date.fromisoformat(case['as_of'])+timedelta(days=1)).isoformat()
    modified['history'].append({'date':future,'error':999,'tolerance':1})
    modified['maintenance'].append(future)
    assert snapshot(runner.evaluate_case(modified))==expected


def test_postmaintenance_policy_never_uses_premaintenance_errors():
    case=next(c for c in cases() if c['scenario']=='known_maintenance_recovered')
    before=[r for r in runner.evaluate_case(case) if r['head']=='maintenance_policy']
    changed=deepcopy(case)
    for row in changed['history']:
        if row['date']<=changed['maintenance'][0]:row['error']+=999
    after=[r for r in runner.evaluate_case(changed) if r['head']=='maintenance_policy']
    assert snapshot(before)==snapshot(after)
    assert all(r['calibrations_used']==3 for r in after)


@pytest.mark.parametrize('scenario,reason',[('insufficient_history','INSUFFICIENT_HISTORY'),
    ('zero_variance','ZERO_RESIDUAL_VARIANCE'),('duplicate_dates','DUPLICATE_CALIBRATION_DATES'),
    ('tolerance_changed','TOLERANCE_CHANGED'),('known_maintenance_recent','INSUFFICIENT_POST_MAINTENANCE_HISTORY')])
def test_abstentions_are_null_with_explicit_reasons(scenario,reason):
    case=next(c for c in cases() if c['scenario']==scenario)
    rows=[r for r in runner.evaluate_case(case) if r['head']=='maintenance_policy']
    assert len(rows)==3 and all(r['probability'] is None and r['abstention_reason']==reason for r in rows)


def row(p,y,base=0):
    return {'probability':p,'y':y,'baseline_probability':base,'gaussian_baseline_shared_sigma':None,
            'abstention_reason':'INSUFFICIENT_HISTORY' if p is None else None,
            'covered_95':True,'normalized_absolute_error':.1}


def test_metrics_report_selection_coverage_and_fair_paired_denominators():
    result=runner.metrics([row(.8,1),row(None,1),row(.1,0,None)],.5)
    assert (result['planned'],result['scored'],result['abstentions'])==(3,2,1)
    assert result['brier']==pytest.approx(.025)
    assert result['paired']['n']==1 and result['paired']['model_brier']==pytest.approx(.04)
    assert result['paired']['baseline_brier']==1
    assert result['baseline_own_subset']['n']==2
    assert result['positives_all']==2 and result['positives_scored']==1
    assert result['abstention_reasons']=={'INSUFFICIENT_HISTORY':1}


def test_zero_probability_is_scored_and_undefined_classification_is_null():
    result=runner.metrics([row(0.,1)],.5)
    assert result['scored']==1 and result['brier']==1
    assert result['classification']['recall']==0 and result['classification']['precision'] is None
    assert runner.metrics([], .5)['brier'] is None


def test_unknown_future_reset_is_not_given_to_maintenance_policy():
    case=next(c for c in cases() if c['scenario']=='maintenance_reset')
    assert case['maintenance']==[]
    rows=runner.evaluate_case(case)
    assert [r['probability'] for r in rows[:3]]==[r['probability'] for r in rows[3:]]


def test_model_and_baseline_ignore_calibration_on_maintenance_day():
    case=next(c for c in cases() if c['scenario']=='known_maintenance_recent')
    case['maintenance']=[case['as_of']]
    rows=[r for r in runner.evaluate_case(case) if r['head']=='maintenance_policy']
    assert all(r['calibrations_used']==0 and r['probability'] is None and r['baseline_probability'] is None for r in rows)


def test_changed_bundle_is_rejected(tmp_path):
    runner.prepare(tmp_path/'bundle',1)
    path=tmp_path/'bundle/dataset.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(runner.ExperimentError,match='hash'):runner.load_bundle(tmp_path/'bundle')


def test_execution_errors_and_dropped_forecasts_invalidate_final_metrics(tmp_path,monkeypatch):
    runner.prepare(tmp_path/'bundle',1)
    monkeypatch.setattr(runner,'identity',lambda commit: {'commit':'a'*40})
    monkeypatch.setattr(runner,'evaluate_case',lambda case: [])
    report=runner.evaluate(tmp_path/'bundle')
    assert report['execution_status']=='FAILED' and report['metrics'] is None
    assert report['evaluated_cases']==0 and len(report['error_cases'])==54


def test_existing_report_is_never_overwritten(tmp_path,monkeypatch):
    output=tmp_path/'result.json';output.write_text('historical')
    monkeypatch.setattr('sys.argv',['runner','evaluate','--bundle',str(tmp_path),'--output',str(output)])
    with pytest.raises(SystemExit) as exc:runner.main()
    assert exc.value.code==2 and output.read_text()=='historical'


def test_setup_failure_leaves_no_final_metrics(tmp_path,monkeypatch):
    output=tmp_path/'result.json'
    monkeypatch.setattr('sys.argv',['runner','evaluate','--bundle',str(tmp_path/'missing'),'--output',str(output)])
    assert runner.main()==2
    assert json.loads(output.read_text())['metrics'] is None


def test_comparison_of_estimators_uses_only_common_available_forecasts():
    items=[c for c in cases() if c['family']=='pressure' and c['scenario'] in ('known_maintenance_recent','known_maintenance_recovered')]
    rows=[row for item in items for row in runner.evaluate_case(item)]
    result=runner.summarize(rows,.5)
    assert result['core_ols']['overall']['scored']==6
    assert result['maintenance_policy']['overall']['scored']==3
    assert result['head_comparison_on_common_forecasts']['n']==3
