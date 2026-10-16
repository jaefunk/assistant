# assistant

GitHub Actions 로 정기 실행되는 **관심사 정보 리포트** 서비스입니다.
`config/interests.yaml` 에 적어 둔 관심사별로 소스(RSS 등)를 수집하고, Claude 로 요약해
`reports/YYYY-MM-DD.md` 로 저장합니다.

## 동작 흐름

```
config/interests.yaml ─▶ collector (sources/*) ─▶ summarizer (Claude) ─▶ report (Markdown) ─▶ reports/
```

신문 배달에 비유하면: `interests.yaml` 이 구독 신청서, `sources/` 가 각 신문사에서 기사를 받아오는 배달원,
`summarizer` 가 기사를 추려 주는 편집자, `report` 가 한 부의 신문으로 묶어 우편함(`reports/`)에 넣는 역할입니다.
GitHub Actions 의 cron 이 매일 아침 배달 시간을 정합니다.

## 로컬 실행

```bash
uv sync --all-groups
cp .env.example .env   # ANTHROPIC_API_KEY 입력 (없으면 요약만 생략됨)
uv run assistant report --stdout --no-summary   # 수집 결과만 미리보기
uv run assistant report                         # reports/ 에 파일 생성
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
| `report.yml` | 매일 00:00 UTC, 수동 실행 | 리포트 생성 후 `reports/` 에 커밋 |

리포트 워크플로를 쓰려면 저장소 Settings → Secrets → Actions 에 `ANTHROPIC_API_KEY` 를 등록하세요.
비어 있으면 요약 없이 수집 목록만 담긴 리포트가 생성됩니다.

## 새 소스 추가하기

1. `src/assistant/sources/` 에 `fetch(spec, limit) -> list[Item]` 을 가진 클래스를 만듭니다.
2. `src/assistant/sources/__init__.py` 의 `REGISTRY` 에 type 이름으로 등록합니다.
3. `config/interests.yaml` 에서 그 type 을 사용합니다.
