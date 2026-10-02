from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is Document:
            return self.session.document

        if self.model is ExtractedField:
            return self.session.fields[0] if self.session.fields else None

        if self.model is InstrumentUnit:
            return self.session.instrument

        return None

    def all(self):
        if self.model is ExtractedField:
            return self.session.fields

        return []


class FakeSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.document = SimpleNamespace(
            id=1,
            processing_status="REVIEW_REQUIRED",
            instrument_unit_id=None,
        )

        self.instrument = SimpleNamespace(
            id=7,
            serial_number="PT-001",
        )

        self.fields = [
            SimpleNamespace(
                id=10,
                document_id=1,
                field_name="serial_number",
                raw_value="WRONG-SERIAL",
                normalized_value="WRONG-SERIAL",
                confidence="1.0",
                validation_status="STAGING",
            ),
            SimpleNamespace(
                id=11,
                document_id=1,
                field_name="calibration_date",
                raw_value="2026-01-15",
                normalized_value="2026-01-15",
                confidence="1.0",
                validation_status="STAGING",
            ),
            SimpleNamespace(
                id=12,
                document_id=1,
                field_name="next_due_date",
                raw_value="2026-01-15",
                normalized_value="2026-01-15",
                confidence="1.0",
                validation_status="STAGING",
            ),
        ]

    def query(self, model):
        return FakeQuery(
            model=model,
            session=self,
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
    fake_db.reset()

    response = client.get(
        "/api/v1/documents/1/fields"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_id"] == 1
    assert data["processing_status"] == "REVIEW_REQUIRED"

    assert len(data["fields"]) == 3

    field = data["fields"][0]

    assert field["field_id"] == 10
    assert field["field_name"] == "serial_number"
    assert field["raw_value"] == "WRONG-SERIAL"
    assert field["normalized_value"] == "WRONG-SERIAL"
    assert field["validation_status"] == "STAGING"


def test_correct_extracted_field_preserves_raw_value():
    fake_db.reset()

    response = client.patch(
        "/api/v1/documents/1/fields/10",
        json={
            "normalized_value": "PT-001"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["field_id"] == 10
    assert data["raw_value"] == "WRONG-SERIAL"
    assert data["normalized_value"] == "PT-001"

    assert fake_db.fields[0].raw_value == "WRONG-SERIAL"
    assert fake_db.fields[0].normalized_value == "PT-001"


def test_revalidate_document_after_human_correction():
    fake_db.reset()

    fake_db.fields[0].normalized_value = "PT-001"
    fake_db.fields[1].normalized_value = "2026-01-15"
    fake_db.fields[2].normalized_value = "2027-01-15"

    response = client.post(
        "/api/v1/documents/1/revalidate"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_id"] == 1
    assert data["processing_status"] == "ACCEPTED"
    assert data["matched_instrument_id"] == 7
    assert data["rules_failed"] == []

    assert fake_db.document.processing_status == "ACCEPTED"
    assert fake_db.document.instrument_unit_id == 7