"""config/interests.yaml 로딩."""

from __future__ import annotations

from pathlib import Path

import yaml

from assistant.models import Interest, Settings, SourceSpec

DEFAULT_CONFIG_PATH = Path("config/interests.yaml")


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    interests = tuple(_parse_interest(entry) for entry in raw.get("interests", []))
    if not interests:
        raise ValueError(f"{path}: 'interests' 가 비어 있습니다.")
    return Settings(
        interests=interests,
        max_items_per_source=int(raw.get("max_items_per_source", 10)),
    )


def _parse_interest(entry: dict) -> Interest:
    name = entry.get("name")
    if not name:
        raise ValueError("interest 항목에 'name' 이 필요합니다.")
    sources = tuple(_parse_source(s, str(name)) for s in entry.get("sources", []))
    return Interest(name=str(name), sources=sources)


def _parse_source(raw: dict, interest_name: str) -> SourceSpec:
    spec = SourceSpec(
        type=str(raw.get("type", "")),
        url=str(raw.get("url", "") or ""),
        days=int(raw.get("days", 7)),
        names=_str_tuple(raw.get("names")),
        genres=_str_tuple(raw.get("genres")),
        areas=_str_tuple(raw.get("areas")),
        since_days=int(raw.get("since_days", 1)),
    )
    if not spec.type:
        raise ValueError(f"{interest_name}: source 에 'type' 이 필요합니다.")
    if not (spec.url or spec.names):
        raise ValueError(f"{interest_name}: source 에 'url' 또는 'names' 가 필요합니다.")
    return spec


def _str_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.split(",")
    return tuple(str(v).strip() for v in value if str(v).strip())
