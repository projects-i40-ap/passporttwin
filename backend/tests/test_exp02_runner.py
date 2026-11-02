from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('exp02_runner', ROOT / 'experiments/run_matching_exp02.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
FIXTURE = ROOT / 'experiments/fixtures/exp02-preparation.json'


def case(name='sample', target='PT-1', scenario='known_serial'):
    return {'case_id': name, 'scenario': scenario, 'pdf_lines': ['Serial: PT-1'],
            'expected_target': target, 'expected_matching_review': target is None}


def evaluated(target, actual, review=False, scenario='known_serial'):
    return dict(case(target=target, scenario=scenario), execution_status='EVALUATED',
                actual_target=actual, baseline_target=actual, matching_review=review,
                document_review_all_rules=review)


def test_false_links_and_wrong_target_links_are_not_correct_abstentions():
    rows = [evaluated('PT-1', 'PT-1'), evaluated(None, None, True),
            evaluated(None, 'PT-1', scenario='ambiguous_document'), evaluated('PT-1', 'PT-2')]
    metrics = runner.summarize(rows)
    assert metrics['system']['false_links'] == 2
    assert metrics['system']['correct_abstentions'] == 1
    assert metrics['system']['link_or_abstention_accuracy'] == .5
    assert metrics['system']['link_precision'] == pytest.approx(1/3)
    assert metrics['system']['link_recall'] == .5
    assert metrics['matching_review_misses'] == 1
    assert metrics['improvement_claim'] is None


def test_link_and_all_rule_review_are_distinct(tmp_path):
    item = case()
    paths = runner.materialize_cases({'cases': [item]}, tmp_path)
    rows = runner.evaluate_cases([item], paths, SimpleNamespace(rollback=lambda: None), {'PT-1'},
                                 extractor=lambda path: {'serial_number': 'PT-1'},
                                 validator=lambda **kwargs: (SimpleNamespace(serial_number='PT-1'), ['R-DATE-02: Invalid due date']))
    assert rows[0]['actual_target'] == 'PT-1'
    assert rows[0]['matching_review'] is False and rows[0]['document_review_all_rules'] is True


def test_ambiguous_document_first_serial_failure_is_visible(tmp_path):
    item = case(target=None, scenario='ambiguous_document')
    item['pdf_lines'] = ['Serial: PT-1', 'Serial: PT-2']
    paths = runner.materialize_cases({'cases': [item]}, tmp_path)
    rows = runner.evaluate_cases([item], paths, SimpleNamespace(rollback=lambda: None), {'PT-1', 'PT-2'},
                                 extractor=lambda path: {'serial_number': 'PT-1'},
                                 validator=lambda db, fields: (SimpleNamespace(serial_number=fields['serial_number']), []))
    report = runner.report_for(rows)
    assert report['execution_status'] == 'COMPLETE'
    assert rows[0]['extracted_serial'] == 'PT-1'
    assert report['metrics']['system']['false_links'] == 1
    assert report['metrics']['matching_review_misses'] == 1


def test_pdf_materialization_is_deterministic(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    a.mkdir(); b.mkdir()
    protocol = {'cases': [case()]}
    first = runner.materialize_cases(protocol, a)['sample']
    second = runner.materialize_cases(protocol, b)['sample']
    assert runner.sha256(first) == runner.sha256(second)


def test_missing_case_is_retained_without_final_metrics(tmp_path):
    item = case()
    rows = runner.evaluate_cases([item], {'sample': tmp_path/'missing.pdf'},
                                 SimpleNamespace(rollback=lambda: None), {'PT-1'},
                                 extractor=lambda path: {}, validator=lambda **kwargs: (None, []))
    report = runner.report_for(rows)
    assert (report['planned'], report['evaluated'], report['errors']) == (1, 0, 1)
    assert report['metrics'] is None
    assert report['partial_diagnostics_not_final_metrics']['system']['link_precision'] is None


def test_rollback_failure_cannot_drop_an_error_case(tmp_path):
    def broken():
        raise RuntimeError('unavailable connection')
    item = case()
    rows = runner.evaluate_cases([item], {'sample': tmp_path/'missing.pdf'},
                                 SimpleNamespace(rollback=broken), set(), extractor=lambda path: {})
    assert len(rows) == 1 and rows[0]['rollback_error_type'] == 'RuntimeError'


@pytest.mark.parametrize('mutation', ['duplicate_catalog', 'unknown_target', 'duplicate_case', 'unsafe_path', 'review_label'])
def test_protocol_rejects_inconsistent_reference_labels(tmp_path, mutation):
    protocol = json.loads(FIXTURE.read_text())
    if mutation == 'duplicate_catalog':
        protocol['catalog'].append(deepcopy(protocol['catalog'][0]))
    elif mutation == 'unknown_target':
        protocol['cases'][0]['expected_target'] = 'NOT-IN-CATALOG'
    elif mutation == 'duplicate_case':
        protocol['cases'].append(deepcopy(protocol['cases'][0]))
    elif mutation == 'unsafe_path':
        protocol['cases'][0]['pdf_filename'] = '../outside.pdf'
    else:
        protocol['cases'][0]['expected_matching_review'] = True
    path = tmp_path/'protocol.json'
    path.write_text(json.dumps(protocol))
    with pytest.raises(runner.ExperimentError):
        runner.load_protocol(path)


@pytest.mark.parametrize('url', ['postgresql://localhost/passporttwin', 'sqlite:///x_test'])
def test_operational_database_is_rejected(url):
    with pytest.raises(runner.ExperimentError):
        runner.validate_database_url(url)


def test_existing_report_is_preserved(tmp_path, monkeypatch):
    path = tmp_path/'report.json'
    path.write_text('historical')
    monkeypatch.setattr('sys.argv', ['runner', '--output', str(path)])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2 and path.read_text() == 'historical'


def test_setup_failure_has_no_metrics(tmp_path, monkeypatch):
    path = tmp_path/'report.json'
    monkeypatch.setattr('sys.argv', ['runner', '--protocol', str(tmp_path/'missing'), '--output', str(path)])
    assert runner.main() == 2
    assert json.loads(path.read_text())['metrics'] is None
