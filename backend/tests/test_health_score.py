from datetime import date

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.health_score import HealthScoreWeights
from app.services.analytics import DriftAnalyticsService
from tests.test_drift_analytics import make_calibration, make_instrument


def calculate(errors, weights=None, lifecycle_state="operational"):
    instrument = make_instrument(1, 1, "PT-HEALTH-001")
    instrument.lifecycle_state = lifecycle_state
    calibrations = [
        make_calibration(i + 1, 1, date(2026, i + 1, 1), error, tolerance=1.0)
        for i, error in enumerate(errors)
    ]
    return DriftAnalyticsService.calculate_drift_and_risk(
        instrument, calibrations, health_score_weights=weights
    )


def test_default_score_preserves_legacy_formula_and_explains_it():
    result = calculate([0.5])
    # Stable error / tolerance = 0.5; 40% and 35% penalties, no state penalty.
    assert result["health_score"] == 62.5
    details = result["health_score_details"]
    assert details["status"] == "CALCULATED"
    assert details["components"]["current_error"]["penalty_points"] == 17.5
    assert sum(c["penalty_points"] for c in details["components"].values()) == 37.5
    assert round(100 - details["total_penalty_points"], 1) == result["health_score"]


def test_custom_weights_change_score_without_changing_drift_or_risk():
    baseline = calculate([0.5], lifecycle_state="out_of_tolerance")
    custom = calculate(
        [0.5], HealthScoreWeights(risk_90_days=0, current_error=0, out_of_tolerance=1),
        lifecycle_state="out_of_tolerance",
    )
    assert baseline["health_score"] == 37.5
    assert custom["health_score"] == 0
    assert custom["drift_models"] == baseline["drift_models"]
    assert custom["risk_out_of_tolerance"] == baseline["risk_out_of_tolerance"]


@pytest.mark.parametrize("error,expected", [(0, 100), (2, 0), (-2, 0)])
def test_score_boundaries(error, expected):
    result = calculate([error], lifecycle_state="out_of_tolerance" if error else "operational")
    assert result["health_score"] == expected


def test_no_data_is_explicit_fallback_without_invented_components():
    result = calculate([])
    assert result["health_score"] == 50
    details = result["health_score_details"]
    assert details["fallback"] is True
    assert details["status"] == "NOT_CALCULATED"
    assert details["components"] == {}
    assert details["total_penalty_points"] is None


@pytest.mark.parametrize("weights", [
    {"risk_90_days": -0.1}, {"risk_90_days": 1.1},
    {"risk_90_days": float("nan")}, {"risk_90_days": float("inf")},
    {"risk_90_days": 0, "current_error": 0, "out_of_tolerance": 0},
    {"risk_90_days": 0.5}, {"unknown": 1},
])
def test_invalid_weights_rejected(weights):
    with pytest.raises(ValidationError):
        HealthScoreWeights(**weights)


def test_environment_config_is_used_by_service(monkeypatch):
    from app.services import analytics

    monkeypatch.setenv(
        "HEALTH_SCORE_WEIGHTS",
        '{"risk_90_days":0,"current_error":1,"out_of_tolerance":0}',
    )
    configured = Settings(_env_file=None)
    monkeypatch.setattr(analytics, "settings", configured)
    assert calculate([0.5])["health_score"] == 50


def test_invalid_environment_config_fails_validation(monkeypatch):
    monkeypatch.setenv("HEALTH_SCORE_WEIGHTS", '{"current_error":0.9}')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
