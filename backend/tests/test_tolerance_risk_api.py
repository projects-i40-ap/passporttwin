from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.instrument import InstrumentUnit
from app.models.maintenance import MaintenanceEvent
from tests.test_drift_analytics import make_instrument
from tests.test_tolerance_risk import history


def test_risk_endpoint_temporal_filter_contract_and_not_found():
    class Session:
        found = True

        def query(self, model):
            self.model = model
            return self

        def filter(self, *args):
            return self

        def first(self):
            return make_instrument(1, 1, "RISK") if self.found else None

        def all(self):
            # Future observation must be excluded even if supplied by a test double.
            return [] if self.model is MaintenanceEvent else history([0.1, 0.23, 0.29, 1000])

    session = Session()

    def override_db():
        yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        result = client.get("/api/v1/instruments/1/tolerance-risk?as_of=2026-03-02")
        assert result.status_code == 200
        data = result.json()
        assert data["calibrations_used"] == 3
        assert data["horizons"]["30_days"]["target_date"] == "2026-04-01"
        assert data["validation_status"] == "EXPERIMENTAL_UNCALIBRATED"
        assert client.get("/api/v1/instruments/1/tolerance-risk?as_of=invalid").status_code == 422
        session.found = False
        assert client.get("/api/v1/instruments/1/tolerance-risk").status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
