"""Prepare/check a synthetic EXP-04 bundle. No final acceptance or database writes."""
import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import importlib.util
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import platform
import random
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / 'generators/generate_synthetic_drift_dataset.py'
UNITS = {'pressure_transmitter': 'bar', 'temperature_sensor': '°C', 'ph_sensor': 'pH'}
MODELS = ('B0', 'B1', 'M1')


class ExperimentError(ValueError):
    """Actionable diagnostics with no credentials or environment dump."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def code_identity(code_commit=None):
    if code_commit is not None and not re.fullmatch('[0-9a-fA-F]{40}', code_commit):
        raise ExperimentError('--code-commit requires a full Git SHA')
    try:
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        if code_commit is None:
            raise ExperimentError('Git unavailable: pass --code-commit from the host') from None
        return {'commit': code_commit, 'working_tree_dirty': None, 'source': 'caller_supplied_not_verified'}
    if code_commit and code_commit != commit:
        raise ExperimentError('Provided commit differs from checkout')
    return {'commit': commit, 'working_tree_dirty': dirty, 'source': 'git_checkout'}


def generate_rows(seed, instruments, calibrations, interval):
    """Reuse the historical generator with an isolated RNG; preserve global state."""
    state = random.getstate()
    try:
        spec = importlib.util.spec_from_file_location('exp04_generator', GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.random = random.Random(seed)
        module.SEED = seed
        rows = module.generate_dataset(instruments, calibrations, interval)
    finally:
        random.setstate(state)
    for row in rows:
        row['unit'] = UNITS[row['instrument_type']]
    return rows


def protocol_for(train):
    return {'version': 'exp04_preparation_v1', 'train_calibrations': train,
        'origin': 'last training calibration per asset; fixed for all its test targets',
        'family_pool': 'training prefixes only, filtered by calendar date <= each forecast origin; includes target asset',
        'prediction_rounding_decimals': 4,
        'models': {'B0': 'last observed error', 'B1': 'mean of eligible asset endpoint slopes in same family', 'M1': 'per-asset OLS'},
        'normalization': 'prediction residual divided by positive tolerance at forecast origin',
        'pooled_metric': 'micro average of normalized forecast errors',
        'acceptance_thresholds': None}


def dataset_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def prepare_bundle(bundle, seed=42, instruments=20, calibrations=8, interval=90, train=6):
    if instruments < 1 or interval < 1 or train < 2 or calibrations <= train:
        raise ExperimentError('Need positive family size/interval and 2 <= train < calibrations')
    rows = generate_rows(seed, instruments, calibrations, interval)
    data = dataset_bytes(rows)
    manifest = {
        'kind': 'EXP04_PREPARATION_BUNDLE_V1',
        'scope': 'Known synthetic linear development data; not an independent final test',
        'seed': seed,
        'generation': {'instruments_per_family': instruments, 'calibrations_per_instrument': calibrations,
                       'interval_days': interval, 'base_start_date': '2023-01-01'},
        'generator_sha256': digest(GENERATOR.read_bytes()),
        'dataset_sha256': digest(data), 'rows': len(rows), 'instruments': 3 * instruments,
        'units': UNITS,
        'protocol': protocol_for(train),
        'python_generation': platform.python_version(),
    }
    # Never reset or overwrite an existing bundle, even a partially created one.
    bundle.mkdir(parents=True, exist_ok=False)
    with (bundle / 'dataset.csv').open('xb') as output:
        output.write(data)
    write_json(bundle / 'manifest.json', manifest)
    return manifest


def load_bundle(bundle):
    manifest_bytes = (bundle / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    data = (bundle / 'dataset.csv').read_bytes()
    if manifest.get('kind') != 'EXP04_PREPARATION_BUNDLE_V1' or manifest.get('units') != UNITS:
        raise ExperimentError('Unrecognized bundle contract or units')
    if digest(data) != manifest['dataset_sha256']:
        raise ExperimentError('Dataset checksum mismatch')
    if digest(GENERATOR.read_bytes()) != manifest['generator_sha256']:
        raise ExperimentError('Generator source differs from the recorded bundle')
    protocol = manifest['protocol']
    if protocol != protocol_for(protocol['train_calibrations']):
        raise ExperimentError('Unsupported preparation protocol; final criteria require a separate protocol')
    groups = validate_rows(list(csv.DictReader(io.StringIO(data.decode('utf-8')))), protocol['train_calibrations'])
    if sum(map(len, groups.values())) != manifest['rows'] or len(groups) != manifest['instruments']:
        raise ExperimentError('Dataset counts disagree with manifest')
    if any(len(group) != manifest['generation']['calibrations_per_instrument'] for group in groups.values()):
        raise ExperimentError('Missing calibrations relative to generation manifest')
    config = manifest['generation']
    if config.get('base_start_date') != '2023-01-01' or not isinstance(manifest['seed'], int) or isinstance(manifest['seed'], bool):
        raise ExperimentError('Invalid generation date or seed contract')
    expected = dataset_bytes(generate_rows(manifest['seed'], config['instruments_per_family'],
                                          config['calibrations_per_instrument'], config['interval_days']))
    if digest(expected) != digest(data):
        raise ExperimentError('Data does not reproduce from recorded seed and generator parameters')
    return manifest, groups, digest(manifest_bytes)


def validate_rows(raw_rows, train):
    if not isinstance(train, int) or isinstance(train, bool) or train < 2 or not raw_rows:
        raise ExperimentError('Non-empty dataset and at least two training calibrations required')
    groups, serials = defaultdict(list), {}
    for raw in raw_rows:
        try:
            row = {key: raw[key] for key in ('serial_number', 'instrument_type', 'unit')}
            row.update(instrument_id=int(raw['instrument_id']),
                       calibration_date=date.fromisoformat(raw['calibration_date']),
                       elapsed_days=float(raw['elapsed_days']), error_value=float(raw['error_value']),
                       tolerance=float(raw['tolerance']))
        except (ValueError, KeyError, TypeError):
            raise ExperimentError('Invalid or missing input fields') from None
        if row['instrument_id'] <= 0 or not row['serial_number'] or row['instrument_type'] not in UNITS or row['unit'] != UNITS[row['instrument_type']]:
            raise ExperimentError('Invalid identity, family or physical unit')
        if not all(math.isfinite(row[key]) for key in ('elapsed_days', 'error_value', 'tolerance')) or row['tolerance'] <= 0:
            raise ExperimentError('Non-finite data or invalid tolerance')
        previous = serials.setdefault(row['serial_number'], row['instrument_id'])
        if previous != row['instrument_id']:
            raise ExperimentError('Serial mapped to multiple instruments')
        groups[row['instrument_id']].append(row)
    for group in groups.values():
        group.sort(key=lambda row: row['calibration_date'])
        if len(group) <= train or len({row['calibration_date'] for row in group}) != len(group):
            raise ExperimentError('Insufficient test history or duplicate calibration date')
        first = group[0]
        for row in group:
            if any(row[key] != first[key] for key in ('serial_number', 'instrument_type', 'unit', 'tolerance')):
                raise ExperimentError('Inconsistent instrument identity, units or tolerance')
            if row['elapsed_days'] != (row['calibration_date'] - first['calibration_date']).days:
                raise ExperimentError('Elapsed time disagrees with calendar dates')
    return dict(sorted(groups.items()))


def forecast_cases(groups, train):
    # Import production kernels only, no app startup, SQL query or database connection.
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.services.analytics import DriftAnalyticsService
    from types import SimpleNamespace
    prefixes = {key: group[:train] for key, group in groups.items()}
    details = []
    for instrument_id, group in groups.items():
        history = prefixes[instrument_id]
        origin = history[-1]
        family_rows = [row for prefix in prefixes.values() for row in prefix
                       if row['instrument_type'] == origin['instrument_type']]
        eligible = [row for row in family_rows if row['calibration_date'] <= origin['calibration_date']]
        def calibration(row):
            return SimpleNamespace(instrument_unit_id=row['instrument_id'],
                                   calibration_date=row['calibration_date'], error_value=row['error_value'])
        model = DriftAnalyticsService._fit_linear_regression([calibration(row) for row in history])
        family_slope = DriftAnalyticsService._calculate_family_drift_rate([calibration(row) for row in eligible])
        for target in group[train:]:
            horizon = (target['calibration_date'] - origin['calibration_date']).days
            elapsed = (target['calibration_date'] - history[0]['calibration_date']).days
            predictions = {'B0': round(origin['error_value'], 4),
                           'B1': round(origin['error_value'] + family_slope * horizon, 4),
                           'M1': round(model['intercept'] + model['slope_per_day'] * elapsed, 4)}
            if horizon <= 0 or not all(math.isfinite(value) for value in predictions.values()):
                raise ExperimentError('Invalid horizon or non-finite model output')
            details.append({'instrument_id': instrument_id, 'serial_number': origin['serial_number'],
                            'family': origin['instrument_type'], 'unit': origin['unit'],
                            'origin_date': origin['calibration_date'].isoformat(),
                            'target_date': target['calibration_date'].isoformat(), 'horizon_days': horizon,
                            'origin_tolerance': origin['tolerance'], 'true_error': target['error_value'],
                            'predictions': predictions,
                            'family_max_date_used': max(row['calibration_date'] for row in eligible).isoformat(),
                            'family_rows_used': len(eligible),
                            'family_rows_excluded_after_origin': len(family_rows) - len(eligible)})
    return details


def metric_set(rows, normalized):
    if not rows:
        raise ExperimentError('Empty metric group')
    result = {}
    for model in MODELS:
        errors = [(row['predictions'][model] - row['true_error']) / (row['origin_tolerance'] if normalized else 1) for row in rows]
        result[model] = {'n': len(errors), 'mae': sum(abs(value) for value in errors) / len(errors),
                         'rmse': math.sqrt(sum(value ** 2 for value in errors) / len(errors))}
    return result


def summarize(details):
    families, horizons = defaultdict(list), defaultdict(list)
    for row in details:
        families[(row['family'], row['unit'], row['horizon_days'])].append(row)
        horizons[row['horizon_days']].append(row)
    return {
        'by_family_and_horizon': [{'family': family, 'unit': unit, 'horizon_days': horizon,
                                  'raw': metric_set(rows, False), 'normalized': metric_set(rows, True)}
                                 for (family, unit, horizon), rows in sorted(families.items())],
        'normalized_overall': metric_set(details, True),
        'normalized_by_horizon': [{'horizon_days': horizon, 'models': metric_set(rows, True)}
                                  for horizon, rows in sorted(horizons.items())],
    }


def evaluate_bundle(bundle, code_commit=None):
    manifest, groups, manifest_hash = load_bundle(bundle)
    identity = code_identity(code_commit)
    details = forecast_cases(groups, manifest['protocol']['train_calibrations'])
    planned = sum(len(group) - manifest['protocol']['train_calibrations'] for group in groups.values())
    if len(details) != planned or any(row['family_max_date_used'] > row['origin_date'] for row in details):
        raise ExperimentError('Incomplete forecasts or temporal leakage')
    source_files = ['experiments/run_drift_exp04.py', 'generators/generate_synthetic_drift_dataset.py',
                    'backend/app/services/analytics.py', 'backend/requirements.txt']
    report = {'experiment': 'EXP-04', 'execution_status': 'COMPLETE',
              'scope': 'Preparation check on known synthetic data; not final acceptance, model selection or industrial validation',
              'calculated_at': datetime.now(timezone.utc).isoformat(), 'git': identity,
              'python': platform.python_version(),
              'packages': {name: version(name) for name in ('sqlalchemy', 'pydantic', 'pydantic-settings')},
              'manifest_sha256': manifest_hash, 'dataset_sha256': manifest['dataset_sha256'], 'generation_reproduced_exactly': True,
              'generation': {'seed': manifest['seed'], **manifest['generation']},
              'protocol': manifest['protocol'], 'instruments': len(groups), 'planned_forecasts': planned,
              'evaluated_forecasts': len(details), 'source_sha256': {name: digest((ROOT / name).read_bytes()) for name in source_files},
              'temporal_checks': {'family_calendar_cutoff_enforced': True,
                                  'test_rows_used_for_fitting': 0,
                                  'forecasts_with_future_family_rows_excluded': sum(row['family_rows_excluded_after_origin'] > 0 for row in details)},
              'metrics': summarize(details), 'details': details}
    if digest((bundle / 'manifest.json').read_bytes()) != manifest_hash or digest((bundle / 'dataset.csv').read_bytes()) != report['dataset_sha256']:
        raise ExperimentError('Bundle changed during evaluation')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--bundle', type=Path, required=True)
    for flag, default in [('seed', 42), ('instruments', 20), ('calibrations', 8), ('interval', 90), ('train', 6)]:
        prepare.add_argument('--' + flag, type=int, default=default)
    evaluate = commands.add_parser('evaluate')
    evaluate.add_argument('--bundle', type=Path, required=True)
    evaluate.add_argument('--output', type=Path, required=True)
    evaluate.add_argument('--code-commit')
    args = parser.parse_args()
    if args.action == 'prepare':
        try:
            manifest = prepare_bundle(args.bundle, args.seed, args.instruments, args.calibrations, args.interval, args.train)
        except (OSError, ExperimentError):
            parser.error('Cannot prepare bundle: check parameters and use a new directory')
        print(f"PREPARED: {args.bundle}; SHA-256 {manifest['dataset_sha256']}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open('x', encoding='utf-8') as stream:
            try:
                report = evaluate_bundle(args.bundle, args.code_commit)
            except Exception as exc:
                report = {'experiment': 'EXP-04', 'execution_status': 'FAILED', 'metrics': None,
                          'error_type': type(exc).__name__,
                          'error': str(exc) if isinstance(exc, ExperimentError) else 'Evaluation failed; check bundle, environment and dependencies'}
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except FileExistsError:
        parser.error('Output exists; reports are never overwritten')
    print(f"{report['execution_status']}: {args.output}")
    return 0 if report['execution_status'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
