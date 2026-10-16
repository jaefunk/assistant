"""소스 타입 이름 -> 수집기 매핑."""

from __future__ import annotations

from assistant.sources.base import Source
from assistant.sources.rss import RssSource

REGISTRY: dict[str, type] = {
    "rss": RssSource,
}


def get_source(type_name: str) -> Source:
    try:
        return REGISTRY[type_name]()
    except KeyError as exc:
        raise ValueError(f"알 수 없는 source type: {type_name!r}") from exc
