from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('exp01_runner', ROOT / 'experiments/run_extraction_exp01.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def item(name='case.pdf', truth=None):
    return {'certificate_id': 1, 'filename': name, 'ground_truth': truth or {'serial_number': 'PT-1'}}


def pdf(path, text=None):
    document = canvas.Canvas(str(path), invariant=1)
    if text:
        document.drawString(50, 750, text)
    document.showPage()
    document.save()


@pytest.mark.parametrize('field,gold,prediction', [
    ('error_value', .1, '0,100'), ('tolerance', '1.00', 1),
    ('calibration_date', '2026-10-01', '01/10/2026'), ('serial_number', 'PT-1', ' PT-1 ')])
def test_normalization_accepts_only_declared_equivalences(field, gold, prediction):
    assert runner.compare_field(field, gold, prediction)['correct']


@pytest.mark.parametrize('field,gold,prediction', [
    ('serial_number', 'PT-1', 'pt-1'), ('unit', 'bar', 'kPa'),
    ('error_value', '.3', '.30000000000000004')])
def test_normalization_does_not_repair_identity_convert_units_or_hide_numeric_error(field, gold, prediction):
    cell = runner.compare_field(field, gold, prediction)
    assert not cell['correct'] and cell['fp'] == cell['fn'] == 1


def test_wrong_missing_spurious_and_absent_values_have_distinct_counts():
    wrong = runner.compare_field('serial_number', 'PT-1', 'PT-2')
    missing = runner.compare_field('serial_number', 'PT-1', None)
    spurious = runner.compare_field('unit', None, 'bar')
    absent = runner.compare_field('unit', None, None)
    metrics = runner.metric_set([wrong, missing, spurious, absent])
    assert (metrics['tp'], metrics['fp'], metrics['fn'], metrics['tn']) == (0, 2, 2, 1)
    assert metrics['accuracy'] == .25 and metrics['potential_review_fraction'] == .75
    assert runner.metric_set([])['f1'] is None
    assert runner.metric_set([absent])['recall'] is None


def test_unannotated_fields_do_not_create_true_negatives(tmp_path):
    pdf(tmp_path / 'case.pdf', 'Serial: PT-1')
    rows = runner.evaluate_cases([item()], tmp_path, extractor=lambda path: {'serial_number': 'PT-1', 'unit': 'bar'})
    report = runner.report_for(rows)
    assert report['metrics']['micro']['annotated_slots'] == 1
    assert report['metrics']['per_field']['unit']['annotated_slots'] == 0
    assert report['details'][0]['unannotated_predictions'] == ['unit']
    assert report['metrics']['human_corrections_measured'] is None


def test_valid_blank_pdf_is_a_missed_field_not_a_success_or_execution_error(tmp_path):
    pdf(tmp_path / 'case.pdf')
    report = runner.report_for(runner.evaluate_cases([item()], tmp_path))
    assert report['execution_status'] == 'COMPLETE'
    assert report['metrics']['micro']['fn'] == 1
    assert report['metrics']['micro']['accuracy'] == 0


@pytest.mark.parametrize('mode', ['missing', 'corrupt', 'exception'])
def test_failed_pdf_is_retained_and_invalidates_final_metrics(tmp_path, mode):
    if mode == 'corrupt':
        (tmp_path / 'case.pdf').write_bytes(b'not a pdf')
    elif mode == 'exception':
        pdf(tmp_path / 'case.pdf', 'Serial: PT-1')
    pdf(tmp_path / 'good.pdf', 'Serial: PT-1')
    def extract(path):
        if Path(path).name == 'case.pdf':
            raise RuntimeError('simulated extractor error')
        return {'serial_number': 'PT-1'}
    rows = runner.evaluate_cases([item(), {**item('good.pdf'), 'certificate_id': 2}], tmp_path, extract)
    report = runner.report_for(rows)
    assert (report['planned_documents'], report['evaluated_documents'], report['errors']) == (2, 1, 1)
    assert report['execution_status'] == 'FAILED' and report['metrics'] is None
    assert report['partial_diagnostics_not_final_metrics']['micro']['annotated_slots'] == 1


def test_real_extractor_evaluates_document_text_without_chronology_validation(tmp_path):
    pdf(tmp_path / 'case.pdf', 'Calibration Date: 2099-01-01')
    rows = runner.evaluate_cases([item(truth={'calibration_date': '2099-01-01'})], tmp_path)
    assert rows[0]['fields']['calibration_date']['correct']


@pytest.mark.parametrize('prediction', ['nan', float('nan'), '31/02/2026'])
def test_invalid_prediction_remains_serializable_and_scores_wrong(prediction):
    field = 'calibration_date' if prediction == '31/02/2026' else 'error_value'
    gold = '2026-01-01' if field == 'calibration_date' else 1
    cell = runner.compare_field(field, gold, prediction)
    assert cell['invalid_prediction'] and cell['fp'] == cell['fn'] == 1
    json.dumps(cell, allow_nan=False)


@pytest.mark.parametrize('rows', [[], [item('../outside.pdf')], [item(), item()],
                                  [item(truth={'unsupported': 1})],
                                  [item(truth={'error_value': 'nan'})]])
def test_manifest_rejects_ambiguous_or_invalid_annotations(tmp_path, rows):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(rows))
    with pytest.raises(runner.ExperimentError):
        runner.load_manifest(path)


def test_existing_report_is_never_overwritten(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    output.write_text('historical')
    monkeypatch.setattr('sys.argv', ['runner', '--output', str(output)])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2 and output.read_text() == 'historical'


def test_setup_failure_has_no_metrics(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['runner', '--manifest', str(tmp_path / 'missing.json'), '--output', str(output)])
    assert runner.main() == 2
    assert json.loads(output.read_text())['execution_status'] == 'SETUP_FAILED'
