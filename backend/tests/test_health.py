from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_root():
    """Valida el punto de entrada base de la API."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "passporttwin-backend"

def test_health_check():
    """Valida el healthcheck utilizado por los orquestadores."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}