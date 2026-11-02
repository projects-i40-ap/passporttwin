"""Temporal isolation, physical units and artifact integrity for EXP-04."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('exp04_runner', ROOT / 'experiments/run_drift_exp04.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def series(instrument=1, start=0, family='pressure_transmitter', scale=1):
    return [dict(instrument_id=str(instrument), serial_number=f'SYN-{instrument}',
                 instrument_type=family, unit=runner.UNITS[family],
                 calibration_date=(date(2024, 1, 1) + timedelta(days=start + i * 10)).isoformat(),
                 elapsed_days=str(i * 10), error_value=str((i + 1) * scale), tolerance=str(10 * scale))
            for i in range(4)]


def forecasts(rows, train=3):
    return runner.forecast_cases(runner.validate_rows(rows, train), train)


def test_preparation_reproduces_identical_bytes_and_preserves_rng(tmp_path):
    state = random.getstate()
    a, b = tmp_path / 'a', tmp_path / 'b'
    runner.prepare_bundle(a, instruments=2)
    runner.prepare_bundle(b, instruments=2)
    assert random.getstate() == state
    assert (a / 'dataset.csv').read_bytes() == (b / 'dataset.csv').read_bytes()
    assert (a / 'manifest.json').read_bytes() == (b / 'manifest.json').read_bytes()
    manifest, groups, _ = runner.load_bundle(a)
    assert manifest['rows'] == 48 and len(groups) == 6
    with pytest.raises(FileExistsError):
        runner.prepare_bundle(a)


def test_future_peer_training_observation_cannot_change_earlier_forecast():
    rows = series(1) + series(2, start=5)
    before = forecasts(rows)
    # Peer day 25 is in its own training prefix, but after asset 1 origin day 20.
    changed = deepcopy(rows)
    changed[6]['error_value'] = '999999'
    after = forecasts(changed)
    target_before = next(row for row in before if row['instrument_id'] == 1)
    target_after = next(row for row in after if row['instrument_id'] == 1)
    assert target_before['predictions'] == target_after['predictions']
    assert target_before['family_rows_excluded_after_origin'] == 1
    assert all(row['family_max_date_used'] <= row['origin_date'] for row in before)


def test_test_labels_and_simulator_truth_never_enter_any_forecast():
    rows = series(1) + series(2, start=5)
    before = forecasts(rows)
    changed = deepcopy(rows)
    for i in (3, 7):
        changed[i]['error_value'] = '123456'
    for row in changed:
        row['true_drift_rate_per_day'] = '99999'
    after = forecasts(changed)
    assert [row['predictions'] for row in before] == [row['predictions'] for row in after]
    assert before[0]['true_error'] != after[0]['true_error']


def test_normalized_metrics_are_unitless_and_raw_metrics_stay_separate():
    rows = series(1) + series(2, family='temperature_sensor', scale=100)
    details = forecasts(rows)
    metrics = runner.summarize(details)
    assert 'raw_overall' not in metrics
    groups = metrics['by_family_and_horizon']
    assert {group['unit'] for group in groups} == {'bar', '°C'}
    for model in runner.MODELS:
        assert groups[0]['normalized'][model]['mae'] == pytest.approx(groups[1]['normalized'][model]['mae'])
        assert metrics['normalized_overall'][model]['n'] == 2
    assert metrics['normalized_overall']['M1']['mae'] == pytest.approx(0)
    assert metrics['normalized_overall']['B0']['mae'] == pytest.approx(.1)


def test_all_models_match_production_at_90_days():
    from app.services.analytics import DriftAnalyticsService
    rows = series()
    for i, row in enumerate(rows):
        row['calibration_date'] = (date(2024, 1, 1) + timedelta(days=i * 90)).isoformat()
        row['elapsed_days'] = str(i * 90)
    group = runner.validate_rows(rows, 3)[1]
    history = [SimpleNamespace(instrument_unit_id=1, calibration_date=row['calibration_date'],
                               error_value=row['error_value'], tolerance=row['tolerance']) for row in group[:3]]
    instrument = SimpleNamespace(id=1, serial_number='SYN-1', lifecycle_state='operational')
    production = DriftAnalyticsService.calculate_drift_and_risk(instrument, history, history)['drift_models']
    result = runner.forecast_cases({1: group}, 3)[0]
    assert result['horizon_days'] == 90
    assert result['predictions'] == {name: model['predictions']['90_days'] for name, model in production.items()}


@pytest.mark.parametrize('field,value', [('error_value', 'nan'), ('tolerance', '0'),
                                        ('elapsed_days', '11'), ('unit', 'pH'),
                                        ('calibration_date', 'invalid')])
def test_invalid_rows_are_rejected_not_skipped(field, value):
    rows = series()
    rows[1][field] = value
    with pytest.raises(runner.ExperimentError):
        runner.validate_rows(rows, 3)


def test_duplicate_dates_or_insufficient_history_fail():
    rows = series()
    rows[1]['calibration_date'] = rows[0]['calibration_date']
    with pytest.raises(runner.ExperimentError):
        runner.validate_rows(rows, 3)
    with pytest.raises(runner.ExperimentError):
        runner.validate_rows(series()[:3], 3)


def test_changed_dataset_hash_is_detected(tmp_path):
    runner.prepare_bundle(tmp_path / 'bundle', instruments=1)
    data = tmp_path / 'bundle/dataset.csv'
    data.write_bytes(data.read_bytes() + b'\n')
    with pytest.raises(runner.ExperimentError, match='checksum'):
        runner.load_bundle(tmp_path / 'bundle')


def test_seed_claim_must_reproduce_the_dataset(tmp_path):
    bundle = tmp_path / 'bundle'
    runner.prepare_bundle(bundle, instruments=1)
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['seed'] = 7
    path.write_text(json.dumps(manifest))
    with pytest.raises(runner.ExperimentError, match='reproduce'):
        runner.load_bundle(bundle)


def test_preparation_protocol_cannot_be_silently_relabeled(tmp_path):
    bundle = tmp_path / 'bundle'
    runner.prepare_bundle(bundle, instruments=1)
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['protocol']['models']['B1'] = 'Another method'
    path.write_text(json.dumps(manifest))
    with pytest.raises(runner.ExperimentError, match='protocol'):
        runner.load_bundle(bundle)


def test_existing_output_is_preserved(tmp_path, monkeypatch):
    output = tmp_path / 'result.json'
    output.write_text('historical')
    monkeypatch.setattr('sys.argv', ['runner', 'evaluate', '--bundle', str(tmp_path), '--output', str(output)])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert output.read_text() == 'historical'


def test_failed_run_has_no_metrics_and_nonzero_exit(tmp_path, monkeypatch):
    output = tmp_path / 'result.json'
    monkeypatch.setattr('sys.argv', ['runner', 'evaluate', '--bundle', str(tmp_path / 'missing'), '--output', str(output)])
    assert runner.main() == 2
    report = json.loads(output.read_text())
    assert report['execution_status'] == 'FAILED' and report['metrics'] is None


def test_manifest_cannot_claim_another_start_date(tmp_path):
    bundle = tmp_path / 'bundle'
    runner.prepare_bundle(bundle, instruments=1)
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['generation']['base_start_date'] = '2025-01-01'
    path.write_text(json.dumps(manifest))
    with pytest.raises(runner.ExperimentError, match='generation date'):
        runner.load_bundle(bundle)
