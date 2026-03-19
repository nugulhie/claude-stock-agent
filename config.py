"""
========================================
한국 주식 분석 대시보드 - 설정 파일
========================================
한국투자증권 KIS API 키 및 전략 파라미터 설정
"""

import os
from dataclasses import dataclass, field
from typing import List

# ============================================================
# KIS API 설정 (한국투자증권 Open API)
# https://apiportal.koreainvestment.com 에서 발급
# ============================================================
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "YOUR_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "YOUR_APP_SECRET")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "00000000-00")  # 계좌번호-상품코드
# KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"  # 실전투자
KIS_BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자

# ============================================================
# Claude API 설정 (Anthropic)
# ============================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

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
