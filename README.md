# assistant

GitHub Actions 로 정기 실행되는 **관심사 정보 리포트** 서비스입니다.
`config/interests.yaml` 에 적어 둔 관심사별로 소스(RSS, KOPIS 공연전산망)를 수집해
`reports/YYYY-MM-DD.md` 로 저장한 뒤 **매일 아침 메일로 보냅니다.** 외부 LLM 은 쓰지 않습니다.

## 동작 흐름

```
config/interests.yaml ─▶ collector (sources/*) ─▶ report (Markdown) ─▶ reports/ + mailer (이메일) + notifier (휴대폰 푸시)
```

신문 배달에 비유하면: `interests.yaml` 이 구독 신청서, `sources/` 가 각 신문사에서 기사를 받아오는 배달원,
`report` 가 한 부의 신문으로 묶는 인쇄소, `mailer` 가 집 앞까지 배달하는 집배원, `notifier` 가 새 기사가 있을 때만
문자를 보내 주는 알림 담당입니다.
GitHub Actions 의 cron 이 매일 아침 배달 시간을 정합니다.

## 로컬 실행

```bash
uv sync --all-groups
cp .env.example .env   # KOPIS_API_KEY, SMTP_* 입력
uv run assistant report --stdout   # 수집 결과만 미리보기
uv run assistant report            # reports/ 에 파일 생성
uv run assistant report --email    # 파일 생성 + 메일 발송 (.env 의 SMTP_* 필요)
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
| `report.yml` | 매일 07:30 KST (22:30 UTC), 수동 실행 | 리포트 생성 → `reports/` 커밋 → 메일 발송 → 새 소식이 있으면 휴대폰 푸시 |
| `kopis-sync.yml` | 매일 01:30 KST (16:30 UTC), 수동 실행 | 메일 없이 KOPIS 공연 장부만 동기화 (`assistant sync-kopis`). 긴 시간 예산으로 미확인 공연을 처리해 아침 실행을 가볍게 함 |

### 필요한 Secrets / Variables

저장소 Settings → Secrets and variables → Actions 에서 등록합니다.

| 종류 | 이름 | 설명 |
| --- | --- | --- |
| Secret | `SMTP_USER` | 보내는 Gmail 주소 |
| Secret | `SMTP_PASSWORD` | Google 계정 → 보안 → 2단계 인증 → **앱 비밀번호** 로 발급한 16자리 |
| Secret | `MAIL_TO` | 받는 주소. 여러 명이면 쉼표로 구분 |
| Secret | `KOPIS_API_KEY` | (선택) `kopis` 소스를 쓸 때. 없으면 그 소스만 경고 후 건너뜀 |
| Secret | `NTFY_TOPIC` | (선택) 휴대폰 푸시용 ntfy 토픽. 없으면 푸시 생략 |
| Secret | `NTFY_TOKEN` | (선택) ntfy 서버에 접근 토큰이 필요할 때 |
| Variable | `NTFY_SERVER` | (선택) 기본 `https://ntfy.sh`. 직접 띄운 서버면 그 주소 |
| Variable | `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | (선택) 기본값 `smtp.gmail.com`, `587`, `SMTP_USER` |

Gmail 이 아닌 SMTP 서버도 `SMTP_HOST`/`SMTP_PORT` 만 바꾸면 됩니다. 465 포트는 SSL, 그 외는 STARTTLS 로 접속합니다.

등록 후 Actions 탭 → `Interest Report` → **Run workflow** 로 바로 한 번 보내 보세요.

### 휴대폰 푸시 (ntfy)

새 소식이 있는 날만 휴대폰으로 알림을 받습니다. 예정 공연 목록만 있는 날은 메일만 갑니다.

1. App Store / Play 스토어에서 **ntfy** 앱을 설치합니다.
2. 앱에서 **Subscribe to topic** 으로 토픽을 하나 만듭니다. 토픽 이름을 아는 사람은 누구나 알림을 볼 수 있으니
   `yeolleum-k8f2m9x4q7` 처럼 길고 추측하기 어려운 이름을 쓰세요.
3. 같은 이름을 저장소 Secret `NTFY_TOPIC` 으로 등록합니다.

알림 제목은 `10/22 새 소식 3건`, 본문은 공연 제목과 공연일 목록이고, 누르면 그날 리포트 파일이 열립니다.
푸시 발송이 실패해도 메일은 이미 나간 뒤라 경고만 남기고 끝냅니다.
[ntfy.sh](https://ntfy.sh) 공개 서버 대신 직접 띄운 서버를 쓰려면 Variable `NTFY_SERVER` 와 필요 시 Secret `NTFY_TOKEN` 을 등록합니다.

수집에 실패한 소스는 리포트 끝에 한 줄로 표시됩니다.

## 소스 종류

| type | 설정 | 동작 |
| --- | --- | --- |
| `rss` | `url`, `keywords`(선택) | RSS/Atom 피드에서 항목을 가져옵니다. `keywords` 가 있으면 제목·요약에 그 중 하나가 들어 있는 글만, `days`(기본 7)보다 오래된 글은 제외. 한 번 실은 글은 `data/rss_seen.json` 에 적어 두고 다시 싣지 않습니다 |
| `kopis` | `names`, `genres`(기본 클래식·대중음악), `areas`(지역, 비우면 전국), `days`(앞으로 며칠, 기본 7), `since_days`(증분 동기화 겹침 일수, 기본 1) | 공연예술통합전산망의 공연 장부를 증분 동기화해 `names` 의 사람이 출연하는 공연 중 새로 올라오거나 바뀐 것을 가져옵니다. `KOPIS_API_KEY` 필요 |

```yaml
interests:
  - name: 소니 RX100M8
    sources:
      - type: rss   # 구글 뉴스 검색 피드
        url: https://news.google.com/rss/search?q=RX100M8&hl=ko&gl=KR&ceid=KR:ko
      - type: rss   # 전체 피드는 키워드로 거름
        url: https://www.sonyalpharumors.com/feed/
        keywords: [RX100]
```

```yaml
  - name: 공연 소식
    sources:
      - type: kopis
        names: [손열음, 조성진, 정명훈]
        areas: [서울, 인천, 경기]
        days: 180
        since_days: 1
```

`kopis` 는 국내에서 티켓을 파는 공연이 의무 등록되는 전산망을 보므로 국내 공연은 거의 빠짐없이 잡힙니다. 해외 공연은 없습니다.
키는 [kopis.or.kr](https://www.kopis.or.kr) 오픈API 신청으로 무료 발급받아 Secret `KOPIS_API_KEY` 로 등록하세요.
공연 장부 `data/kopis_performances.json` 을 두고 증분 동기화합니다. 이름이 맞는 공연이 새로 잡히거나 바뀌면 장부에 "보고 대기" 로 표시하고, 다음 리포트 실행이 그것을 메일에 싣습니다. 리포트에는 예정 공연 전체도 날짜순 D-day 와 함께 붙습니다. 장부가 없으면 앞으로 `days`일치 공연을 전부 목록에 넣고(전체 동기화), 그 뒤로는 마지막 동기화일 이후 등록·수정된 공연만 받습니다. 처음 보는 공연만 상세(출연진)를 조회하고, 하루 상한을 넘기면 미확인으로 남겨 다음 날 이어서 처리합니다. 끝난 공연은 장부에서 지웁니다. 장부를 다시 맞추려면 Actions 의 Run workflow 에서 `kopis_full_sync` 를 켜세요.

방화벽이 호출을 불규칙하게 막으므로 호출 사이에 7초를 두고, 막히면 30초·60초·120초 뒤 다시 시도합니다. 한 공연이 계속 막히면 건너뛰고 다음 실행에서 다시 봅니다. 하루 한 번이라 수십 분 걸려도 괜찮습니다. 장르 코드: `CCCA` 클래식, `CCCD` 대중음악, `CCCC` 국악, `GGGA` 뮤지컬, `AAAA` 연극, `BBBC` 무용.

수집 실패나 API 오류는 경고만 남기고 다른 소스로 계속 진행합니다.

## 새 소스 추가하기

1. `src/assistant/sources/` 에 `fetch(spec, limit) -> list[Item]` 을 가진 클래스를 만듭니다.
2. `src/assistant/sources/__init__.py` 의 `REGISTRY` 에 type 이름으로 등록합니다.
3. `config/interests.yaml` 에서 그 type 을 사용합니다.
