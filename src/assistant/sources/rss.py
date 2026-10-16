"""RSS / Atom 피드 수집기."""

from __future__ import annotations

from datetime import UTC, datetime
from time import mktime

import feedparser
import httpx

from assistant.models import Item, SourceSpec


class RssSource:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0, follow_redirects=True)

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        response = self._client.get(spec.url)
        response.raise_for_status()
        return parse_feed(response.text, limit)


def parse_feed(text: str, limit: int) -> list[Item]:
    feed = feedparser.parse(text)
    items: list[Item] = []
    for entry in feed.entries[:limit]:
        published = None
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if struct:
            published = datetime.fromtimestamp(mktime(struct), tz=UTC)
        items.append(
            Item(
                title=entry.get("title", "(제목 없음)").strip(),
                url=entry.get("link", ""),
                published=published,
                summary=entry.get("summary", ""),
            )
        )
    return items
