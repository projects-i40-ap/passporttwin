from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core.config import Settings
from app.database.session import get_db
from app.main import app
from app.api import instruments

PUBLIC_ID = UUID("4434615b-3283-4615-9a74-93654abeef01")


@pytest.fixture
def client():
    class Session:
        found = True
        def query(self, *args): return self
        def filter(self, *args): return self
        def first(self):
            return SimpleNamespace(id=1, public_id=PUBLIC_ID, serial_number="PT-PASSPORT",
                manufacturer="TEST",model="TEST",location="Lab A",criticality="HIGH",
                lifecycle_state="operational",aas_sync_status="PENDING",created_at=datetime(2026,1,1)) if self.found else None
    session = Session()
    def override(): yield session
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_resolver_uses_configured_frontend_and_canonical_uuid(client, monkeypatch):
    monkeypatch.setattr(instruments, "settings", Settings(_env_file=None,
        passport_frontend_base_url="https://passport.example.com/"))
    response = client[0].get(f"/api/v1/instruments/passport/{PUBLIC_ID}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == f"https://passport.example.com/passport/{PUBLIC_ID}"


def test_qr_encodes_configured_resolver_not_view(client, monkeypatch):
    captured = []
    original = instruments.qrcode.QRCode.add_data
    def capture(self, value, *args, **kwargs):
        captured.append(value)
        return original(self,value,*args,**kwargs)
    monkeypatch.setattr(instruments.qrcode.QRCode,"add_data",capture)
    monkeypatch.setattr(instruments,"settings",Settings(_env_file=None,
        public_api_base_url="https://api.example.com/gateway/"))
    response = client[0].get(f"/api/v1/instruments/{PUBLIC_ID}/qr")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert captured == [f"https://api.example.com/gateway/api/v1/instruments/passport/{PUBLIC_ID}"]


def test_read_by_public_id_and_missing_instrument(client):
    http, session = client
    assert http.get(f"/api/v1/instruments/by-public-id/{PUBLIC_ID}").json()["serial_number"] == "PT-PASSPORT"
    session.found = False
    for path in (f"by-public-id/{PUBLIC_ID}",f"passport/{PUBLIC_ID}",f"{PUBLIC_ID}/qr"):
        assert http.get('/api/v1/instruments/'+path,follow_redirects=False).status_code == 404
    assert http.get('/api/v1/instruments/by-public-id/not-a-uuid').status_code == 422


@pytest.mark.parametrize('url', ['javascript:alert(1)','ftp://example.com','https://user:pass@example.com','https://example.com?x=1','https://example.com/#fragment'])
def test_invalid_base_urls_fail_configuration(url):
    with pytest.raises(ValidationError): Settings(_env_file=None,public_api_base_url=url)
    with pytest.raises(ValidationError): Settings(_env_file=None,passport_frontend_base_url=url)
