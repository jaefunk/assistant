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
    )


def test_render_contains_sections() -> None:
    md = render([_digest()], date(2026, 10, 16))
    assert md.startswith("# 관심사 리포트 2026-10-16")
    assert "## AI" in md
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


def test_render_appends_attribution_footer_once() -> None:
    items = [
        Item(title="A", url="https://x/a", attribution="출처: KOPIS"),
        Item(title="B", url="https://x/b", attribution="출처: KOPIS"),
    ]
    digest = InterestDigest(interest=Interest(name="공연", sources=()), items=items)
    md = render([digest], date(2026, 1, 1))
    assert md.count("출처: KOPIS") == 1
    assert md.endswith("---\n_출처: KOPIS_\n")


def test_render_without_attribution_has_no_footer() -> None:
    digest = InterestDigest(
        interest=Interest(name="AI", sources=()), items=[Item("A", "https://x")]
    )
    assert "---" not in render([digest], date(2026, 1, 1))


def test_render_standing_items_with_dday_and_failures() -> None:
    digest = InterestDigest(
        interest=Interest(name="공연", sources=()),
        items=[
            Item(title="새 소식", url="https://x/n", details="출연 손열음"),
            Item(
                title="리사이틀",
                url="https://x/r",
                details="예술의전당",
                standing=True,
                event_date=date(2026, 10, 22),
            ),
        ],
        failures=["AI · rss https://feed: 502"],
    )
    md = render([digest], date(2026, 10, 16))
    assert "- [새 소식](https://x/n)" in md
    assert "**예정 (1건)**" in md
    assert "- 10.22(목) D-6 · [리사이틀](https://x/r) · 예술의전당" in md
    assert "_수집 실패: AI · rss https://feed: 502_" in md


def test_render_only_standing_says_no_news() -> None:
    digest = InterestDigest(
        interest=Interest(name="공연", sources=()),
        items=[
            Item(title="리사이틀", url="https://x/r", standing=True, event_date=date(2026, 10, 16))
        ],
    )
    md = render([digest], date(2026, 10, 16))
    assert "_새로 올라온 항목이 없습니다._" in md
    assert "D-Day" in md
