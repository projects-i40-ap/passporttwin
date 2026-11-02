import json
import pytest
from app.services.document_identity import serial_identity_fields


@pytest.mark.parametrize('text', [
    'Serial Number: PT-001', 'Serial Number : PT-001', 'serial number: PT-001',
    'SERIAL NUMBER:\tPT-001', 'Serial\tNumber PT-001',
    'Serial: PT-001', 'Serial PT-001', 'S/N: PT-001',
    'Número de Serie: PT-001', 'Número de Serie PT-001',
])
def test_supported_serial_labels_return_the_value_not_label_words(text):
    assert serial_identity_fields(text)=={'serial_number':'PT-001'}


@pytest.mark.parametrize('text', [
    'Serial Number:', 'Serial Number:   ', 'Serial Number:\nCalibration Date: 2026-01-01',
    'Serial:\nCalibration Date: 2026-01-01', 'NotSerial: PT-001', 'Serial Numberish: PT-001',
])
def test_missing_values_or_label_substrings_do_not_create_phantom_identity(text):
    assert serial_identity_fields(text)=={}


@pytest.mark.parametrize('lines', [
    ['Serial Number: PT-A','S/N: PT-B'], ['S/N: PT-B','Serial Number: PT-A'],
])
def test_mixed_long_and_short_labels_preserve_ambiguity(lines):
    result=serial_identity_fields('\n'.join(lines))
    assert result['serial_number']==''
    assert json.loads(result['serial_candidates'])==['PT-A','PT-B']


def test_same_serial_repeated_with_different_labels_is_not_ambiguous():
    assert serial_identity_fields('Serial Number: PT-A\nSerial: PT-A\nS/N: PT-A')=={'serial_number':'PT-A'}
