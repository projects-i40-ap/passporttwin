import hashlib
import json
import math

from app.core.config import settings
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.calibration import CalibrationEvent
from app.services.analytics import DriftAnalyticsService
from app.services.tolerance_risk import estimate_tolerance_risk
from app.services.audit_service import AuditService


def numeric(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else str(value)


def create_snapshot(db, instrument, as_of):
    history = db.query(CalibrationEvent).filter(
        CalibrationEvent.instrument_unit_id == instrument.id,
        CalibrationEvent.calibration_date <= as_of,
    ).order_by(CalibrationEvent.calibration_date, CalibrationEvent.id).all()
    manifest = {
        "lifecycle_state": instrument.lifecycle_state,
        "calibrations": [{"id": c.id, "calibration_date": c.calibration_date.isoformat(),
                          "error_value": numeric(c.error_value), "tolerance": numeric(c.tolerance)}
                         for c in history],
    }
    input_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, allow_nan=False).encode()).hexdigest()
    weights = settings.health_score_weights.model_dump()
    valid_score_inputs = all(
        c.error_value is not None and math.isfinite(float(c.error_value))
        and c.tolerance is not None and math.isfinite(float(c.tolerance)) and float(c.tolerance) > 0
        for c in history
    )
    if valid_score_inputs:
        score = DriftAnalyticsService.calculate_drift_and_risk(
            instrument, history, health_score_weights=settings.health_score_weights,
        )["health_score_details"]
    else:
        score = {"status": "NOT_CALCULATED", "reason": "INVALID_CALIBRATION_VALUES",
                 "score": None, "weights": weights, "method_version": "weighted_penalties_v1"}
    risk = estimate_tolerance_risk(history, as_of)
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
