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
    sources = tuple(
        SourceSpec(type=str(s["type"]), url=str(s["url"])) for s in entry.get("sources", [])
    )
    return Interest(name=str(name), sources=sources)
