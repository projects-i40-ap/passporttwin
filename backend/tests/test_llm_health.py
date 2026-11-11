"""Tests de la sonda de disponibilidad de `llama.cpp` (Spec 001 — T7)."""

import requests

from app.core.config import settings
from app.services import llm_health


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def test_probe_reports_available_when_server_answers(monkeypatch):
    monkeypatch.setattr(settings, "ai_probe_enabled", True)
    monkeypatch.setattr(settings, "ai_base_url", "http://llama.test/v1")
    llm_health.reset_availability_cache()
    monkeypatch.setattr(llm_health.requests, "get", lambda *args, **kwargs: FakeResponse(200))

    assert llm_health.llama_cpp_available() is True


def test_probe_reports_unavailable_when_server_is_down(monkeypatch):
    monkeypatch.setattr(settings, "ai_probe_enabled", True)
    llm_health.reset_availability_cache()

    def refuse(*args, **kwargs):
        raise requests.exceptions.ConnectionError("apagado")

    monkeypatch.setattr(llm_health.requests, "get", refuse)

    assert llm_health.llama_cpp_available() is False


def test_probe_is_cached_until_forced(monkeypatch):
    monkeypatch.setattr(settings, "ai_probe_enabled", True)
    monkeypatch.setattr(settings, "ai_probe_cache_seconds", 60.0)
    llm_health.reset_availability_cache()
    calls = {"count": 0}

    def down(*args, **kwargs):
        calls["count"] += 1
        raise requests.exceptions.Timeout("lento")

    monkeypatch.setattr(llm_health.requests, "get", down)
    assert llm_health.llama_cpp_available() is False
    assert llm_health.llama_cpp_available() is False
    assert calls["count"] == 1

    monkeypatch.setattr(llm_health.requests, "get", lambda *args, **kwargs: FakeResponse(200))
    assert llm_health.llama_cpp_available(force=True) is True


def test_probe_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_probe_enabled", False)
    llm_health.reset_availability_cache()

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("no debe sondearse el servidor si la sonda está desactivada")

    monkeypatch.setattr(llm_health.requests, "get", must_not_be_called)

    assert llm_health.llama_cpp_available() is False
