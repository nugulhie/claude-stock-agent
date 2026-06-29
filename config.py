"""
========================================
한국 주식 분석 대시보드 - 설정 파일
========================================
한국투자증권 KIS API 키 및 전략 파라미터 설정
"""

import os
from dataclasses import dataclass, field
from typing import List


def _load_env_file(path: str = ".env"):
    """Load simple KEY=VALUE or export KEY=VALUE lines when env vars are absent."""
    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_env_file()

# ============================================================
# KIS API 설정 (한국투자증권 Open API)
# https://apiportal.koreainvestment.com 에서 발급
# ============================================================
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "YOUR_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "YOUR_APP_SECRET")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "00000000-00")  # 계좌번호-상품코드
KIS_PAPER_URL = "https://openapivts.koreainvestment.com:29443"
KIS_LIVE_URL = "https://openapi.koreainvestment.com:9443"
KIS_TRADING_MODE = os.getenv("KIS_TRADING_MODE", "paper").lower()
KIS_BASE_URL = os.getenv(
    "KIS_BASE_URL",
    KIS_LIVE_URL if KIS_TRADING_MODE in {"live", "real"} else KIS_PAPER_URL,
)

# ============================================================
# Claude API 설정 (Anthropic)
# ============================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"


def normalize_stock_codes(value) -> List[str]:
    """쉼표/공백 구분 종목코드를 6자리 숫자 목록으로 정리."""
    if not value:
        return []
    if isinstance(value, str):
        raw_codes = value.replace("\n", ",").replace(" ", ",").split(",")
    else:
        raw_codes = list(value)

    codes = []
    seen = set()
    for raw in raw_codes:
        code = str(raw).strip()
        if not code:
            continue
        if code.isdigit():
            code = code.zfill(6)
        if len(code) == 6 and code.isdigit() and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes

# ============================================================
# 투자 전략 설정
# ============================================================
@dataclass
class StrategyConfig:
    """공격적 투자 전략 파라미터"""

    # 자본금 설정
    initial_capital: int = 300_000          # 초기 자본금 (30만원)
    target_capital: int = 10_000_000        # 목표 금액 (1,000만원)

    # 포지션 관리
    max_positions: int = 5                  # 최대 동시 보유 종목 수
    max_position_pct: float = 0.40          # 종목당 최대 투자 비율 (40%)
    min_position_pct: float = 0.10          # 종목당 최소 투자 비율 (10%)

    # 손절/익절 기준
    stop_loss_pct: float = -0.05            # 손절 기준 (-5%)
    take_profit_pct: float = 0.15           # 익절 기준 (+15%)
    trailing_stop_pct: float = 0.07         # 트레일링 스탑 (7%)

    # 스크리닝 필터
    min_market_cap: int = 50_000_000_000    # 최소 시가총액 (500억)
    max_market_cap: int = 2_000_000_000_000 # 최대 시가총액 (2조) - 소형주 위주
    min_volume: int = 100_000               # 최소 거래량
    min_volume_increase: float = 2.0        # 거래량 급증 배수 (평균 대비)

    # 재무제표 필터
    max_per: float = 30.0                   # 최대 PER
    max_pbr: float = 3.0                    # 최대 PBR
    min_roe: float = 5.0                    # 최소 ROE (%)
    max_debt_ratio: float = 200.0           # 최대 부채비율 (%)

    # 기술적 분석 파라미터
    rsi_oversold: float = 30.0              # RSI 과매도 기준
    rsi_overbought: float = 70.0            # RSI 과매수 기준
    macd_signal_period: int = 9             # MACD 시그널 기간
    bb_period: int = 20                     # 볼린저밴드 기간
    bb_std: float = 2.0                     # 볼린저밴드 표준편차

    # 분석 가중치
    commodity_weight: float = 0.25          # 원자재 시그널 가중치
    news_weight: float = 0.20              # 뉴스 시그널 가중치
    technical_weight: float = 0.35         # 기술적 분석 가중치
    fundamental_weight: float = 0.20       # 재무 분석 가중치

    # 탈출 조건
    max_holding_days: int = 15              # 최대 보유 기간 (일)
    sideways_threshold_pct: float = 2.0     # 횡보 판단 기준 (±%)
    signal_exit_score: float = 30.0         # 신호 악화 매도 기준 (종합점수 이하)
    daily_loss_close_positions: bool = True  # 일일 손실한도 시 손실 포지션 정리

    # Claude AI 연동
    use_claude_sentiment: bool = True       # Claude 뉴스 감성 분석
    use_claude_overview: bool = True        # Claude 시장 해석
    use_claude_decision: bool = True        # Claude 최종 판단


# ============================================================
# 관심 섹터 및 원자재 연관 종목
# ============================================================
@dataclass
class SectorConfig:
    """섹터별 종목 매핑"""

    # 원자재 관련주
    commodity_stocks: dict = field(default_factory=lambda: {
        "철강": ["005490", "004020", "001230"],    # POSCO홀딩스, 현대제철, 동국제강
        "정유": ["010950", "096770", "267250"],    # S-Oil, SK이노베이션, HD현대
        "화학": ["051910", "010060", "011170"],    # LG화학, OCI홀딩스, 롯데케미칼
        "비철금속": ["018470", "104700"],           # 조일알미늄, 한국철강
        "2차전지소재": ["003670", "005070"],        # 포스코퓨처엠, 코스모신소재
    })

    # 원자재 가격 추적 대상
    commodities_to_track: list = field(default_factory=lambda: [
        "CL=F",    # WTI 원유
        "GC=F",    # 금
        "SI=F",    # 은
        "HG=F",    # 구리
        "NG=F",    # 천연가스
        "ZW=F",    # 밀
        "X:USDKRW", # 원/달러 환율
    ])

    # 관심 테마
    theme_keywords: list = field(default_factory=lambda: [
        "AI", "반도체", "2차전지", "로봇", "방산",
        "원전", "수소", "바이오", "우주항공", "양자컴퓨터"
    ])

    # 사용자가 .env에서 추가하는 관심 종목
    user_watchlist: list = field(default_factory=lambda: normalize_stock_codes(
        os.getenv("WATCHLIST_CODES", "")
    ))


# ============================================================
# 뉴스 분석 설정
# ============================================================
@dataclass
class NewsConfig:
    """뉴스 크롤링 및 감성 분석 설정"""
    sources: list = field(default_factory=lambda: [
        "https://finance.naver.com/news/mainnews.naver",
    ])
    sentiment_threshold_positive: float = 0.6
    sentiment_threshold_negative: float = -0.3
    max_news_age_hours: int = 24


# ============================================================
# 매매 시간 설정
# ============================================================
MARKET_OPEN = "09:00"
MARKET_CLOSE = "15:30"
PRE_MARKET_ANALYSIS = "08:30"    # 장 시작 전 분석 시점
POST_MARKET_REVIEW = "15:40"     # 장 마감 후 리뷰 시점


# 전역 설정 인스턴스
STRATEGY = StrategyConfig()
SECTORS = SectorConfig()
NEWS = NewsConfig()


def get_kis_mode() -> str:
    """현재 KIS 접속 모드 표시용."""
    return "live" if KIS_BASE_URL == KIS_LIVE_URL else "paper"


def get_config_issues(require_kis: bool = False, live: bool = False) -> dict:
    """실행 전 사용자가 바로 이해할 수 있는 설정 문제 목록."""
    errors = []
    warnings = []

    missing_kis = []
    if KIS_APP_KEY in {"", "YOUR_APP_KEY"}:
        missing_kis.append("KIS_APP_KEY")
    if KIS_APP_SECRET in {"", "YOUR_APP_SECRET"}:
        missing_kis.append("KIS_APP_SECRET")
    if KIS_ACCOUNT_NO in {"", "00000000-00"} or "-" not in KIS_ACCOUNT_NO:
        missing_kis.append("KIS_ACCOUNT_NO")

    if missing_kis:
        message = "KIS 설정 필요: " + ", ".join(missing_kis)
        if require_kis:
            errors.append(message)
        else:
            warnings.append(message)

    if STRATEGY.stop_loss_pct >= 0:
        errors.append("stop_loss_pct는 음수여야 합니다.")
    if STRATEGY.take_profit_pct <= 0:
        errors.append("take_profit_pct는 양수여야 합니다.")
    if not 0 < STRATEGY.max_position_pct <= 1:
        errors.append("max_position_pct는 0~1 범위여야 합니다.")
    if STRATEGY.min_position_pct > STRATEGY.max_position_pct:
        errors.append("min_position_pct가 max_position_pct보다 큽니다.")

    weight_total = (
        STRATEGY.commodity_weight
        + STRATEGY.news_weight
        + STRATEGY.technical_weight
        + STRATEGY.fundamental_weight
    )
    if abs(weight_total - 1.0) > 0.001:
        errors.append(f"분석 가중치 합이 1.0이 아닙니다: {weight_total:.3f}")

    return {"errors": errors, "warnings": warnings}


def get_default_watchlist() -> List[str]:
    """섹터 기본 종목과 사용자 관심종목을 중복 없이 합친 목록."""
    codes = []
    for sector_codes in SECTORS.commodity_stocks.values():
        codes.extend(sector_codes)
    codes.extend(SECTORS.user_watchlist)
    return normalize_stock_codes(codes)
