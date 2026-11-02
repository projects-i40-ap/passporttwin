"""Canonical materialization is proven by its ingestion audit, not staging status."""
from app.models.calibration import AuditLog
from app.models.instrument import InstrumentUnit


def ingestion_event(db, document_id):
    for event in db.query(AuditLog).filter(AuditLog.action == 'CALIBRATION_INGESTED').all():
        details = getattr(event, 'details', None) or {}
        if getattr(event, 'action', None) == 'CALIBRATION_INGESTED' and details.get('document_id') == document_id:
            return event
    return None


def materialization_state(db, document):
    event = ingestion_event(db, document.id)
    if event is not None:
        details = event.details or {}
        instrument_id = details.get('instrument_id') or (event.entity_id if event.entity_name == 'instrument_unit' else None)
        instrument = db.query(InstrumentUnit).filter(InstrumentUnit.id == instrument_id).first() if instrument_id else None
        public_id = getattr(instrument, 'public_id', None)
        return {'status': 'MATERIALIZED', 'can_materialize': False,
                'audit_event_id': event.id, 'calibration_event_id': details.get('calibration_event_id'),
                'instrument_id': instrument_id, 'instrument_public_id': str(public_id) if public_id else None,
                'message': 'Este documento ya se incorporó al historial canónico.'}
    if getattr(document, 'source_type', None) != 'PDF_CERTIFICATE':
        message = 'Solo los certificados de calibración se incorporan a este historial.'
    elif document.processing_status != 'ACCEPTED':
        message = 'Guarda las correcciones y valida los campos antes de incorporar la calibración.'
    elif not document.instrument_unit_id:
        message = 'El documento necesita un instrumento vinculado antes de incorporarse.'
    else:
        return {'status': 'NOT_MATERIALIZED', 'can_materialize': True,
                'message': 'Campos validados. La calibración todavía no se ha incorporado al historial.'}
    return {'status': 'NOT_MATERIALIZED', 'can_materialize': False, 'message': message}
