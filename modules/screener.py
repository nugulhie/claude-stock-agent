"""
========================================
주식 스크리너 모듈
========================================
재무제표 기반 필터링, 원자재 연관주 분석,
소형주/테마주 스크리닝
"""

import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import STRATEGY, SECTORS


@dataclass
class StockScore:
    """종목 종합 점수"""
    code: str
    name: str
    price: int
    total_score: float          # 0~100 종합 점수
    fundamental_score: float    # 재무 점수
    technical_score: float      # 기술적 점수
    commodity_score: float      # 원자재 연동 점수
    momentum_score: float       # 모멘텀 점수
    reasons: List[str]          # 매수 근거 목록
    risk_flags: List[str]       # 리스크 경고


class StockScreener:
    """종합 주식 스크리너"""

    def __init__(self, kis_api):
        self.api = kis_api
        self.strategy = STRATEGY
        self.sectors = SECTORS

    # --------------------------------------------------
    # 재무제표 기반 필터링
    # --------------------------------------------------
    def screen_fundamentals(self, stock_code: str, price_data: Dict,
                            financial_data: Dict) -> tuple:
        """
        재무제표 기반 스크리닝
        Returns: (score: 0-100, reasons: list, flags: list)
        """
        score = 0.0
        reasons = []
        flags = []

        per = price_data.get("per", 0)
        pbr = price_data.get("pbr", 0)
        roe = financial_data.get("roe", 0)
        debt_ratio = financial_data.get("debt_ratio", 0)
        op_margin = financial_data.get("operating_margin", 0)
        rev_growth = financial_data.get("revenue_growth", 0)

        # PER 분석 (저PER 선호, 단 적자 기업 제외)
        if 0 < per <= 10:
            score += 25
            reasons.append(f"저PER ({per:.1f}) - 저평가 가능성")
        elif 10 < per <= self.strategy.max_per:
            score += 15
            reasons.append(f"적정 PER ({per:.1f})")
        elif per > self.strategy.max_per:
            score -= 10
            flags.append(f"고PER ({per:.1f}) 주의")
        elif per < 0:
            flags.append("적자 기업 (PER 음수)")

        # PBR 분석 (PBR=0은 데이터 없음이므로 제외)
        if 0 < pbr <= 1.0:
            score += 20
            reasons.append(f"저PBR ({pbr:.2f}) - 자산가치 대비 저평가")
        elif 0 < pbr <= self.strategy.max_pbr:
            score += 10

        # ROE 분석
        if roe >= 15:
            score += 25
            reasons.append(f"높은 ROE ({roe:.1f}%) - 자본 효율 우수")
        elif roe >= self.strategy.min_roe:
            score += 15
            reasons.append(f"양호한 ROE ({roe:.1f}%)")
        elif roe < self.strategy.min_roe and roe > 0:
            score += 5
        elif roe <= 0:
            score -= 15
            flags.append(f"음의 ROE ({roe:.1f}%) - 수익성 악화")

        # 부채비율
        if debt_ratio <= 100:
            score += 15
            reasons.append(f"건전한 부채비율 ({debt_ratio:.0f}%)")
        elif debt_ratio <= self.strategy.max_debt_ratio:
            score += 5
        else:
            score -= 15
            flags.append(f"높은 부채비율 ({debt_ratio:.0f}%) 주의")

        # 매출 성장률
        if rev_growth >= 20:
            score += 15
            reasons.append(f"매출 급성장 ({rev_growth:.1f}%)")
        elif rev_growth >= 5:
            score += 10
            reasons.append(f"매출 성장 ({rev_growth:.1f}%)")
        elif rev_growth < 0:
            flags.append(f"매출 역성장 ({rev_growth:.1f}%)")

        return max(0, min(100, score)), reasons, flags

    # --------------------------------------------------
    # 원자재 연관 분석
    # --------------------------------------------------
    def analyze_commodity_sensitivity(self, stock_code: str,
                                     commodity_changes: Dict[str, float]) -> tuple:
        """
        원자재 가격 변동과 종목의 연관성 분석
        commodity_changes: {"CL=F": +2.5, "GC=F": -1.2, ...} (% 변동)
        Returns: (score: 0-100, reasons: list)
        """
        score = 50.0  # 기본 중립 점수
        reasons = []

        # 해당 종목이 어떤 원자재 섹터인지 확인
        stock_sector = None
        for sector, codes in self.sectors.commodity_stocks.items():
            if stock_code in codes:
                stock_sector = sector
                break

        if not stock_sector:
            return 50.0, ["원자재 직접 연관 없음 (일반 종목)"]

        # 섹터별 원자재 연동 로직
        sector_commodity_map = {
            "철강": {"HG=F": 0.3, "CL=F": -0.2},     # 구리가↑→철강수요↑, 유가↑→비용↑
            "정유": {"CL=F": 0.5, "NG=F": 0.2},       # 유가↑→매출↑
            "화학": {"CL=F": -0.3, "NG=F": -0.2},     # 유가↑→원가↑→부담
            "비철금속": {"HG=F": 0.5, "GC=F": 0.2},   # 구리/금 가격 직접 연동
            "2차전지소재": {"HG=F": 0.3, "SI=F": 0.2}, # 구리/리튬 연관
        }

        mappings = sector_commodity_map.get(stock_sector, {})
        for commodity, sensitivity in mappings.items():
            change = commodity_changes.get(commodity, 0)
            impact = change * sensitivity * 10  # 점수 스케일링
            score += impact

            if abs(change) > 1.0:
                direction = "상승" if change > 0 else "하락"
                effect = "호재" if impact > 0 else "악재"
                reasons.append(
                    f"{commodity} {direction}({change:+.1f}%) → {stock_sector} {effect}"
                )

        # 환율 영향 (원/달러)
        usd_change = commodity_changes.get("X:USDKRW", 0)
        if abs(usd_change) > 0.5:
            if stock_sector in ["정유", "화학"]:
                # 원화 약세 → 수출 기업 유리
                score += usd_change * 3
                reasons.append(f"원/달러 {usd_change:+.1f}% → 수출 영향")

        return max(0, min(100, score)), reasons

    # --------------------------------------------------
    # 소형주 / 급등주 필터
    # --------------------------------------------------
    def screen_small_cap_momentum(self, stock_data: Dict,
                                  daily_prices: List[Dict]) -> tuple:
        """
        소형주 모멘텀 스크리닝
        Returns: (score: 0-100, reasons: list, flags: list)
        """
        score = 0.0
        reasons = []
        flags = []

        market_cap = stock_data.get("market_cap", 0)
        volume = stock_data.get("volume", 0)
        change_pct = stock_data.get("change_pct", 0)

        # 시가총액 필터 (소형주 선호)
        if self.strategy.min_market_cap <= market_cap <= self.strategy.max_market_cap:
            score += 20
            cap_bil = market_cap / 1_000_000_000
            reasons.append(f"적정 시총 ({cap_bil:.0f}억) - 소형주 범위")
        elif market_cap < self.strategy.min_market_cap:
            flags.append("극소형주 - 유동성 리스크")
        elif market_cap > self.strategy.max_market_cap:
            score += 5  # 대형주는 안정적이나 급등 가능성 낮음

        # 거래량 분석
        if len(daily_prices) >= 20:
            avg_volume = sum(d["volume"] for d in daily_prices[:20]) / 20
            if avg_volume > 0:
                vol_ratio = volume / avg_volume
                if vol_ratio >= self.strategy.min_volume_increase * 2:
                    score += 25
                    reasons.append(f"거래량 폭증 ({vol_ratio:.1f}배) - 수급 유입")
                elif vol_ratio >= self.strategy.min_volume_increase:
                    score += 15
                    reasons.append(f"거래량 증가 ({vol_ratio:.1f}배)")

        # 5일/20일 모멘텀
        if len(daily_prices) >= 5:
            price_5d_ago = daily_prices[4]["close"]
            current = daily_prices[0]["close"] if daily_prices else stock_data.get("price", 0)
            if price_5d_ago > 0:
                momentum_5d = (current - price_5d_ago) / price_5d_ago * 100
                if 3 <= momentum_5d <= 15:
                    score += 20
                    reasons.append(f"5일 모멘텀 +{momentum_5d:.1f}% (상승 추세)")
                elif momentum_5d > 15:
                    score += 10
                    flags.append(f"5일 +{momentum_5d:.1f}% (과열 주의)")
                elif momentum_5d < -10:
                    flags.append(f"5일 {momentum_5d:.1f}% (급락)")

        # 52주 신저가 대비 위치
        high_52w = stock_data.get("high_52w", 0)
        low_52w = stock_data.get("low_52w", 0)
        price = stock_data.get("price", 0)
        if high_52w > low_52w > 0 and price > 0:
            position = (price - low_52w) / (high_52w - low_52w) * 100
            if 20 <= position <= 50:
                score += 15
                reasons.append(f"52주 하단권 ({position:.0f}%) - 반등 가능성")
            elif position > 90:
                flags.append(f"52주 최고가 근접 ({position:.0f}%)")

        return max(0, min(100, score)), reasons, flags

    # --------------------------------------------------
    # 종합 스크리닝
    # --------------------------------------------------
    def comprehensive_screen(self, stock_code: str, stock_name: str,
                             price_data: Dict, financial_data: Dict,
                             daily_prices: List[Dict],
                             commodity_changes: Dict[str, float],
                             technical_score: float = 50.0) -> StockScore:
        """모든 분석을 종합한 최종 점수 산출"""

        # 1. 재무 분석
        fund_score, fund_reasons, fund_flags = self.screen_fundamentals(
            stock_code, price_data, financial_data
        )

        # 2. 원자재 연관 분석
        comm_score, comm_reasons = self.analyze_commodity_sensitivity(
            stock_code, commodity_changes
        )

        # 3. 모멘텀 분석
        mom_score, mom_reasons, mom_flags = self.screen_small_cap_momentum(
            price_data, daily_prices
        )

        # 4. 가중 평균 종합 점수
        # 뉴스 점수는 generate_signal에서 별도 반영, 여기서는 모멘텀으로 대체
        total_score = (
            fund_score * self.strategy.fundamental_weight +
            technical_score * self.strategy.technical_weight +
            comm_score * self.strategy.commodity_weight +
            mom_score * self.strategy.news_weight
        )

        all_reasons = fund_reasons + comm_reasons + mom_reasons
        all_flags = fund_flags + mom_flags

        return StockScore(
            code=stock_code,
            name=stock_name,
            price=price_data.get("price", 0),
            total_score=round(total_score, 1),
            fundamental_score=round(fund_score, 1),
            technical_score=round(technical_score, 1),
            commodity_score=round(comm_score, 1),
            momentum_score=round(mom_score, 1),
            reasons=all_reasons,
            risk_flags=all_flags,
        )
