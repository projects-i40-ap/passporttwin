"""Tests de la clasificación documental por contenido (Spec 001 — T7)."""

from app.services import document_classifier

CERTIFICATE_TEXT = (
    "Certificate of Calibration\n"
    "Serial Number: PT-001\n"
    "Calibration Date: 2026-01-15\n"
    "Due Date: 2027-01-15\n"
    "Max Error: 0.5\n"
    "Tolerance: 1.0\n"
)

DATASHEET_TEXT = (
    "DS18B20 Programmable Resolution 1-Wire Digital Thermometer\n"
    "FEATURES\n"
    "PIN CONFIGURATION\n"
    "ABSOLUTE MAXIMUM RATINGS\n"
    "ORDERING INFORMATION\n"
    "ELECTRICAL CHARACTERISTICS\n"
)

AMBIGUOUS_TEXT = (
    "Technical data\n"
    "Certificate of calibration\n"
    "Calibration Date: 2026-01-15\n"
)


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePDF:
    def __init__(self, text):
        self.pages = [FakePage(text)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def patch_text(monkeypatch, text):
    monkeypatch.setattr(
        document_classifier.pdfplumber,
        "open",
        lambda path: FakePDF(text),
    )


def test_certificate_text_is_classified_as_certificate(monkeypatch):
    patch_text(monkeypatch, CERTIFICATE_TEXT)

    assert document_classifier.classify_document("x.pdf", "x.pdf") == "PDF_CERTIFICATE"


def test_datasheet_markers_win_over_generic_specifications(monkeypatch):
    patch_text(monkeypatch, DATASHEET_TEXT)

    assert document_classifier.classify_document("ds18b20.pdf", "ds18b20.pdf") == "PDF_DATASHEET"


def test_specific_certificate_markers_win_on_ties(monkeypatch):
    patch_text(monkeypatch, AMBIGUOUS_TEXT)

    assert document_classifier.classify_document("x.pdf", "x.pdf") == "PDF_CERTIFICATE"


def test_filename_hint_is_only_a_tiebreaker(monkeypatch):
    patch_text(monkeypatch, "Texto sin marcadores conocidos")

    assert document_classifier.classify_document("ficha-tecnica.pdf", "ficha.pdf") == "PDF_DATASHEET"


def test_unknown_content_defaults_to_certificate(monkeypatch):
    patch_text(monkeypatch, "Texto sin marcadores conocidos")

    assert document_classifier.classify_document("documento.pdf", "documento.pdf") == "PDF_CERTIFICATE"


def test_unreadable_pdf_falls_back_to_filename(monkeypatch):
    def explode(path):
        raise RuntimeError("PDF corrupto")

    monkeypatch.setattr(document_classifier.pdfplumber, "open", explode)

    assert document_classifier.classify_document("datasheet.pdf", "datasheet.pdf") == "PDF_DATASHEET"
    assert document_classifier.classify_document("raro.pdf", "raro.pdf") == "PDF_CERTIFICATE"
