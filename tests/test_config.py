from pathlib import Path

import pytest

from assistant.config import load_settings


def test_load_settings(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text(
        "interests:\n"
        "  - name: AI\n"
        "    sources:\n"
        "      - type: rss\n"
        "        url: https://example.com/feed\n"
        "max_items_per_source: 3\n",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert [i.name for i in settings.interests] == ["AI"]
    assert settings.interests[0].sources[0].url == "https://example.com/feed"
    assert settings.max_items_per_source == 3


def test_empty_interests_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text("interests: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_repo_config_is_valid() -> None:
    settings = load_settings(Path(__file__).parent.parent / "config" / "interests.yaml")
    assert settings.interests


def test_claude_search_source_parses_query_and_days(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text(
        "interests:\n"
        "  - name: AI\n"
        "    sources:\n"
        "      - type: claude_search\n"
        "        query: LLM 소식\n"
        "        days: 3\n",
        encoding="utf-8",
    )
    spec = load_settings(cfg).interests[0].sources[0]
    assert (spec.type, spec.query, spec.days, spec.url) == ("claude_search", "LLM 소식", 3, "")


def test_source_without_url_or_query_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text(
        "interests:\n  - name: AI\n    sources:\n      - type: rss\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_kopis_source_parses_names_and_genres(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text(
        "interests:\n"
        "  - name: 공연\n"
        "    sources:\n"
        "      - type: kopis\n"
        "        names: [손열음, 조성진]\n"
        "        genres: CCCA, CCCD\n"
        "        areas: [서울, 경기]\n"
        "        days: 90\n"
        "        since_days: 2\n",
        encoding="utf-8",
    )
    spec = load_settings(cfg).interests[0].sources[0]
    assert spec.names == ("손열음", "조성진")
    assert spec.genres == ("CCCA", "CCCD")
    assert spec.areas == ("서울", "경기")
    assert (spec.days, spec.since_days) == (90, 2)


def test_interest_summarize_flag(tmp_path: Path) -> None:
    cfg = tmp_path / "interests.yaml"
    cfg.write_text(
        "interests:\n"
        "  - name: 공연\n"
        "    summarize: false\n"
        "    sources:\n"
        "      - type: kopis\n"
        "        names: [손열음]\n"
        "  - name: AI\n"
        "    sources:\n"
        "      - type: rss\n"
        "        url: https://example.com/feed\n",
        encoding="utf-8",
    )
    interests = load_settings(cfg).interests
    assert interests[0].summarize is False
    assert interests[1].summarize is True
