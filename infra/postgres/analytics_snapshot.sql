-- Idempotent additive migration for existing databases. No source data modified.
CREATE TABLE IF NOT EXISTS analytics_snapshot (
    id SERIAL PRIMARY KEY,
    instrument_unit_id INTEGER NOT NULL REFERENCES instrument_unit(id),
    as_of DATE NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    input_hash VARCHAR(64) NOT NULL,
    input_manifest JSON NOT NULL,
    weights JSON NOT NULL,
    score_method_version VARCHAR NOT NULL,
    risk_method_version VARCHAR NOT NULL,
    score_status VARCHAR NOT NULL,
    risk_status VARCHAR NOT NULL,
    health_score DOUBLE PRECISION,
    probability_30 DOUBLE PRECISION,
    probability_60 DOUBLE PRECISION,
    probability_90 DOUBLE PRECISION,
    score_result JSON NOT NULL,
    risk_result JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analytics_snapshot_instrument_unit_id
    ON analytics_snapshot(instrument_unit_id);
