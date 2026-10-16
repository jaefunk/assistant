from datetime import UTC, date, datetime

import httpx
import pytest

from assistant.models import SourceSpec
from assistant.sources import get_source
from assistant.sources.kopis import KopisSource, date_chunks, match_names, parse_rows, to_item

LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs>
  <db>
    <mt20id>PF1</mt20id><prfnm>손열음 피아노 리사이틀</prfnm>
    <prfpdfrom>2026.10.18</prfpdfrom><prfpdto>2026.10.18</prfpdto>
    <fcltynm>예술의전당 콘서트홀</fcltynm><genrenm>서양음악(클래식)</genrenm>
    <prfstate>공연예정</prfstate>
  </db>
  <db>
    <mt20id>PF2</mt20id><prfnm>KBS교향악단 제832회 정기연주회</prfnm>
    <prfpdfrom>2026.11.28</prfpdfrom><prfpdto>2026.11.28</prfpdto>
    <fcltynm>예술의전당 콘서트홀</fcltynm>
  </db>
  <db>
    <mt20id>PF3</mt20id><prfnm>어떤 다른 공연</prfnm>
    <prfpdfrom>2026.12.01</prfpdfrom><prfpdto>2026.12.01</prfpdto><fcltynm>어딘가</fcltynm>
  </db>
</dbs>"""

DETAILS = {
    "PF1": """<dbs><db>
        <mt20id>PF1</mt20id><prfcast>손열음</prfcast><pcseguidance>R석 120,000원</pcseguidance>
        <dtguidance>일요일(17:00)</dtguidance><visit>N</visit>
        <updatedate>2026-10-15 09:30:00</updatedate>
        <relates>
          <relate><relatenm>인터파크</relatenm><relateurl>https://tickets.interpark.com/1</relateurl></relate>
          <relate><relatenm>예스24</relatenm><relateurl>https://ticket.yes24.com/1</relateurl></relate>
        </relates>
    </db></dbs>""",
    "PF2": """<dbs><db>
        <mt20id>PF2</mt20id><prfcast>정 명훈, 김선욱 등</prfcast>
        <pcseguidance>VIP 120,000원</pcseguidance><relates></relates>
    </db></dbs>""",
    "PF3": """<dbs><db><mt20id>PF3</mt20id><prfcast>아무개</prfcast></db></dbs>""",
}

ERROR_XML = (
    "<dbs><db><returncode>02</returncode>"
    "<errmsg>SERVICE KEY IS NOT REGISTERED ERROR</errmsg></db></dbs>"
)


def _client(requests: list[httpx.Request], list_xml: str = LIST_XML) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/pblprfr"):
            return httpx.Response(200, text=list_xml)
        mt20id = path.rsplit("/", 1)[-1]
        return httpx.Response(200, text=DETAILS[mt20id])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _spec(**kw) -> SourceSpec:
    base = dict(type="kopis", names=("손열음", "정명훈"), genres=("CCCA",), days=10, since_days=1)
    base.update(kw)
    return SourceSpec(**base)


def test_date_chunks_cover_range_in_31_day_pieces() -> None:
    chunks = date_chunks(date(2026, 10, 16), 70, 31)
    assert chunks[0] == (date(2026, 10, 16), date(2026, 11, 15))
    assert chunks[1] == (date(2026, 11, 16), date(2026, 12, 16))
    assert chunks[2] == (date(2026, 12, 17), date(2026, 12, 25))
    assert all((b - a).days < 31 for a, b in chunks)


def test_match_names_ignores_spaces() -> None:
    assert match_names(("정명훈", "조성진"), "지휘 정 명훈, 협연 김선욱") == ["정명훈"]
    assert match_names(("조성진",), "아무도 없음") == []


def test_parse_rows_raises_on_error_response() -> None:
    with pytest.raises(RuntimeError, match="SERVICE KEY"):
        parse_rows(ERROR_XML)


def test_parse_rows_reads_relates() -> None:
    row = parse_rows(DETAILS["PF1"])[0]
    assert row["prfcast"] == "손열음"
    assert row["relates"][0] == {"name": "인터파크", "url": "https://tickets.interpark.com/1"}


def test_fetch_matches_by_title_then_by_cast() -> None:
    requests: list[httpx.Request] = []
    source = KopisSource(client=_client(requests), api_key="k", delay=0, today=date(2026, 10, 16))
    items = source.fetch(_spec(), limit=10)

    assert [i.title for i in items] == ["손열음 피아노 리사이틀", "KBS교향악단 제832회 정기연주회"]
    assert items[0].url == "https://tickets.interpark.com/1"
    assert "출연 손열음" in items[0].details
    assert "R석 120,000원" in items[0].details
    assert "일요일(17:00)" in items[0].details
    assert items[0].published == datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
    assert items[0].attribution.startswith("출처:")
    assert items[1].published is None
    assert "예매 인터파크, 예스24" in items[0].details
    # 예매처 링크가 없으면 KOPIS 공개 페이지로
    assert items[1].url.endswith("mt20id=PF2")

    list_requests = [r for r in requests if r.url.path.endswith("/pblprfr")]
    assert len(list_requests) == 1
    params = dict(list_requests[0].url.params)
    assert params["afterdate"] == "20261015"
    assert params["shcate"] == "CCCA"
    assert params["stdate"] == "20261016"
    assert params["service"] == "k"
    # 상세는 PF1(제목 일치), PF2, PF3 각 1회
    assert sum(1 for r in requests if not r.url.path.endswith("/pblprfr")) == 3


def test_fetch_respects_limit() -> None:
    source = KopisSource(client=_client([]), api_key="k", delay=0, today=date(2026, 10, 16))
    assert len(source.fetch(_spec(), limit=1)) == 1


def test_fetch_without_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("KOPIS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="KOPIS_API_KEY"):
        KopisSource(client=_client([]), delay=0).fetch(_spec(), limit=1)


def test_fetch_error_response_raises() -> None:
    source = KopisSource(
        client=_client([], list_xml=ERROR_XML), api_key="bad", delay=0, today=date(2026, 10, 16)
    )
    with pytest.raises(RuntimeError, match="kopis 오류 02"):
        source.fetch(_spec(), limit=1)


def test_to_item_without_detail() -> None:
    item = to_item({"mt20id": "PF9", "prfnm": "공연", "fcltynm": "홀"}, {}, ["손열음"])
    assert item.url.endswith("mt20id=PF9")
    assert item.details == "출연 손열음 · 홀"


def test_registry_has_kopis() -> None:
    assert isinstance(get_source("kopis"), KopisSource)


def test_http_error_includes_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<error>stdate is invalid</error>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = KopisSource(client=client, api_key="k", delay=0, today=date(2026, 10, 16))
    with pytest.raises(RuntimeError, match="HTTP 400.*stdate is invalid"):
        source.fetch(_spec(), limit=1)
