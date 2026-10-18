"""
Tests TDD del Bloque LEGO 1 (Spec 001 — T2).

Cubren:
- La extracción determinista ampliada de `PDFCertificateExtractor`
  (incluyendo `unit` y `operating_range`).
- La extracción vía `LLMOCRDocumentExtractor` simulando `llama.cpp`
  sirviendo `gemma-4-e4b` (con limpieza de bloques Markdown ```json).
- El fallback automático a determinista ante errores de red, timeout o
  JSON inválido (RF-LEGO-02), sin lanzar excepción.
"""

import pytest
import requests

from app.services import pdf_extractor
from app.services.pdf_extractor import (
    HybridDocumentExtractor,
    LLMOCRDocumentExtractor,
    PDFCertificateExtractor,
)

SAMPLE_CERTIFICATE_TEXT = (
    "Certificate of Calibration\n"
    "S/N: PT-WIKA-001\n"
    "Calibration Date: 2026-01-15\n"
    "Due Date: 2027-01-15\n"
    "Max Error: 0.5\n"
    "Tolerance: 1.0\n"
    "Unidad: bar\n"
    "Rango: 0-10 bar\n"
)

LLM_JSON_CONTENT = (
    '{"serial_number": "PT-WIKA-001", '
    '"calibration_date": "2026-01-15", '
    '"next_due_date": "2027-01-15", '
    '"error_value": 0.5, '
    '"tolerance": 1.0, '
    '"unit": "kPa", '
    '"operating_range": "0 - 10 bar"}'
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


def patch_pdf_text(monkeypatch, text=SAMPLE_CERTIFICATE_TEXT):
    """Sustituye `pdfplumber.open` por un PDF falso con el texto indicado."""
    monkeypatch.setattr(
        pdf_extractor.pdfplumber,
        "open",
        lambda path: FakePDF(text),
    )


class FakeHTTPResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}"
            )

    def json(self):
        return self._payload


def llama_cpp_response(content):
    """Construye una respuesta OpenAI-compatible de `llama.cpp`."""
    return FakeHTTPResponse(
        payload={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        }
    )


def make_extractor(enabled=True):
    return LLMOCRDocumentExtractor(
        base_url="http://localhost:8080/v1",
        model_name="gemma-4-e4b",
        timeout=5.0,
        enabled=enabled,
    )


# --- Extracción determinista ampliada --------------------------------------


def test_deterministic_extractor_captures_unit_and_operating_range(monkeypatch):
    patch_pdf_text(monkeypatch)

    fields = PDFCertificateExtractor.extract_and_parse("certificate.pdf")

    assert fields["serial_number"] == "PT-WIKA-001"
    assert fields["calibration_date"] == "2026-01-15"
    assert fields["next_due_date"] == "2027-01-15"
    assert fields["error_value"] == 0.5
    assert fields["tolerance"] == 1.0
    assert fields["unit"] == "bar"
    assert fields["operating_range"] == "0-10 bar"


def test_deterministic_extractor_can_return_full_text(monkeypatch):
    patch_pdf_text(monkeypatch)

    fields = PDFCertificateExtractor.extract_and_parse(
        "certificate.pdf",
        include_full_text=True,
    )

    assert "__full_text__" in fields
    assert "Certificate of Calibration" in fields["__full_text__"]


# --- Extracción vía LLM (llama.cpp mockeado) -------------------------------


def test_llm_extractor_parses_json_from_markdown_fence(monkeypatch):
    patch_pdf_text(monkeypatch)

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return llama_cpp_response(f"```json\n{LLM_JSON_CONTENT}\n```")

    monkeypatch.setattr(pdf_extractor.requests, "post", fake_post)

    extractor = make_extractor(enabled=True)
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="llm")

    assert captured["url"] == "http://localhost:8080/v1/chat/completions"
    assert captured["json"]["model"] == "gemma-4-e4b"
    assert captured["timeout"] == 5.0

    assert fields["extractor_used"] == "llm"
    assert fields["serial_number"] == "PT-WIKA-001"
    assert fields["unit"] == "kPa"
    assert fields["operating_range"] == "0 - 10 bar"


def test_llm_extractor_is_skipped_when_disabled_in_auto_mode(monkeypatch):
    patch_pdf_text(monkeypatch)

    def fake_post(*args, **kwargs):
        raise AssertionError("llama.cpp no debería invocarse si está desactivado")

    monkeypatch.setattr(pdf_extractor.requests, "post", fake_post)

    extractor = make_extractor(enabled=False)
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="auto")

    assert fields["extractor_used"] == "deterministic"
    assert fields["unit"] == "bar"


# --- Fallback resiliente (RF-LEGO-02) --------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.ConnectionError("llama.cpp apagado"),
        requests.exceptions.Timeout("timeout agotado"),
        requests.exceptions.HTTPError("HTTP 500"),
    ],
)
def test_llm_extractor_falls_back_on_network_and_timeout(monkeypatch, failure):
    patch_pdf_text(monkeypatch)

    def fake_post(*args, **kwargs):
        raise failure

    monkeypatch.setattr(pdf_extractor.requests, "post", fake_post)

    extractor = make_extractor(enabled=True)

    # No debe propagar ninguna excepción.
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="llm")

    assert fields["extractor_used"] == "deterministic_fallback"
    assert fields["serial_number"] == "PT-WIKA-001"
    assert fields["unit"] == "bar"


def test_llm_extractor_falls_back_on_malformed_json(monkeypatch):
    patch_pdf_text(monkeypatch)

    monkeypatch.setattr(
        pdf_extractor.requests,
        "post",
        lambda *args, **kwargs: llama_cpp_response("Lo siento, no puedo ayudarte."),
    )

    extractor = make_extractor(enabled=True)
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="llm")

    assert fields["extractor_used"] == "deterministic_fallback"
    assert fields["unit"] == "bar"


def test_llm_extractor_falls_back_on_unexpected_payload(monkeypatch):
    patch_pdf_text(monkeypatch)

    monkeypatch.setattr(
        pdf_extractor.requests,
        "post",
        lambda *args, **kwargs: FakeHTTPResponse(payload={"unexpected": True}),
    )

    extractor = make_extractor(enabled=True)
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="llm")

    assert fields["extractor_used"] == "deterministic_fallback"


def test_hybrid_extractor_alias_is_available(monkeypatch):
    patch_pdf_text(monkeypatch)

    monkeypatch.setattr(
        pdf_extractor.requests,
        "post",
        lambda *args, **kwargs: llama_cpp_response(LLM_JSON_CONTENT),
    )

    extractor = HybridDocumentExtractor(
        base_url="http://localhost:8080/v1",
        model_name="gemma-4-e2b",
        timeout=5.0,
        enabled=True,
    )
    fields = extractor.extract_and_parse("certificate.pdf", extractor_mode="auto")

    assert fields["extractor_used"] == "llm"
    assert fields["serial_number"] == "PT-WIKA-001"
