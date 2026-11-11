-- =============================================================================
-- Modelos de instrumento y vínculo de fichas técnicas (Spec 001 — T9)
-- Migración aditiva e idempotente: no borra ni renombra nada existente.
-- Se aplica al arrancar (tools/dev.py) y en bases ya creadas.
-- =============================================================================

-- 1. El modelo (tipo) pasa a tener identidad de fabricante y modelo.
ALTER TABLE instrument_type
    ADD COLUMN IF NOT EXISTS manufacturer TEXT,
    ADD COLUMN IF NOT EXISTS model TEXT;

-- 2. Una ficha técnica describe un modelo, no un ejemplar.
ALTER TABLE document
    ADD COLUMN IF NOT EXISTS instrument_type_id INTEGER
        REFERENCES instrument_type(id) ON DELETE SET NULL;

-- 3. Dos tipos no pueden describir el mismo fabricante+modelo.
--    Índice parcial: los tipos históricos sin identidad quedan fuera.
CREATE UNIQUE INDEX IF NOT EXISTS ux_instrument_type_identity
    ON instrument_type (lower(manufacturer), lower(model))
    WHERE manufacturer IS NOT NULL AND model IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_document_instrument_type
    ON document (instrument_type_id);
