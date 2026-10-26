from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.tolerance_risk import estimate_tolerance_risk

START = date(2026, 1, 1)


def history(errors, tolerance=1):
    return [SimpleNamespace(calibration_date=START + timedelta(days=i * 30),
                            error_value=e, tolerance=tolerance) for i, e in enumerate(errors)]


def test_reference_date_controls_targets_and_excludes_future():
    rows = history([0.1, 0.23, 0.29, 1000])
    as_of = START + timedelta(days=60)
    result = estimate_tolerance_risk(rows, as_of)
    assert result == estimate_tolerance_risk(rows[:3], as_of)
    assert result["calibrations_used"] == 3
    assert result["horizons"]["30_days"]["target_date"] == (as_of + timedelta(days=30)).isoformat()


def test_sign_symmetry_and_valid_probabilities():
    as_of = START + timedelta(days=90)
    positive = estimate_tolerance_risk(history([0.1, 0.25, 0.28, 0.47]), as_of)
    negative = estimate_tolerance_risk(history([-0.1, -0.25, -0.28, -0.47]), as_of)
    for key, row in positive["horizons"].items():
        p = row["probability_out_of_tolerance"]
        assert 0 <= p <= 1
        assert p == pytest.approx(negative["horizons"][key]["probability_out_of_tolerance"])


def test_uncertainty_grows_with_extrapolation():
    result = estimate_tolerance_risk(history([0.1, 0.25, 0.28, 0.47]), START + timedelta(days=90))
    rows = list(result["horizons"].values())
    assert rows[0]["predictive_std"] < rows[1]["predictive_std"] < rows[2]["predictive_std"]


def test_perfect_line_has_no_unjustified_probability():
    result = estimate_tolerance_risk(history([0, 0.3, 0.6]), START + timedelta(days=60))
    assert result["horizons"]["60_days"]["predicted_error"] == pytest.approx(1.2)
    assert result["horizons"]["60_days"]["projected_out_of_tolerance"] is True
    assert result["horizons"]["60_days"]["probability_out_of_tolerance"] is None


@pytest.mark.parametrize("errors", [[], [0.1], [0.1, 0.2]])
def test_insufficient_history(errors):
    assert estimate_tolerance_risk(history(errors), date(2026, 12, 1))["reason"] == "INSUFFICIENT_HISTORY"


@pytest.mark.parametrize("value", [0, -1, None, float("inf"), float("nan")])
def test_invalid_tolerance(value):
    result = estimate_tolerance_risk(history([0.1, 0.2, 0.35], value), date(2026, 12, 1))
    assert result["reason"] == "INVALID_CALIBRATION_VALUES"


def test_duplicate_dates_and_changed_tolerance_are_not_silently_accepted():
    rows = history([0.1, 0.2, 0.3])
    rows[1].calibration_date = rows[0].calibration_date
    assert estimate_tolerance_risk(rows, date(2026, 12, 1))["reason"] == "DUPLICATE_CALIBRATION_DATES"
    rows = history([0.1, 0.2, 0.3])
    rows[0].tolerance = 2
    assert estimate_tolerance_risk(rows, date(2026, 12, 1))["reason"] == "TOLERANCE_CHANGED"
