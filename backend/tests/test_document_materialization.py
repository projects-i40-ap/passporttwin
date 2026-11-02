from datetime import date, timedelta
import hashlib

from app.models.calibration import AuditLog, CalibrationEvent
from app.models.document import Document, ExtractedField
from app.services.aas_builder import AASBuilder
from tests.test_analytics_snapshots import setup
import pytest


def certificate(db, instrument, status='ACCEPTED', source_type='PDF_CERTIFICATE'):
    doc = Document(instrument_unit_id=instrument.id, original_filename='certificate.pdf', file_path='not-read',
                   sha256_hash=hashlib.sha256(str(instrument.id).encode()).hexdigest(),
                   source_type=source_type, processing_status=status)
    db.add(doc); db.flush()
    values = {'serial_number': instrument.serial_number, 'calibration_date': str(date.today()-timedelta(days=1)),
              'next_due_date': str(date.today()+timedelta(days=90)), 'error_value': '0.02', 'tolerance': '0.1'}
    for key, value in values.items():
        db.add(ExtractedField(document_id=doc.id, field_name=key, raw_value=value,
                              normalized_value=value, validation_status='STAGING'))
    db.flush()
    return doc


def projection(monkeypatch, success=True):
    for name in ('sync_calibration_submodel', 'sync_document_provenance', 'sync_operational_state'):
        monkeypatch.setattr(AASBuilder, name, staticmethod(lambda *args: success))


def test_accepted_staging_is_not_materialized_without_canonical_audit(setup):
    client, db, instrument = setup
    doc = certificate(db, instrument)
    result = client.get(f'/api/v1/documents/{doc.id}/fields').json()
    assert result['materialization']['status'] == 'NOT_MATERIALIZED'
    assert result['materialization']['can_materialize'] is True
    assert result['matched_instrument_id'] == instrument.id
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count() == 0


@pytest.mark.parametrize('status,source,linked', [
    ('REVIEW_REQUIRED','PDF_CERTIFICATE',True), ('RECEIVED','PDF_CERTIFICATE',True),
    ('ACCEPTED','PDF_DATASHEET',True), ('ACCEPTED','PDF_CERTIFICATE',False),
])
def test_ineligible_documents_cannot_be_offered_for_materialization(setup,status,source,linked):
    client, db, instrument = setup
    doc = certificate(db, instrument, status, source)
    if not linked: doc.instrument_unit_id = None; db.flush()
    result = client.get(f'/api/v1/documents/{doc.id}/fields').json()['materialization']
    assert result['status'] == 'NOT_MATERIALIZED' and result['can_materialize'] is False
    assert client.post(f'/api/v1/documents/{doc.id}/accept').status_code == 400
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count() == 0


def test_validation_and_materialization_are_separate_and_survive_reload(setup,monkeypatch):
    client, db, instrument = setup
    projection(monkeypatch)
    doc = certificate(db, instrument, 'REVIEW_REQUIRED')
    root = f'/api/v1/documents/{doc.id}'
    assert client.post(root+'/revalidate').json()['processing_status'] == 'ACCEPTED'
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count() == 0
    response = client.post(root+'/accept')
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'CANONICAL_COMMITTED'
    assert result['aas_projection']['status'] == 'UPDATED'
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count() == 1
    materialized = client.get(root+'/fields').json()['materialization']
    assert materialized['status'] == 'MATERIALIZED' and materialized['can_materialize'] is False
    assert materialized['calibration_event_id'] == result['calibration_event_id']
    assert materialized['instrument_id'] == instrument.id
    assert materialized['instrument_public_id'] == str(instrument.public_id)
    assert db.query(AuditLog).filter(AuditLog.id == materialized['audit_event_id']).one().action == 'CALIBRATION_INGESTED'
    assert client.post(root+'/accept').status_code == 409
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count() == 1


def test_legacy_ingestion_is_recognized_without_guessing_calibration_id(setup):
    client, db, instrument = setup
    doc = certificate(db, instrument)
    db.add(AuditLog(entity_name='instrument_unit',entity_id=instrument.id,action='CALIBRATION_INGESTED',details={'document_id':doc.id}));db.flush()
    state = client.get(f'/api/v1/documents/{doc.id}/fields').json()['materialization']
    assert state['status']=='MATERIALIZED' and state['can_materialize'] is False
    assert state['calibration_event_id'] is None and state['instrument_id']==instrument.id
    assert client.post(f'/api/v1/documents/{doc.id}/accept').status_code==409


def test_unrelated_audit_does_not_mark_document_materialized(setup):
    client, db, instrument = setup
    doc = certificate(db, instrument)
    db.add(AuditLog(entity_name='instrument_unit',entity_id=instrument.id,action='CALIBRATION_INGESTED',details={'document_id':doc.id+999}));db.flush()
    assert client.get(f'/api/v1/documents/{doc.id}/fields').json()['materialization']['can_materialize'] is True


def test_projection_failure_does_not_hide_committed_calibration(setup,monkeypatch):
    client, db, instrument = setup
    projection(monkeypatch,False)
    doc = certificate(db,instrument)
    response = client.post(f'/api/v1/documents/{doc.id}/accept')
    assert response.status_code==200
    assert response.json()['aas_projection']['status']=='ERROR'
    assert response.json()['status']=='CANONICAL_COMMITTED'
    assert instrument.aas_sync_status == 'ERROR'
    assert db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id == instrument.id).count()==1
    assert client.get(f'/api/v1/documents/{doc.id}/fields').json()['materialization']['status']=='MATERIALIZED'


def test_saving_correction_requires_revalidation_before_materialization(setup):
    client, db, instrument = setup
    doc = certificate(db,instrument)
    field=db.query(ExtractedField).filter(ExtractedField.document_id==doc.id,ExtractedField.field_name=='error_value').one()
    response=client.patch(f'/api/v1/documents/{doc.id}/fields/{field.id}',json={'normalized_value':'0.03'})
    assert response.status_code==200
    assert client.get(f'/api/v1/documents/{doc.id}/fields').json()['materialization']['can_materialize'] is False
    assert client.post(f'/api/v1/documents/{doc.id}/accept').status_code==400
