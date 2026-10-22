import json
from datetime import date

import httpx

from assistant.models import Interest, InterestDigest, Item
from assistant.notifier import NtfyConfig, build_push, report_url, send

DAY = date(2026, 10, 22)


def _digest(name: str, items: list[Item]) -> InterestDigest:
    return InterestDigest(interest=Interest(name=name, sources=()), items=items)


def test_from_env_requires_topic_and_defaults_server() -> None:
    assert NtfyConfig.from_env({}) is None
    assert NtfyConfig.from_env({"NTFY_TOPIC": "  "}) is None
    config = NtfyConfig.from_env({"NTFY_TOPIC": "abc", "NTFY_SERVER": ""})
    assert config == NtfyConfig(server="https://ntfy.sh", topic="abc")
    config = NtfyConfig.from_env(
        {"NTFY_TOPIC": "abc", "NTFY_SERVER": "https://my.ntfy/", "NTFY_TOKEN": "tk"}
    )
    assert (config.server, config.token) == ("https://my.ntfy", "tk")


def test_build_push_none_without_news() -> None:
    standing = Item(title="예정", url="", standing=True, event_date=DAY)
    assert build_push([_digest("공연", [standing])], DAY) is None
    assert build_push([_digest("공연", [])], DAY) is None


def test_build_push_lists_news_with_event_date() -> None:
    items = [
        Item(title="손열음 리사이틀", url="", event_date=date(2026, 12, 1)),
        Item(title="조성진 협연", url=""),
        Item(title="예정만", url="", standing=True, event_date=DAY),
    ]
    push = build_push([_digest("공연 소식", items)], DAY)
    assert push == ("10/22 새 소식 2건", "손열음 리사이틀 (12.01)\n조성진 협연")


def test_build_push_truncates_and_prefixes_interest_when_several() -> None:
    many = [Item(title=f"공연 {i}", url="") for i in range(10)]
    push = build_push([_digest("공연", many), _digest("뉴스", [Item(title="기사", url="")])], DAY)
    assert push is not None
    title, body = push
    assert title == "10/22 새 소식 11건"
    lines = body.splitlines()
    assert lines[0] == "[공연] 공연 0"
    assert lines[-1] == "외 3건"
    assert len(lines) == 9


def test_send_posts_json_with_topic_and_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "x"})

    config = NtfyConfig(server="https://ntfy.example", topic="t0p1c", token="tk")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        send("제목", "본문", config, click="https://x/r", client=client)

    assert len(seen) == 1
    assert str(seen[0].url) == "https://ntfy.example"
    assert seen[0].headers["Authorization"] == "Bearer tk"
    body = json.loads(seen[0].content)
    assert body == {
        "topic": "t0p1c",
        "title": "제목",
        "message": "본문",
        "tags": ["bell"],
        "click": "https://x/r",
    }


def test_send_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    config = NtfyConfig(server="https://ntfy.example", topic="t")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            send("a", "b", config, client=client)
        except httpx.HTTPStatusError:
            return
    raise AssertionError("HTTP 오류가 예외로 올라와야 한다")


def test_report_url_only_inside_actions() -> None:
    assert report_url(DAY, {}) == ""
    url = report_url(DAY, {"GITHUB_REPOSITORY": "me/assistant", "GITHUB_REF_NAME": "main"})
    assert url == "https://github.com/me/assistant/blob/main/reports/2026-10-22.md"
