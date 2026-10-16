"""파이프라인 전반에서 쓰는 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceSpec:
    """config/interests.yaml 의 source 한 항목.

    rss 는 url 을, claude_search 는 query 를, kopis 는 names 를 쓴다.
    """

    type: str
    url: str = ""
    query: str = ""
    days: int = 7
    names: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    since_days: int = 1


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
    summary: str = ""  # 요약 모델에 넘길 설명. 리포트에는 안 보임
    details: str = ""  # 리포트에 제목 아래 한 줄로 보여줄 정보 (장소, 기간, 가격 등)
    attribution: str = ""  # 데이터 출처 표기 의무가 있는 소스의 문구. 리포트 끝에 모아 표시


@dataclass
class InterestDigest:
    """관심사별 수집 결과 + (선택) 요약."""

    interest: Interest
    items: list[Item] = field(default_factory=list)
    summary: str | None = None
