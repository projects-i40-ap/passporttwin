"""Explicit MVP design policy, not a metrological certification."""
from datetime import timedelta
import math

from app.services.tolerance_risk import estimate_tolerance_risk


def risk_after_maintenance(calibrations, maintenance, as_of):
    events=[m for m in maintenance if m.event_date<=as_of]
    last=max((m.event_date for m in events),default=None)
    # Event order within one day is unknown: require subsequent calibration dates.
    history=[c for c in calibrations if c.calibration_date<=as_of and (last is None or c.calibration_date>last)]
    result=estimate_tolerance_risk(history,as_of)
    result['maintenance_policy_version']='rebaseline_after_any_maintenance_v1'
    result['last_maintenance_date']=last.isoformat() if last else None
    if last and result.get('reason')=='INSUFFICIENT_HISTORY':
        result['reason']='INSUFFICIENT_POST_MAINTENANCE_HISTORY'
    return result


def calculate_lifecycle_health(instrument, calibrations, documents, incidents, maintenance, as_of, weights):
    history=sorted([c for c in calibrations if c.calibration_date<=as_of],key=lambda c:(c.calibration_date,c.id))
    latest=history[-1] if history else None
    valid=bool(latest and latest.error_value is not None and latest.tolerance is not None
               and math.isfinite(float(latest.error_value)) and math.isfinite(float(latest.tolerance))
               and float(latest.tolerance)>0
               and (latest.next_due_date is None or latest.next_due_date>=latest.calibration_date))
    calibration=None
    if valid and latest.next_due_date:
        calibration=1.0 if (abs(float(latest.error_value))>float(latest.tolerance)
            or latest.result in ('fail','out_of_tolerance')
            or instrument.lifecycle_state in ('blocked','out_of_tolerance')
            or latest.next_due_date<as_of) else .5 if latest.next_due_date<=as_of+timedelta(days=30) else 0.0
    risk=risk_after_maintenance(history,maintenance,as_of)
    probabilities=[v['probability_out_of_tolerance'] for v in risk['horizons'].values()]
    risk_penalty=max(probabilities) if len(probabilities)==3 and all(p is not None for p in probabilities) else None
    unresolved=[i for i in incidents if as_of-timedelta(days=90)<=i.incident_date<=as_of
                and (i.resolved_at is None or i.resolved_at.date()>as_of)]
    severities={'LOW':.25,'MEDIUM':.5,'HIGH':1.,'CRITICAL':1.}
    incident_penalty=min(1.,sum(severities.get(i.severity.upper(),0) for i in unresolved)) if all(
        i.severity and i.severity.upper() in severities for i in unresolved) else None
    # Six equally weighted checks, each exposed for inspection.
    quality={name: bool(getattr(instrument,name,None) and str(getattr(instrument,name)).strip())
             for name in ('serial_number','manufacturer','model','location')}
    quality['valid_metrology']=valid
    quality['accepted_documentation']=bool(documents) and all(d.processing_status=='ACCEPTED' for d in documents)
    penalties={'calibration_status':calibration,'predicted_risk':risk_penalty,
               'recent_incidents':incident_penalty,'data_quality':1-sum(quality.values())/len(quality)}
    values=weights.model_dump()
    components={key:{'value':value,'weight':values[key],
                     'penalty_points':value*values[key]*100 if value is not None else None}
                for key,value in penalties.items()}
    missing=[key for key,value in penalties.items() if value is None and values[key]>0]
    total=sum(c['penalty_points'] or 0 for c in components.values())
    score=round(max(0,min(100,100-total)),1) if not missing else None
    return {'health_score':score,'health_score_details':{
        'method_version':'lifecycle_health_v2','validation_status':'DESIGN_POLICY_SYNTHETIC_ONLY',
        'status':'CALCULATED' if score is not None else 'NOT_CALCULATED',
        'reason': 'MISSING_REQUIRED_COMPONENTS' if missing else None,
        'missing_components':missing,'fallback':False,'score':score,'weights':values,
        'components':components,'total_penalty_points':total if score is not None else None,
        'quality_checks':quality,'active_recent_incidents':len(unresolved),
        'as_of':as_of.isoformat()},'tolerance_risk':risk}
