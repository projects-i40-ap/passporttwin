-- Requires fleet_overview.sql and the analytics_snapshot additive migration.
CREATE OR REPLACE VIEW passporttwin_bi.fleet_analytics AS
WITH latest AS (
    SELECT DISTINCT ON (instrument_unit_id) * FROM analytics_snapshot
    WHERE as_of <= CURRENT_DATE
    ORDER BY instrument_unit_id, as_of DESC, computed_at DESC, id DESC
), source AS (
    SELECT s.*, jsonb_build_object(
        'input_schema_version', 2,
        'instrument', jsonb_build_object('serial_number',i.serial_number,'manufacturer',i.manufacturer,
            'model',i.model,'location',i.location,'lifecycle_state',i.lifecycle_state),
        'calibrations', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'id', c.id, 'calibration_date', c.calibration_date,
                'error_value', c.error_value, 'tolerance', c.tolerance,
                'next_due_date', c.next_due_date, 'result', c.result
            ) ORDER BY c.calibration_date, c.id)
            FROM calibration_event c
            WHERE c.instrument_unit_id=s.instrument_unit_id AND c.calibration_date<=s.as_of
        ), '[]'::jsonb),
        'documents',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',d.id,'processing_status',d.processing_status) ORDER BY d.id)
            FROM document d WHERE d.instrument_unit_id=i.id),'[]'::jsonb),
        'incidents',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',e.id,'incident_date',e.incident_date,
            'severity',e.severity,'resolved_date',e.resolved_at::date) ORDER BY e.id)
            FROM incident e WHERE e.instrument_unit_id=i.id AND e.incident_date<=s.as_of),'[]'::jsonb),
        'maintenance',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',m.id,'event_date',m.event_date) ORDER BY m.id)
            FROM maintenance_event m WHERE m.instrument_unit_id=i.id AND m.event_date<=s.as_of),'[]'::jsonb)
    ) AS current_manifest
    FROM latest s JOIN instrument_unit i ON i.id=s.instrument_unit_id
)
SELECT f.*, s.id AS snapshot_id, s.as_of AS analytics_as_of,
    s.computed_at AS analytics_computed_at, s.input_hash,
    s.score_method_version, s.risk_method_version, s.weights AS score_weights,
    s.score_status, s.risk_status,
    s.score_result->>'reason' AS score_reason,
    s.risk_result->>'reason' AS risk_reason,
    s.risk_result->'horizons'->'90_days'->>'uncertainty_status' AS risk_uncertainty_90,
    CASE WHEN s.id IS NULL THEN 'MISSING'
         WHEN s.as_of < CURRENT_DATE THEN 'STALE_DATE'
         WHEN s.input_manifest::jsonb <> s.current_manifest THEN 'STALE_INPUTS'
         ELSE 'CURRENT' END AS analytics_status,
    s.health_score AS snapshot_health_score,
    s.probability_30 AS snapshot_probability_30,
    s.probability_60 AS snapshot_probability_60,
    s.probability_90 AS snapshot_probability_90,
    CASE WHEN s.as_of=CURRENT_DATE AND s.input_manifest::jsonb=s.current_manifest
         THEN s.health_score END AS current_health_score,
    CASE WHEN s.as_of=CURRENT_DATE AND s.input_manifest::jsonb=s.current_manifest
         THEN s.probability_30 END AS current_probability_30,
    CASE WHEN s.as_of=CURRENT_DATE AND s.input_manifest::jsonb=s.current_manifest
         THEN s.probability_60 END AS current_probability_60,
    CASE WHEN s.as_of=CURRENT_DATE AND s.input_manifest::jsonb=s.current_manifest
         THEN s.probability_90 END AS current_probability_90
FROM passporttwin_bi.fleet_overview f
LEFT JOIN source s ON s.instrument_unit_id=f.instrument_id;
