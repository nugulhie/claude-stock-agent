# 한국주식 자동매매 시스템

한국투자증권 KIS API 연동 기반의 자동매매 + 분석 대시보드 시스템입니다.

## 주요 기능

**신호 생성기 기반 자동 매수/매도** - 4가지 분석을 종합하여 매매 판단을 내립니다:

| 분석 영역 | 가중치 | 세부 내용 |
|-----------|--------|-----------|
| 기술적 분석 | 35% | RSI, MACD, 볼린저밴드, 이동평균선, 스토캐스틱, 거래량 |
| 펀더멘털 분석 | 20% | PER, PBR, ROE, 부채비율, 매출성장률 |
| 원자재 연동 | 25% | WTI, 금, 구리, 천연가스 → 관련 섹터 영향도 분석 |
| 뉴스 감성 | 20% | 네이버 금융 뉴스 감성 분석 (호재/악재 키워드) |

**리스크 관리**: 손절 -5%, 익절 +15%, 트레일링 스탑 -7%, 장기 횡보 강제 매도, 신호 악화 매도, 일일 최대 손실 10%

## 프로젝트 구조

```
kr-stock-analyzer/
├── config.py              # 전략 파라미터 & API 키 설정
├── auto_trader.py         # 자동매매 엔진 + 스케줄러
├── dashboard.py           # Streamlit 웹 대시보드
├── requirements.txt       # 의존성
├── modules/
│   ├── kis_api.py         # 한국투자증권 API 연동
│   ├── screener.py        # 종목 스크리닝 (재무/원자재/소형주)
│   ├── market_data.py     # 뉴스/환율/원자재 수집
│   ├── technical.py       # 기술적 분석 & 신호 생성기
│   └── portfolio.py       # 포트폴리오 & 리스크 관리
├── tests/                 # 유닛 테스트
├── data/                  # 매매 기록, 판단 로그 (자동 생성)
│   ├── trades.json        # 매매 기록
│   ├── decisions.jsonl    # 매매 판단 근거 로그
│   └── auto_trader.log    # 실행 로그
└── strategies/            # 커스텀 전략 (확장용)
```

---

## 초기 설정

### 1. Python 설치

Python 3.9 이상이 필요합니다.

```bash
# macOS (Homebrew)
brew install python@3.11

# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-pip python3-venv

# 버전 확인
python3 --version
```

### 2. 프로젝트 클론 & 의존성 설치

```bash
git clone <repository-url>
cd kr-stock-analyzer

# 가상환경 생성 (권장)
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows

# 의존성 설치
pip install -r requirements.txt
```

**requirements.txt 내용:**
- `requests` — HTTP 요청 (KIS API 통신)
- `beautifulsoup4` — 네이버 금융 뉴스 크롤링
- `yfinance` — 국제 원자재/환율 데이터
- `schedule` — 장중 스케줄러
- `streamlit` — 웹 대시보드
- `pandas` — 데이터 처리

### 3. 한국투자증권 API 키 발급

1. [KIS Developers](https://apiportal.koreainvestment.com) 가입
2. **서비스 신청** → **Open API** 앱 생성
3. 앱키(App Key), 앱시크릿(App Secret) 발급
4. 계좌번호 확인 (형식: `12345678-01`)

### 4. 환경변수 설정

```bash
# 터미널에서 직접 설정
export KIS_APP_KEY="발급받은_앱키"
export KIS_APP_SECRET="발급받은_앱시크릿"
export KIS_ACCOUNT_NO="계좌번호-상품코드"

# 또는 .env 파일로 관리 (자동 로드됨)
cat > .env << 'EOF'
KIS_APP_KEY="발급받은_앱키"
KIS_APP_SECRET="발급받은_앱시크릿"
KIS_ACCOUNT_NO="12345678-01"
KIS_TRADING_MODE="paper"
WATCHLIST_CODES="005930,000660,373220"
EOF
```

### 5. 설정 점검

먼저 API 키와 전략 설정을 확인합니다.

```bash
python3 auto_trader.py --check-config
```

실전 URL을 기본값으로 쓰고 싶으면 `.env`에 아래처럼 둡니다. 단, `python3 auto_trader.py --live`는 이 설정 없이도 실전 URL을 직접 사용합니다.

```bash
KIS_TRADING_MODE="live"
```

### 6. 동작 확인

```bash
python3 auto_trader.py --once
```

정상이면 종목 분석 결과가 출력됩니다. API 키 오류가 나면 4단계를 재확인하세요.

---

## 실행 방법

### 자동매매 (모의투자)
```bash
python3 auto_trader.py
```

### 자동매매 (실전투자)
```bash
python3 auto_trader.py --live
```

실전 모드는 실제 주문을 전송하므로 실행 시 `LIVE` 입력 확인을 요구합니다. 서버나 `nohup`처럼 비대화형으로 실행할 때만 아래처럼 명시 확인 플래그를 붙입니다.

```bash
python3 auto_trader.py --live --yes-live
```

### 1회 분석만
```bash
python3 auto_trader.py --once
```

### 관심종목 확인
```bash
python3 auto_trader.py --watchlist
```

### 원하는 종목만 분석
```bash
python3 auto_trader.py --analyze 005930,000660
python3 auto_trader.py --analyze 005930,000660 --json
```

### 대시보드
```bash
streamlit run dashboard.py
# 브라우저에서 http://localhost:8501 접속
```

### 테스트 실행
```bash
python3 -m unittest discover tests/ -v
```

---

## 자동매매 스케줄

| 시간 | 작업 | 주기 |
|------|------|------|
| 08:30 | 장전 분석 | 매일 1회 |
| 09:05 | 장전 후보 상위 3개 자동 매수 | 매일 1회 |
| 09:10~15:20 | 보유종목 모니터링 (손절/익절/트레일링/횡보) | 10분 |
| 09:30~15:00 | 신규 매수 기회 탐색 | 30분 |
| 10:00~14:00 | 보유종목 신호 재평가 (악화 시 매도) | 1시간 |
| 15:40 | 일일 성과 리포트 | 매일 1회 |

---

## 매매 판단 기준

### 진입 (매수)
- 종합점수 60점 이상 + 신뢰도 70% 이상
- 강력매수(75점↑) 시그널에서 자동 실행
- 포지션 사이징: 신뢰도 80↑ → 40%, 60↑ → 25%, 기타 → 10%

### 탈출 (매도) — 6가지 조건
| 조건 | 기준 | 체크 주기 |
|------|------|-----------|
| 손절 | 매입가 대비 -5% | 10분 |
| 익절 | 매입가 대비 +15% | 10분 |
| 트레일링 스탑 | 고점 대비 -7% | 10분 |
| 장기 횡보 | 15일 보유 + ±2% 내 횡보 | 10분 |
| 신호 악화 | 재분석 시 종합 30점 이하 | 1시간 |
| 일일 손실한도 | 자본금 10% 초과 시 최대 손실 종목 정리 | 10분 |

---

## 로그 구조

### data/auto_trader.log
실행 과정 전체 로그 (분석, 매수/매도, 에러).

### data/trades.json
매매 기록만. 대시보드의 "매매 기록" 탭에서 조회 가능.
```json
[{"timestamp": "2025-01-15 09:35:00", "code": "005490", "name": "POSCO홀딩스",
  "side": "BUY", "qty": 3, "price": 320000, "reason": "MACD 골든크로스; RSI 과매도",
  "signal_score": 78.5, "profit_pct": null}]
```

### data/decisions.jsonl
모든 분석 결과의 판단 근거 (매수/매도/스킵 모두 포함). 한 줄에 하나씩 JSON.
```json
{"timestamp":"2025-01-15 09:30:12","code":"005490","name":"POSCO홀딩스","signal":"강력매수",
 "final_score":78.5,"confidence":57.0,
 "scores":{"technical":72.3,"fundamental":65.0,"commodity":81.5,"news":15.0},
 "indicators":{"RSI":28.3,"MACD":150.2,"SMA_5":318000,...},
 "reasons":["RSI 과매도 (28.3)","MACD 골든크로스","구리 상승 → 철강 호재"],
 "risk_flags":[],"action":"BUY","action_detail":""}
```

---

## 서버에서 자동 실행 유지 가이드

### 방법 1: nohup (간단)

```bash
# 백그라운드 실행 (터미널 종료해도 유지)
nohup python3 auto_trader.py > /dev/null 2>&1 &
echo $!  # PID 확인

# 종료
kill <PID>
```

### 방법 2: systemd 서비스 (Linux, 권장)

```bash
sudo tee /etc/systemd/system/stock-trader.service << 'EOF'
[Unit]
Description=Korean Stock Auto Trader
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/kr-stock-analyzer
Environment="KIS_APP_KEY=your_key"
Environment="KIS_APP_SECRET=your_secret"
Environment="KIS_ACCOUNT_NO=12345678-01"
ExecStart=/path/to/kr-stock-analyzer/venv/bin/python3 auto_trader.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# 서비스 등록 및 시작
sudo systemctl daemon-reload
sudo systemctl enable stock-trader
sudo systemctl start stock-trader

# 상태 확인
sudo systemctl status stock-trader

# 로그 확인
journalctl -u stock-trader -f

# 중지
sudo systemctl stop stock-trader
```

### 방법 3: macOS launchd (Mac, 권장)

```bash
cat > ~/Library/LaunchAgents/com.stock-trader.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stock-trader</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/kr-stock-analyzer/venv/bin/python3</string>
        <string>/path/to/kr-stock-analyzer/auto_trader.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/kr-stock-analyzer</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>KIS_APP_KEY</key>
        <string>your_key</string>
        <key>KIS_APP_SECRET</key>
        <string>your_secret</string>
        <key>KIS_ACCOUNT_NO</key>
        <string>12345678-01</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/kr-stock-analyzer/data/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/kr-stock-analyzer/data/launchd.err</string>
</dict>
</plist>
EOF

# 등록
launchctl load ~/Library/LaunchAgents/com.stock-trader.plist

# 해제
launchctl unload ~/Library/LaunchAgents/com.stock-trader.plist
```

### 방법 4: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python3", "auto_trader.py"]
```

```bash
docker build -t stock-trader .
docker run -d --name stock-trader \
  -e KIS_APP_KEY="..." \
  -e KIS_APP_SECRET="..." \
  -e KIS_ACCOUNT_NO="12345678-01" \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  stock-trader
```

---

## 운영 체크리스트

- [ ] KIS API 토큰은 12시간마다 자동 갱신 (코드 내장)
- [ ] KIS API 호출 제한: 초당 20건 (sleep 내장)
- [ ] 로그 확인: `tail -f data/auto_trader.log`
- [ ] 판단 근거: `tail -f data/decisions.jsonl`
- [ ] 매매 기록: `cat data/trades.json | python3 -m json.tool`
- [ ] 장 운영시간: 09:00~15:30 (스케줄러가 시간대별 자동 관리)
- [ ] 주말/공휴일: 스케줄러 실행되나 API가 데이터 미반환 → 자연 스킵

## 전략 파라미터 조정

`config.py`의 `StrategyConfig`에서 수정:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `stop_loss_pct` | -0.05 | 손절 기준 |
| `take_profit_pct` | 0.15 | 익절 기준 |
| `trailing_stop_pct` | 0.07 | 트레일링 스탑 |
| `max_positions` | 5 | 최대 동시 보유 |
| `max_holding_days` | 15 | 장기 보유 한도 (일) |
| `signal_exit_score` | 30.0 | 신호 악화 매도 기준 |

---

## 주의사항

- 이 시스템은 투자 보조 도구이며 투자 권유가 아닙니다
- 30만원 → 1,000만원(33배)은 극도로 공격적인 목표로 원금 손실 위험이 매우 큽니다
- **반드시 모의투자로 충분히 검증한 후** 실전 적용하세요
- 모든 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다
