"""Isolated, dated EXP-03 preparation runner. Historical benchmark stays unchanged.

Requires a fresh PostgreSQL database named *_test and backend dependencies.
No network API/LLM/BaSyx is used: TestClient exercises upload and process routes.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
class ExperimentSetupError(ValueError):
    """Safe, actionable setup diagnostic without connection strings."""


class CaseError(ValueError):
    """Safe case diagnostic without response bodies."""


DOCUMENT_RULES = ('R-ID-01', 'R-DATE-01', 'R-DATE-02', 'R-UNIT-01',
                  'R-RANGE-01', 'R-MISSING-01')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_manifest(path):
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not rows:
        raise ExperimentSetupError('Manifest must be a non-empty list')
    names, ids = set(), set()
    for row in rows:
        name = row['filename']
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ExperimentSetupError('Manifest filenames must be plain local filenames')
        if name in names or row['certificate_id'] in ids:
            raise ExperimentSetupError('Duplicate filename or certificate_id in manifest')
        names.add(name)
        ids.add(row['certificate_id'])
        if row['expected_status'] not in ('ACCEPTED', 'REVIEW_REQUIRED'):
            raise ExperimentSetupError('Invalid expected document status')
        rules = row['expected_rules_failed']
        if not isinstance(rules, list) or any(rule not in DOCUMENT_RULES for rule in rules):
            raise ExperimentSetupError('Expected rules must belong to the declared document scope')
        if bool(rules) != (row['expected_status'] == 'REVIEW_REQUIRED'):
            raise ExperimentSetupError('Expected status and expected rules disagree')
    return rows


def scores(pairs):
    tp = sum(expected and actual for expected, actual in pairs)
    fp = sum(not expected and actual for expected, actual in pairs)
    fn = sum(expected and not actual for expected, actual in pairs)
    tn = sum(not expected and not actual for expected, actual in pairs)
    return {
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'evaluated': len(pairs),
        'positive_support': tp + fn,
        'accuracy': (tp + tn) / len(pairs) if pairs else None,
        'precision': tp / (tp + fp) if tp + fp else None,
        'recall': tp / (tp + fn) if tp + fn else None,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def summarize(details):
    evaluated = [row for row in details if row['execution_status'] == 'EVALUATED']
    rule_ids = sorted(set(DOCUMENT_RULES).union(
        rule for row in evaluated for rule in row['triggered_rules']))
    return {
        'document_detection': scores([
            (row['expected_status'] == 'REVIEW_REQUIRED', row['actual_status'] == 'REVIEW_REQUIRED')
            for row in evaluated]),
        'status_exact_match': sum(row['actual_status'] == row['expected_status'] for row in evaluated) / len(evaluated) if evaluated else None,
        'rule_set_exact_match': sum(row['expected_rules'] == row['triggered_rules'] for row in evaluated) / len(evaluated) if evaluated else None,
        'per_rule': {rule: scores([(rule in row['expected_rules'], rule in row['triggered_rules'])
                                   for row in evaluated]) for rule in rule_ids},
    }


def evaluate_cases(client, rows, batch_dir):
    """Retain one result per input. HTTP, JSON and extraction failures are errors."""
    details = []
    for item in rows:
        row = {'certificate_id': item['certificate_id'], 'filename': item['filename'],
               'expected_status': item['expected_status'],
               'expected_rules': sorted(set(item['expected_rules_failed'])),
               'execution_status': 'ERROR', 'stage': 'read_pdf'}
        details.append(row)
        try:
            path = batch_dir / item['filename']
            with path.open('rb') as stream:
                row['stage'] = 'upload'
                response = client.post('/api/v1/documents/upload',
                                       files={'file': (path.name, stream, 'application/pdf')})
            if response.status_code != 201:
                raise CaseError(f'Expected upload HTTP 201, received {response.status_code}; duplicates are not reused')
            doc_id = response.json()['document_id']
            row['document_id'] = doc_id
            row['stage'] = 'process'
            response = client.post(f'/api/v1/documents/{doc_id}/process',
                                   params={'extractor': 'deterministic'})
            if response.status_code != 200:
                raise CaseError(f'Expected process HTTP 200, received {response.status_code}')
            result = response.json()
            if result['processing_status'] not in ('ACCEPTED', 'REVIEW_REQUIRED'):
                raise CaseError('Unexpected processing status; not a negative classification')
            if result.get('extractor_used') != 'deterministic':
                raise CaseError('Experiment requires the deterministic extractor')
            if not isinstance(result['rules_failed'], list) or not all(isinstance(r, str) for r in result['rules_failed']):
                raise CaseError('Malformed rules_failed response')
            row.update(execution_status='EVALUATED', stage='complete',
                       actual_status=result['processing_status'],
                       triggered_rules=sorted({rule.split(':', 1)[0].strip() for rule in result['rules_failed']}),
                       matched_instrument_id=result['matched_instrument_id'],
                       extractor_used=result['extractor_used'])
        except Exception as exc:
            # Do not persist response bodies, connection URLs or secrets in diagnostics.
            row['error_type'] = type(exc).__name__
            row['error'] = str(exc) if isinstance(exc, CaseError) else 'Case failed; inspect the isolated API logs. No sample was dropped.'
    return details


def report_for(details):
    errors = sum(row['execution_status'] == 'ERROR' for row in details)
    summary = summarize(details)
    return {
        'execution_status': 'FAILED' if errors else 'COMPLETE',
        'planned': len(details), 'evaluated': len(details) - errors, 'errors': errors,
        'expected_rule_support': {rule: sum(rule in row['expected_rules'] for row in details) for rule in DOCUMENT_RULES},
        'metrics': None if errors else summary,
        'partial_diagnostics_not_final_metrics': summary if errors else None,
        'details': details,
    }


def validate_database_url(value):
    from sqlalchemy.engine import make_url
    url = make_url(value)
    if url.get_backend_name() != 'postgresql' or not (url.database or '').endswith('_test'):
        raise ExperimentSetupError('Requires an explicit disposable PostgreSQL DATABASE_URL named *_test')
    return url


def source_identity(code_commit=None):
    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    if code_commit is not None and not re.fullmatch(r'[0-9a-fA-F]{40}', code_commit):
        raise ExperimentSetupError('--code-commit must be a full 40-character Git SHA')
    try:
        commit = git('rev-parse', 'HEAD')
        dirty = bool(git('status', '--porcelain'))
    except (OSError, subprocess.CalledProcessError):
        if not code_commit:
            raise ExperimentSetupError('Git unavailable: supply --code-commit from the host; source hashes identify actual executed files') from None
        return {'commit': code_commit, 'working_tree_dirty': None,
                'identity_source': 'caller_supplied_not_verified; executed sources hashed separately'}
    if code_commit and code_commit != commit:
        raise ExperimentSetupError('--code-commit does not match the accessible Git checkout')
    return {'commit': commit, 'working_tree_dirty': dirty, 'identity_source': 'git_checkout'}


def provenance(manifest, catalog, rows, reference_date, code_commit=None):
    versions = {}
    for package in ('fastapi', 'sqlalchemy', 'pdfplumber', 'requests', 'httpx', 'psycopg2-binary', 'reportlab', 'starlette', 'anyio', 'pydantic'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    inputs = [{'name': 'manifest', 'sha256': sha256(manifest)},
              {'name': 'catalog', 'sha256': sha256(catalog)}]
    for row in rows:
        path = manifest.parent / row['filename']
        inputs.append({'name': row['filename'], 'sha256': sha256(path) if path.is_file() else None})
    source_files = ['experiments/run_rules_exp03.py', 'backend/app/services/document_validation.py',
                    'backend/app/services/pdf_extractor.py', 'backend/app/api/documents.py',
                    'backend/app/database/session.py', 'backend/app/core/config.py',
                    'backend/requirements.txt']
    return {'experiment': 'EXP-03', 'run_id': str(uuid.uuid4()),
            'started_at': datetime.now(timezone.utc).isoformat(),
            'reference_date': reference_date.isoformat(), 'python': platform.python_version(),
            'packages': versions, 'git': source_identity(code_commit), 'inputs': inputs,
            'input_manifest_sha256': hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
            'source_sha256': {name: sha256(ROOT / name) for name in source_files},
            'scope': 'Synthetic document detection via isolated upload/process routes; preparation run, not final acceptance',
            'excluded_rules': {'R-DUP-01': 'upload rule, not document classification',
                               'R-TOL-01': 'canonical acceptance, not document classification'},
            'metric_policy': 'Undefined denominators are null; incomplete runs have no final metrics. COMPLETE does not mean acceptance passed.'}


def execute(manifest, catalog_path, reference_date, code_commit=None):
    rows = load_manifest(manifest)
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    metadata = provenance(manifest, catalog_path, rows, reference_date, code_commit)
    value = os.environ.get('DATABASE_URL', '')
    url = validate_database_url(value)
    from sqlalchemy import create_engine, inspect
    check_engine = create_engine(url)
    try:
        # No ORM import/create_all, data write or RAW directory creation before this guard.
        if inspect(check_engine).get_table_names():
            raise ExperimentSetupError('Database must be fresh with no public tables; no cleanup or reuse is performed')
    finally:
        check_engine.dispose()

    with tempfile.TemporaryDirectory(prefix='ptwin-exp03-raw-') as raw_dir:
        os.environ['STORAGE_RAW_DIR'] = raw_dir
        sys.path.insert(0, str(ROOT / 'backend'))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import documents
        from app.database.session import Base, engine, SessionLocal
        from app.models.instrument import InstrumentType, InstrumentUnit
        from app.services.document_validation import validation_reference_date
        # A dedicated app avoids app.main startup and unrelated endpoints/services.
        Base.metadata.create_all(bind=engine)
        try:
            with SessionLocal() as db:
                types = {}
                for item in catalog['types']:
                    instance = InstrumentType(**item)
                    db.add(instance)
                    db.flush()
                    types[item['name']] = instance.id
                for item in catalog['instruments']:
                    fields = {key: val for key, val in item.items() if key != 'type'}
                    db.add(InstrumentUnit(**fields, instrument_type_id=types[item['type']],
                                          location='EXP03 isolated test catalog'))
                db.commit()
            app = FastAPI()
            app.include_router(documents.router, prefix='/api/v1')
            app.dependency_overrides[validation_reference_date] = lambda: reference_date
            with TestClient(app) as client:
                details = evaluate_cases(client, rows, manifest.parent)
            metadata.update(report_for(details))
        finally:
            engine.dispose()
    after = [{'name': entry['name'], 'sha256': sha256(path) if path.is_file() else None}
             for entry, path in zip(metadata['inputs'],
                                    [manifest, catalog_path] + [manifest.parent / row['filename'] for row in rows])]
    metadata['input_integrity'] = 'UNCHANGED' if after == metadata['inputs'] else 'CHANGED'
    if metadata['input_integrity'] == 'CHANGED':
        metadata['partial_diagnostics_not_final_metrics'] = metadata['metrics'] or metadata['partial_diagnostics_not_final_metrics']
        metadata['metrics'] = None
        metadata['execution_status'] = 'FAILED_INPUT_CHANGED'
    metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'generators/test_certificates_batch/ground_truth.json')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'experiments/fixtures/exp03-catalog.json')
    parser.add_argument('--reference-date', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--code-commit', help='Host Git SHA when running in an image without Git')
    args = parser.parse_args()
    # Reserve output before any DB mutation; refuse to overwrite historical evidence.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open('x', encoding='utf-8') as stream:
            try:
                report = execute(args.manifest.resolve(), args.catalog.resolve(), args.reference_date, args.code_commit)
            except Exception as exc:
                report = {'experiment': 'EXP-03', 'execution_status': 'SETUP_FAILED',
                          'error_type': type(exc).__name__,
                          'error': str(exc) if isinstance(exc, ExperimentSetupError) else 'Setup failed. Check fresh *_test database, manifest and catalog; no final metrics.',
                          'metrics': None}
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except FileExistsError:
        parser.error('Output exists: choose a new run filename; reports are never overwritten')
    print(f"{report['execution_status']}: {args.output}")
    return 0 if report['execution_status'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
