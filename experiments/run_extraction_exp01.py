"""Offline field-level EXP-01 preparation; no matching, rules or human corrections."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('serial_number', 'calibration_date', 'next_due_date', 'error_value',
          'tolerance', 'unit', 'operating_range')


class ExperimentError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(field, value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('Unsupported field value')
    text = str(value).strip()
    if field in ('error_value', 'tolerance'):
        try:
            number = Decimal(text.replace(',', '.'))
        except InvalidOperation:
            raise ValueError('Invalid numeric value') from None
        if not number.is_finite():
            raise ValueError('Non-finite numeric value')
        return number
    if field in ('calibration_date', 'next_due_date'):
        for pattern in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(text, pattern).date().isoformat()
            except ValueError:
                pass
        raise ValueError('Invalid calendar date')
    return text  # Case and punctuation retained; no unit conversions or identity repair.


def load_manifest(path):
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not rows:
        raise ExperimentError('Manifest must be a non-empty list')
    names, ids = set(), set()
    for row in rows:
        name = row['filename']
        if not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name:
            raise ExperimentError('PDF filename must be a plain local filename')
        if name in names or row['certificate_id'] in ids:
            raise ExperimentError('Duplicate filename or certificate identifier')
        names.add(name)
        ids.add(row['certificate_id'])
        truth = row['ground_truth']
        if not isinstance(truth, dict) or not truth or any(field not in FIELDS for field in truth):
            raise ExperimentError('Ground truth must explicitly annotate supported fields')
        for field, value in truth.items():
            try:
                normalize(field, value)
            except ValueError:
                raise ExperimentError('Invalid ground-truth value; fix annotations before evaluation') from None
    return rows


def compare_field(field, expected, actual):
    gold = normalize(field, expected)
    invalid = False
    try:
        predicted = normalize(field, actual)
    except ValueError:
        predicted, invalid = None, True
    expected_present = gold is not None
    actual_present = predicted is not None or invalid
    correct = not invalid and predicted == gold
    stored_actual = actual if isinstance(actual, (str, int, float, bool, type(None))) else repr(actual)
    if isinstance(stored_actual, float) and not math.isfinite(stored_actual):
        stored_actual = str(stored_actual)
    return {'expected': expected, 'actual': stored_actual, 'correct': correct,
            'expected_present': expected_present, 'actual_present': actual_present,
            'invalid_prediction': invalid,
            'tp': int(expected_present and actual_present and correct),
            'fp': int(actual_present and not correct),
            'fn': int(expected_present and not correct),
            'tn': int(not expected_present and not actual_present)}


def metric_set(cells):
    tp, fp, fn, tn = (sum(cell[key] for cell in cells) for key in ('tp', 'fp', 'fn', 'tn'))
    return {'annotated_slots': len(cells), 'expected_present': sum(cell['expected_present'] for cell in cells),
            'exact_matches': sum(cell['correct'] for cell in cells),
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'accuracy': sum(cell['correct'] for cell in cells) / len(cells) if cells else None,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            'potential_review_fraction': sum(not cell['correct'] for cell in cells) / len(cells) if cells else None}


def evaluate_cases(rows, batch_dir, extractor=None):
    sys.path.insert(0, str(ROOT / 'backend'))
    import pdfplumber
    if extractor is None:
        from app.services.pdf_extractor import PDFCertificateExtractor
        extractor = PDFCertificateExtractor.extract_and_parse
    details = []
    for item in rows:
        row = {'certificate_id': item['certificate_id'], 'filename': item['filename'],
               'execution_status': 'ERROR', 'stage': 'read_pdf'}
        details.append(row)
        try:
            path = batch_dir / item['filename']
            # Corrupt/unreadable PDF is an execution error; valid blank PDF is scored as missed fields.
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    raise ValueError('PDF has no pages')
            row['stage'] = 'extract'
            extracted = extractor(str(path))
            if not isinstance(extracted, dict):
                raise ValueError('Extractor did not return a mapping')
            row['fields'] = {field: compare_field(field, expected, extracted.get(field))
                             for field, expected in item['ground_truth'].items()}
            row['unannotated_predictions'] = sorted(field for field in FIELDS
                                                    if field in extracted and field not in item['ground_truth'])
            row.update(execution_status='EVALUATED', stage='complete')
        except Exception as exc:
            row.pop('fields', None)
            row['error_type'] = type(exc).__name__
            row['error'] = 'PDF case failed; retained in planned count, no final metrics for incomplete runs'
    return details


def summarize(details):
    evaluated = [row for row in details if row['execution_status'] == 'EVALUATED']
    per_field = {field: metric_set([row['fields'][field] for row in evaluated if field in row['fields']])
                 for field in FIELDS}
    cells = [cell for row in evaluated for cell in row['fields'].values()]
    return {'per_field': per_field, 'micro': metric_set(cells),
            'documents_all_annotated_fields_correct': sum(all(cell['correct'] for cell in row['fields'].values()) for row in evaluated),
            'human_corrections_measured': None}


def report_for(details):
    errors = sum(row['execution_status'] == 'ERROR' for row in details)
    metrics = summarize(details)
    return {'execution_status': 'FAILED' if errors else 'COMPLETE',
            'planned_documents': len(details), 'evaluated_documents': len(details) - errors,
            'errors': errors, 'metrics': None if errors else metrics,
            'partial_diagnostics_not_final_metrics': metrics if errors else None, 'details': details}


def code_identity(commit=None):
    if commit is not None and not re.fullmatch('[0-9a-fA-F]{40}', commit):
        raise ExperimentError('--code-commit requires a full Git SHA')
    try:
        found = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        if not commit:
            raise ExperimentError('Git unavailable: pass --code-commit from host') from None
        return {'commit': commit, 'working_tree_dirty': None, 'source': 'caller_supplied_not_verified'}
    if commit and commit != found:
        raise ExperimentError('Provided commit differs from checkout')
    return {'commit': found, 'working_tree_dirty': dirty, 'source': 'git_checkout'}


def input_hashes(manifest, rows):
    return {'manifest': sha256(manifest), 'pdfs': {
        row['filename']: sha256(manifest.parent / row['filename']) if (manifest.parent / row['filename']).is_file() else None
        for row in rows}}


def execute(manifest, commit=None):
    rows = load_manifest(manifest)
    inputs = input_hashes(manifest, rows)
    identity = code_identity(commit)
    details = evaluate_cases(rows, manifest.parent)
    report = report_for(details)
    source_files = ['experiments/run_extraction_exp01.py', 'backend/app/services/pdf_extractor.py',
                    'backend/app/core/config.py', 'backend/requirements.txt']
    report.update(experiment='EXP-01', scope='Synthetic deterministic PDF extraction preparation; not final acceptance',
                  calculated_at=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                  packages={name: version(name) for name in ('pdfplumber', 'pdfminer.six', 'pydantic', 'pydantic-settings')},
                  git=identity, inputs=inputs, input_manifest_sha256=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                  source_sha256={name: sha256(ROOT / name) for name in source_files},
                  planned_annotated_slots=sum(len(row['ground_truth']) for row in rows),
                  extractor='production_deterministic_pdf',
                  baseline_comparison={'status': 'NOT_EVALUATED', 'reason': 'No independent manual or alternative extractor baseline measured'},
                  comparison_policy={'version': 'exp01_preparation_v1',
                      'text': 'strip outer whitespace; case and punctuation preserved; no unit conversion',
                      'dates': 'calendar-valid ISO or DD/MM/YYYY normalized to ISO; no chronology rules',
                      'numbers': 'exact finite Decimal equality; decimal comma normalized; no numerical tolerance',
                      'wrong_present_value': 'one FP and one FN when gold present',
                      'unannotated_fields': 'excluded, never counted as true negatives',
                      'undefined_denominators': None,
                      'review_fraction': 'disagreeing annotated slots / annotated slots, not measured human edits',
                      'acceptance_thresholds': None})
    report['input_integrity'] = 'UNCHANGED' if input_hashes(manifest, rows) == inputs else 'CHANGED'
    if report['input_integrity'] == 'CHANGED':
        report['partial_diagnostics_not_final_metrics'] = report['metrics'] or report['partial_diagnostics_not_final_metrics']
        report['metrics'] = None
        report['execution_status'] = 'FAILED_INPUT_CHANGED'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'generators/test_certificates_batch/ground_truth.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--code-commit')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open('x', encoding='utf-8') as stream:
            try:
                report = execute(args.manifest.resolve(), args.code_commit)
            except Exception as exc:
                report = {'experiment': 'EXP-01', 'execution_status': 'SETUP_FAILED', 'metrics': None,
                          'error_type': type(exc).__name__,
                          'error': str(exc) if isinstance(exc, ExperimentError) else 'Setup failed; check manifest and environment'}
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except FileExistsError:
        parser.error('Output exists; reports are never overwritten')
    print(f"{report['execution_status']}: {args.output}")
    return 0 if report['execution_status'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
