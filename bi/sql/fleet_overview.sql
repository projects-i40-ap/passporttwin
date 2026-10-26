-- Apply explicitly to the canonical application database, not Metabase's database.
-- Read-only projection; no source rows or application tables are modified.
CREATE SCHEMA IF NOT EXISTS passporttwin_bi;
CREATE OR REPLACE VIEW passporttwin_bi.fleet_overview AS
WITH latest AS (
    SELECT DISTINCT ON (instrument_unit_id) *
    FROM calibration_event
    WHERE calibration_date <= CURRENT_DATE
    ORDER BY instrument_unit_id, calibration_date DESC, id DESC
), reviews AS (
    SELECT instrument_unit_id, COUNT(*) AS documents_to_review
    FROM document
    WHERE processing_status IN ('REVIEW_REQUIRED', 'FAILED_EXTRACTION')
    GROUP BY instrument_unit_id
), base AS (
    SELECT i.id AS instrument_id, i.public_id, i.serial_number,
           t.name AS family, i.location, i.criticality, i.lifecycle_state,
           i.aas_sync_status, c.calibration_date, c.next_due_date,
           c.error_value, c.tolerance, c.result AS calibration_result,
           c.next_due_date - CURRENT_DATE AS days_to_due,
           COALESCE(r.documents_to_review, 0) AS documents_to_review,
           CASE WHEN c.tolerance > 0
                     AND c.tolerance::text NOT IN ('NaN', 'Infinity', '-Infinity')
                     AND c.error_value::text NOT IN ('NaN', 'Infinity', '-Infinity')
                THEN ABS(c.error_value) / c.tolerance END AS observed_error_ratio
    FROM instrument_unit i
    JOIN instrument_type t ON t.id = i.instrument_type_id
    LEFT JOIN latest c ON c.instrument_unit_id = i.id
    LEFT JOIN reviews r ON r.instrument_unit_id = i.id
    WHERE COALESCE(i.lifecycle_state, '') <> 'retired'
), classified AS (
    SELECT *,
       CASE
         WHEN lifecycle_state IN ('out_of_tolerance', 'blocked')
           OR calibration_result IN ('fail', 'out_of_tolerance')
           OR observed_error_ratio > 1 OR days_to_due < 0 THEN 'red'
         WHEN calibration_date IS NULL OR observed_error_ratio IS NULL
           OR next_due_date IS NULL THEN 'gray'
         WHEN days_to_due <= 30 OR documents_to_review > 0
           OR observed_error_ratio >= 0.8 OR aas_sync_status = 'ERROR'
           THEN 'yellow'
         ELSE 'green'
       END AS traffic_light,
       CASE
         WHEN lifecycle_state IN ('out_of_tolerance', 'blocked') THEN 'LIFECYCLE_ALERT'
         WHEN calibration_result IN ('fail', 'out_of_tolerance')
           OR observed_error_ratio > 1 THEN 'OUT_OF_TOLERANCE'
         WHEN days_to_due < 0 THEN 'CALIBRATION_OVERDUE'
         WHEN calibration_date IS NULL THEN 'NO_CALIBRATION'
         WHEN observed_error_ratio IS NULL THEN 'INVALID_METROLOGY'
         WHEN next_due_date IS NULL THEN 'MISSING_DUE_DATE'
         WHEN days_to_due <= 30 THEN 'DUE_WITHIN_30_DAYS'
         WHEN documents_to_review > 0 THEN 'DOCUMENT_REVIEW'
         WHEN observed_error_ratio >= 0.8 THEN 'NEAR_TOLERANCE'
         WHEN aas_sync_status = 'ERROR' THEN 'AAS_SYNC_ERROR'
         ELSE 'NO_ALERT'
       END AS primary_reason
    FROM base
)
SELECT *, CASE traffic_light WHEN 'red' THEN 1 WHEN 'yellow' THEN 2
                            WHEN 'gray' THEN 3 ELSE 4 END AS priority_rank
FROM classified;
