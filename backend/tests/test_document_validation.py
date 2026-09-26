from types import SimpleNamespace

from app.models.instrument import InstrumentUnit
from app.services.document_validation import validate_document_fields


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