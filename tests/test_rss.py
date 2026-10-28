import json
from datetime import date

import httpx

from assistant.models import SourceSpec
from assistant.sources.rss import RssSource, load_seen, matches_keywords, parse_feed

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>A</title><link>https://x/a</link>
<pubDate>Thu, 16 Oct 2026 00:00:00 GMT</pubDate></item>
<item><title>B</title><link>https://x/b</link></item>
<item><title>C</title><link>https://x/c</link></item>
</channel></rss>"""

CAMERA_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>Sony RX100 VIII rumored for Q4</title><link>https://x/1</link></item>
<item><title>New A7R VI announced</title><link>https://x/2</link>
<description>&lt;p&gt;Also mentions the rx100m8 in passing.&lt;/p&gt;</description></item>
<item><title>Nikon news</title><link>https://x/3</link></item>
</channel></rss>"""

TODAY = date(2026, 10, 28)


def test_parse_feed_respects_limit() -> None:
    items = parse_feed(FEED, limit=2)
    assert [i.title for i in items] == ["A", "B"]
    assert items[0].published is not None
    assert items[1].published is None


def test_matches_keywords_ignores_case_and_spaces() -> None:
    assert matches_keywords(("RX100 VIII", "RX100M8"), "sony rx100viii leak")
    assert matches_keywords(("rx100m8",), "Sony", "...the RX100 M8 is coming")
    assert not matches_keywords(("RX100",), "Nikon Z9")
    assert matches_keywords((), "anything")


def test_parse_feed_filters_by_keywords_in_title_or_summary() -> None:
    items = parse_feed(CAMERA_FEED, keywords=("RX100 VIII", "RX100M8"))
    assert [i.url for i in items] == ["https://x/1", "https://x/2"]


def _client(feed: str) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=feed)))


def test_fetch_reports_each_item_once(tmp_path) -> None:
    seen_path = tmp_path / "seen.json"
    spec = SourceSpec(type="rss", url="https://feed", keywords=("RX100",))
    first = RssSource(_client(CAMERA_FEED), seen_path=seen_path, today=TODAY).fetch(spec, 10)
    assert [i.url for i in first] == ["https://x/1", "https://x/2"]
    assert json.loads(seen_path.read_text(encoding="utf-8")) == {
        "https://x/1": "2026-10-28",
        "https://x/2": "2026-10-28",
    }
    # 같은 피드를 다음 날 다시 받으면 이미 실은 항목은 빠진다
    second = RssSource(_client(CAMERA_FEED), seen_path=seen_path, today=date(2026, 10, 29)).fetch(
        spec, 10
    )
    assert second == []


def test_fetch_limit_applies_after_seen_filter(tmp_path) -> None:
    seen_path = tmp_path / "seen.json"
    seen_path.write_text(json.dumps({"https://x/a": "2026-10-27"}), encoding="utf-8")
    spec = SourceSpec(type="rss", url="https://feed")
    items = RssSource(_client(FEED), seen_path=seen_path, today=TODAY).fetch(spec, 1)
    assert [i.url for i in items] == ["https://x/b"]


def test_fetch_skips_items_older_than_days(tmp_path) -> None:
    spec = SourceSpec(type="rss", url="https://feed", days=7)
    # A 는 10/16 글이라 10/28 기준 7일보다 오래됐다. B, C 는 날짜가 없어 통과
    items = RssSource(_client(FEED), seen_path=tmp_path / "s.json", today=TODAY).fetch(spec, 10)
    assert [i.url for i in items] == ["https://x/b", "https://x/c"]
    spec = SourceSpec(type="rss", url="https://feed", days=30)
    items = RssSource(_client(FEED), seen_path=tmp_path / "t.json", today=TODAY).fetch(spec, 10)
    assert [i.url for i in items] == ["https://x/a", "https://x/b", "https://x/c"]


def test_load_seen_prunes_old_and_broken(tmp_path) -> None:
    path = tmp_path / "seen.json"
    path.write_text(
        json.dumps({"https://old": "2026-01-01", "https://new": "2026-10-20", "https://bad": 3}),
        encoding="utf-8",
    )
    assert load_seen(path, TODAY) == {"https://new": "2026-10-20"}
    path.write_text("not json", encoding="utf-8")
    assert load_seen(path, TODAY) == {}
    assert load_seen(None, TODAY) == {}
