from datetime import datetime
from types import SimpleNamespace

from app.services.aas_builder import AASBuilder


def test_sync_document_provenance_projects_all_documents(monkeypatch):
    instrument = SimpleNamespace(
        serial_number="PT-001",
    )

    documents = [
        SimpleNamespace(
            id=2,
            original_filename="certificate_2.pdf",
            source_type="PDF_CERTIFICATE",
            sha256_hash="hash-2",
            processing_status="ACCEPTED",
            uploaded_at=datetime(2026, 10, 3, 20, 3, 50),
        ),
        SimpleNamespace(
            id=1,
            original_filename="certificate_1.pdf",
            source_type="PDF_CERTIFICATE",
            sha256_hash="hash-1",
            processing_status="ACCEPTED",
            uploaded_at=datetime(2026, 10, 3, 17, 58, 51),
        ),
    ]

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

    def fake_put(url, json, headers, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "app.services.aas_builder.requests.put",
        fake_put,
    )

    result = AASBuilder.sync_document_provenance(
        instrument,
        documents,
    )

    assert result is True

    assert captured["url"].endswith(
        "/shells/AAS_PT_001/aas/submodels/DocumentProvenance"
    )

    payload = captured["payload"]

    assert payload["idShort"] == "DocumentProvenance"
    assert payload["identification"]["id"] == "Submodel_DocumentProvenance_PT_001"
    assert (
        payload["semanticId"]["keys"][0]["value"]
        == "urn:passporttwin:submodel:document-provenance:1:0"
    )

    assert [
        element["idShort"]
        for element in payload["submodelElements"]
    ] == [
        "Document_1",
        "Document_2",
    ]

    first_document = payload["submodelElements"][0]

    assert first_document["modelType"]["name"] == "SubmodelElementCollection"

    first_values = {
        element["idShort"]: element["value"]
        for element in first_document["value"]
    }

    assert first_values["DocumentId"] == "1"
    assert first_values["OriginalFilename"] == "certificate_1.pdf"
    assert first_values["SourceType"] == "PDF_CERTIFICATE"
    assert first_values["Sha256"] == "hash-1"
    assert first_values["ProcessingStatus"] == "ACCEPTED"
    assert first_values["UploadedAt"] == "2026-10-03T17:58:51"