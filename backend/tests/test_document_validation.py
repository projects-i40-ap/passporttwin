from types import SimpleNamespace

from app.core.config import Settings
from app.models.instrument import InstrumentType, InstrumentUnit
from app.services.document_validation import (
    validate_document_fields,
    validate_operating_range,
    validate_unit_compatibility,
)


class FakeInstrumentQuery:
    def __init__(self, instrument):
        self.instrument = instrument

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.instrument


class FakeSession:
    def __init__(self, instrument=None):
        self.instrument = instrument

    def query(self, model):
        if model is InstrumentUnit:
            return FakeInstrumentQuery(self.instrument)

        raise AssertionError(f"Unexpected model queried: {model}")


def test_validate_document_fields_accepts_valid_document():
    instrument = SimpleNamespace(
        id=7,
        serial_number="PT-001",
    )
    db = FakeSession(instrument=instrument)

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
    }

    target_unit, rules_failed = validate_document_fields(
        db=db,
        fields=fields,
    )

    assert target_unit is instrument
    assert rules_failed == []


def test_validate_document_fields_requires_known_instrument():
    db = FakeSession(instrument=None)

    fields = {
        "serial_number": "UNKNOWN-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
    }

    target_unit, rules_failed = validate_document_fields(
        db=db,
        fields=fields,
    )

    assert target_unit is None
    assert (
        "R-ID-01: Serial no coincide con ningún activo canónico registrado."
        in rules_failed
    )


def test_validate_document_fields_detects_invalid_due_date():
    instrument = SimpleNamespace(
        id=7,
        serial_number="PT-001",
    )
    db = FakeSession(instrument=instrument)

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2026-01-15",
    }

    target_unit, rules_failed = validate_document_fields(
        db=db,
        fields=fields,
    )

    assert target_unit is instrument
    assert (
        "R-DATE-02: La fecha de vencimiento es anterior o igual a la de calibración."
        in rules_failed
    )


class FakeTypeQuery:
    def __init__(self, instrument_type):
        self.instrument_type = instrument_type

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.instrument_type


class FakeSessionWithTypes:
    def __init__(self, instrument=None, instrument_type=None):
        self.instrument = instrument
        self.instrument_type = instrument_type

    def query(self, model):
        if model is InstrumentUnit:
            return FakeInstrumentQuery(self.instrument)

        if model is InstrumentType:
            return FakeTypeQuery(self.instrument_type)

        raise AssertionError(f"Unexpected model queried: {model}")


def _instrument_with_type(unit):
    instrument_type = SimpleNamespace(id=1, name="pressure_transmitter", unit=unit)

    return SimpleNamespace(
        id=7,
        serial_number="PT-001",
        instrument_type_id=1,
        instrument_type=instrument_type,
    )


# --- R-UNIT-01 -------------------------------------------------------------


def test_validate_unit_compatibility_accepts_convertible_units():
    assert validate_unit_compatibility("kPa", "bar") is True
    assert validate_unit_compatibility("°C", "c") is True
    assert validate_unit_compatibility("psi", "MPa") is True


def test_validate_unit_compatibility_rejects_incompatible_units():
    assert validate_unit_compatibility("pH", "bar") is False
    assert validate_unit_compatibility("°C", "bar") is False


def test_validate_document_fields_accepts_compatible_unit():
    instrument = _instrument_with_type("bar")
    db = FakeSessionWithTypes(instrument=instrument)

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
        "unit": "kPa",
    }

    target_unit, rules_failed = validate_document_fields(db=db, fields=fields)

    assert target_unit is instrument
    assert rules_failed == []


def test_validate_document_fields_flags_incompatible_unit():
    instrument = _instrument_with_type("bar")
    db = FakeSessionWithTypes(instrument=instrument)

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
        "unit": "pH",
    }

    target_unit, rules_failed = validate_document_fields(db=db, fields=fields)

    assert target_unit is instrument
    assert (
        "R-UNIT-01: Unidad incompatible con la magnitud canónica del activo."
        in rules_failed
    )


def test_validate_document_fields_resolves_unit_from_instrument_type_table():
    instrument = SimpleNamespace(
        id=7,
        serial_number="PT-001",
        instrument_type_id=1,
    )
    instrument_type = SimpleNamespace(id=1, unit="bar")
    db = FakeSessionWithTypes(
        instrument=instrument,
        instrument_type=instrument_type,
    )

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
        "unit": "mbar",
    }

    _, rules_failed = validate_document_fields(db=db, fields=fields)

    assert rules_failed == []


# --- R-RANGE-01 ------------------------------------------------------------


def test_validate_operating_range_detects_inverted_range():
    assert validate_operating_range("10 - 5 bar") is False
    assert validate_operating_range("2.5-1.5 MPa") is False


def test_validate_operating_range_accepts_valid_range():
    assert validate_operating_range("0 - 10 bar") is True
    assert validate_operating_range("1,5-2,5 kPa") is True


def test_validate_document_fields_flags_incoherent_operating_range():
    instrument = SimpleNamespace(id=7, serial_number="PT-001")
    db = FakeSession(instrument=instrument)

    fields = {
        "serial_number": "PT-001",
        "calibration_date": "2026-01-15",
        "next_due_date": "2027-01-15",
        "operating_range": "10 - 5 bar",
    }

    _, rules_failed = validate_document_fields(db=db, fields=fields)

    assert "R-RANGE-01: Rango operativo incoherente o inválido." in rules_failed


# --- R-MISSING-01 ----------------------------------------------------------


def test_validate_document_fields_flags_empty_document():
    db = FakeSession(instrument=None)

    _, rules_failed = validate_document_fields(db=db, fields={})

    assert (
        "R-MISSING-01: Faltan campos obligatorios en el documento."
        in rules_failed
    )


def test_validate_document_fields_flags_missing_calibration_date():
    instrument = SimpleNamespace(id=7, serial_number="PT-001")
    db = FakeSession(instrument=instrument)

    _, rules_failed = validate_document_fields(
        db=db,
        fields={"serial_number": "PT-001"},
    )

    assert (
        "R-MISSING-01: Faltan campos obligatorios en el documento."
        in rules_failed
    )


# --- Configuración LEGO (app/core/config.py) -------------------------------


def test_settings_ai_lego_defaults(monkeypatch):
    for variable in (
        "AI_LEGO_ENABLED",
        "AI_BASE_URL",
        "AI_MODEL_NAME",
        "AI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(variable, raising=False)

    settings = Settings(_env_file=None)

    assert settings.ai_lego_enabled is False
    assert settings.ai_base_url == "http://host.docker.internal:8080/v1"
    assert settings.ai_model_name == "gemma-4-e4b"
    assert settings.ai_timeout_seconds == 12.0


def test_settings_reads_ai_lego_environment(monkeypatch):
    monkeypatch.setenv("AI_LEGO_ENABLED", "true")
    monkeypatch.setenv("AI_MODEL_NAME", "gemma-4-e2b")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "30")

    settings = Settings(_env_file=None)

    assert settings.ai_lego_enabled is True
    assert settings.ai_model_name == "gemma-4-e2b"
    assert settings.ai_timeout_seconds == 30.0