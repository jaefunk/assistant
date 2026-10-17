import json
from datetime import UTC, date, datetime

import httpx
import pytest

from assistant.models import SourceSpec
from assistant.sources import get_source
from assistant.sources.kopis import (
    KopisSource,
    clean_ticket_open,
    date_chunks,
    in_areas,
    load_store,
    match_names,
    parse_rows,
    to_item,
)

LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs>
  <db>
    <mt20id>PF1</mt20id><prfnm>손열음 피아노 리사이틀</prfnm>
    <prfpdfrom>2026.10.18</prfpdfrom><prfpdto>2026.10.18</prfpdto>
    <fcltynm>예술의전당 콘서트홀</fcltynm><genrenm>서양음악(클래식)</genrenm>
    <area>서울특별시</area><prfstate>공연예정</prfstate>
  </db>
  <db>
    <mt20id>PF2</mt20id><prfnm>KBS교향악단 제832회 정기연주회</prfnm>
    <prfpdfrom>2026.11.28</prfpdfrom><prfpdto>2026.11.28</prfpdto>
    <fcltynm>예술의전당 콘서트홀</fcltynm><area>서울특별시</area>
  </db>
  <db>
    <mt20id>PF3</mt20id><prfnm>어떤 다른 공연</prfnm>
    <prfpdfrom>2026.12.01</prfpdfrom><prfpdto>2026.12.01</prfpdto><fcltynm>어딘가</fcltynm>
    <area>경기도</area>
  </db>
  <db>
    <mt20id>PF4</mt20id><prfnm>손열음 부산 리사이틀</prfnm>
    <prfpdfrom>2026.12.05</prfpdfrom><prfpdto>2026.12.05</prfpdto><fcltynm>부산콘서트홀</fcltynm>
    <area>부산광역시</area>
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
    "PF4": """<dbs><db><mt20id>PF4</mt20id><prfcast>손열음</prfcast></db></dbs>""",
}

ERROR_XML = (
    "<dbs><db><returncode>02</returncode>"
    "<errmsg>SERVICE KEY IS NOT REGISTERED ERROR</errmsg></db></dbs>"
)

TODAY = date(2026, 10, 16)


def _client(requests: list[httpx.Request], list_xml: str = LIST_XML) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/pblprfr"):
            return httpx.Response(200, text=list_xml)
        mt20id = path.rsplit("/", 1)[-1]
        return httpx.Response(200, text=DETAILS[mt20id])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _source(client: httpx.Client, store_path=None, **kw) -> KopisSource:
    base = dict(api_key="k", delay=0, backoff=0, today=TODAY, store_path=store_path)
    base.update(kw)
    return KopisSource(client=client, **base)


def _spec(**kw) -> SourceSpec:
    base = dict(type="kopis", names=("손열음", "정명훈"), genres=("CCCA",), days=10, since_days=1)
    base.update(kw)
    return SourceSpec(**base)


def _detail_requests(requests: list[httpx.Request]) -> list[str]:
    return [r.url.path.rsplit("/", 1)[-1] for r in requests if not r.url.path.endswith("/pblprfr")]


def _news(items):
    return [i for i in items if not i.standing]


def _standing(items):
    return [i for i in items if i.standing]


def _list_params(requests: list[httpx.Request]) -> list[dict[str, str]]:
    return [dict(r.url.params) for r in requests if r.url.path.endswith("/pblprfr")]


# --- 순수 함수 ----------------------------------------------------------------


def test_date_chunks_cover_range_in_31_day_pieces() -> None:
    chunks = date_chunks(date(2026, 10, 16), 70, 31)
    assert chunks[0] == (date(2026, 10, 16), date(2026, 11, 15))
    assert chunks[1] == (date(2026, 11, 16), date(2026, 12, 16))
    assert chunks[2] == (date(2026, 12, 17), date(2026, 12, 25))
    assert all((b - a).days < 31 for a, b in chunks)


def test_in_areas_prefix_match_and_empty_means_all() -> None:
    assert in_areas(("서울", "경기"), "서울특별시")
    assert not in_areas(("서울", "경기"), "부산광역시")
    assert in_areas((), "부산광역시")


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


def test_to_item_without_detail() -> None:
    item = to_item("PF9", {"prfnm": "공연", "fcltynm": "홀"}, {}, ["손열음"])
    assert item.url.endswith("mt20id=PF9")
    assert item.details == "출연 손열음 · 홀"


def test_registry_has_kopis() -> None:
    assert isinstance(get_source("kopis"), KopisSource)


# --- 전체 동기화 (장부 없음) ------------------------------------------------------


def test_full_sync_lists_without_afterdate_and_checks_cast() -> None:
    requests: list[httpx.Request] = []
    all_items = _source(_client(requests)).fetch(_spec(), limit=10)
    items = _news(all_items)

    assert [i.title for i in items] == [
        "손열음 피아노 리사이틀",
        "KBS교향악단 제832회 정기연주회",
        "손열음 부산 리사이틀",
    ]
    # 예정 공연 전체는 standing 으로 함께 온다 (공연일 포함)
    standing = _standing(all_items)
    assert [i.title for i in standing] == [i.title for i in items]
    assert standing[0].event_date == date(2026, 10, 18)
    assert items[0].url == "https://tickets.interpark.com/1"
    assert "출연 손열음" in items[0].details
    assert "R석 120,000원" in items[0].details
    assert "일요일(17:00)" in items[0].details
    assert items[0].published == datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
    assert items[0].attribution.startswith("출처:")
    assert items[1].url.endswith("mt20id=PF2")  # 예매처 링크가 없으면 KOPIS 공개 페이지로
    assert items[1].published is None

    params = _list_params(requests)
    assert len(params) == 1
    assert "afterdate" not in params[0]
    assert (params[0]["shcate"], params[0]["stdate"], params[0]["service"]) == (
        "CCCA",
        "20261016",
        "k",
    )
    assert _detail_requests(requests) == ["PF1", "PF2", "PF3", "PF4"]


def test_fetch_filters_by_area() -> None:
    items = _news(_source(_client([])).fetch(_spec(areas=("서울", "인천", "경기")), limit=10))
    assert [i.title for i in items] == ["손열음 피아노 리사이틀", "KBS교향악단 제832회 정기연주회"]


def test_fetch_respects_limit() -> None:
    assert len(_news(_source(_client([])).fetch(_spec(), limit=1))) == 1


def test_fetch_without_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("KOPIS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="KOPIS_API_KEY"):
        KopisSource(client=_client([]), delay=0, backoff=0, store_path=None).fetch(_spec(), limit=1)


def test_fetch_error_response_raises() -> None:
    source = _source(_client([], list_xml=ERROR_XML), api_key="bad")
    with pytest.raises(RuntimeError, match="kopis 오류 02"):
        source.fetch(_spec(), limit=1)


def test_http_error_includes_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<error>stdate is invalid</error>")

    source = _source(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError, match="HTTP 400.*stdate is invalid"):
        source.fetch(_spec(), limit=1)


def test_blocked_response_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(400, text="<HTML><H1>Request Blocked</H1></HTML>")
        if request.url.path.endswith("/pblprfr"):
            return httpx.Response(200, text=LIST_XML)
        return httpx.Response(200, text=DETAILS[request.url.path.rsplit("/", 1)[-1]])

    items = _source(httpx.Client(transport=httpx.MockTransport(handler))).fetch(_spec(), limit=10)
    assert len(_news(items)) == 3
    assert calls["n"] >= 2


def test_time_budget_stops_early() -> None:
    requests: list[httpx.Request] = []
    assert _source(_client(requests), time_budget=-1).fetch(_spec(), limit=10) == []
    assert requests == []


# --- 장부와 증분 동기화 -------------------------------------------------------------


def test_store_is_written_and_second_run_is_incremental(tmp_path) -> None:
    store_path = tmp_path / "store.json"

    first: list[httpx.Request] = []
    items = _source(_client(first), store_path=store_path).fetch(_spec(), limit=10)
    assert len(_news(items)) == 3
    assert _detail_requests(first) == ["PF1", "PF2", "PF3", "PF4"]

    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert store["last_sync"] == "2026-10-16"
    assert store["performances"]["PF1"]["matched"] == ["손열음"]
    assert store["performances"]["PF1"]["detail"]["pcseguidance"] == "R석 120,000원"
    assert store["performances"]["PF3"]["matched"] == []
    assert store["performances"]["PF3"]["detail"] is None
    assert store["performances"]["PF1"]["pending_report"] is False
    assert store["performances"]["PF1"]["reported"] == "2026-10-16"

    # 다음 날: afterdate = last_sync - since_days, 아는 공연은 상세를 다시 부르지 않고
    # 바뀐 게 없으니 리포트할 것도 없다
    second: list[httpx.Request] = []
    items = _source(_client(second), store_path=store_path, today=date(2026, 10, 17)).fetch(
        _spec(), limit=10
    )
    assert _news(items) == []
    assert len(_standing(items)) == 3
    assert _list_params(second)[0]["afterdate"] == "20261015"
    assert _detail_requests(second) == []
    assert json.loads(store_path.read_text(encoding="utf-8"))["last_sync"] == "2026-10-17"


def test_changed_known_performance_is_reported_without_detail_call(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    _source(_client([]), store_path=store_path).fetch(_spec(), limit=10)

    # PF1 의 날짜가 바뀌어서 목록에 다시 나타남
    changed = LIST_XML.replace(
        "<prfpdfrom>2026.10.18</prfpdfrom><prfpdto>2026.10.18</prfpdto>",
        "<prfpdfrom>2026.10.25</prfpdfrom><prfpdto>2026.10.25</prfpdto>",
    )
    requests: list[httpx.Request] = []
    items = _source(
        _client(requests, list_xml=changed), store_path=store_path, today=date(2026, 10, 17)
    ).fetch(_spec(), limit=10)
    news = _news(items)
    assert [i.title for i in news] == ["손열음 피아노 리사이틀"]
    assert "2026.10.25" in news[0].details
    assert _detail_requests(requests) == []


def test_pending_performances_are_checked_on_next_run(tmp_path) -> None:
    store_path = tmp_path / "store.json"

    first: list[httpx.Request] = []
    items = _source(_client(first), store_path=store_path, max_detail=2).fetch(_spec(), limit=10)
    assert _detail_requests(first) == ["PF1", "PF2"]
    assert [i.title for i in _news(items)] == [
        "손열음 피아노 리사이틀",
        "KBS교향악단 제832회 정기연주회",
    ]
    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert "checked" not in store["performances"]["PF3"]
    assert "checked" not in store["performances"]["PF4"]

    # 다음 날 증분 목록이 비어 있어도 미확인 공연을 이어서 확인하고, 맞으면 리포트한다
    second: list[httpx.Request] = []
    empty = "<dbs></dbs>"
    items = _source(
        _client(second, list_xml=empty), store_path=store_path, today=date(2026, 10, 17)
    ).fetch(_spec(), limit=10)
    assert _detail_requests(second) == ["PF3", "PF4"]
    assert [i.title for i in _news(items)] == ["손열음 부산 리사이틀"]


def test_full_sync_env_forces_full_listing(tmp_path, monkeypatch) -> None:
    store_path = tmp_path / "store.json"
    _source(_client([]), store_path=store_path).fetch(_spec(), limit=10)
    monkeypatch.setenv("KOPIS_FULL_SYNC", "1")
    requests: list[httpx.Request] = []
    _source(_client(requests), store_path=store_path, today=date(2026, 10, 17)).fetch(
        _spec(), limit=10
    )
    assert "afterdate" not in _list_params(requests)[0]


def test_load_store_drops_finished_performances(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps(
            {
                "last_sync": "2026-10-10",
                "performances": {
                    "OLD": {"prfpdto": "2026.10.15", "checked": "2026-10-10"},
                    "NOW": {"prfpdto": "2026.10.16", "checked": "2026-10-10"},
                    "NEW": {"prfpdto": "2026.12.01", "checked": "2026-10-10"},
                },
            }
        ),
        encoding="utf-8",
    )
    store = load_store(store_path, TODAY)
    assert set(store["performances"]) == {"NOW", "NEW"}
    assert store["last_sync"] == "2026-10-10"


# --- 동기화 전용 실행과 보고 대기 ---------------------------------------------------


def test_sync_keeps_pending_report_until_fetch(tmp_path) -> None:
    store_path = tmp_path / "store.json"

    # 새벽: 장부만 동기화. 맞는 공연은 보고 대기로 남는다
    source = _source(_client([]), store_path=store_path)
    _, store = source.sync(_spec())
    waiting = [k for k, v in store["performances"].items() if v.get("pending_report")]
    assert sorted(waiting) == ["PF1", "PF2", "PF4"]
    assert "reported" not in store["performances"]["PF1"]

    # 아침: 증분 목록은 비어 있어도 보고 대기 공연이 메일에 실리고 표시가 지워진다
    requests: list[httpx.Request] = []
    items = _source(_client(requests, list_xml="<dbs></dbs>"), store_path=store_path).fetch(
        _spec(), limit=10
    )
    assert [i.title for i in _news(items)] == [
        "손열음 피아노 리사이틀",
        "KBS교향악단 제832회 정기연주회",
        "손열음 부산 리사이틀",
    ]
    assert _detail_requests(requests) == []
    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert not any(v.get("pending_report") for v in store["performances"].values())

    # 그 다음 실행에서는 새 소식이 없고 예정 공연만 남는다
    items = _source(_client([], list_xml="<dbs></dbs>"), store_path=store_path).fetch(
        _spec(), limit=10
    )
    assert _news(items) == []
    assert len(_standing(items)) == 3


class _FakeClaude:
    """티켓 오픈 검색용 가짜 클라이언트. 호출된 프롬프트를 기록한다."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []
        self.beta = type("B", (), {})()
        self.beta.messages = self

    def create(self, **kwargs):
        from types import SimpleNamespace

        self.prompts.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=self.answer)],
        )


def test_ticket_open_lookup_is_attached_once(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    claude = _FakeClaude("검색 결과입니다.\n일반 예매 2026-10-01 14:00 (인터파크)")
    items = _source(_client([]), store_path=store_path, claude_client=claude).fetch(
        _spec(), limit=10
    )
    news = _news(items)
    assert "티켓 오픈 일반 예매 2026-10-01 14:00 (인터파크)" in news[0].details
    assert len(claude.prompts) == 3  # 맞은 공연 3건, 각 1회
    assert "손열음 피아노 리사이틀" in claude.prompts[0]

    # 다음 실행에서는 다시 검색하지 않는다
    claude2 = _FakeClaude("정보 없음")
    _source(
        _client([], list_xml="<dbs></dbs>"), store_path=store_path, claude_client=claude2
    ).fetch(_spec(), limit=10)
    assert claude2.prompts == []


def test_ticket_open_lookup_no_info_is_empty(tmp_path) -> None:
    claude = _FakeClaude("정보 없음")
    items = _source(_client([]), store_path=tmp_path / "s.json", claude_client=claude).fetch(
        _spec(), limit=10
    )
    assert "티켓 오픈" not in _news(items)[0].details


# --- 이름 목록 변경 ---------------------------------------------------------------


def test_new_name_rematches_from_stored_cast(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    first: list[httpx.Request] = []
    items = _source(_client(first), store_path=store_path).fetch(_spec(names=("손열음",)), limit=10)
    assert [i.title for i in _news(items)] == ["손열음 피아노 리사이틀", "손열음 부산 리사이틀"]
    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert store["performances"]["PF2"]["cast"].startswith("정 명훈")
    assert store["performances"]["PF2"]["matched"] == []

    # 정명훈 추가: 저장된 출연진으로 PF2 만 다시 상세를 받아 보고한다
    second: list[httpx.Request] = []
    items = _source(
        _client(second, list_xml="<dbs></dbs>"), store_path=store_path, today=date(2026, 10, 17)
    ).fetch(_spec(names=("손열음", "정명훈")), limit=10)
    assert _detail_requests(second) == ["PF2"]
    assert [i.title for i in _news(items)] == ["KBS교향악단 제832회 정기연주회"]


def test_removed_name_shrinks_matched_without_calls(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    _source(_client([]), store_path=store_path).fetch(_spec(), limit=10)
    requests: list[httpx.Request] = []
    items = _source(
        _client(requests, list_xml="<dbs></dbs>"), store_path=store_path, today=date(2026, 10, 17)
    ).fetch(_spec(names=("손열음",)), limit=10)
    assert _detail_requests(requests) == []
    assert [i.title for i in _standing(items)] == ["손열음 피아노 리사이틀", "손열음 부산 리사이틀"]


def test_legacy_entry_without_cast_is_rechecked(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps(
            {
                "last_sync": "2026-10-15",
                "performances": {
                    "PF2": {
                        "prfnm": "KBS교향악단 제832회 정기연주회",
                        "prfpdto": "2026.11.28",
                        "checked": "2026-10-15",
                        "matched": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    requests: list[httpx.Request] = []
    items = _source(_client(requests, list_xml="<dbs></dbs>"), store_path=store_path).fetch(
        _spec(), limit=10
    )
    assert _detail_requests(requests) == ["PF2"]
    assert [i.title for i in _news(items)] == ["KBS교향악단 제832회 정기연주회"]


def test_ticket_open_lookup_runs_even_when_kopis_budget_is_spent(tmp_path) -> None:
    """긴 동기화로 KOPIS 예산을 다 써도 티켓 오픈 검색은 돈다 (Claude 호출이라 예산과 무관)."""
    store_path = tmp_path / "s.json"
    # 먼저 장부를 만들어 보고 대기 공연을 남겨 둔다
    _source(_client([]), store_path=store_path).sync(_spec())
    claude = _FakeClaude("일반 예매 2026-10-01 14:00")
    _source(
        _client([], list_xml="<dbs></dbs>"),
        store_path=store_path,
        claude_client=claude,
        time_budget=-1,
    ).sync(_spec())
    assert len(claude.prompts) == 3


# --- 차단 내성, 티켓 오픈 정리, 예정 목록 축약 ------------------------------------------


def test_persistently_blocked_detail_is_skipped_and_sync_continues(tmp_path) -> None:
    store_path = tmp_path / "store.json"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/pblprfr"):
            return httpx.Response(200, text=LIST_XML)
        if path.endswith("/PF2"):
            return httpx.Response(400, text="<HTML><H1>Request Blocked</H1></HTML>")
        return httpx.Response(200, text=DETAILS[path.rsplit("/", 1)[-1]])

    source = _source(httpx.Client(transport=httpx.MockTransport(handler)), store_path=store_path)
    items = source.fetch(_spec(), limit=10)
    # PF2 는 건너뛰고 나머지는 확인된다
    assert [i.title for i in _news(items)] == ["손열음 피아노 리사이틀", "손열음 부산 리사이틀"]
    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert "checked" not in store["performances"]["PF2"]
    assert "checked" in store["performances"]["PF3"]
    assert store["last_sync"] == "2026-10-16"


def test_clean_ticket_open_strips_leaked_prefix() -> None:
    junk = (
        "검색 결과\nNeed times. Print the X content."
        "팬클럽 선예매 2026-09-10 / 일반 예매 2026-09-14 20:00"
    )
    assert clean_ticket_open(junk) == "선예매 2026-09-10 / 일반 예매 2026-09-14 20:00"
    assert (
        clean_ticket_open("일반 예매 2026-10-02 16:00 (예스24)")
        == "일반 예매 2026-10-02 16:00 (예스24)"
    )
    assert clean_ticket_open("정보 없음") == ""
    assert clean_ticket_open("Sorry, I could not find it.") == ""
    assert clean_ticket_open("") == ""


def test_standing_item_details_are_compact() -> None:
    perf = {
        "prfnm": "공연",
        "fcltynm": "홀",
        "prfpdfrom": "2026.11.08",
        "prfpdto": "2026.11.08",
        "ticket_open": "일반 예매 2026-10-02 16:00",
    }
    detail = {"pcseguidance": "R석 480,000원", "dtguidance": "일요일(17:00)", "relates": []}
    news = to_item("PF1", perf, detail, ["임윤찬"])
    standing = to_item("PF1", perf, detail, ["임윤찬"], standing=True)
    assert "R석 480,000원" in news.details
    assert standing.details == "출연 임윤찬 · 홀 · 티켓 오픈 일반 예매 2026-10-02 16:00"


def test_load_store_cleans_stored_ticket_open(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps(
            {
                "last_sync": "2026-10-16",
                "performances": {
                    "PF1": {
                        "prfpdto": "2026.12.04",
                        "ticket_open": "Need times. 일반 예매 2026-09-14 20:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    store = load_store(store_path, TODAY)
    assert store["performances"]["PF1"]["ticket_open"] == "일반 예매 2026-09-14 20:00"
