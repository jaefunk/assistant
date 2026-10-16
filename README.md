# assistant

GitHub Actions 로 정기 실행되는 **관심사 정보 리포트** 서비스입니다.
`config/interests.yaml` 에 적어 둔 관심사별로 소스(RSS, Claude 웹 검색)를 수집하고, Claude 로 요약해
`reports/YYYY-MM-DD.md` 로 저장한 뒤 **매일 아침 8시(KST)에 메일로 보냅니다.**

## 동작 흐름

```
config/interests.yaml ─▶ collector (sources/*) ─▶ summarizer (Claude) ─▶ report (Markdown) ─▶ reports/ + mailer (이메일)
```

신문 배달에 비유하면: `interests.yaml` 이 구독 신청서, `sources/` 가 각 신문사에서 기사를 받아오는 배달원,
`summarizer` 가 기사를 추려 주는 편집자, `report` 가 한 부의 신문으로 묶는 인쇄소, `mailer` 가 집 앞까지 배달하는
집배원입니다. GitHub Actions 의 cron 이 매일 아침 8시 배달 시간을 정합니다.

## 로컬 실행

```bash
uv sync --all-groups
cp .env.example .env   # ANTHROPIC_API_KEY 입력 (없으면 요약만 생략됨)
uv run assistant report --stdout --no-summary   # 수집 결과만 미리보기
uv run assistant report                         # reports/ 에 파일 생성
uv run assistant report --email                 # 파일 생성 + 메일 발송 (.env 의 SMTP_* 필요)
```

## 개발

```bash
uv run ruff check .      # 린트
uv run ruff format .     # 포맷
uv run pytest            # 테스트
```

## GitHub Actions

| 워크플로 | 트리거 | 역할 |
| --- | --- | --- |
| `ci.yml` | push(main), PR | 린트 · 포맷 검사 · 테스트 |
| `report.yml` | 매일 08:00 KST (23:00 UTC), 수동 실행 | 리포트 생성 → `reports/` 커밋 → 메일 발송 |

### 필요한 Secrets / Variables

저장소 Settings → Secrets and variables → Actions 에서 등록합니다.

| 종류 | 이름 | 설명 |
| --- | --- | --- |
| Secret | `SMTP_USER` | 보내는 Gmail 주소 |
| Secret | `SMTP_PASSWORD` | Google 계정 → 보안 → 2단계 인증 → **앱 비밀번호** 로 발급한 16자리 |
| Secret | `MAIL_TO` | 받는 주소. 여러 명이면 쉼표로 구분 |
| Secret | `ANTHROPIC_API_KEY` | (선택) 없으면 요약 없이 수집 목록만 발송 |
| Variable | `ANTHROPIC_WORKSPACE_ID` | (선택) 키가 워크스페이스에 묶여 있지 않을 때 필요. Console → Workspaces 에서 ID 확인 |
| Variable | `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | (선택) 기본값 `smtp.gmail.com`, `587`, `SMTP_USER` |

요약 호출이 실패하면 경고만 남기고 요약 없는 리포트를 보냅니다. 메일이 안 오는 것보다 요약이 빠진 메일이 낫기 때문입니다.

Gmail 이 아닌 SMTP 서버도 `SMTP_HOST`/`SMTP_PORT` 만 바꾸면 됩니다. 465 포트는 SSL, 그 외는 STARTTLS 로 접속합니다.

등록 후 Actions 탭 → `Interest Report` → **Run workflow** 로 바로 한 번 보내 보세요.

## 소스 종류

| type | 설정 | 동작 |
| --- | --- | --- |
| `rss` | `url` | RSS/Atom 피드에서 최신 항목을 가져옵니다 |
| `claude_search` | `query`, `days`(기본 7) | Claude 가 웹을 검색해 최근 `days`일 이내 글을 직접 골라옵니다. `ANTHROPIC_API_KEY` 필요 |

```yaml
interests:
  - name: AI / LLM
    sources:
      - type: claude_search
        query: LLM, AI 에이전트, 주요 AI 모델 출시 소식
        days: 7
      - type: rss
        url: https://hnrss.org/newest?q=LLM&points=50
```

`claude_search` 는 관심사마다 Claude 호출 한 번에 웹 검색을 최대 6회 씁니다. 웹 검색은 검색 1,000회당 $10 과 토큰 비용이 듭니다.
검색 실패나 API 오류는 경고만 남기고 다른 소스로 계속 진행합니다.

## 새 소스 추가하기

1. `src/assistant/sources/` 에 `fetch(spec, limit) -> list[Item]` 을 가진 클래스를 만듭니다.
2. `src/assistant/sources/__init__.py` 의 `REGISTRY` 에 type 이름으로 등록합니다.
3. `config/interests.yaml` 에서 그 type 을 사용합니다.
