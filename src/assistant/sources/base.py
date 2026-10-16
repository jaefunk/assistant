"""수집기(Source) 인터페이스."""

from __future__ import annotations

from typing import Protocol

from assistant.models import Item, SourceSpec


class Source(Protocol):
    """소스 하나에서 Item 목록을 가져오는 수집기.

    새 수집기를 추가하려면 이 프로토콜을 만족하는 클래스를 만들고
    sources/__init__.py 의 REGISTRY 에 type 이름으로 등록하면 됩니다.
    """

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]: ...
