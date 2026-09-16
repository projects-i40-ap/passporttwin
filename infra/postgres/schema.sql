-- =============================================================================
-- PassportTwin - Canonical Schema Definition (MVP 0 & MVP 1 Consolidated)
-- =============================================================================

CREATE TABLE IF NOT EXISTS instrument_type (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,          -- e.g. 'pressure_transmitter', 'temperature_sensor'
    magnitude       TEXT NOT NULL,                 -- e.g. 'Pressure', 'Temperature', 'pH'
    unit            TEXT NOT NULL,                 -- e.g. 'bar', '°C', 'pH'
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS instrument_unit (
    id                 SERIAL PRIMARY KEY,
    public_id          UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    instrument_type_id INTEGER REFERENCES instrument_type(id) ON DELETE RESTRICT,
    serial_number      TEXT UNIQUE NOT NULL,
    manufacturer       TEXT NOT NULL,
    model              TEXT NOT NULL,
    location           TEXT,
    criticality        TEXT DEFAULT 'MEDIUM',
    installed_at       DATE,
    lifecycle_state    TEXT DEFAULT 'operational', -- operational | pending | out_of_tolerance | blocked | retired
    aas_sync_status    TEXT DEFAULT 'PENDING',     -- PENDING | SYNCED | ERROR
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document (
    id                 SERIAL PRIMARY KEY,
    instrument_unit_id INTEGER REFERENCES instrument_unit(id) ON DELETE SET NULL,
    original_filename  TEXT NOT NULL,
    file_path          TEXT NOT NULL,
    source_type        TEXT DEFAULT 'MANUAL_UPLOAD', -- PDF_CERTIFICATE | INVENTORY_CSV | MANUAL_UPLOAD
    sha256_hash        VARCHAR(64) UNIQUE NOT NULL,  -- Regla R-DUP-01: Control criptográfico de unicidad
    processing_status  TEXT DEFAULT 'RECEIVED',      -- RECEIVED | EXTRACTED | VALIDATED | ACCEPTED | REVIEW_REQUIRED | FAILED_EXTRACTION
    uploaded_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_field (
    id                 SERIAL PRIMARY KEY,
    document_id        INTEGER REFERENCES document(id) ON DELETE CASCADE,
    field_name         TEXT NOT NULL,                -- e.g. 'serial_number', 'calibration_date', 'error_value'
    raw_value          TEXT,
    normalized_value   TEXT,
    confidence         TEXT DEFAULT '1.0',
    validation_status  TEXT DEFAULT 'STAGING',       -- STAGING | ACCEPTED | REVIEW_REQUIRED | REJECTED
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calibration_event (
    id                 SERIAL PRIMARY KEY,
    instrument_unit_id INTEGER REFERENCES instrument_unit(id) ON DELETE RESTRICT,
    calibration_date   DATE NOT NULL,
    error_value        NUMERIC,
    tolerance          NUMERIC,
    result             TEXT,                         -- pass | fail | out_of_tolerance
    next_due_date      DATE,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS maintenance_event (
    id                 SERIAL PRIMARY KEY,
    instrument_unit_id INTEGER REFERENCES instrument_unit(id) ON DELETE RESTRICT,
    event_date         DATE NOT NULL,
    description        TEXT NOT NULL,
    cost_estimate      NUMERIC,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incident (
    id                 SERIAL PRIMARY KEY,
    instrument_unit_id INTEGER REFERENCES instrument_unit(id) ON DELETE RESTRICT,
    incident_date      DATE NOT NULL,
    description        TEXT NOT NULL,
    severity           TEXT DEFAULT 'LOW',
    resolved_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    entity_name TEXT NOT NULL,
    entity_id   INTEGER NOT NULL,
    action      TEXT NOT NULL,
    details     JSONB,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Índices operacionales mínimos
CREATE INDEX IF NOT EXISTS idx_instrument_unit_serial ON instrument_unit(serial_number);
CREATE INDEX IF NOT EXISTS idx_instrument_unit_public_id ON instrument_unit(public_id);
CREATE INDEX IF NOT EXISTS idx_document_sha256 ON document(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_extracted_field_document ON extracted_field(document_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_name, entity_id);