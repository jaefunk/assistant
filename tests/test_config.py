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
