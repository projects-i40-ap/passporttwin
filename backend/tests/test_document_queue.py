"""Tests de la cola de procesamiento de la subida (Spec 001 — T7)."""

from types import SimpleNamespace

from app.api import documents as documents_api


class FakeSession:
    def __init__(self, document):
        self.document = document
        self.closed = False

    def query(self, model):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.document

    def rollback(self):
        pass

    def commit(self):
        pass

    def close(self):
        self.closed = True


def test_queued_document_is_processed_with_auto_extraction(monkeypatch):
    session = FakeSession(SimpleNamespace(id=9, processing_status="QUEUED"))
    calls = {}

    monkeypatch.setattr(documents_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        documents_api,
        "_extract_and_store",
        lambda db, doc, extractor, reference_date: calls.update(
            extractor=extractor, document_id=doc.id
        ) or {},
    )

    documents_api._process_queued_document(9)

    assert calls == {"extractor": "auto", "document_id": 9}
    assert session.closed is True


def test_document_already_processed_is_not_reprocessed(monkeypatch):
    session = FakeSession(SimpleNamespace(id=9, processing_status="REVIEW_REQUIRED"))

    monkeypatch.setattr(documents_api, "SessionLocal", lambda: session)

    def must_not_run(*args, **kwargs):
        raise AssertionError("no debe reprocesarse un documento ya revisado")

    monkeypatch.setattr(documents_api, "_extract_and_store", must_not_run)

    documents_api._process_queued_document(9)

    assert session.closed is True


def test_processing_failure_marks_document_as_failed(monkeypatch):
    document = SimpleNamespace(id=9, processing_status="QUEUED")
    session = FakeSession(document)

    monkeypatch.setattr(documents_api, "SessionLocal", lambda: session)

    def explode(*args, **kwargs):
        raise RuntimeError("modelo caído")

    monkeypatch.setattr(documents_api, "_extract_and_store", explode)

    documents_api._process_queued_document(9)

    assert document.processing_status == "FAILED_EXTRACTION"
    assert session.closed is True
