"""소스 타입 이름 -> 수집기 매핑."""

from __future__ import annotations

from assistant.sources.base import Source
from assistant.sources.claude_search import ClaudeSearchSource
from assistant.sources.kopis import KopisSource
from assistant.sources.rss import RssSource

REGISTRY: dict[str, type] = {
    "rss": RssSource,
    "claude_search": ClaudeSearchSource,
    "kopis": KopisSource,
}


def get_source(type_name: str) -> Source:
    try:
        return REGISTRY[type_name]()
    except KeyError as exc:
        raise ValueError(f"알 수 없는 source type: {type_name!r}") from exc
