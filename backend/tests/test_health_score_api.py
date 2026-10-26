from datetime import date

from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.calibration import CalibrationEvent
from tests.test_drift_analytics import make_calibration, make_instrument


def test_predictions_api_serializes_score_breakdown():
    instrument = make_instrument(1, 1, "PT-HEALTH-API")
    calibration = make_calibration(1, 1, date(2026, 1, 1), 0.5, tolerance=1)

    class Query:
        def __init__(self, model):
            self.model = model

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def first(self):
            return instrument

        def all(self):
            return [calibration] if self.model is CalibrationEvent else [(1,)]

    class Session:
        def query(self, model):
            return Query(model)

    def override_db():
        yield Session()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/v1/instruments/1/predictions")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 200
    result = response.json()
    assert result["health_score"] == 62.5
    details = result["health_score_details"]
    assert details["score"] == result["health_score"]
    assert details["components"]["risk_90_days"]["value"] == 0.5
    assert round(100 - details["total_penalty_points"], 1) == result["health_score"]
