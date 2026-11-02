"""Controls that prevent partial, stale or mislabeled EXP-03 evidence."""
from datetime import date
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('exp03_runner', ROOT / 'experiments/run_rules_exp03.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def item(name='test.pdf', rules=None):
    rules = rules or []
    return {'certificate_id': 1, 'filename': name,
            'expected_status': 'REVIEW_REQUIRED' if rules else 'ACCEPTED',
            'expected_rules_failed': rules}


class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)

    def post(self, *args, **kwargs):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def success(rules=None):
    rules = rules or []
    return Response(200, {'processing_status': 'REVIEW_REQUIRED' if rules else 'ACCEPTED',
                          'rules_failed': rules, 'matched_instrument_id': 7,
                          'extractor_used': 'deterministic'})


def test_clock_can_be_fixed_without_changing_default(monkeypatch):
    from app.services import document_validation as validation
    instrument = SimpleNamespace(id=7, serial_number='PT-001')

    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return instrument

    db = SimpleNamespace(query=lambda model: Query())
    fields = {'serial_number': 'PT-001', 'calibration_date': '2026-10-31'}
    monkeypatch.setattr(validation, 'validation_reference_date', lambda: date(2026, 11, 1))
    assert validation.validate_document_fields(db, fields)[1] == []
    assert any(rule.startswith('R-DATE-01:') for rule in validation.validate_document_fields(
        db, fields, reference_date=date(2026, 10, 1))[1])
    assert validation.validate_document_fields(db, fields, reference_date=date(2026, 10, 31))[1] == []


def test_rule_metrics_include_false_matches_and_undefined_support():
    rows = [dict(execution_status='EVALUATED', expected_status='REVIEW_REQUIRED',
                 actual_status='REVIEW_REQUIRED', expected_rules=['R-ID-01'],
                 triggered_rules=['R-DATE-01'])]
    result = runner.summarize(rows)
    assert result['document_detection']['f1'] == 1
    assert result['rule_set_exact_match'] == 0
    assert result['per_rule']['R-ID-01']['fn'] == 1
    assert result['per_rule']['R-DATE-01']['fp'] == 1
    assert result['per_rule']['R-UNIT-01']['recall'] is None
    assert result['per_rule']['R-UNIT-01']['precision'] is None


@pytest.mark.parametrize('failure', [Response(409, {}), Response(500, {}), TimeoutError()])
def test_upload_failures_are_retained_and_never_reuse_duplicates(tmp_path, failure):
    (tmp_path / 'test.pdf').write_bytes(b'fixture')
    rows = runner.evaluate_cases(Client([failure]), [item()], tmp_path)
    report = runner.report_for(rows)
    assert len(rows) == report['planned'] == report['errors'] == 1
    assert report['execution_status'] == 'FAILED'
    assert report['metrics'] is None
    assert report['details'][0]['stage'] == 'upload'


@pytest.mark.parametrize('failure', [Response(422, {}), Response(200, {}),
                                    Response(200, {'processing_status': 'FAILED_EXTRACTION'})])
def test_process_failures_are_not_true_negatives(tmp_path, failure):
    (tmp_path / 'test.pdf').write_bytes(b'fixture')
    rows = runner.evaluate_cases(Client([Response(201, {'document_id': 1}), failure]), [item()], tmp_path)
    assert runner.report_for(rows)['evaluated'] == 0
    assert rows[0]['stage'] == 'process'


def test_missing_case_does_not_disappear_and_other_cases_are_evaluated(tmp_path):
    (tmp_path / 'valid.pdf').write_bytes(b'fixture')
    rows = [item('missing.pdf'), {**item('valid.pdf'), 'certificate_id': 2}]
    report = runner.report_for(runner.evaluate_cases(
        Client([Response(201, {'document_id': 1}), success()]), rows, tmp_path))
    assert (report['planned'], report['evaluated'], report['errors']) == (2, 1, 1)
    assert report['metrics'] is None
    assert report['partial_diagnostics_not_final_metrics']['document_detection']['tn'] == 1


def test_classification_error_is_complete_evidence_not_an_execution_failure(tmp_path):
    (tmp_path / 'test.pdf').write_bytes(b'fixture')
    rows = runner.evaluate_cases(Client([Response(201, {'document_id': 1}), success()]),
                                 [item(rules=['R-ID-01'])], tmp_path)
    report = runner.report_for(rows)
    assert report['execution_status'] == 'COMPLETE'
    assert report['metrics']['document_detection']['fn'] == 1
    assert report['metrics']['per_rule']['R-ID-01']['recall'] == 0


@pytest.mark.parametrize('value', ['postgresql://localhost/passporttwin', 'sqlite:///x_test'])
def test_rejects_operational_database_names(value):
    with pytest.raises(ValueError, match='disposable'):
        runner.validate_database_url(value)


@pytest.mark.parametrize('rows', [[], [item('../escape.pdf')], [item(), item()],
                                  [dict(item(), expected_rules_failed=['R-TOL-01'])]])
def test_manifest_rejects_empty_unsafe_duplicate_and_out_of_scope_cases(tmp_path, rows):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        runner.load_manifest(path)


def test_existing_report_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / 'report.json'
    path.write_text('historical')
    monkeypatch.setattr('sys.argv', ['runner', '--reference-date', '2026-10-01', '--output', str(path)])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert path.read_text() == 'historical'


def test_setup_failure_leaves_structured_report(tmp_path, monkeypatch):
    path = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['runner', '--reference-date', '2026-10-01', '--output', str(path)])
    monkeypatch.setattr(runner, 'execute', lambda *args: (_ for _ in ()).throw(ValueError('bad setup')))
    assert runner.main() == 2
    report = json.loads(path.read_text())
    assert report['execution_status'] == 'SETUP_FAILED'
    assert report['metrics'] is None


def test_host_commit_required_when_git_is_not_available(monkeypatch):
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(ValueError, match='Git unavailable'):
        runner.source_identity()
    result = runner.source_identity('a' * 40)
    assert result['commit'] == 'a' * 40
    assert result['working_tree_dirty'] is None


def test_reference_date_is_not_a_public_request_parameter():
    from fastapi import FastAPI
    from app.api.documents import router
    app = FastAPI()
    app.include_router(router)
    for path in ('/documents/{document_id}/process', '/documents/{document_id}/revalidate'):
        params = app.openapi()['paths'][path]['post']['parameters']
        assert 'reference_date' not in {parameter['name'] for parameter in params}
