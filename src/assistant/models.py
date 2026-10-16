"""파이프라인 전반에서 쓰는 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceSpec:
    """config/interests.yaml 의 source 한 항목."""

    type: str
    url: str


@dataclass(frozen=True)
class Interest:
    """관심사 하나. 여러 소스를 가진다."""

    name: str
    sources: tuple[SourceSpec, ...]


@dataclass(frozen=True)
class Settings:
    interests: tuple[Interest, ...]
    max_items_per_source: int = 10


@dataclass(frozen=True)
class Item:
    """소스에서 수집한 정보 한 건."""

    title: str
    url: str
    published: datetime | None = None
    summary: str = ""


@dataclass
class InterestDigest:
    """관심사별 수집 결과 + (선택) 요약."""

    interest: Interest
    items: list[Item] = field(default_factory=list)
    summary: str | None = None
