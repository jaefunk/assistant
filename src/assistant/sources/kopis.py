"""KOPIS 공연예술통합전산망 오픈 API 수집기.

국내에서 티켓을 파는 공연은 예매처가 이 전산망에 의무 등록하므로, 출연자 이름으로
거르면 국내 공연은 거의 빠짐없이 잡힌다.

동작: 공연 장부(data/kopis_performances.json)를 두고 증분으로 동기화한다.
- 장부가 없으면 전체 동기화: 앞으로 days 일치 공연을 모두 목록에 넣는다.
- 장부가 있으면 마지막 동기화일 - since_days 이후 등록·수정된 공연만 받는다 (afterdate).
- 처음 보는 공연만 상세(출연진)를 조회한다. 하루 상한을 넘기면 '미확인' 으로 남겨
  다음 실행에서 이어서 처리한다. 끝난 공연은 장부에서 지운다.
- 확인한 공연은 출연진 텍스트(cast)도 장부에 남긴다. names 가 바뀌면 API 호출 없이 다시 대조해
  새로 맞는 공연은 상세를 다시 받아 보고 대기로 올린다.
- names 가 출연하는 공연이 새로 잡히거나 바뀌면 장부에 '보고 대기(pending_report)' 로 표시하고,
  리포트 실행(fetch)이 그것들을 싣고 표시를 지운다. 동기화 전용 실행(sync)은 장부만 맞추므로
  새벽에 찾은 공연도 아침 메일에 실린다.
- 리포트에는 그 외에 names 의 예정 공연 전체를 standing 항목(날짜순, D-day)으로 함께 준다.
- 새로 잡힌 공연은 Claude 웹 검색 한 번으로 티켓 오픈 일시를 찾아 붙인다 (ANTHROPIC_API_KEY
  가 있을 때만, 실행당 최대 5건).
워크플로가 data/ 를 커밋하므로 장부는 날마다 이어진다. KOPIS_FULL_SYNC=1 이면 장부가
있어도 전체 동기화를 한 번 다시 한다.

config 예:
    - type: kopis
      names: [손열음, 조성진]     # 공연명 또는 출연진에 이 이름이 있으면 수집
      areas: [서울, 인천, 경기]   # 지역(area) 이 이걸로 시작하는 공연만. 비우면 전국
      genres: [CCCA, CCCD]       # 장르 코드. 기본 CCCA(클래식), CCCD(대중음악)
      days: 180                  # 오늘부터 며칠 뒤까지의 공연을 볼지
      since_days: 1              # 증분 동기화 시 마지막 동기화일에서 며칠을 겹쳐 받을지

API 메모 (가이드 v5.0 기준):
- 목록 GET {BASE}/pblprfr?service=KEY&stdate&eddate&cpage&rows&shcate&afterdate
  기간은 최대 31일, rows 최대 100. 응답은 XML <dbs><db>...</db></dbs>.
- 상세 GET {BASE}/pblprfr/{mt20id}?service=KEY → prfcast, prfcrew, pcseguidance,
  dtguidance, relates/relate/relatenm/relateurl, updatedate 등.
- 오류도 HTTP 200 으로 오고 본문에 <returncode>, <errmsg> 가 있다.
- 방화벽이 'Request Blocked'(HTTP 400 HTML) 로 불규칙하게 막는다 (2026-10 실측, 호출 간격과
  무관). 7초 간격을 두고, 막히면 30초 쉬었다가 다시 시도하면 통과한다.
  python-httpx 기본 User-Agent 는 아예 400 으로 막힌다.
- 이용약관상 출처 표기가 의무다 (Item.attribution 으로 리포트 끝에 표시).
"""

from __future__ import annotations

import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from assistant.models import Item, SourceSpec

log = logging.getLogger(__name__)

BASE_URL = os.environ.get("KOPIS_BASE_URL", "http://www.kopis.or.kr/openApi/restful")
DEFAULT_GENRES = ("CCCA", "CCCD")  # 서양음악(클래식), 대중음악
CHUNK_DAYS = 31
ROWS = 100
MAX_DETAIL_CALLS = 150
MAX_TICKET_LOOKUPS = 5  # 실행당 티켓 오픈 일시 웹 검색 횟수
TIME_BUDGET_SECONDS = 1500.0  # 이 시간을 넘기면 그때까지 모은 것만 돌려준다
STORE_PATH = Path(os.environ.get("KOPIS_STORE_PATH", "data/kopis_performances.json"))
BLOCKED_MARKER = "Request Blocked"
PUBLIC_PAGE = "https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20id={mt20id}"
ATTRIBUTION = "출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)"
LIST_FIELDS = ("prfnm", "prfpdfrom", "prfpdto", "fcltynm", "area", "genrenm", "prfstate")


class KopisSource:
    def __init__(
        self,
        client: httpx.Client | None = None,
        api_key: str | None = None,
        delay: float = 7.0,
        backoff: float = 30.0,
        today: date | None = None,
        time_budget: float = TIME_BUDGET_SECONDS,
        store_path: Path | None = STORE_PATH,
        full_sync: bool | None = None,
        max_detail: int = MAX_DETAIL_CALLS,
        claude_client=None,
        ticket_lookups: int = MAX_TICKET_LOOKUPS,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; assistant-report/0.1)"},
        )
        self._api_key = api_key
        self._delay = delay
        self._backoff = backoff
        self._today = today
        self._time_budget = time_budget
        self._started = 0.0
        self._store_path = store_path
        self._full_sync = full_sync
        self._max_detail = max_detail
        self._claude_client = claude_client
        self._ticket_lookups = ticket_lookups

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        """장부를 동기화한 뒤 보고 대기 공연(새 소식)과 예정 공연 전체(standing)를 돌려준다."""
        today, store = self.sync(spec)
        performances: dict[str, dict] = store["performances"]

        items: list[Item] = []
        for mt20id, entry in performances.items():
            if not entry.get("pending_report"):
                continue
            matched = [n for n in spec.names if n in entry.get("matched", [])]
            if not matched:
                entry["pending_report"] = False
                continue
            if len(items) < limit:
                items.append(to_item(mt20id, entry, entry.get("detail") or {}, matched))
                entry["pending_report"] = False
                entry["reported"] = today.isoformat()
        save_store(self._store_path, store)

        for mt20id, entry in performances.items():
            matched = [n for n in spec.names if n in entry.get("matched", [])]
            if matched:
                items.append(
                    to_item(mt20id, entry, entry.get("detail") or {}, matched, standing=True)
                )
        log.info(
            "kopis: 새 소식 %d건, 예정 공연 %d건",
            sum(1 for i in items if not i.standing),
            len(items),
        )
        return items

    def sync(self, spec: SourceSpec) -> tuple[date, dict]:
        """장부를 동기화하고 (오늘 날짜, 장부) 를 돌려준다. 리포트는 만들지 않는다."""
        api_key = (self._api_key or os.environ.get("KOPIS_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("KOPIS_API_KEY 가 없어 kopis 소스를 쓸 수 없습니다.")
        if not spec.names:
            raise RuntimeError("kopis 소스에는 names 가 필요합니다.")

        today = self._today or date.today()
        genres = spec.genres or DEFAULT_GENRES
        self._started = time.monotonic()

        store = load_store(self._store_path, today)
        performances: dict[str, dict] = store["performances"]
        rematch(performances, spec.names)
        full_sync = self._full_sync
        if full_sync is None:
            full_sync = os.environ.get("KOPIS_FULL_SYNC", "") == "1" or not store.get("last_sync")
        after = None
        if not full_sync:
            after = date.fromisoformat(store["last_sync"]) - timedelta(days=spec.since_days)
        log.info(
            "kopis: %s 동기화 (장부 %d건%s)",
            "전체" if full_sync else "증분",
            len(performances),
            "" if after is None else f", {after.isoformat()} 이후 등록·수정분",
        )

        # 1) 목록: 새로 보이거나 바뀐 공연을 장부에 넣는다. 이미 아는 공연이 바뀌었고 names 가
        #    출연하면 보고 대기로 표시한다.
        touched: list[str] = []
        listing_complete = True
        for genre in genres:
            for start, end in date_chunks(today, spec.days, CHUNK_DAYS):
                if self._over_budget():
                    listing_complete = False
                    break
                for perf in self._list(api_key, start, end, genre, after):
                    mt20id = perf.get("mt20id", "")
                    if not mt20id or not in_areas(spec.areas, perf.get("area", "")):
                        continue
                    entry = performances.setdefault(mt20id, {"first_seen": today.isoformat()})
                    changed = any(entry.get(f) != perf.get(f, "") for f in LIST_FIELDS)
                    for f in LIST_FIELDS:
                        entry[f] = perf.get(f, "")
                    if changed or "checked" not in entry:
                        entry["updated"] = today.isoformat()
                        if mt20id not in touched:
                            touched.append(mt20id)
                        if entry.get("matched"):
                            entry["pending_report"] = True
        pending = [k for k, v in performances.items() if "checked" not in v]
        log.info("kopis: 새로 보이거나 바뀐 공연 %d건, 미확인 %d건", len(touched), len(pending))

        # 2) 미확인 공연은 상세(출연진)를 조회한다.
        #    이번에 바뀐 것부터, 그 다음 지난 실행에서 남은 것 순서로.
        detail_calls = 0
        order = touched + [k for k in pending if k not in touched]
        try:
            for mt20id in order:
                entry = performances[mt20id]
                if "checked" in entry:
                    continue
                if self._over_budget() or detail_calls >= self._max_detail:
                    log.warning(
                        "kopis: 상세 조회를 %d회에서 멈춥니다. 미확인은 다음 실행에서 이어갑니다.",
                        detail_calls,
                    )
                    break
                detail = self._detail(api_key, mt20id)
                detail_calls += 1
                matched = match_names(
                    spec.names,
                    entry.get("prfnm", ""),
                    str(detail.get("prfcast", "")),
                    str(detail.get("prfcrew", "")),
                )
                entry["checked"] = today.isoformat()
                entry["cast"] = f"{detail.get('prfcast', '')} / {detail.get('prfcrew', '')}"
                entry["matched"] = matched
                entry["detail"] = detail if matched else None
                if matched:
                    entry["pending_report"] = True
            # 3) 새로 잡힌 공연은 티켓 오픈 일시를 웹에서 찾아 둔다
            self._lookup_ticket_open(performances)
        finally:
            if listing_complete:
                store["last_sync"] = today.isoformat()
            save_store(self._store_path, store)
        log.info("kopis: 상세 조회 %d회", detail_calls)
        return today, store

    def _lookup_ticket_open(self, performances: dict[str, dict]) -> None:
        targets = [
            (k, v)
            for k, v in performances.items()
            if v.get("pending_report") and v.get("matched") and "ticket_open" not in v
        ]
        if not targets:
            return
        client = self._claude_client
        if client is None:
            from assistant.claude import make_client

            client = make_client()
        if client is None:
            return
        for mt20id, entry in targets[: self._ticket_lookups]:
            if self._over_budget():
                return
            entry["ticket_open"] = lookup_ticket_open(client, entry)
            log.info("kopis: 티켓 오픈 검색 %s → %s", mt20id, entry["ticket_open"] or "정보 없음")

    def _over_budget(self) -> bool:
        elapsed = time.monotonic() - self._started
        if elapsed <= self._time_budget:
            return False
        log.warning("kopis: 시간 예산 %.0f초 초과, 여기까지 모은 것만 씁니다.", self._time_budget)
        return True

    # --- HTTP ---------------------------------------------------------------

    def _list(
        self, api_key: str, start: date, end: date, genre: str, after: date | None
    ) -> Iterator[dict[str, str]]:
        page = 1
        while True:
            params = {
                "service": api_key,
                "stdate": start.strftime("%Y%m%d"),
                "eddate": end.strftime("%Y%m%d"),
                "cpage": str(page),
                "rows": str(ROWS),
                "shcate": genre,
            }
            if after is not None:
                params["afterdate"] = after.strftime("%Y%m%d")
            rows = parse_rows(self._get(f"{BASE_URL}/pblprfr", params))
            yield from rows  # type: ignore[misc]
            if len(rows) < ROWS:
                return
            page += 1

    def _detail(self, api_key: str, mt20id: str) -> dict[str, object]:
        rows = parse_rows(self._get(f"{BASE_URL}/pblprfr/{mt20id}", {"service": api_key}))
        return rows[0] if rows else {}

    def _get(self, url: str, params: dict[str, str]) -> str:
        for attempt in (1, 2, 3):
            if self._delay:
                time.sleep(self._delay)
            response = self._client.get(url, params=params)
            body = response.text.strip()
            if response.status_code >= 400 and BLOCKED_MARKER in body:
                # 방화벽 차단. 잠시 쉬고 다시 시도한다.
                log.warning(
                    "kopis: 요청 차단됨 (%s), %.0f초 후 재시도 %d", url, self._backoff, attempt
                )
                if self._backoff:
                    time.sleep(self._backoff)
                continue
            if response.status_code >= 400:
                # 본문에 이유가 있는 경우가 많다. 로그에 남긴다.
                raise RuntimeError(
                    f"kopis HTTP {response.status_code} ({url}): {body.replace(chr(10), ' ')[:300]}"
                )
            if body:
                return response.text
            log.warning("kopis: 빈 응답 (%s), 재시도 %d", url, attempt)
        raise RuntimeError(f"kopis: 요청이 계속 실패합니다 ({url})")


# --- 장부 ---------------------------------------------------------------------


def load_store(path: Path | None, today: date) -> dict:
    """장부를 읽고 끝난 공연(종료일 < 오늘)은 지운다. 파일이 없거나 깨졌으면 빈 장부."""
    store: dict = {"last_sync": None, "performances": {}}
    if path is None or not path.exists():
        return store
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("kopis: 장부 파일을 읽지 못해 새로 시작합니다 (%s)", path)
        return store
    if isinstance(raw, dict) and isinstance(raw.get("performances"), dict):
        store["last_sync"] = raw.get("last_sync")
        cutoff = today.strftime("%Y.%m.%d")
        store["performances"] = {
            k: v
            for k, v in raw["performances"].items()
            if isinstance(v, dict) and (not v.get("prfpdto") or v["prfpdto"] >= cutoff)
        }
    return store


def rematch(performances: dict[str, dict], names: tuple[str, ...]) -> int:
    """names 가 바뀌었을 때 저장된 출연진 텍스트로 다시 대조한다.

    새로 맞게 된 공연은 상세(가격·예매처)가 없으므로 '미확인' 으로 되돌려 다시 조회하게 한다.
    출연진 텍스트가 없는 옛 항목도 미확인으로 되돌린다. 되돌린 건수를 돌려준다.
    """
    reverted = 0
    for entry in performances.values():
        if "checked" not in entry:
            continue
        if "cast" not in entry:
            entry.pop("checked")
            reverted += 1
            continue
        new = match_names(names, entry.get("prfnm", ""), entry["cast"])
        old = entry.get("matched", [])
        if new == old:
            continue
        if any(n not in old for n in new):
            entry.pop("checked")  # 새로 맞는 이름이 생김 → 상세를 다시 받는다
            reverted += 1
        else:
            entry["matched"] = new  # 이름이 빠진 경우: 상세는 그대로, 맞는 이름만 줄인다
    if reverted:
        log.info("kopis: 이름 목록 변경으로 %d건을 다시 확인합니다.", reverted)
    return reverted


def save_store(path: Path | None, store: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )


# --- 티켓 오픈 일시 검색 ---------------------------------------------------------


def lookup_ticket_open(client, entry: dict) -> str:
    """Claude 웹 검색으로 티켓 오픈(예매 시작) 일시를 한 줄로 찾는다. 못 찾으면 빈 문자열."""
    from anthropic import APIError

    from assistant.claude import DEFAULT_MODEL, FALLBACK_BETA

    where = f"{entry.get('fcltynm', '')}, {entry.get('prfpdfrom', '')}"
    prompt = (
        f"공연 '{entry.get('prfnm', '')}' ({where}) 의 티켓 오픈(예매 시작) 일시를 웹에서 "
        "찾아 주세요. 선예매와 일반 예매가 다르면 둘 다 적습니다. "
        "최종 답변은 설명 없이 한 줄만, 예: '일반 예매 2026-10-20 14:00 (인터파크)'. "
        "확실한 정보가 없으면 정확히 '정보 없음' 이라고만 답하세요."
    )
    try:
        response = client.beta.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=2000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except APIError as exc:
        log.warning("kopis: 티켓 오픈 검색 실패 (%s): %s", entry.get("prfnm", ""), exc)
        return ""
    if response.stop_reason == "refusal":
        return ""
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    line = text.splitlines()[-1].strip() if text else ""
    if not line or "정보 없음" in line:
        return ""
    return line[:200]


# --- 순수 함수 (테스트 대상) --------------------------------------------------


def date_chunks(start: date, days: int, chunk: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """[start, start+days] 를 chunk 일 이하 구간들로 자른다 (양 끝 포함)."""
    end = start + timedelta(days=days)
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=chunk - 1), end)
        chunks.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return chunks


def in_areas(areas: tuple[str, ...], area: str) -> bool:
    """areas 가 비어 있으면 전국. '서울' 은 '서울특별시' 에 맞는다."""
    return not areas or any(area.startswith(a) for a in areas)


def match_names(names: tuple[str, ...], *texts: str) -> list[str]:
    """공백을 무시하고 이름이 텍스트에 들어 있는지 본다. 맞은 이름 목록을 돌려준다."""
    haystack = "".join(texts).replace(" ", "")
    return [name for name in names if name.replace(" ", "") and name.replace(" ", "") in haystack]


def parse_rows(xml_text: str) -> list[dict[str, object]]:
    """<dbs><db>...</db></dbs> 를 dict 목록으로. 오류 응답이면 RuntimeError."""
    root = ET.fromstring(xml_text)
    rows: list[dict[str, object]] = []
    for db in root.iter("db"):
        row: dict[str, object] = {}
        for child in db:
            if child.tag == "relates":
                row["relates"] = [
                    {
                        "name": (rel.findtext("relatenm") or "").strip(),
                        "url": (rel.findtext("relateurl") or "").strip(),
                    }
                    for rel in child.iter("relate")
                ]
            elif len(child) == 0:
                row[child.tag] = (child.text or "").strip()
        rows.append(row)
    if len(rows) == 1 and "returncode" in rows[0] and rows[0].get("returncode") not in ("", "00"):
        raise RuntimeError(f"kopis 오류 {rows[0]['returncode']}: {rows[0].get('errmsg', '')}")
    return rows


def to_item(
    mt20id: str,
    perf: dict,
    detail: dict[str, object],
    matched: list[str],
    standing: bool = False,
) -> Item:
    relates = detail.get("relates") or []
    first_link = next((r["url"] for r in relates if r.get("url")), "")  # type: ignore[index]
    ticket_sites = ", ".join(r["name"] for r in relates if r.get("name"))  # type: ignore[index]

    period = f"{perf.get('prfpdfrom', '')}~{perf.get('prfpdto', '')}".strip("~")
    parts = [
        f"출연 {', '.join(matched)}",
        "내한" if detail.get("visit") == "Y" else "",
        perf.get("fcltynm", ""),
        period,
        str(detail.get("dtguidance", "")),
        str(detail.get("pcseguidance", "")),
        f"예매 {ticket_sites}" if ticket_sites else "",
        f"티켓 오픈 {perf.get('ticket_open')}" if perf.get("ticket_open") else "",
    ]
    details = " · ".join(p for p in parts if p)
    return Item(
        title=perf.get("prfnm") or "(제목 없음)",
        url=first_link or PUBLIC_PAGE.format(mt20id=mt20id),
        published=_parse_datetime(str(detail.get("updatedate") or detail.get("frstregdt") or "")),
        summary=details,
        details=details,
        attribution=ATTRIBUTION,
        standing=standing,
        event_date=_parse_kopis_date(perf.get("prfpdfrom", "")),
    )


def _parse_kopis_date(value: str) -> date | None:
    """'2026.10.22' 형식."""
    try:
        return datetime.strptime(value, "%Y.%m.%d").date()
    except ValueError:
        return None


def _parse_datetime(value: str) -> datetime | None:
    """'2019-07-25 10:03:14' 형식. 못 읽으면 None."""
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
