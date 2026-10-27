"""Design-policy sensitivity, not a claim of optimal weights or field validity."""
from datetime import date,timedelta
import json,random,sys
from pathlib import Path
from types import SimpleNamespace as N
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.schemas.health_score_v2 import LifecycleHealthWeights
from app.services.lifecycle_health import calculate_lifecycle_health


def run():
    rng=random.Random(20261027);day=date(2026,10,27)
    configs=[LifecycleHealthWeights(),LifecycleHealthWeights(calibration_status=.4,predicted_risk=.3,recent_incidents=.15,data_quality=.15),
             LifecycleHealthWeights(calibration_status=.2,predicted_risk=.4,recent_incidents=.2,data_quality=.2)]
    count=0;max_change=0
    for i in range(1000):
        offset=rng.uniform(-.8,.8);slope=rng.uniform(-.1,.1)
        c=dict(instrument=N(serial_number='TEST',manufacturer='TEST',model='TEST',location='LAB',lifecycle_state='operational'),
            calibrations=[N(id=j,calibration_date=day-timedelta(days=30*(7-j)),error_value=offset+slope*j+rng.gauss(0,.08),
                            tolerance=1,next_due_date=day+timedelta(days=90),result='pass') for j in range(8)],
            documents=[N(processing_status='ACCEPTED' if rng.random()<.8 else 'REVIEW_REQUIRED')],incidents=[],maintenance=[],as_of=day)
        baseline=calculate_lifecycle_health(**c,weights=configs[0])['health_score']
        for weights in configs:
            r=calculate_lifecycle_health(**c,weights=weights);score=r['health_score']
            assert score is not None and 0<=score<=100
            assert abs(score-round(100-r['health_score_details']['total_penalty_points'],1))<=.1
            bound=50*sum(abs(a-b) for a,b in zip(configs[0].model_dump().values(),weights.model_dump().values()))+.1
            assert abs(score-baseline)<=bound
            max_change=max(max_change,abs(score-baseline));count+=3
        prior=baseline
        for severity in ('LOW','MEDIUM','HIGH'):
            c['incidents']=[N(incident_date=day,severity=severity,resolved_at=None)]
            score=calculate_lifecycle_health(**c,weights=configs[0])['health_score']
            assert score<=prior;prior=score;count+=1
    return {'seed':20261027,'cases':1000,'checks_passed':count,'max_weight_sensitivity_points':max_change,
            'weights':[c.model_dump() for c in configs],'scope':'Design consistency and bounded sensitivity; no clinical/metrological optimality claim'}


if __name__=='__main__':
    result=run();print(json.dumps(result,indent=2))
