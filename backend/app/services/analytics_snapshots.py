import hashlib
import json
import math

from app.core.config import settings
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.calibration import CalibrationEvent
from app.services.lifecycle_health import calculate_lifecycle_health
from app.services.health_context import load_context
from app.services.tolerance_risk import estimate_tolerance_risk
from app.services.audit_service import AuditService


def numeric(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else str(value)


def build_manifest(instrument, context):
    history = context['calibrations']
    return {
        'input_schema_version': 2,
        'instrument': {key: getattr(instrument, key) for key in
                       ('serial_number', 'manufacturer', 'model', 'location', 'lifecycle_state')},
        'calibrations': [{'id': c.id, 'calibration_date': c.calibration_date.isoformat(),
                          'error_value': numeric(c.error_value), 'tolerance': numeric(c.tolerance),
                          'next_due_date': c.next_due_date.isoformat() if c.next_due_date else None,
                          'result': c.result} for c in history],
        'documents': [{'id': d.id, 'processing_status': d.processing_status} for d in context['documents']],
        'incidents': [{'id': i.id, 'incident_date': i.incident_date.isoformat(), 'severity': i.severity,
                       'resolved_date': i.resolved_at.date().isoformat() if i.resolved_at else None}
                      for i in context['incidents']],
        'maintenance': [{'id': m.id, 'event_date': m.event_date.isoformat()} for m in context['maintenance']],
    }

def create_snapshot(db, instrument, as_of):
    context = load_context(db, instrument.id, as_of)
    manifest = build_manifest(instrument, context)

    input_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result = calculate_lifecycle_health(instrument, as_of=as_of,
                                      weights=settings.lifecycle_health_weights, **context)
    score, risk = result['health_score_details'], result['tolerance_risk']
    weights = score['weights']
    snapshot = AnalyticsSnapshot(
        instrument_unit_id=instrument.id, as_of=as_of, input_hash=input_hash,
        input_manifest=manifest, weights=weights, score_method_version=score["method_version"],
        risk_method_version=risk["method_version"], score_status=score["status"],
        risk_status=risk["status"],
        health_score=score["score"] if score["status"] == "CALCULATED" else None,
        score_result=score, risk_result=risk,
        **{f"probability_{h}": risk["horizons"].get(f"{h}_days", {}).get("probability_out_of_tolerance")
           for h in (30, 60, 90)},
    )
    db.add(snapshot)
    db.flush()
    AuditService.log_event(
        db=db, entity_name="analytics_snapshot", entity_id=snapshot.id,
        action="ANALYTICS_SNAPSHOT_CREATED", source="analytics.snapshot.refresh",
        details={"instrument_unit_id": instrument.id, "as_of": as_of.isoformat(),
                 "input_hash": input_hash, "score_method_version": snapshot.score_method_version,
                 "risk_method_version": snapshot.risk_method_version},
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot
