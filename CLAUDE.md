# kr-stock-analyzer

한국투자증권(KIS) Open API 기반 자동매매 + Streamlit 대시보드 시스템.
30만원→1,000만원 목표, 자체 점수 시스템(신호생성기)이 매매 판단.

## Structure

```
config.py              # 전략 파라미터(StrategyConfig), API 키, 섹터-원자재 매핑(SectorConfig), 뉴스(NewsConfig)
auto_trader.py         # AutoTrader 클래스 + run_scheduler() 장중 스케줄러
dashboard.py           # Streamlit 대시보드 (시장현황/매매신호/포트폴리오/종목분석/매매기록)
modules/
├── kis_api.py         # KISApi: OAuth2 인증, 시세조회, 주문, 잔고, 재무 (REST)
├── screener.py        # StockScreener: 재무/원자재/모멘텀 스크리닝 → StockScore
├── market_data.py     # MarketDataCollector: 네이버뉴스 크롤링, yfinance 환율/원자재, 감성분석
├── technical.py       # TechnicalAnalyzer: SMA/EMA/RSI/MACD/BB/스토캐스틱 → TradeSignal
└── portfolio.py       # PortfolioManager: 포지션 사이징, 손절/익절/트레일링, 매매기록
strategies/            # 커스텀 전략 확장용 (비어 있음)
data/                  # 런타임 생성: trades.json, auto_trader.log
```

## Commands

```bash
pip install -r requirements.txt          # 의존성 설치
python auto_trader.py                    # 모의투자 스케줄러
python auto_trader.py --live             # 실전투자 (주의!)
python auto_trader.py --once             # 1회 분석 (상위 5개 신호 출력)
streamlit run dashboard.py               # 대시보드
```

환경변수: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`

## Key Domain

**신호생성기**: 기술적(35%) + 원자재(25%) + 펀더멘털(20%) + 뉴스(20%) 가중 평균
- 75↑ 강력매수, 60↑ 매수, 40~60 보유, 25~40 매도, 25↓ 강력매도
- 기술적 점수: RSI/MACD/BB/SMA/거래량/스토캐스틱 종합 (-100~+100 → 0~100 정규화)
- confidence = min(100, |final_score - 50| × 2)

**원자재-섹터 민감도**: 철강(구리+0.3, 유가-0.2), 정유(유가+0.5, 가스+0.2), 화학(유가-0.3, 가스-0.2), 비철금속(구리+0.5, 금+0.2), 2차전지(구리+0.3, 은+0.2)

**리스크**: 손절-5%, 익절+15%, 트레일링-7%, 일일손실한도 10%, 현금 5% 유지, 최대 5종목

**스케줄**: 08:30 장전분석 → 10분마다 포지션체크 → 30분마다 매수탐색 → 15:40 리포트

## Tech Stack

Python 3.9+, KIS Open API (REST/OAuth2), yfinance, BeautifulSoup4, schedule, Streamlit, pandas
기술적 지표: 순수 Python (numpy/pandas 미사용)

## Rules

- `--live` 없으면 모의투자 (실제 주문 X)
- KIS API 초당 20건 제한 → sleep 포함
- `KIS_BASE_URL` 모의/실전 전환 필요
- 한글 주석/로그 사용
- data/ 디렉토리는 런타임 자동 생성
