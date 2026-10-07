# 나만의 미국장 데일리 브리핑 — 따라하기 설명서

매일 아침 6시 50분쯤, 미국 증시 정리 페이지가 자동으로 업데이트되는 나만의 사이트를 만듭니다.
**코딩 몰라도 됩니다.** 클릭과 복사·붙여넣기만 해요. 소요 시간 15분 정도.

비용: **0원** (GitHub 무료 플랜으로 충분)

---

## 준비물

이 폴더에 있는 파일 4개:

| 파일 | 하는 일 |
|---|---|
| `market_brief.py` | 데이터 모아서 페이지 만드는 프로그램 |
| `requirements.txt` | 프로그램에 필요한 부품 목록 |
| `daily.yml` | "매일 아침 자동 실행" 설정 |
| `README.md` | 지금 보는 설명서 |

---

## 1단계. GitHub 가입

1. https://github.com 접속 → **Sign up** 으로 가입
2. 아이디는 사이트 주소에 들어가니 마음에 드는 걸로 (예: `minsu` → 주소가 `minsu.github.io/...`)

## 2단계. 저장소(repository) 만들기

1. 로그인 후 오른쪽 위 **＋** → **New repository**
2. Repository name: `market-brief`
3. **Public** 선택 (무료로 사이트를 띄우려면 Public이어야 해요)
4. **Create repository** 클릭

## 3단계. 파일 올리기

1. 방금 만든 저장소 화면에서 **uploading an existing file** 링크 클릭
2. `market_brief.py`, `requirements.txt`, `README.md` 세 개를 끌어다 놓기
   (`daily.yml`은 다음 단계에서 따로 넣어요)
3. 아래 초록색 **Commit changes** 클릭

## 4단계. 자동 실행 설정 넣기

이 파일은 특별한 폴더에 들어가야 해서 직접 만듭니다.

1. 저장소 화면에서 **Add file** → **Create new file**
2. 파일 이름 칸에 정확히 이렇게 입력: `.github/workflows/daily.yml`
   (슬래시 `/`를 치면 자동으로 폴더가 만들어져요)
3. 컴퓨터에서 `daily.yml`을 메모장으로 열어 **내용 전체 복사** → 큰 입력칸에 붙여넣기
4. **Commit changes...** → 다시 **Commit changes**

## 5단계. 사이트 공개 켜기

1. 저장소 위쪽 메뉴 **Settings** → 왼쪽 메뉴 **Pages**
2. **Source** 를 **GitHub Actions** 로 변경 (저장 버튼 없음, 바로 적용)

## 6단계. 처음 한 번 수동으로 돌려보기

1. 저장소 위쪽 메뉴 **Actions**
2. 왼쪽에서 **데일리 마켓 브리핑** 클릭 → 오른쪽 **Run workflow** → 초록 **Run workflow**
3. 3~5분 기다리면 초록 체크 ✅ 가 뜹니다 (신고가 스캔 때문에 조금 걸려요)
4. 완료된 실행을 클릭하면 **deploy** 박스 아래에 사이트 주소가 나와요
   → `https://내아이디.github.io/market-brief/`

이 주소를 휴대폰 홈 화면에 추가해두면 앱처럼 쓸 수 있어요. 🎉
이제부터는 **매일 아침 자동**으로 업데이트됩니다.

---

## (선택) 회사 이름·설명을 한국어로

기본 상태에선 신고가 종목의 회사명·설명이 영어로 나와요. 한국어로 바꾸려면:

1. https://console.anthropic.com 에서 API 키 발급 (유료, 하루 몇 원 수준)
2. 저장소 **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Name: `ANTHROPIC_API_KEY` / Secret: 발급받은 키 → **Add secret**

다음 실행부터 한국어로 나옵니다. 안 해도 나머지는 다 정상 작동해요.

---

## 내 입맛대로 바꾸기

저장소에서 `market_brief.py` 클릭 → 오른쪽 위 연필(✏️) 아이콘 → 맨 위 **설정** 부분만 고치고 **Commit changes**.

- **관심 종목 바꾸기**: `WATCHLIST` 줄을 수정. 예) 테슬라 추가 → `("TSLA", "테슬라", "$"),`
  티커는 https://finance.yahoo.com 에서 회사 검색하면 나와요.
- **지표 추가/삭제**: `INDICATORS` 줄 수정. 예) 달러 인덱스 → `("DX-Y.NYB", "달러 인덱스", ""),`
- **뉴스 검색어**: `HEADLINE_QUERY`, `KOREA_IMPACT_QUERIES`
- **신고가 카드 개수**: `TOP_HIGHS`

괄호·따옴표·쉼표 모양만 기존 줄처럼 맞춰주면 됩니다.
고친 뒤 바로 확인하고 싶으면 6단계처럼 **Run workflow**.

---

## 문제가 생기면

- **Actions에 빨간 ❌가 떴어요** → 그 실행을 클릭 → 빨간 단계를 펼치면 에러 메시지가 보여요. 그 내용을 복사해서 Claude에게 붙여넣고 물어보세요.
- **페이지 일부 칸이 비어 있어요** → 그 데이터 출처가 잠깐 막힌 거예요. 나머지는 정상으로 나오고 다음 날 보통 돌아옵니다.
- **자동 실행이 멈췄어요** → GitHub은 저장소에 60일간 아무 변화가 없으면 예약 실행을 끕니다. Actions 탭에 뜨는 **Enable workflow** 버튼을 누르면 다시 켜져요.
- **시간이 좀 늦게 업데이트돼요** → GitHub 예약 실행은 붐비는 시간에 10~30분 늦어질 수 있어요. 정상입니다.

---

## 데이터 출처 참고

- 가격·차트·밸류에이션: Yahoo Finance (`yfinance`) — 비공식 경로라 가끔 끊길 수 있음
- Put/Call: SPY 옵션 거래량으로 직접 계산 (CBOE 공식 지수와 수치가 다를 수 있음)
- 신고가: S&P500 + 나스닥100 약 520개 종목 대상, 종가 기준 1년 최고가
- 뉴스: Google News RSS

투자 판단의 책임은 본인에게 있습니다.
