"""EXP-02 preparation using real extraction and SQL matching on a fresh *_test DB."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'generators/test_certificates_batch'


class ExperimentError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_protocol(path):
    protocol = json.loads(path.read_text(encoding='utf-8'))
    if protocol['version'] != 'exp02_preparation_v1' or protocol['acceptance_thresholds'] is not None:
        raise ExperimentError('Unsupported preparation contract')
    catalog, cases = protocol['catalog'], protocol['cases']
    serials = [row['serial_number'] for row in catalog]
    if not catalog or len(set(serials)) != len(serials) or not cases:
        raise ExperimentError('Need a non-empty catalog with unique serials and non-empty cases')
    for row in catalog:
        if not isinstance(row['serial_number'], str) or not row['serial_number'] or row['family'] not in protocol['families']:
            raise ExperimentError('Invalid catalog identity or family')
    ids = set()
    for case in cases:
        name = case['case_id']
        if not re.fullmatch('[a-zA-Z0-9_-]+', name) or name in ids:
            raise ExperimentError('Case identifiers must be unique and safe filenames')
        ids.add(name)
        if ('pdf_filename' in case) == ('pdf_lines' in case):
            raise ExperimentError('Each case must have exactly one PDF source')
        if 'pdf_filename' in case:
            name = case['pdf_filename']
            if not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name:
                raise ExperimentError('PDF filename must be a plain local filename')
        elif not isinstance(case['pdf_lines'], list) or not case['pdf_lines'] or not all(isinstance(line, str) for line in case['pdf_lines']):
            raise ExperimentError('Synthetic PDF lines must be non-empty text')
        if case['expected_target'] is not None and case['expected_target'] not in serials:
            raise ExperimentError('Expected target absent from reference catalog')
        if type(case['expected_matching_review']) is not bool or case['expected_matching_review'] != (case['expected_target'] is None):
            raise ExperimentError('Preparation labels require review for abstention cases')
    return protocol


def render_pdf(case, path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    pdf = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    pdf.setTitle(case['case_id'])
    for index, line in enumerate(case['pdf_lines']):
        pdf.drawString(50, 750 - 25 * index, line)
    pdf.save()


def materialize_cases(protocol, folder):
    paths = {}
    for case in protocol['cases']:
        if 'pdf_filename' in case:
            paths[case['case_id']] = BATCH / case['pdf_filename']
        else:
            path = folder / (case['case_id'] + '.pdf')
            render_pdf(case, path)
            paths[case['case_id']] = path
    return paths


def evaluate_cases(cases, paths, db, catalog_serials, extractor=None, validator=None):
    import pdfplumber
    if extractor is None:
        from app.services.pdf_extractor import PDFCertificateExtractor
        extractor = PDFCertificateExtractor.extract_and_parse
    if validator is None:
        from app.services.document_validation import validate_document_fields
        validator = validate_document_fields
    details = []
    for case in cases:
        row = {'case_id': case['case_id'], 'scenario': case['scenario'],
               'expected_target': case['expected_target'], 'expected_matching_review': case['expected_matching_review'],
               'execution_status': 'ERROR', 'stage': 'read_pdf'}
        details.append(row)
        try:
            path = paths[case['case_id']]
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    raise ValueError('No PDF pages')
            row['stage'] = 'extract'
            fields = extractor(str(path))
            if not isinstance(fields, dict):
                raise ValueError('Extractor did not return a mapping')
            row['stage'] = 'match'
            target, rules = validator(db=db, fields=fields)
            serial = fields.get('serial_number')
            row.update(execution_status='EVALUATED', stage='complete', extracted_serial=serial,
                       actual_target=target.serial_number if target is not None else None,
                       baseline_target=serial if serial in catalog_serials else None,
                       matching_review=not bool(serial) or any(rule.startswith('R-ID-01:') for rule in rules),
                       document_review_all_rules=bool(rules), rules_failed=rules)
        except Exception as exc:
            try:
                db.rollback()
            except Exception as rollback_error:
                row['rollback_error_type'] = type(rollback_error).__name__
            row['error_type'] = type(exc).__name__
            row['error'] = 'Case failed and retained; incomplete runs have no final metrics'
    return details


def link_metrics(rows, target_key):
    assigned = sum(row[target_key] is not None for row in rows)
    expected = sum(row['expected_target'] is not None for row in rows)
    correct_links = sum(row[target_key] is not None and row[target_key] == row['expected_target'] for row in rows)
    false_links = sum(row[target_key] is not None and row[target_key] != row['expected_target'] for row in rows)
    return {'evaluated': len(rows), 'expected_links': expected, 'assigned_links': assigned,
            'correct_links': correct_links, 'false_links': false_links,
            'correct_abstentions': sum(row[target_key] is None and row['expected_target'] is None for row in rows),
            'link_or_abstention_accuracy': sum(row[target_key] == row['expected_target'] for row in rows) / len(rows) if rows else None,
            'link_precision': correct_links / assigned if assigned else None,
            'link_recall': correct_links / expected if expected else None,
            'false_link_fraction_of_assignments': false_links / assigned if assigned else None,
            'abstention_rate': (len(rows) - assigned) / len(rows) if rows else None}


def summarize(details):
    rows = [row for row in details if row['execution_status'] == 'EVALUATED']
    return {'system': link_metrics(rows, 'actual_target'), 'exact_serial_baseline': link_metrics(rows, 'baseline_target'),
            'baseline_same_policy_as_system': True, 'improvement_claim': None,
            'baseline_agrees_with_system': all(row['baseline_target'] == row['actual_target'] for row in rows) if rows else None,
            'matching_review_rate': sum(row['matching_review'] for row in rows) / len(rows) if rows else None,
            'document_review_rate_all_rules': sum(row['document_review_all_rules'] for row in rows) / len(rows) if rows else None,
            'matching_review_misses': sum(row['expected_matching_review'] and not row['matching_review'] for row in rows),
            'by_scenario': {scenario: link_metrics([row for row in rows if row['scenario'] == scenario], 'actual_target')
                            for scenario in sorted({row['scenario'] for row in details})}}


def report_for(details):
    errors = sum(row['execution_status'] == 'ERROR' for row in details)
    metrics = summarize(details)
    return {'execution_status': 'FAILED' if errors else 'COMPLETE', 'planned': len(details),
            'evaluated': len(details) - errors, 'errors': errors,
            'metrics': None if errors else metrics,
            'partial_diagnostics_not_final_metrics': metrics if errors else None, 'details': details}


def code_identity(commit=None):
    if commit is not None and not re.fullmatch('[0-9a-fA-F]{40}', commit):
        raise ExperimentError('--code-commit requires a full Git SHA')
    try:
        found = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        if not commit:
            raise ExperimentError('Git unavailable: supply --code-commit from host') from None
        return {'commit': commit, 'working_tree_dirty': None, 'source': 'caller_supplied_not_verified'}
    if commit and commit != found:
        raise ExperimentError('Provided commit differs from checkout')
    return {'commit': found, 'working_tree_dirty': dirty, 'source': 'git_checkout'}


def validate_database_url(value):
    from sqlalchemy.engine import make_url
    url = make_url(value)
    if url.get_backend_name() != 'postgresql' or not (url.database or '').endswith('_test'):
        raise ExperimentError('Explicit fresh PostgreSQL *_test database required')
    return url


def execute(protocol_path, commit=None):
    protocol = load_protocol(protocol_path)
    identity = code_identity(commit)
    protocol_hash = sha256(protocol_path)
    url = validate_database_url(os.environ.get('DATABASE_URL', ''))
    from sqlalchemy import create_engine, inspect
    probe = create_engine(url)
    try:
        if inspect(probe).get_table_names():
            raise ExperimentError('Database already has public tables; use a fresh database, no reset is performed')
    finally:
        probe.dispose()
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.database.session import Base, engine, SessionLocal
    from app.models.instrument import InstrumentType, InstrumentUnit
    # Imports above create no schema. The fresh database guard has already succeeded.
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            types = {}
            for name, values in protocol['families'].items():
                obj = InstrumentType(name=name, **values)
                db.add(obj)
                db.flush()
                types[name] = obj.id
            for item in protocol['catalog']:
                db.add(InstrumentUnit(instrument_type_id=types[item['family']],
                                      **{key: value for key, value in item.items() if key != 'family'}))
            db.commit()
            with tempfile.TemporaryDirectory(prefix='ptwin-exp02-') as raw:
                paths = materialize_cases(protocol, Path(raw))
                inputs = {name: sha256(path) if path.is_file() else None for name, path in paths.items()}
                details = evaluate_cases(protocol['cases'], paths, db, {row['serial_number'] for row in protocol['catalog']})
                stable = inputs == {name: sha256(path) if path.is_file() else None for name, path in paths.items()}
    finally:
        engine.dispose()
    report = report_for(details)
    source_files = ['experiments/run_matching_exp02.py', 'backend/app/services/pdf_extractor.py',
                    'backend/app/services/document_validation.py', 'backend/app/models/instrument.py',
                    'backend/app/database/session.py', 'backend/requirements.txt']
    report.update(experiment='EXP-02', scope='Known synthetic preparation, not final acceptance',
                  git=identity, calculated_at=datetime.now(timezone.utc).isoformat(),
                  validation_clock='Current UTC date of production validator; matching metrics independent of date rules',
                  python=platform.python_version(),
                  packages={name: version(name) for name in ('pdfplumber', 'reportlab', 'sqlalchemy', 'psycopg2-binary')},
                  protocol_sha256=protocol_hash, ambiguity_policy=protocol['ambiguity_policy'],
                  catalog_entries=len(protocol['catalog']), scenarios=dict(Counter(case['scenario'] for case in protocol['cases'])),
                  inputs_sha256=inputs, source_sha256={name: sha256(ROOT / name) for name in source_files},
                  acceptance_thresholds=None)
    report['input_integrity'] = 'UNCHANGED' if stable and sha256(protocol_path) == protocol_hash else 'CHANGED'
    if report['input_integrity'] == 'CHANGED':
        report['partial_diagnostics_not_final_metrics'] = report['metrics'] or report['partial_diagnostics_not_final_metrics']
        report['metrics'] = None
        report['execution_status'] = 'FAILED_INPUT_CHANGED'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=ROOT / 'experiments/fixtures/exp02-preparation.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--code-commit')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open('x', encoding='utf-8') as stream:
            try:
                report = execute(args.protocol.resolve(), args.code_commit)
            except Exception as exc:
                report = {'experiment': 'EXP-02', 'execution_status': 'SETUP_FAILED', 'metrics': None,
                          'error_type': type(exc).__name__,
                          'error': str(exc) if isinstance(exc, ExperimentError) else 'Setup failed; check fresh *_test database and protocol'}
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except FileExistsError:
        parser.error('Output exists; reports are never overwritten')
    print(f"{report['execution_status']}: {args.output}")
    return 0 if report['execution_status'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
