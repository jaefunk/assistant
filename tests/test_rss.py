from assistant.sources.rss import parse_feed

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>A</title><link>https://x/a</link>
<pubDate>Thu, 16 Oct 2026 00:00:00 GMT</pubDate></item>
<item><title>B</title><link>https://x/b</link></item>
<item><title>C</title><link>https://x/c</link></item>
</channel></rss>"""


def test_parse_feed_respects_limit() -> None:
    items = parse_feed(FEED, limit=2)
    assert [i.title for i in items] == ["A", "B"]
    assert items[0].published is not None
    assert items[1].published is None
