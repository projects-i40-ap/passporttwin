"""Tests de la regla de número de serie (Spec 001 — T14)."""

import pytest

from app.services.serial_numbers import InvalidSerial, normalize_serial


@pytest.mark.parametrize(
    "value,expected",
    [
        ("DS18B20-001", "DS18B20-001"),
        ("ds18b20-001", "DS18B20-001"),
        ("  PT_001  ", "PT_001"),
        ("AB", "AB"),
        ("A1", "A1"),
    ],
)
def test_valid_serials_are_normalized(value, expected):
    assert normalize_serial(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "A",
        "DS 18B20",
        "DS18B20/001",
        "DS18B20.001",
        "DS18B20#1",
        "-DS18B20",
        "_DS18B20",
        "D" * 41,
        "sensor de temperatura",
    ],
)
def test_invalid_serials_are_rejected(value):
    with pytest.raises(InvalidSerial):
        normalize_serial(value)
