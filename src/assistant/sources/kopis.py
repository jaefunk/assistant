"""KOPIS 공연예술통합전산망 오픈 API 수집기.

국내에서 티켓을 파는 공연은 예매처가 이 전산망에 의무 등록하므로, 출연자 이름으로
거르면 국내 공연은 거의 빠짐없이 잡힌다.

config 예:
    - type: kopis
      names: [손열음, 조성진]     # 공연명 또는 출연진에 이 이름이 있으면 수집
      areas: [서울, 인천, 경기]   # 지역(area) 이 이걸로 시작하는 공연만. 비우면 전국
      genres: [CCCA, CCCD]       # 장르 코드. 기본 CCCA(클래식), CCCD(대중음악)
      days: 180                  # 오늘부터 며칠 뒤까지의 공연을 볼지
      since_days: 1              # 최근 N일 안에 등록·수정된 공연만 (afterdate)

API 메모 (가이드 v5.0 기준):
- 목록 GET {BASE}/pblprfr?service=KEY&stdate&eddate&cpage&rows&shcate&afterdate
  기간은 최대 31일, rows 최대 100. 응답은 XML <dbs><db>...</db></dbs>.
- 상세 GET {BASE}/pblprfr/{mt20id}?service=KEY → prfcast, prfcrew, pcseguidance,
  dtguidance, relates/relate/relatenm/relateurl 등.
- 오류도 HTTP 200 으로 오고 본문에 <returncode>, <errmsg> 가 있다.
- 방화벽이 성공 요청 기준 분당 10회를 넘으면 'Request Blocked'(HTTP 400 HTML) 로 막고,
  그 1분 창이 끝날 때까지 계속 막는다 (2026-10 실측). 그래서 7초 간격(분당 8~9회)을
  두고, 막히면 30초 쉬었다가 다시 시도한다. 하루 한 번 도는 작업이라 느려도 된다.
  python-httpx 기본 User-Agent 도 400 으로 막힌다.
- 이용약관상 출처 표기가 의무다 (Item.attribution 으로 리포트 끝에 표시).
"""

from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import httpx

from assistant.models import Item, SourceSpec

log = logging.getLogger(__name__)

BASE_URL = os.environ.get("KOPIS_BASE_URL", "http://www.kopis.or.kr/openApi/restful")
DEFAULT_GENRES = ("CCCA", "CCCD")  # 서양음악(클래식), 대중음악
CHUNK_DAYS = 31
ROWS = 100
MAX_DETAIL_CALLS = 60
TIME_BUDGET_SECONDS = 600.0  # 이 시간을 넘기면 그때까지 모은 것만 돌려준다
BLOCKED_MARKER = "Request Blocked"
PUBLIC_PAGE = "https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20id={mt20id}"
ATTRIBUTION = "출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)"


class KopisSource:
    def __init__(
        self,
        client: httpx.Client | None = None,
        api_key: str | None = None,
        delay: float = 7.0,
        backoff: float = 30.0,
        today: date | None = None,
        time_budget: float = TIME_BUDGET_SECONDS,
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

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        api_key = (self._api_key or os.environ.get("KOPIS_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("KOPIS_API_KEY 가 없어 kopis 소스를 쓸 수 없습니다.")
        if not spec.names:
            raise RuntimeError("kopis 소스에는 names 가 필요합니다.")

        today = self._today or date.today()
        after = today - timedelta(days=spec.since_days)
        genres = spec.genres or DEFAULT_GENRES
        self._started = time.monotonic()

        # 1) 목록: 장르 × 31일 구간을 돌며 최근 등록·수정된 공연을 모은다 (mt20id 로 중복 제거)
        candidates: dict[str, dict[str, str]] = {}
        for genre in genres:
            for start, end in date_chunks(today, spec.days, CHUNK_DAYS):
                if self._over_budget():
                    break
                for perf in self._list(api_key, start, end, genre, after):
                    if not in_areas(spec.areas, perf.get("area", "")):
                        continue
                    candidates.setdefault(perf.get("mt20id", ""), perf)
        candidates.pop("", None)
        log.info("kopis: 후보 %d건 (등록·수정 %s 이후)", len(candidates), after.isoformat())

        # 2) 공연명에 이름이 없으면 상세의 출연진까지 확인한다
        items: list[Item] = []
        detail_calls = 0
        for mt20id, perf in candidates.items():
            if self._over_budget():
                break
            matched = match_names(spec.names, perf.get("prfnm", ""))
            detail: dict[str, object] | None = None
            if not matched:
                if detail_calls >= MAX_DETAIL_CALLS:
                    log.warning(
                        "kopis: 상세 조회 한도(%d)에 도달해 나머지는 건너뜁니다.", MAX_DETAIL_CALLS
                    )
                    break
                detail = self._detail(api_key, mt20id)
                detail_calls += 1
                matched = match_names(
                    spec.names, str(detail.get("prfcast", "")), str(detail.get("prfcrew", ""))
                )
            if not matched:
                continue
            if detail is None:
                detail = self._detail(api_key, mt20id)
                detail_calls += 1
            items.append(to_item(perf, detail, matched))
            if len(items) >= limit:
                break
        return items

    def _over_budget(self) -> bool:
        elapsed = time.monotonic() - self._started
        if elapsed <= self._time_budget:
            return False
        log.warning("kopis: 시간 예산 %.0f초 초과, 여기까지 모은 것만 씁니다.", self._time_budget)
        return True

    # --- HTTP ---------------------------------------------------------------

    def _list(
        self, api_key: str, start: date, end: date, genre: str, after: date
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
                "afterdate": after.strftime("%Y%m%d"),
            }
            rows = parse_rows(self._get(f"{BASE_URL}/pblprfr", params))
            yield from rows
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


def to_item(perf: dict[str, str], detail: dict[str, object], matched: list[str]) -> Item:
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
    ]
    details = " · ".join(p for p in parts if p)
    return Item(
        title=perf.get("prfnm", "(제목 없음)"),
        url=first_link or PUBLIC_PAGE.format(mt20id=perf.get("mt20id", "")),
        published=_parse_datetime(str(detail.get("updatedate") or detail.get("frstregdt") or "")),
        summary=details,
        details=details,
        attribution=ATTRIBUTION,
    )


def _parse_datetime(value: str) -> datetime | None:
    """'2019-07-25 10:03:14' 형식. 못 읽으면 None."""
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
