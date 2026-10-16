from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from assistant.models import SourceSpec
from assistant.sources import get_source
from assistant.sources.claude_search import ClaudeSearchSource, build_prompt, parse_items

JSON_TEXT = """검색 결과를 정리했습니다.
```json
[
  {"title": "A", "url": "https://x/a", "published": "2026-10-15", "summary": "에이"},
  {"title": "B", "url": "https://x/b", "published": null, "summary": ""},
  {"title": "", "url": "https://x/no-title"},
  {"title": "C", "url": "https://x/c", "published": "unknown"}
]
```"""


def test_parse_items_extracts_array_and_skips_invalid() -> None:
    items = parse_items(JSON_TEXT, limit=10)
    assert [i.title for i in items] == ["A", "B", "C"]
    assert items[0].published == datetime(2026, 10, 15, tzinfo=UTC)
    assert items[0].summary == "에이"
    assert items[1].published is None
    assert items[2].published is None


def test_parse_items_respects_limit() -> None:
    assert len(parse_items(JSON_TEXT, limit=2)) == 2


def test_parse_items_without_array_raises() -> None:
    with pytest.raises(ValueError):
        parse_items("검색 결과가 없습니다.", limit=5)


def test_build_prompt_mentions_query_days_limit() -> None:
    spec = SourceSpec(type="claude_search", query="LLM 소식", days=3)
    prompt = build_prompt(spec, 5, date(2026, 10, 16))
    assert "LLM 소식" in prompt
    assert "3일" in prompt
    assert "5개" in prompt
    assert "2026-10-16" in prompt


class _FakeMessages:
    """첫 호출은 pause_turn, 두 번째 호출에서 최종 JSON 을 돌려준다."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                stop_reason="pause_turn",
                stop_details=None,
                content=[SimpleNamespace(type="server_tool_use", text="")],
            )
        return SimpleNamespace(
            stop_reason="end_turn",
            stop_details=None,
            content=[SimpleNamespace(type="text", text=JSON_TEXT)],
        )


def test_fetch_resumes_after_pause_turn() -> None:
    messages = _FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    source = ClaudeSearchSource(client=client, model="m")
    items = source.fetch(SourceSpec(type="claude_search", query="q"), limit=10)

    assert [i.title for i in items] == ["A", "B", "C"]
    assert len(messages.calls) == 2
    assert messages.calls[0]["tools"][0]["type"] == "web_search_20260209"
    # 두 번째 호출은 assistant 턴을 붙여 이어 보낸다
    assert messages.calls[1]["messages"][-1]["role"] == "assistant"


def test_fetch_without_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        ClaudeSearchSource().fetch(SourceSpec(type="claude_search", query="q"), limit=1)


def test_registry_has_claude_search() -> None:
    assert isinstance(get_source("claude_search"), ClaudeSearchSource)
