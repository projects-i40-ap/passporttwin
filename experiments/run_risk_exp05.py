"""EXP-05 preparation: known synthetic risk scenarios, abstentions and maintenance."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import subprocess
from statistics import NormalDist
import sys
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / 'experiments/acceptance/protocol.json'
HEADS = ('core_ols', 'maintenance_policy')
HORIZONS = (30, 60, 90)
CONTROLS = ('insufficient_history', 'zero_variance', 'duplicate_dates', 'tolerance_changed',
            'known_maintenance_recent', 'known_maintenance_recovered')


class ExperimentError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def protocol_for(per_cell):
    old = json.loads(HISTORICAL.read_text())
    return {'version': 'exp05_preparation_v1', 'scope': 'Known development generator, not independent final validation',
            'historical_protocol_sha256': digest(HISTORICAL.read_bytes()),
            'seed': old['seed'], 'families': old['families'], 'training_lengths': old['training_lengths'],
            'scenarios': old['scenarios'], 'instruments_per_cell': per_cell, 'horizons': list(HORIZONS),
            'controls': list(CONTROLS), 'classification_threshold': .5,
            'target': 'Exceedance at each target date, not any crossing during the interval',
            'baselines': 'Last observed out-of-tolerance state within each eligible history; plus Gaussian persistence sharing the model predictive std on its available subset; abstain if latest date ambiguous',
            'metrics_scope': 'Model available subset; paired baseline comparison; baseline own subset; compare estimator heads only on common available forecasts',
            'acceptance_thresholds': None}


def generate_cases(protocol):
    old = json.loads(HISTORICAL.read_text())
    rng = random.Random(protocol['seed'])
    cases = []
    start = date(2024, 1, 1)
    def pack(identifier, family, scenario, values, n, tolerance, maintenance=None):
        history = [{'date': (start + timedelta(days=i*30)).isoformat(), 'error': v, 'tolerance': tolerance}
                   for i, v in enumerate(values[:n])]
        origin = start + timedelta(days=(n-1)*30)
        return {'id': identifier, 'family': family, 'scenario': scenario, 'as_of': origin.isoformat(),
                'history': history, 'maintenance': maintenance or [],
                'targets': [{'date': (origin+timedelta(days=h)).isoformat(), 'horizon': h,
                             'error': v, 'tolerance': tolerance} for h, v in zip(HORIZONS, values[n:])]}
    for family, tolerance in old['families'].items():
        for n in old['training_lengths']:
            for scenario in old['scenarios']:
                for index in range(protocol['instruments_per_cell']):
                    offset, drift = rng.uniform(-1.1, 1.1), rng.uniform(-.09, .09)
                    values = []
                    for step in range(n+3):
                        mean = offset + (0 if scenario == 'stable' else drift*step)
                        if scenario == 'curvature': mean += .008*step**2
                        if scenario == 'step_change' and step >= n: mean += .65
                        if scenario == 'maintenance_reset' and step >= n: mean = 0
                        sigma = .6 if scenario == 'heavy_tail' and rng.random() < .1 else .12
                        values.append((mean+rng.gauss(0, sigma))*tolerance)
                    cases.append(pack(f'{family}-{n}-{scenario}-{index}', family, scenario, values, n, tolerance))
        for control in CONTROLS:
            values = [v*tolerance for v in (1.2, 1.1, 1.3, 1.2, 1.0, .02, .08, .04, .03, .05, .02)]
            n = 8
            if control == 'insufficient_history':
                n, values = 2, [v*tolerance for v in (.1, .12, .11, .13, .1)]
            elif control == 'zero_variance':
                n, values = 3, [v*tolerance for v in (0, .125, .25, .375, .5, .625)]
            item = pack(f'{family}-{control}', family, control, values, n, tolerance)
            if control == 'duplicate_dates': item['history'][-2]['date'] = item['history'][-1]['date']
            if control == 'tolerance_changed': item['history'][0]['tolerance'] *= 2
            if control == 'known_maintenance_recent':
                item['maintenance'] = [(date.fromisoformat(item['as_of'])-timedelta(days=15)).isoformat()]
            if control == 'known_maintenance_recovered':
                item['maintenance'] = [(date.fromisoformat(item['as_of'])-timedelta(days=75)).isoformat()]
            cases.append(item)
    return cases


def prepare(bundle, per_cell=3):
    if not isinstance(per_cell, int) or isinstance(per_cell, bool) or per_cell < 1:
        raise ExperimentError('Positive instruments-per-cell required')
    protocol = protocol_for(per_cell)
    data = canonical(generate_cases(protocol))
    bundle.mkdir(parents=True, exist_ok=False)
    (bundle / 'dataset.json').write_bytes(data)
    with (bundle / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump({'protocol': protocol, 'dataset_sha256': digest(data), 'cases': len(json.loads(data)),
                   'generator_sha256': digest(Path(__file__).read_bytes()), 'python': platform.python_version()},
                  stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def load_bundle(bundle):
    raw = (bundle / 'manifest.json').read_bytes()
    manifest = json.loads(raw)
    protocol = manifest['protocol']
    if protocol != protocol_for(protocol['instruments_per_cell']):
        raise ExperimentError('Protocol differs from supported preparation contract')
    if manifest['generator_sha256'] != digest(Path(__file__).read_bytes()):
        raise ExperimentError('Generator/evaluator source changed since bundle creation')
    data = (bundle / 'dataset.json').read_bytes()
    if digest(data) != manifest['dataset_sha256'] or canonical(generate_cases(protocol)) != data:
        raise ExperimentError('Dataset hash or regeneration mismatch')
    cases = json.loads(data)
    if len(cases) != manifest['cases']:
        raise ExperimentError('Case count mismatch')
    return manifest, cases, digest(raw)


def eligible_history(case, head):
    origin = date.fromisoformat(case['as_of'])
    events = [date.fromisoformat(value) for value in case['maintenance'] if date.fromisoformat(value) <= origin]
    cutoff = max(events) if head == 'maintenance_policy' and events else None
    return [row for row in case['history'] if date.fromisoformat(row['date']) <= origin
            and (cutoff is None or date.fromisoformat(row['date']) > cutoff)]


def baseline_probability(history):
    if not history:
        return None
    latest = max(row['date'] for row in history)
    rows = [row for row in history if row['date'] == latest]
    if len(rows) != 1:
        return None
    error, tolerance = rows[0]['error'], rows[0]['tolerance']
    if not math.isfinite(error) or not math.isfinite(tolerance) or tolerance <= 0:
        return None
    return float(abs(error) > tolerance)


def evaluate_case(case):
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.services.tolerance_risk import estimate_tolerance_risk
    from app.services.lifecycle_health import risk_after_maintenance
    origin = date.fromisoformat(case['as_of'])
    history = [N(calibration_date=date.fromisoformat(row['date']), error_value=row['error'], tolerance=row['tolerance']) for row in case['history']]
    maintenance = [N(event_date=date.fromisoformat(value)) for value in case['maintenance']]
    outcomes = {'core_ols': estimate_tolerance_risk(history, origin),
                'maintenance_policy': risk_after_maintenance(history, maintenance, origin)}
    details = []
    for head in HEADS:
        outcome = outcomes[head]
        eligible = eligible_history(case, head)
        baseline = baseline_probability(eligible)
        for target in case['targets']:
            h = target['horizon']
            if h not in HORIZONS or target['date'] != (origin+timedelta(days=h)).isoformat():
                raise ExperimentError('Target is not the declared forecast date')
            item = outcome['horizons'].get(f'{h}_days', {})
            if item and item['target_date'] != target['date']:
                raise ExperimentError('Service target date differs from label')
            p = item.get('probability_out_of_tolerance')
            if p is not None and (not math.isfinite(p) or not 0 <= p <= 1):
                raise ExperimentError('Invalid probability')
            gaussian_baseline = None
            if p is not None and baseline is not None:
                latest = max(eligible, key=lambda row: row['date'])
                normal = NormalDist(mu=latest['error'], sigma=item['predictive_std'])
                gaussian_baseline = max(0., min(1., normal.cdf(-latest['tolerance']) + 1 - normal.cdf(latest['tolerance'])))
            reason = outcome.get('reason') if not item else item.get('uncertainty_status') if p is None else None
            details.append({'case_id': case['id'], 'family': case['family'], 'scenario': case['scenario'],
                'head': head, 'horizon': h, 'origin': case['as_of'], 'target_date': target['date'],
                'y': int(abs(target['error']) > target['tolerance']), 'truth_error': target['error'],
                'probability': p, 'baseline_probability': baseline, 'gaussian_baseline_shared_sigma': gaussian_baseline, 'abstention_reason': reason,
                'calibrations_used': outcome['calibrations_used'], 'last_maintenance_date': outcome.get('last_maintenance_date'),
                'predicted_error': item.get('predicted_error'), 'predictive_std': item.get('predictive_std'),
                'normalized_absolute_error': abs(item['predicted_error']-target['error'])/target['tolerance'] if p is not None else None,
                'covered_95': abs(item['predicted_error']-target['error']) <= 1.959963984540054*item['predictive_std'] if p is not None else None})
    return details


def classification(rows, key, threshold):
    pairs = [(row['y'], row[key] >= threshold) for row in rows]
    tp = sum(y and p for y,p in pairs); fp = sum(not y and p for y,p in pairs)
    fn = sum(y and not p for y,p in pairs); tn = sum(not y and not p for y,p in pairs)
    return {'n':len(rows), 'tp':tp, 'fp':fp, 'fn':fn, 'tn':tn,
            'precision':tp/(tp+fp) if tp+fp else None, 'recall':tp/(tp+fn) if tp+fn else None,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def metrics(rows, threshold):
    available = [row for row in rows if row['probability'] is not None]
    baselines = [row for row in rows if row['baseline_probability'] is not None]
    paired = [row for row in available if row['baseline_probability'] is not None]
    gaussian = [row for row in available if row['gaussian_baseline_shared_sigma'] is not None]
    def mean(values): return sum(values)/len(values) if values else None
    def brier(values,key): return mean([(row[key]-row['y'])**2 for row in values])
    bins = []
    for i in range(10):
        group = [row for row in available if min(9,int(row['probability']*10)) == i]
        if group: bins.append({'bin':i, 'n':len(group), 'mean_probability':mean([r['probability'] for r in group]), 'observed_rate':mean([r['y'] for r in group])})
    return {'planned':len(rows), 'scored':len(available), 'abstentions':len(rows)-len(available),
            'positives_all':sum(row['y'] for row in rows), 'positives_scored':sum(row['y'] for row in available),
            'coverage_fraction':len(available)/len(rows) if rows else None,
            'abstention_reasons':dict(Counter(row['abstention_reason'] for row in rows if row['probability'] is None)),
            'brier':brier(available,'probability'), 'classification':classification(available,'probability',threshold),
            'paired':{'n':len(paired),'model_brier':brier(paired,'probability'),'baseline_brier':brier(paired,'baseline_probability')},
            'gaussian_persistence_shared_sigma':{'n':len(gaussian),'model_brier':brier(gaussian,'probability'),'baseline_brier':brier(gaussian,'gaussian_baseline_shared_sigma')},
            'baseline_own_subset':{'n':len(baselines),'abstentions':len(rows)-len(baselines),
                                   'brier':brier(baselines,'baseline_probability'),'classification':classification(baselines,'baseline_probability',threshold)},
            'ece_10_bins':sum(b['n']*abs(b['mean_probability']-b['observed_rate']) for b in bins)/len(available) if available else None,
            'reliability_bins':bins, 'coverage_95_on_scored':mean([row['covered_95'] for row in available]),
            'mae_in_tolerance_units_on_scored':mean([row['normalized_absolute_error'] for row in available])}


def summarize(details, threshold):
    result = {}
    for head in HEADS:
        rows = [row for row in details if row['head'] == head]
        result[head] = {'overall':metrics(rows,threshold),
                       'by_horizon':{str(h):metrics([row for row in rows if row['horizon']==h],threshold) for h in HORIZONS},
                       'by_scenario':{s:metrics([row for row in rows if row['scenario']==s],threshold) for s in sorted({row['scenario'] for row in rows})}}
    groups = {}
    for row in details:
        groups.setdefault((row['case_id'],row['horizon']),{})[row['head']] = row
    common = [group for group in groups.values() if all(head in group and group[head]['probability'] is not None for head in HEADS)]
    result['head_comparison_on_common_forecasts'] = {'n':len(common),
        **{head+'_brier':sum((group[head]['probability']-group[head]['y'])**2 for group in common)/len(common) if common else None for head in HEADS}}
    return result


def identity(commit=None):
    if commit is not None and not re.fullmatch('[0-9a-fA-F]{40}', commit): raise ExperimentError('Full Git SHA required')
    try:
        found = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True,stderr=subprocess.DEVNULL).strip())
    except (OSError,subprocess.CalledProcessError):
        if not commit: raise ExperimentError('Git unavailable: supply --code-commit from host') from None
        return {'commit':commit,'working_tree_dirty':None,'source':'caller_supplied_not_verified'}
    if commit and commit!=found: raise ExperimentError('Commit differs from checkout')
    return {'commit':found,'working_tree_dirty':dirty,'source':'git_checkout'}


def evaluate(bundle, commit=None):
    manifest,cases,manifest_hash = load_bundle(bundle)
    source = identity(commit)
    details,errors = [],[]
    for case in cases:
        try:
            rows=evaluate_case(case)
            if len(rows)!=6 or {(row['head'],row['horizon']) for row in rows}!={(head,h) for head in HEADS for h in HORIZONS}:
                raise ExperimentError('Incomplete or duplicate forecast rows')
            details.extend(rows)
        except Exception as exc: errors.append({'case_id':case['id'],'error_type':type(exc).__name__})
    threshold=manifest['protocol']['classification_threshold']
    source_files=['experiments/run_risk_exp05.py','backend/app/services/tolerance_risk.py','backend/app/services/lifecycle_health.py','experiments/acceptance/protocol.json']
    stable = digest((bundle/'manifest.json').read_bytes())==manifest_hash and digest((bundle/'dataset.json').read_bytes())==manifest['dataset_sha256']
    return {'experiment':'EXP-05','scope':'Known synthetic preparation, not final independent validation',
            'execution_status':'COMPLETE' if not errors and stable else 'FAILED',
            'calculated_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'git':source,
            'protocol':manifest['protocol'],'dataset_sha256':manifest['dataset_sha256'],'manifest_sha256':manifest_hash,
            'generation_reproduced_exactly':True,'input_integrity':'UNCHANGED' if stable else 'CHANGED',
            'planned_cases':len(cases),'evaluated_cases':len(cases)-len(errors),
            'planned_forecasts_per_head':len(cases)*3,'error_cases':errors,
            'source_sha256':{name:digest((ROOT/name).read_bytes()) for name in source_files},
            'metrics':summarize(details,threshold) if not errors and stable else None,
            'partial_diagnostics_not_final_metrics':summarize(details,threshold) if errors or not stable else None,
            'details':details}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--per-cell',type=int,default=3)
    p=sub.add_parser('evaluate');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--code-commit')
    args=parser.parse_args()
    if args.action=='prepare':
        try: prepare(args.bundle,args.per_cell)
        except (OSError,ExperimentError): parser.error('Check parameters and use a new bundle directory')
        print(f'PREPARED: {args.bundle}');return 0
    args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with args.output.open('x',encoding='utf-8') as stream:
            try: report=evaluate(args.bundle,args.code_commit)
            except Exception as exc: report={'experiment':'EXP-05','execution_status':'SETUP_FAILED','metrics':None,'error_type':type(exc).__name__,'error':str(exc) if isinstance(exc,ExperimentError) else 'Check bundle and environment'}
            json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    except FileExistsError: parser.error('Output exists; reports are never overwritten')
    print(f"{report['execution_status']}: {args.output}")
    return 0 if report['execution_status']=='COMPLETE' else 2


if __name__=='__main__': raise SystemExit(main())
