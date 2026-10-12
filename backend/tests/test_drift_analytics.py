from datetime import date

from app.models.calibration import CalibrationEvent
from app.models.instrument import InstrumentUnit
from app.services.analytics import DriftAnalyticsService


def make_instrument(
    instrument_id: int,
    instrument_type_id: int,
    serial_number: str,
) -> InstrumentUnit:
    return InstrumentUnit(
        id=instrument_id,
        instrument_type_id=instrument_type_id,
        serial_number=serial_number,
        manufacturer="TEST",
        model="TEST-MODEL",
        lifecycle_state="operational",
    )


def make_calibration(
    calibration_id: int,
    instrument_unit_id: int,
    calibration_date: date,
    error_value: float,
    tolerance: float = 0.10,
) -> CalibrationEvent:
    return CalibrationEvent(
        id=calibration_id,
        instrument_unit_id=instrument_unit_id,
        calibration_date=calibration_date,
        error_value=error_value,
        tolerance=tolerance,
        result=(
            "out_of_tolerance"
            if abs(error_value) > tolerance
            else "pass"
        ),
    )


def test_no_calibration_data_returns_expected_status():
    instrument = make_instrument(
        instrument_id=1,
        instrument_type_id=1,
        serial_number="PT-TEST-001",
    )

    result = DriftAnalyticsService.calculate_drift_and_risk(
        instrument=instrument,
        calibrations=[],
        family_calibrations=[],
    )

    assert result["status"] == "NO_CALIBRATION_DATA"
    assert result["health_score"] == 50.0


def test_b0_persistence_uses_last_observed_error():
    instrument = make_instrument(
        instrument_id=1,
        instrument_type_id=1,
        serial_number="PT-TEST-001",
    )

    calibrations = [
        make_calibration(
            1,
            1,
            date(2024, 1, 1),
            0.01,
        ),
        make_calibration(
            2,
            1,
            date(2024, 4, 1),
            0.03,
        ),
        make_calibration(
            3,
            1,
            date(2024, 7, 1),
            0.05,
        ),
    ]

    result = DriftAnalyticsService.calculate_drift_and_risk(
        instrument=instrument,
        calibrations=calibrations,
        family_calibrations=calibrations,
    )

    b0 = result["drift_models"]["B0"]

    assert b0["name"] == "persistence"
    assert b0["predictions"]["30_days"] == 0.05
    assert b0["predictions"]["60_days"] == 0.05
    assert b0["predictions"]["90_days"] == 0.05


def test_b1_uses_mean_family_drift_rate():
    instrument = make_instrument(
        instrument_id=1,
        instrument_type_id=1,
        serial_number="PT-TEST-001",
    )

    target_calibrations = [
        make_calibration(
            1,
            1,
            date(2024, 1, 1),
            0.00,
        ),
        make_calibration(
            2,
            1,
            date(2024, 4, 10),
            0.10,
        ),
    ]

    family_calibrations = [
        make_calibration(
            1,
            1,
            date(2024, 1, 1),
            0.00,
        ),
        make_calibration(
            2,
            1,
            date(2024, 4, 10),
            0.10,
        ),
        make_calibration(
            3,
            2,
            date(2024, 1, 1),
            0.00,
        ),
        make_calibration(
            4,
            2,
            date(2024, 4, 10),
            0.20,
        ),
    ]

    result = DriftAnalyticsService.calculate_drift_and_risk(
        instrument=instrument,
        calibrations=target_calibrations,
        family_calibrations=family_calibrations,
    )

    b1 = result["drift_models"]["B1"]

    # 100 días:
    # instrumento 1 -> 0.10 / 100 = 0.001/día
    # instrumento 2 -> 0.20 / 100 = 0.002/día
    # media familia -> 0.0015/día
    assert b1["drift_rate_per_day"] == 0.0015

    # Último error = 0.10
    # + 30 días * 0.0015 = 0.145
    assert b1["predictions"]["30_days"] == 0.145


def test_m1_linear_regression_recovers_linear_trend():
    instrument = make_instrument(
        instrument_id=1,
        instrument_type_id=1,
        serial_number="PT-TEST-001",
    )

    calibrations = [
        make_calibration(
            1,
            1,
            date(2024, 1, 1),
            0.00,
            tolerance=1.0,
        ),
        make_calibration(
            2,
            1,
            date(2024, 1, 31),
            0.03,
            tolerance=1.0,
        ),
        make_calibration(
            3,
            1,
            date(2024, 3, 1),
            0.06,
            tolerance=1.0,
        ),
        make_calibration(
            4,
            1,
            date(2024, 3, 31),
            0.09,
            tolerance=1.0,
        ),
    ]

    result = DriftAnalyticsService.calculate_drift_and_risk(
        instrument=instrument,
        calibrations=calibrations,
        family_calibrations=calibrations,
    )

    m1 = result["drift_models"]["M1"]

    assert m1["name"] == "linear_regression_per_asset"
    assert m1["calibrations_used"] == 4
    assert m1["drift_rate_per_day"] == 0.001

    # Última calibración: día 90 con error 0.09.
    # A +30 días -> día 120 -> 0.12.
    assert m1["predictions"]["30_days"] == 0.12
    assert m1["predictions"]["60_days"] == 0.15
    assert m1["predictions"]["90_days"] == 0.18