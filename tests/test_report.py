from datetime import UTC, date, datetime
from pathlib import Path

from assistant.models import Interest, InterestDigest, Item
from assistant.report import render, write


def _digest() -> InterestDigest:
    return InterestDigest(
        interest=Interest(name="AI", sources=()),
        items=[
            Item(title="Hello", url="https://x/1", published=datetime(2026, 10, 16, tzinfo=UTC))
        ],
        summary="- 요약 한 줄",
    )


def test_render_contains_sections() -> None:
    md = render([_digest()], date(2026, 10, 16))
    assert md.startswith("# 관심사 리포트 2026-10-16")
    assert "## AI" in md
    assert "- 요약 한 줄" in md
    assert "[Hello](https://x/1) · 2026-10-16" in md


def test_render_empty_interest() -> None:
    md = render([InterestDigest(interest=Interest(name="빈", sources=()))], date(2026, 1, 1))
    assert "_수집된 항목이 없습니다._" in md


def test_write_creates_dated_file(tmp_path: Path) -> None:
    path = write("# x\n", date(2026, 10, 16), tmp_path / "out")
    assert path == tmp_path / "out" / "2026-10-16.md"
    assert path.read_text(encoding="utf-8") == "# x\n"


def test_render_item_without_url_is_plain_text() -> None:
    digest = InterestDigest(
        interest=Interest(name="AI", sources=()),
        items=[Item(title="링크 없음", url="")],
    )
    md = render([digest], date(2026, 1, 1))
    assert "- 링크 없음\n" in md
    assert "]()" not in md


def test_render_item_details_on_second_line() -> None:
    digest = InterestDigest(
        interest=Interest(name="공연", sources=()),
        items=[Item(title="리사이틀", url="https://x/r", details="출연 손열음 · 예술의전당")],
    )
    md = render([digest], date(2026, 1, 1))
    assert "- [리사이틀](https://x/r)  \n  출연 손열음 · 예술의전당\n" in md
