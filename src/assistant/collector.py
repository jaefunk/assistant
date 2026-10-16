"""관심사별로 소스를 돌며 Item 을 모은다."""

from __future__ import annotations

import logging

from assistant.models import InterestDigest, Settings
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
        digest.items.sort(key=lambda i: i.published or 0, reverse=True)  # type: ignore[arg-type]
        digests.append(digest)
    return digests
