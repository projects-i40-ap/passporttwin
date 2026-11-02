import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.documents import router
from app.database.session import get_db
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit
from app.models.calibration import AuditLog, CalibrationEvent
from app.services.document_identity import serial_identity_fields, unresolved_serial_ambiguity
from app.services.pdf_extractor import PDFCertificateExtractor, HybridDocumentExtractor
from app.services.document_validation import validate_document_fields

TEXT = 'Serial: PT-A\nSerial: PT-B\nCalibration Date: 2026-01-01\nDue Date: 2027-01-01'


@pytest.mark.parametrize('text', ['Serial: PT-A\nSerial: PT-B', 'Serial: PT-B\nSerial: PT-A'])
def test_multiple_serials_never_automatically_choose_the_first(text):
    fields = PDFCertificateExtractor._parse_text(text)
    assert fields['serial_number'] == ''
    assert json.loads(fields['serial_candidates']) == ['PT-A', 'PT-B']
    assert unresolved_serial_ambiguity(fields)


def test_repeated_identical_serial_is_not_ambiguous():
    assert serial_identity_fields('Serial: PT-A\nS/N: PT-A') == {'serial_number': 'PT-A'}


@pytest.mark.parametrize('mode', ['deterministic', 'llm', 'auto'])
def test_llm_cannot_resolve_multiple_textual_serials(monkeypatch, mode):
    monkeypatch.setattr(PDFCertificateExtractor, 'extract_text', staticmethod(lambda path: TEXT))
    monkeypatch.setattr(HybridDocumentExtractor, '_extract_with_llama_cpp', lambda self, text: {'serial_number': 'PT-A'})
    fields = HybridDocumentExtractor(enabled=True).extract_and_parse('ignored.pdf', extractor_mode=mode)
    assert fields['serial_number'] == ''
    assert json.loads(fields['serial_candidates']) == ['PT-A', 'PT-B']


def test_conflicting_llm_serial_requires_review(monkeypatch):
    monkeypatch.setattr(PDFCertificateExtractor, 'extract_text', staticmethod(lambda path: 'Serial: PT-A'))
    monkeypatch.setattr(HybridDocumentExtractor, '_extract_with_llama_cpp', lambda self, text: {'serial_number': 'PT-B'})
    fields = HybridDocumentExtractor(enabled=True).extract_and_parse('ignored.pdf', extractor_mode='llm')
    assert unresolved_serial_ambiguity(fields)
    assert json.loads(fields['serial_candidates']) == ['PT-A', 'PT-B']


@pytest.mark.parametrize('metadata', ['not-json', 'null', '["PT-A"]', '["PT-A", "PT-A"]', '[1, 2]'])
def test_malformed_identity_evidence_does_not_allow_matching(metadata):
    fields = {'serial_number': 'PT-A', 'serial_candidates': metadata, 'calibration_date': '2026-01-01'}
    class NoLookup:
        def query(self, model):
            raise AssertionError('Ambiguous identities must not query a target')
    target, rules = validate_document_fields(NoLookup(), fields)
    assert target is None and any(rule.startswith('R-ID-AMBIGUOUS:') for rule in rules)


class Query:
    def __init__(self, db, model, rows):
        self.db, self.model, self.rows = db, model, rows

    def filter(self, *expressions):
        for expr in expressions:
            name = expr.left.name
            value = expr.right.value
            self.rows = [row for row in self.rows if getattr(row, name, None) == value]
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows[:]

    def delete(self):
        self.db.fields = [row for row in self.db.fields if row not in self.rows]


class ReviewSession:
    def __init__(self):
        self.document = SimpleNamespace(id=1, processing_status='ACCEPTED', instrument_unit_id=1,
                                        source_type='PDF_CERTIFICATE', file_path='fixture.pdf')
        self.fields, self.events, self.calibrations = [], [], []
        self.instruments = [SimpleNamespace(id=index, serial_number=serial,
                             instrument_type=SimpleNamespace(unit='bar'))
                            for index, serial in enumerate(('PT-A', 'PT-B'), start=1)]
        self.next_id = 1

    def query(self, model):
        rows = {Document: [self.document], ExtractedField: self.fields, InstrumentUnit: self.instruments,
                AuditLog: self.events, CalibrationEvent: self.calibrations}[model]
        return Query(self, model, rows[:])

    def add(self, value):
        value.id = self.next_id
        self.next_id += 1
        if isinstance(value, ExtractedField):
            self.fields.append(value)
        elif isinstance(value, AuditLog):
            self.events.append(value)
        elif isinstance(value, CalibrationEvent):
            self.calibrations.append(value)

    def commit(self):
        pass

    def refresh(self, value):
        pass


@pytest.fixture
def review_client(monkeypatch):
    monkeypatch.setattr(PDFCertificateExtractor, 'extract_text', staticmethod(lambda path: TEXT))
    db = ReviewSession()
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client, db


def test_http_ambiguity_requires_explicit_choice_and_revalidation(review_client):
    client, db = review_client
    result = client.post('/api/v1/documents/1/process?extractor=deterministic').json()
    assert result['processing_status'] == 'REVIEW_REQUIRED'
    assert result['matched_instrument_id'] is None  # Clears a previously stored link.
    assert any(rule.startswith('R-ID-AMBIGUOUS:') for rule in result['rules_failed'])
    fields = client.get('/api/v1/documents/1/fields').json()['fields']
    serial = next(row for row in fields if row['field_name'] == 'serial_number')
    evidence = next(row for row in fields if row['field_name'] == 'serial_candidates')
    assert serial['normalized_value'] == '' and evidence['read_only']
    original = evidence['raw_value']
    assert client.patch(f"/api/v1/documents/1/fields/{evidence['field_id']}", json={'normalized_value': '[]'}).status_code == 400
    assert client.post('/api/v1/documents/1/revalidate').json()['matched_instrument_id'] is None
    assert client.post('/api/v1/documents/1/accept').status_code == 400
    client.patch(f"/api/v1/documents/1/fields/{serial['field_id']}", json={'normalized_value': 'PT-OUTSIDE'})
    assert client.post('/api/v1/documents/1/revalidate').json()['processing_status'] == 'REVIEW_REQUIRED'
    saved = client.patch(f"/api/v1/documents/1/fields/{serial['field_id']}", json={'normalized_value': 'PT-B'})
    assert saved.json()['raw_value'] == ''
    assert client.post('/api/v1/documents/1/accept').status_code == 400
    result = client.post('/api/v1/documents/1/revalidate').json()
    assert result['processing_status'] == 'ACCEPTED' and result['matched_instrument_id'] == 2
    evidence_row = next(row for row in db.fields if row.field_name == 'serial_candidates')
    assert evidence_row.raw_value == evidence_row.normalized_value == original
    assert any(event.action == 'FIELD_CORRECTED' and event.details['after']['normalized_value'] == 'PT-B' for event in db.events)
    # A subsequent edit or reprocessing cannot retain an accepted link.
    client.patch(f"/api/v1/documents/1/fields/{serial['field_id']}", json={'normalized_value': 'PT-A'})
    assert db.document.instrument_unit_id is None and db.document.processing_status == 'REVIEW_REQUIRED'
    assert client.post('/api/v1/documents/1/accept').status_code == 400
    client.post('/api/v1/documents/1/revalidate')
    assert client.post('/api/v1/documents/1/process?extractor=deterministic').json()['matched_instrument_id'] is None
