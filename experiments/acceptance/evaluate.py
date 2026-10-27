"""Run the frozen synthetic protocol against actual project services."""
import argparse
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import NormalDist
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.tolerance_risk import estimate_tolerance_risk
from app.services.analytics import DriftAnalyticsService
from app.schemas.health_score import HealthScoreWeights


def metrics(rows):
    if not rows: return {'n':0}
    bins=[]
    for i in range(10):
        group=[r for r in rows if min(9,int(r['p']*10))==i]
        if group: bins.append({'n':len(group),'mean_probability':sum(r['p'] for r in group)/len(group),
                               'observed_rate':sum(r['y'] for r in group)/len(group)})
    n=len(rows)
    return {'n':n,'positives':sum(r['y'] for r in rows),
        'brier':sum((r['p']-r['y'])**2 for r in rows)/n,
        'state_persistence_brier':sum((r['b0']-r['y'])**2 for r in rows)/n,
        'gaussian_persistence_brier':sum((r['bp']-r['y'])**2 for r in rows)/n,
        'ece':sum(b['n']*abs(b['mean_probability']-b['observed_rate']) for b in bins)/n,
        'mae_in_tolerance_units':sum(r['absolute_error'] for r in rows)/n,
        'coverage_95':sum(r['covered'] for r in rows)/n,'reliability_bins':bins}


def run(protocol):
    rng=random.Random(protocol['seed'])
    rows=[]; dataset=[]; abstentions=0
    for family,tolerance in protocol['families'].items():
        for n in protocol['training_lengths']:
            for scenario in protocol['scenarios']:
                for instrument in range(protocol['instruments_per_cell']):
                    offset=rng.uniform(-1.1,1.1);drift=rng.uniform(-0.09,0.09)
                    values=[]
                    for step in range(n+3):
                        mean=offset+(0 if scenario=='stable' else drift*step)
                        if scenario=='curvature': mean+=0.008*step**2
                        if scenario=='step_change' and step>=n: mean+=0.65
                        if scenario=='maintenance_reset' and step>=n: mean=0
                        sigma=0.6 if scenario=='heavy_tail' and rng.random()<0.1 else 0.12
                        values.append((mean+rng.gauss(0,sigma))*tolerance)
                    dataset.append([family,n,scenario,instrument,values])
                    start=date(2024,1,1)
                    history=[SimpleNamespace(id=i+1,calibration_date=start+timedelta(days=i*30),error_value=v,tolerance=tolerance)
                             for i,v in enumerate(values[:n])]
                    cutoff=history[-1].calibration_date
                    forecast=estimate_tolerance_risk(history,cutoff)
                    for h,truth in zip(protocol['horizons_days'],values[n:]):
                        item=forecast['horizons'][f'{h}_days'];p=item['probability_out_of_tolerance']
                        if p is None: abstentions+=1;continue
                        assert math.isfinite(p) and 0<=p<=1
                        assert item['target_date']==(cutoff+timedelta(days=h)).isoformat()
                        baseline=NormalDist(mu=values[n-1],sigma=item['predictive_std'])
                        bp=baseline.cdf(-tolerance)+1-baseline.cdf(tolerance)
                        rows.append({'family':family,'scenario':scenario,'training_n':n,'horizon':h,
                            'p':p,'y':int(abs(truth)>tolerance),'b0':int(abs(values[n-1])>tolerance),'bp':bp,
                            'absolute_error':abs(item['predicted_error']-truth)/tolerance,
                            'covered':abs(truth-item['predicted_error'])<=1.959963984540054*item['predictive_std']})
    normal=[r for r in rows if r['scenario'] in ('stable','linear')]
    m=metrics(normal)
    thresholds=protocol['checks']
    checks={'probabilities_finite_in_unit_interval':True,
            'linear_normal_pooled_brier_better_than_state_persistence':m['brier']<m['state_persistence_brier'],
            'linear_normal_pooled_ece':m['ece']<=thresholds['linear_normal_pooled_ece_max'],
            'linear_normal_pooled_95_coverage':m['coverage_95']>=thresholds['linear_normal_pooled_95_coverage_min']}
    return {'protocol':protocol,'dataset_sha256':hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
        'trajectories':len(dataset),'forecasts':len(rows),'abstentions':abstentions,'checks':checks,
        'overall':metrics(rows),'normal_linear_pooled':m,
        'by_scenario':{s:metrics([r for r in rows if r['scenario']==s]) for s in protocol['scenarios']},
        'by_family':{f:metrics([r for r in rows if r['family']==f]) for f in protocol['families']},
        'by_horizon':{str(h):metrics([r for r in rows if r['horizon']==h]) for h in protocol['horizons_days']},
        'by_training_length':{str(n):metrics([r for r in rows if r['training_n']==n]) for n in protocol['training_lengths']}}


def health_checks():
    configs=[HealthScoreWeights(),HealthScoreWeights(risk_90_days=.5,current_error=.3,out_of_tolerance=.2),
             HealthScoreWeights(risk_90_days=.2,current_error=.6,out_of_tolerance=.2)]
    checks=0;max_sensitivity=0
    for state in ('operational','out_of_tolerance'):
        previous=101
        for i in range(21):
            error=i/10
            instrument=SimpleNamespace(id=1,serial_number='ACCEPT',lifecycle_state=state)
            calibration=SimpleNamespace(id=1,instrument_unit_id=1,calibration_date=date(2026,1,1),error_value=error,tolerance=1)
            baseline=DriftAnalyticsService.calculate_drift_and_risk(instrument,[calibration],health_score_weights=configs[0])
            assert baseline['health_score']<=previous;previous=baseline['health_score'];checks+=1
            for weights in configs:
                result=DriftAnalyticsService.calculate_drift_and_risk(instrument,[calibration],health_score_weights=weights)
                score=result['health_score'];assert 0<=score<=100
                assert abs(score-round(100-result['health_score_details']['total_penalty_points'],1))<=0.1
                max_sensitivity=max(max_sensitivity,abs(score-baseline['health_score']));checks+=2
    return {'checks_passed':checks,'weight_sets':[w.model_dump() for w in configs],
            'max_change_points':max_sensitivity,'scope':'Metrological v1 design consistency only; incidents and data quality are not implemented.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--code-sha');args=parser.parse_args()
    protocol_path=Path(__file__).with_name('protocol.json')
    report=run(json.loads(protocol_path.read_text()))
    report['health_v1']=health_checks()
    report['protocol_sha256']=hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    report['code_sha']=args.code_sha or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'dataset_sha256':report['dataset_sha256'],'forecasts':report['forecasts'],'checks':report['checks'],'normal_linear_pooled':report['normal_linear_pooled'],
                      'health_v1':report['health_v1']},indent=2))
