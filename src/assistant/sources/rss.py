"""RSS / Atom 피드 수집기.

- keywords 가 있으면 제목·요약에 그 중 하나라도 들어 있는 항목만 남긴다 (대소문자·공백 무시).
- days 일보다 오래된 글은 뺀다 (기본 7). 날짜가 없는 글은 통과. 처음 붙인 피드가 묵은 글을
  한꺼번에 쏟아내지 않게 한다.
- 한 번 리포트에 실은 항목은 장부(data/rss_seen.json)에 적어 두고 다음 실행에서는 빼서,
  피드가 같은 글을 며칠씩 보여줘도 새 소식만 싣는다. 오래된 기록은 SEEN_KEEP_DAYS 뒤 지운다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import mktime
from urllib.parse import urlparse

import feedparser
import httpx

from assistant.models import Item, SourceSpec

log = logging.getLogger(__name__)

SEEN_PATH = Path(os.environ.get("RSS_SEEN_PATH", "data/rss_seen.json"))
SEEN_KEEP_DAYS = 90


class RssSource:
    def __init__(
        self,
        client: httpx.Client | None = None,
        seen_path: Path | None = SEEN_PATH,
        today: date | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; assistant-report/0.1)"},
        )
        self._seen_path = seen_path
        self._today = today

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        response = self._client.get(spec.url)
        response.raise_for_status()
        today = self._today or datetime.now(tz=UTC).date()
        seen = load_seen(self._seen_path, today)
        oldest = today - timedelta(days=spec.days)
        total = len(feedparser.parse(response.text).entries)
        matched = parse_feed(response.text, spec.keywords)
        recent = [i for i in matched if i.published is None or i.published.date() >= oldest]
        items = [i for i in recent if i.url not in seen][:limit]
        log.info(
            "rss: %s 항목 %d개 → 키워드 %d → 최근 %d일 %d → 새 글 %d",
            urlparse(spec.url).netloc,
            total,
            len(matched),
            spec.days,
            len(recent),
            len(items),
        )
        for item in items:
            seen[item.url] = today.isoformat()
        save_seen(self._seen_path, seen)
        return items


def parse_feed(text: str, keywords: tuple[str, ...] = (), limit: int | None = None) -> list[Item]:
    """피드를 Item 목록으로. keywords 가 있으면 제목·요약에 하나라도 들어 있는 항목만."""
    feed = feedparser.parse(text)
    items: list[Item] = []
    for entry in feed.entries:
        if limit is not None and len(items) >= limit:
            break
        title = (entry.get("title") or "(제목 없음)").strip()
        if not matches_keywords(keywords, title, _summary_text(entry)):
            continue
        published = None
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if struct:
            published = datetime.fromtimestamp(mktime(struct), tz=UTC)
        items.append(Item(title=title, url=entry.get("link", ""), published=published))
    return items


def matches_keywords(keywords: tuple[str, ...], *texts: str) -> bool:
    """keywords 가 비어 있으면 모두 통과. 대소문자와 공백을 무시하고 하나라도 들어 있으면 통과."""
    if not keywords:
        return True
    haystack = "".join(texts).replace(" ", "").casefold()
    return any(k.replace(" ", "").casefold() in haystack for k in keywords if k.strip())


def load_seen(path: Path | None, today: date) -> dict[str, str]:
    """{url: 처음 실은 날짜}. SEEN_KEEP_DAYS 보다 오래된 기록은 버린다."""
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("rss: 장부 파일을 읽지 못해 새로 시작합니다 (%s)", path)
        return {}
    if not isinstance(raw, dict):
        return {}
    cutoff = (today - timedelta(days=SEEN_KEEP_DAYS)).isoformat()
    return {k: v for k, v in raw.items() if isinstance(v, str) and v >= cutoff}


def save_seen(path: Path | None, seen: dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _summary_text(entry) -> str:
    """요약은 키워드 대조에만 쓴다 (리포트에는 안 싣는다). HTML 태그는 벗긴다."""
    return re.sub(r"<[^>]+>", " ", entry.get("summary", "") or "")
