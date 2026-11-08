import httpx
import pytest

from app.config import settings
from app.services import complaints_ai as ai


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._payload


def gemini_payload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_provider_choice(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ai.default_llm() is None
    monkeypatch.setattr(settings, "anthropic_api_key", "x")
    assert ai.default_llm() is ai.anthropic_llm
    monkeypatch.setattr(settings, "gemini_api_key", "y")
    assert ai.default_llm() is ai.gemini_llm


def test_gemini_reply_is_parsed_and_validated(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    reply = '```json\n{"category": "plumbing", "urgency": "high", "confidence": 88}\n```'
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(gemini_payload(reply)))
    r = ai.classify_complaint("Water leaking in bathroom", llm=ai.gemini_llm)
    assert (r.category, r.urgency, r.source) == ("plumbing", "high", "llm")


@pytest.mark.parametrize("resp", [FakeResp({}, 429), FakeResp(gemini_payload("no json here")),
                                  FakeResp({"candidates": []})])
def test_gemini_failures_fall_back_to_keywords(monkeypatch, resp):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: resp)
    r = ai.classify_complaint("Water leaking from the tap", llm=ai.gemini_llm)
    assert r.source == "fallback" and r.category == "plumbing"


def test_safety_rule_still_wins_over_gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    reply = '{"category": "general", "urgency": "low", "confidence": 95}'
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(gemini_payload(reply)))
    r = ai.classify_complaint("Gas smell in the corridor", llm=ai.gemini_llm)
    assert r.urgency == "critical" and r.safety_escalated
