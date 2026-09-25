from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.document import Document, ExtractedField


class FakeQuery:
    def __init__(self, model, document, field):
        self.model = model
        self.document = document
        self.field = field

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is Document:
            return self.document

        if self.model is ExtractedField:
            return self.field

        return None

    def all(self):
        if self.model is ExtractedField:
            return [self.field]

        return []


class FakeSession:
    def __init__(self):
        self.document = SimpleNamespace(
            id=1,
            processing_status="REVIEW_REQUIRED",
        )

        self.field = SimpleNamespace(
            id=10,
            document_id=1,
            field_name="serial_number",
            raw_value="SN-RAW-001",
            normalized_value="SN-RAW-001",
            confidence="1.0",
            validation_status="STAGING",
        )

    def query(self, model):
        return FakeQuery(
            model=model,
            document=self.document,
            field=self.field,
        )

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


fake_db = FakeSession()


def override_get_db():
    try:
        yield fake_db
    finally:
        pass


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_get_extracted_fields():
    response = client.get(
        "/api/v1/documents/1/fields"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_id"] == 1
    assert data["processing_status"] == "REVIEW_REQUIRED"

    assert len(data["fields"]) == 1

    field = data["fields"][0]

    assert field["field_id"] == 10
    assert field["field_name"] == "serial_number"
    assert field["raw_value"] == "SN-RAW-001"
    assert field["normalized_value"] == "SN-RAW-001"
    assert field["validation_status"] == "STAGING"


def test_correct_extracted_field_preserves_raw_value():
    response = client.patch(
        "/api/v1/documents/1/fields/10",
        json={
            "normalized_value": "SN-CORRECTED-001"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["field_id"] == 10
    assert data["raw_value"] == "SN-RAW-001"
    assert data["normalized_value"] == "SN-CORRECTED-001"

    assert fake_db.field.raw_value == "SN-RAW-001"
    assert (
        fake_db.field.normalized_value
        == "SN-CORRECTED-001"
    )