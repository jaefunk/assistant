from types import SimpleNamespace

import anthropic
import httpx2

from assistant.models import Interest, InterestDigest, Item
from assistant.summarizer import summarize, summarize_one


def _digest() -> InterestDigest:
    return InterestDigest(
        interest=Interest(name="AI", sources=()),
        items=[Item(title="Hello", url="https://x/1")],
    )


class _FailingMessages:
    def create(self, **kwargs):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx2.Response(400, request=request, json={"error": {"message": "nope"}})
        raise anthropic.BadRequestError("nope", response=response, body=None)


class _OkMessages:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason="end_turn",
            stop_details=None,
            content=[SimpleNamespace(type="text", text="- 요약")],
        )


def _client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def test_api_error_returns_none_instead_of_raising() -> None:
    assert summarize_one(_client(_FailingMessages()), "m", _digest()) is None


def test_success_returns_text_and_passes_model() -> None:
    messages = _OkMessages()
    assert summarize_one(_client(messages), "claude-opus-5-5", _digest()) == "- 요약"
    assert messages.kwargs["model"] == "claude-opus-5-5"
    assert "Hello" in messages.kwargs["messages"][0]["content"]


def test_summarize_skips_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    digest = _digest()
    summarize([digest])
    assert digest.summary is None
