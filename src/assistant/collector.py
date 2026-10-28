"""관심사별로 소스를 돌며 Item 을 모은다."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from assistant.models import InterestDigest, Item, Settings
from assistant.sources import get_source

log = logging.getLogger(__name__)


def collect(settings: Settings) -> list[InterestDigest]:
    digests: list[InterestDigest] = []
    for interest in settings.interests:
        digest = InterestDigest(interest=interest)
        for spec in interest.sources:
            try:
                items = get_source(spec.type).fetch(spec, settings.max_items_per_source)
            except Exception as exc:  # 소스 하나가 죽어도 리포트 전체는 나가야 한다
                label = _host(spec.url) or ", ".join(spec.names)
                log.warning("수집 실패: %s %s (%s): %s", spec.type, label, interest.name, exc)
                digest.failures.append(f"{interest.name} · {spec.type} {label}: {str(exc)[:120]}")
                continue
            digest.items.extend(items)
        news = [i for i in digest.items if not i.standing]
        standing = [i for i in digest.items if i.standing]
        news.sort(key=_sort_key, reverse=True)
        standing.sort(key=lambda i: (i.event_date is None, i.event_date or date.max))
        digest.items = news + standing
        digests.append(digest)
    return digests


_OLDEST = datetime.min.replace(tzinfo=UTC)


def _host(url: str) -> str:
    """실패 표시용. 긴 피드 주소 대신 호스트만."""
    return urlparse(url).netloc or url


def _sort_key(item: Item) -> datetime:
    """최신순 정렬. 날짜 없는 항목은 맨 뒤로."""
    return item.published or _OLDEST
