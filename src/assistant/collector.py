"""관심사별로 소스를 돌며 Item 을 모은다."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

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
                log.warning("수집 실패: %s (%s): %s", spec.url, interest.name, exc)
                continue
            digest.items.extend(items)
        digest.items.sort(key=_sort_key, reverse=True)
        digests.append(digest)
    return digests


_OLDEST = datetime.min.replace(tzinfo=UTC)


def _sort_key(item: Item) -> datetime:
    """최신순 정렬. 날짜 없는 항목은 맨 뒤로."""
    return item.published or _OLDEST
