# 한국주식 자동매매 시스템 - 프로젝트 컨텍스트

## 프로젝트 개요

한국투자증권(KIS) Open API 기반의 자동매매 + 분석 대시보드 시스템.
30만원 자본으로 1,000만원 목표의 공격적 투자 전략을 구현한다.
Claude API가 아닌 자체 점수 시스템(신호생성기)이 매매를 결정한다.

## 핵심 설계 원칙

- **4가지 분석 종합**: 기술적(35%) + 원자재(25%) + 펀더멘털(20%) + 뉴스(20%) 가중 평균
- **원자재 민감 반응**: 국제 원자재 가격 변동이 관련 섹터 종목 점수에 직접 반영
- **리스크 우선**: 손절(-5%), 익절(+15%), 트레일링스탑(-7%), 일일 손실한도(10%) 자동 적용
- **순수 Python**: 기술적 지표를 numpy/pandas 없이 직접 구현

## 프로젝트 구조

```
kr-stock-analyzer/
├── config.py              # 전략 파라미터, API 키, 섹터 매핑
├── auto_trader.py         # 자동매매 엔진 + 장중 스케줄러
├── dashboard.py           # Streamlit 웹 대시보드 (5개 탭)
├── requirements.txt       # Python 의존성
├── .claude/
│   └── context.md         # 이 파일 (프로젝트 컨텍스트)
├── modules/
│   ├── __init__.py        # 모듈 export
│   ├── kis_api.py         # 한국투자증권 REST API 클라이언트
│   ├── screener.py        # 종목 스크리닝 (재무/원자재/모멘텀)
│   ├── market_data.py     # 뉴스 크롤링, 환율, 원자재 가격 수집
│   ├── technical.py       # 기술적 지표 계산 + 매매 신호 생성
│   └── portfolio.py       # 포트폴리오 관리, 포지션 사이징, 리스크
├── strategies/            # 커스텀 전략 확장용 (비어 있음)
└── data/                  # 런타임 생성: trades.json, auto_trader.log
```

## 의존성 (requirements.txt)

- requests >= 2.28.0 (HTTP 요청)
- beautifulsoup4 >= 4.11.0 (뉴스 크롤링)
- yfinance >= 0.2.18 (원자재/환율 데이터)
- schedule >= 1.2.0 (장중 스케줄러)
- streamlit >= 1.28.0 (대시보드 UI)
- pandas >= 2.0.0 (데이터 처리)

## config.py — 설정 상세

### API 설정
- `KIS_APP_KEY`: 환경변수 `KIS_APP_KEY`
- `KIS_APP_SECRET`: 환경변수 `KIS_APP_SECRET`
- `KIS_ACCOUNT_NO`: 환경변수 `KIS_ACCOUNT_NO` (형식: "12345678-01")
- `KIS_BASE_URL`: 실전 `https://openapi.koreainvestment.com:9443` / 모의 `https://openapivts.koreainvestment.com:29443`

### StrategyConfig 클래스
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| initial_capital | 300,000 | 초기 자본금 (원) |
| target_capital | 10,000,000 | 목표 자본금 (원) |
| max_positions | 5 | 최대 동시 보유 종목 수 |
| max_position_pct | 0.40 | 종목당 최대 비중 (40%) |
| min_position_pct | 0.10 | 종목당 최소 비중 (10%) |
| stop_loss_pct | -0.05 | 손절 기준 (-5%) |
| take_profit_pct | 0.15 | 익절 기준 (+15%) |
| trailing_stop_pct | 0.07 | 트레일링 스탑 (고점 대비 -7%) |
| min_market_cap | 50,000,000,000 | 최소 시총 (500억) |
| max_market_cap | 2,000,000,000,000 | 최대 시총 (2조) |
| min_volume | 100,000 | 최소 일일 거래량 |
| min_volume_increase | 2.0 | 거래량 급증 배율 |
| max_per | 30.0 | 최대 PER |
| max_pbr | 3.0 | 최대 PBR |
| min_roe | 5.0 | 최소 ROE (%) |
| max_debt_ratio | 200.0 | 최대 부채비율 (%) |
| rsi_oversold | 30.0 | RSI 과매도 |
| rsi_overbought | 70.0 | RSI 과매수 |
| macd_signal_period | 9 | MACD 시그널 기간 |
| bb_period | 20 | 볼린저밴드 기간 |
| bb_std | 2.0 | 볼린저밴드 표준편차 |
| commodity_weight | 0.25 | 원자재 가중치 |
| news_weight | 0.20 | 뉴스 가중치 |
| technical_weight | 0.35 | 기술적 가중치 |
| fundamental_weight | 0.20 | 펀더멘털 가중치 |

### SectorConfig 클래스
**원자재 관련주 매핑**:
- 철강: 005490(POSCO홀딩스), 004020(현대제철), 001230(동국제강)
- 정유: 010950(S-Oil), 096770(SK이노베이션), 267250(현대중공업)
- 화학: 051910(LG화학), 010060(OCI), 011170(롯데케미칼)
- 비철금속: 018470(조일알미늄), 104700(한국철강)
- 2차전지소재: 003670(포스코퓨처엠), 005070(코스모신소재)

**추적 원자재 심볼**: CL=F(WTI), GC=F(금), SI=F(은), HG=F(구리), NG=F(천연가스), ZW=F(밀), X:USDKRW(환율)

**테마 키워드**: AI, 반도체, 2차전지, 로봇, 방산, 원전, 수소, 바이오, 우주항공, 양자컴퓨터

### NewsConfig 클래스
- sources: `["https://finance.naver.com/news/mainnews.naver"]`
- sentiment_threshold_positive: 0.6
- sentiment_threshold_negative: -0.3
- max_news_age_hours: 24

### 장 시간 상수
- MARKET_OPEN: "09:00"
- MARKET_CLOSE: "15:30"
- PRE_MARKET_ANALYSIS: "08:30"
- POST_MARKET_REVIEW: "15:40"

### 전역 인스턴스
- `STRATEGY = StrategyConfig()`
- `SECTORS = SectorConfig()`
- `NEWS = NewsConfig()`

## modules/kis_api.py — KISApi 클래스

### 인증
- `__init__()`: API 키/시크릿/계좌번호 로드, 토큰 캐시 초기화
- `get_access_token()`: OAuth2 토큰 발급, 12시간 캐시
- `_headers(tr_id, hashkey)`: 공통 헤더 생성 (Bearer 토큰, 앱키, TR ID)
- `_get_hashkey(body)`: POST `/uapi/hashkey` → HASH 값 반환

### 시세 조회
- `get_current_price(stock_code)`: 현재가/등락/거래량/시총/PER/PBR/EPS/BPS
  - 반환: `{code, price, change, change_pct, volume, trade_amount, high, low, open, high_52w, low_52w, market_cap, per, pbr, eps, bps}`
- `get_daily_prices(stock_code, period="D", count=100)`: 일봉/주봉/월봉 OHLCV
  - period: "D"(일), "W"(주), "M"(월)
  - 반환: `[{date, open, high, low, close, volume, change_pct}, ...]`
- `get_volume_rank(limit=30)`: 거래량 상위 종목
  - 반환: `[{code, name, price, change_pct, volume, trade_amount}, ...]`

### 주문
- `place_order(stock_code, qty, price=0, side="buy", order_type="market")`:
  - side: "buy"(TTTC0802U) / "sell"(TTTC0801U)
  - order_type: "market"(01) / "limit"(00)

### 잔고
- `get_balance()`: 계좌 잔고 및 보유종목
  - 반환: `{holdings: [{code, name, qty, avg_price, current_price, profit_pct, profit_amt}], total_eval, total_profit, cash, total_buy_amt}`

### 재무
- `get_financial_data(stock_code)`: 재무비율
  - 반환: `{code, roe, roa, debt_ratio, operating_margin, net_margin, revenue_growth, current_ratio}`

## modules/technical.py — 기술적 분석

### Signal Enum
```python
STRONG_BUY = "강력매수"
BUY = "매수"
HOLD = "보유"
SELL = "매도"
STRONG_SELL = "강력매도"
```

### TradeSignal 데이터클래스
```python
@dataclass
class TradeSignal:
    code: str               # 종목코드
    name: str               # 종목명
    signal: Signal          # 매매 신호
    confidence: float       # 신뢰도 (0~100)
    price: int              # 현재가
    target_price: int       # 목표가
    stop_loss_price: int    # 손절가
    reasons: List[str]      # 매매 근거
    indicators: Dict        # 기술적 지표값
    timestamp: str = ""     # 타임스탬프
```

### TechnicalAnalyzer 클래스

**지표 계산 메서드** (순수 Python, numpy/pandas 미사용):
- `calc_sma(prices, period)`: 단순이동평균
- `calc_ema(prices, period)`: 지수이동평균 (multiplier = 2/(period+1))
- `calc_rsi(prices, period=14)`: RSI (100 - 100/(1+RS))
- `calc_macd(prices, fast=12, slow=26, signal_period=9)`: MACD선, 시그널선, 히스토그램
- `calc_bollinger_bands(prices, period=20, std_dev=2.0)`: 상단/중단/하단 밴드
- `calc_stochastic(highs, lows, closes, k_period=14, d_period=3)`: %K, %D

**generate_signal() — 핵심 신호 생성**:
- 입력: stock_code, stock_name, daily_prices(최소 30개), fundamental_score, commodity_score, news_score
- 최신순 → 시간순으로 뒤집어서 계산

**기술적 점수 산정 (-100 ~ +100)**:
| 조건 | 점수 |
|------|------|
| RSI < 30 (과매도) | +25 |
| RSI 30~40 | +10 |
| RSI > 70 (과매수) | -25 |
| RSI 60~70 | -5 |
| MACD 골든크로스 | +30 |
| MACD > 시그널 (지속) | +15 |
| MACD 데드크로스 | -30 |
| MACD < 시그널 (지속) | -15 |
| 가격 <= 하단밴드 | +20 |
| 가격 >= 상단밴드 | -20 |
| 가격 > 중단밴드 | +5 |
| SMA5 > SMA20 | +10 |
| SMA5↗SMA20 크로스 | +15 추가 |
| SMA5 < SMA20 | -10 |
| 가격 > SMA60 | +5 |
| 가격 < SMA60 | -5 |
| 거래량비율 > 3.0 + 상승 | +20 |
| 거래량비율 > 2.0 | +10 |
| 스토캐스틱 %K,%D < 20 | +10 |
| 스토캐스틱 %K,%D > 80 | -10 |

**최종 점수 계산**:
```
tech_normalized = (tech_score + 100) / 2          → 0~100 정규화
final_score = tech_normalized × 0.35
            + fundamental_score × 0.20
            + commodity_score × 0.25
            + ((news_score + 100) / 2) × 0.20
```

**신호 결정**:
- final_score >= 75 → STRONG_BUY
- 60~74 → BUY
- 40~59 → HOLD
- 25~39 → SELL
- < 25 → STRONG_SELL

**가격 목표**:
- 매수 신호: target = price × 1.15, stop_loss = price × 0.95
- 기타: target = price × 0.95, stop_loss = price × 0.95
- confidence = min(100, |final_score - 50| × 2)

**get_technical_score()**: 간소화 버전, 0~100 점수만 반환 (RSI, MACD, SMA5/20만 사용)

## modules/screener.py — 종목 스크리닝

### StockScore 데이터클래스
```python
@dataclass
class StockScore:
    code: str                   # 종목코드
    name: str                   # 종목명
    price: int                  # 현재가
    total_score: float          # 종합 점수 (0~100)
    fundamental_score: float    # 재무 점수
    technical_score: float      # 기술적 점수
    commodity_score: float      # 원자재 점수
    momentum_score: float       # 모멘텀 점수
    reasons: List[str]          # 매수 근거
    risk_flags: List[str]       # 리스크 경고
```

### StockScreener 클래스

**screen_fundamentals(stock_code, price_data, financial_data) → (score, reasons, flags)**:
- PER: 0~10 → +25, 10~30 → +15, >30 → -10, <0 → 적자 플래그
- PBR: 0~1 → +20, 1~3 → +10
- ROE: >=15% → +25, 5~15% → +15, 0~5% → +5, <=0 → -15 + 플래그
- 부채비율: <=100% → +15, 100~200% → +5, >200% → -15 + 플래그
- 매출성장: >=20% → +15, 5~20% → +10, <0% → 플래그

**analyze_commodity_sensitivity(stock_code, commodity_changes) → (score, reasons)**:
- 기본 50점(중립)에서 시작
- 섹터-원자재 민감도:
  - 철강: HG=F(구리) +0.3, CL=F(유가) -0.2
  - 정유: CL=F +0.5, NG=F +0.2
  - 화학: CL=F -0.3, NG=F -0.2
  - 비철금속: HG=F +0.5, GC=F +0.2
  - 2차전지소재: HG=F +0.3, SI=F +0.2
- impact = commodity_change_pct × sensitivity × 10
- USD/KRW 변동 > 0.5%: 정유/화학에 USD변동 × 3 반영

**screen_small_cap_momentum(stock_data, daily_prices) → (score, reasons, flags)**:
- 시총 500억~2조: +20 (범위 밖 시 플래그)
- 거래량비율 >= 4.0: +25, >= 2.0: +15
- 5일 모멘텀 3~15%: +20, >15%: +10 + 과열 플래그
- 52주 위치 20~50%: +15 (회복 구간), >90%: 고점 플래그

**comprehensive_screen() → StockScore**:
- 위 3가지 + technical_score를 가중 합산
- (fundamental × 0.20) + (technical × 0.35) + (commodity × 0.25) + (momentum × 0.20)

## modules/market_data.py — 시장 데이터

### 데이터클래스
```python
@dataclass
class NewsItem:
    title: str              # 뉴스 제목
    url: str                # 기사 URL
    source: str             # 출처
    date: str               # 날짜
    sentiment: float        # 감성 점수 (-1.0 ~ +1.0)
    keywords: List[str]     # 감지된 키워드
    related_stocks: List[str]  # 관련 종목

@dataclass
class CommodityData:
    symbol: str             # 심볼 (예: "CL=F")
    name: str               # 이름 (예: "WTI 원유")
    price: float            # 현재가
    change_pct: float       # 등락률 (%)
    trend: str              # "상승"/"하락"/"보합"
```

### MarketDataCollector 클래스

**감성 분석 키워드 사전**:
- 호재(26개): 급등, 상승, 호재, 최고, 돌파, 신고가, 수주, 흑자전환, 매출증가, 영업이익, 배당, 자사주, 목표가상향, 매수추천, 성장, 회복, 기대, 강세, 반등, 상한가, 대박, 수출호조, 실적개선, 사상최대, 턴어라운드, 호실적
- 악재(25개): 급락, 하락, 악재, 최저, 적자, 손실, 하한가, 매도, 목표가하향, 부진, 하방, 약세, 폭락, 실적악화, 매출감소, 부채, 감자, 상폐, 워크아웃, 리스크, 경고, 위기, 불안, 조정, 투매

**뉴스 메서드**:
- `fetch_naver_finance_news(stock_code=None, max_items=20)`: 네이버 금융 크롤링
  - stock_code 있으면: `/item/news_news.naver?code=XXXXX` (종목별 뉴스)
  - 없으면: `/news/mainnews.naver` (메인 뉴스)
- `_analyze_sentiment(text)`: (pos - neg) / (pos + neg), 키워드 없으면 0.0
- `_extract_keywords(text)`: 텍스트에서 감성 키워드 추출
- `get_news_sentiment_score(stock_code)`: 15개 뉴스 평균 감성 → score(-100~+100), reasons

**환율 메서드**:
- `get_exchange_rates()`: yfinance로 USD/EUR/JPY/CNY 환율 조회, 실패 시 네이버 금융 fallback
- `_get_exchange_rates_naver()`: 네이버 금융 시장지표 스크래핑

**원자재 메서드**:
- `get_commodity_prices()`: yfinance 5일 히스토리 → CommodityData 리스트
- `get_commodity_changes()`: {symbol: change_pct} 딕셔너리 반환

**시장 개요**:
- `get_market_overview()`: 환율 + 원자재 + 시장심리(원자재 강세/약세/중립) 종합

## modules/portfolio.py — 포트폴리오 관리

### 데이터클래스
```python
@dataclass
class Position:
    code: str               # 종목코드
    name: str               # 종목명
    qty: int                # 보유 수량
    avg_price: float        # 평균 매입가
    current_price: float    # 현재가
    entry_date: str         # 진입 일시
    highest_price: float    # 진입 후 최고가 (트레일링스탑용)
    signal_score: float     # 진입 시 신호 신뢰도
    stop_loss: float        # 손절가
    take_profit: float      # 익절가
    # @property
    profit_pct: float       # (current - avg) / avg × 100
    market_value: float     # qty × current_price
    profit_amount: float    # qty × (current - avg)

@dataclass
class TradeLog:
    timestamp: str          # 매매 시각
    code: str               # 종목코드
    name: str               # 종목명
    side: str               # "BUY" / "SELL"
    qty: int                # 수량
    price: int              # 체결가
    reason: str             # 매매 사유
    signal_score: float     # 신호 점수
    profit_pct: Optional[float]  # 수익률 (SELL만)
```

### PortfolioManager 클래스

**초기화**:
- initial_capital: 기본 300,000
- cash: initial_capital
- positions: Dict[str, Position]
- daily_loss_limit: initial_capital × 0.10
- log_file: "data/trades.json"

**포지션 사이징**:
- `calculate_position_size(price, signal_confidence) → int`:
  - confidence >= 80% → 40% 비중
  - confidence >= 60% → 25% 비중
  - 기타 → 10% 비중
  - available = min(max_invest, cash × 0.95) — 현금 5% 유지
  - 최대 보유 종목 수 초과 시 0 반환

**매매 실행**:
- `execute_buy(code, name, price, qty, signal_score, reason) → bool`:
  - 자금 부족 시 수량 자동 조정
  - 이미 보유 중이면 평균 매입가 재계산 (물타기)
  - stop_loss = price × 0.95, take_profit = price × 1.15
- `execute_sell(code, price, qty=0, reason) → bool`:
  - qty=0이면 전량 매도
  - 부분 매도 지원

**리스크 관리**:
- `check_stop_conditions(code, current_price) → Optional[str]`:
  - highest_price 갱신 (트레일링스탑 기준)
  - 손절: profit_pct <= -5%
  - 익절: profit_pct >= +15%
  - 트레일링스탑: (current - highest) / highest <= -7%
  - 해당 없으면 None
- `check_daily_risk() → bool`:
  - 미실현 손실 + 일일 실현 손실 < 자본금 10% → True(매수 가능)

**포트폴리오 조회**:
- `get_total_value()`: cash + sum(qty × current_price)
- `get_portfolio_summary()`: 총평가, 손익, 수익률, 현금비율, 보유종목 상세, 목표달성률
- `get_performance_stats()`: SELL 기록 기반 — 승률, 평균수익/손실, 손익비, 최대이익/손실

**매매 기록**:
- `_log_trade()`: TradeLog 생성 → trade_history 추가 → JSON 저장
- `_save_history()`: data/trades.json에 직렬화 저장

## auto_trader.py — 자동매매 엔진

### AutoTrader 클래스

**생성자**: `__init__(paper_trading=True)`
- KISApi, StockScreener, MarketDataCollector, TechnicalAnalyzer, PortfolioManager 초기화
- watchlist: SectorConfig의 원자재 관련주로 구성

**핵심 메서드**:

| 메서드 | 실행 시점 | 역할 |
|--------|-----------|------|
| `pre_market_analysis()` | 08:30 | 시장개요 수집 → 관심종목+거래량 상위 20개 분석 → 매수 후보(최대 50개) 반환 |
| `monitor_positions()` | 10분마다 | 보유종목 손절/익절/트레일링스탑 체크 → 자동 매도 |
| `scan_buy_opportunities()` | 30분마다 | 거래량 상위 15개 스캔 → 강력매수+신뢰도>=70 → 자동 매수 |
| `post_market_review()` | 15:40 | 일일 성과 리포트 로깅 |

**내부 헬퍼**:
- `_analyze_stock(code, commodity_changes)`: 현재가+60일봉+재무+기술점수+뉴스감성 → TradeSignal
- `_execute_buy(signal)`: 포지션 사이징 → 모의/실전 매수
- `_execute_sell(code, price, reason)`: 모의/실전 매도

### run_scheduler(paper_trading=True)
- 08:30 → morning_analysis (장전 분석 + 상위 3개 자동 매수)
- 09:10~15:20 (10분 간격) → monitor_positions
- 09:30~15:00 (30분 간격) → scan_buy_opportunities
- 15:40 → post_market_review
- 무한 루프 (schedule.run_pending(), 1초 간격)

### CLI 인자
```bash
python auto_trader.py          # 모의투자 + 스케줄러 (기본)
python auto_trader.py --live   # 실전투자 모드
python auto_trader.py --once   # 1회 분석만 (상위 5개 신호 출력)
```

## dashboard.py — Streamlit 대시보드

**설정**: 제목 "한국주식 자동매매 대시보드", wide 레이아웃
**초기화**: `@st.cache_resource`로 모듈 인스턴스 캐싱

### 사이드바
- 모드 선택: 모의투자/실전투자
- 초기자본/목표자본 표시
- 전략 파라미터 (손절/익절/트레일링/최대종목수)
- 분석 가중치 표시
- 새로고침 버튼

### 탭 1: 시장현황
- 환율: USD/EUR/JPY/CNY → KRW (등락률 delta 표시)
- 국제 원자재: 6열 그리드, 가격+등락률 (색상: 초록/빨강/회색)
- 거래량 상위: 종목코드, 종목명, 현재가, 등락률, 거래량, 거래대금 테이블

### 탭 2: 매매신호
- 종목코드 입력 (쉼표 구분, 기본: 원자재 관련주 3개)
- "신호 생성" 버튼 → progress bar
- 신뢰도 순 정렬, 확장형 표시:
  - 색상 코드: STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
  - 현재가/목표가/손절가 메트릭
  - 매수/매도 근거 리스트
  - 기술적 지표 테이블

### 탭 3: 포트폴리오
- 4열 메트릭: 총평가, 총손익, 수익률, 목표달성률
- 2열 메트릭: 현금, 보유종목수
- 보유종목 테이블 (코드, 종목명, 수량, 평균가, 현재가, 수익률, 손익, 비중)
- 성과통계: 승률, 평균수익, 평균손실, 손익비

### 탭 4: 종목분석
- 종목코드 입력 (기본: 005490)
- 기본정보: 현재가(등락률 delta), 거래량, PER, PBR
- 재무지표: ROE, 부채비율, 영업이익률, 매출성장률
- 차트: 주가 추이 (라인), 거래량 추이 (바)

### 탭 5: 매매기록
- data/trades.json 읽기
- 테이블: 시간, 종목코드, 종목명, 구분, 수량, 가격, 사유, 신호점수, 수익률
- 기록 없으면 에러 표시

### 푸터
- 투자 보조 도구 면책 고지

## 투자 전략 상세

### 대상 종목
- **원자재 관련주**: POSCO홀딩스, 현대제철, 동국제강, S-Oil, SK이노베이션, LG화학 등
- **소형주**: 시총 500억~2조 범위 (변동성 활용)
- **테마주/급등주**: 거래량 상위에서 실시간 발굴
- **전체 시장**: 거래량 급증 종목은 섹터 무관 분석

### 원자재-섹터 연동 매핑
| 원자재 | 철강 | 정유 | 화학 | 비철금속 | 2차전지소재 |
|--------|------|------|------|----------|-------------|
| WTI 유가↑ | 비용↑(악재, -0.2) | 매출↑(호재, +0.5) | 원가↑(악재, -0.3) | - | - |
| 구리↑ | 수요↑(호재, +0.3) | - | - | 직접호재(+0.5) | 호재(+0.3) |
| 금↑ | - | - | - | 호재(+0.2) | - |
| 천연가스↑ | - | 호재(+0.2) | 원가↑(악재, -0.2) | - | - |
| 은↑ | - | - | - | - | 호재(+0.2) |
| 원화약세 | - | 수출호재(×3) | 수출호재(×3) | - | - |

### 매매 조건 요약
- **매수**: 종합점수 60↑, 신뢰도 70↑ (강력매수 시 자동 실행)
- **매도**: 손절 -5% / 익절 +15% / 트레일링 -7% / 종합점수 25↓
- **포지션**: 최대 5종목, 종목당 10~40%, 현금 5% 유지
- **일일 리스크**: 최대 손실 자본금의 10%

### 비즈니스 로직 흐름
1. **장전 08:30**: 시장개요(환율+원자재) 수집 → 거래량 상위 20개 추가 → 최대 50개 후보 분석 → 매수 후보 선정 → 상위 3개 자동 매수
2. **장중 10분마다**: 보유종목 현재가 체크 → 손절/익절/트레일링스탑 자동 매도
3. **장중 30분마다**: 거래량 상위 15개 스캔 → 강력매수(신뢰도>=70) 발견 시 자동 매수
4. **장후 15:40**: 일일 성과 리포트

## 기술 스택
- Python 3.9+
- 한국투자증권 KIS Developers Open API (REST, OAuth2)
- yfinance (원자재/환율 데이터)
- BeautifulSoup4 (네이버 금융 뉴스 크롤링)
- schedule (장중 스케줄러, 1초 polling)
- Streamlit (대시보드 UI, wide 레이아웃)
- pandas (데이터 처리, 대시보드 테이블)
- 기술적 지표: 순수 Python 구현 (외부 TA 라이브러리 미사용)

## 실행 방법
```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
export KIS_APP_KEY="..."
export KIS_APP_SECRET="..."
export KIS_ACCOUNT_NO="12345678-01"

# 모의투자 자동매매
python auto_trader.py

# 실전투자 (주의!)
python auto_trader.py --live

# 1회 분석만
python auto_trader.py --once

# 대시보드
streamlit run dashboard.py
```

## 주의사항
- 이 시스템은 투자 보조 도구이며 투자 권유가 아님
- 30만원→1,000만원(33배)은 극도로 공격적인 목표로, 원금 손실 위험이 매우 큼
- 반드시 모의투자로 충분히 검증한 후 실전 적용
- KIS API 호출 제한(초당 20건)에 유의하여 sleep 포함됨
- config.py의 `KIS_BASE_URL`을 모의투자/실전투자에 맞게 전환 필요
- data/ 디렉토리는 런타임에 자동 생성됨
