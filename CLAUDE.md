# assistant

GitHub Actions 로 정기 실행되는 관심사 정보 리포트 서비스. Python 3.13, uv 로 관리.

## 명령

- 설치: `uv sync --all-groups`
- 린트/포맷: `uv run ruff check .` / `uv run ruff format .`
- 테스트: `uv run pytest`
- 실행: `uv run assistant report --stdout --no-summary`

## 구조

- `config/interests.yaml` : 관심사와 소스 정의
- `src/assistant/config.py` : 설정 로딩
- `src/assistant/sources/` : 수집기. `REGISTRY` 에 type 이름으로 등록. `rss`(url), `claude_search`(query, Claude 웹 검색), `kopis`(names, 공연전산망. `KOPIS_API_KEY` 필요. `data/kopis_performances.json` 장부를 증분 동기화)
- `src/assistant/claude.py` : Anthropic 클라이언트 생성 (API 키, 워크스페이스 헤더). summarizer 와 claude_search 가 공유
- `src/assistant/collector.py` : 관심사별 수집 (소스 하나가 실패해도 계속 진행)
- `src/assistant/summarizer.py` : Claude 요약. `ANTHROPIC_API_KEY` 없으면 건너뛰고, API 실패는 경고만 남김
- `src/assistant/report.py` : Markdown 렌더링 및 `reports/` 저장
- `src/assistant/mailer.py` : SMTP 메일 발송. `SMTP_USER`/`SMTP_PASSWORD`/`MAIL_TO` 환경변수 필요
- `.github/workflows/report.yml` : 매일 08:00 KST(23:00 UTC) 리포트 생성 → 커밋 → `--email` 발송

## 규칙

- 네트워크를 타는 테스트는 쓰지 않는다. 파서 단위로 테스트하거나 `httpx.MockTransport` 를 쓴다 (`tests/test_rss.py`, `tests/test_kopis.py` 참고).
- 새 의존성은 `uv add` 로 추가하고 `uv.lock` 을 함께 커밋한다.
- 커밋 전 `ruff check`, `ruff format --check`, `pytest` 가 통과해야 한다 (CI 와 동일).
