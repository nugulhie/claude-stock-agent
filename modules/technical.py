"""
========================================
기술적 분석 및 매매 신호 생성기
========================================
RSI, MACD, 볼린저밴드, 이동평균선 등
기술적 지표 계산 및 종합 매매 시그널 생성
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import STRATEGY


class Signal(Enum):
    STRONG_BUY = "강력매수"
    BUY = "매수"
    HOLD = "보유"
    SELL = "매도"
    STRONG_SELL = "강력매도"


@dataclass
class TradeSignal:
    """매매 신호"""
    code: str
    name: str
    signal: Signal
    confidence: float           # 0~100 신뢰도
    price: int
    target_price: int           # 목표가
    stop_loss_price: int        # 손절가
    reasons: List[str]
    indicators: Dict[str, float]
    timestamp: str = ""


class TechnicalAnalyzer:
    """기술적 분석기"""

    def __init__(self):
        self.config = STRATEGY

    # --------------------------------------------------
    # 기본 지표 계산
    # --------------------------------------------------
    @staticmethod
    def calc_sma(prices: List[float], period: int) -> List[Optional[float]]:
        """단순이동평균 (SMA)"""
        result = [None] * len(prices)
        for i in range(period - 1, len(prices)):
            result[i] = sum(prices[i - period + 1:i + 1]) / period
        return result

    @staticmethod
    def calc_ema(prices: List[float], period: int) -> List[Optional[float]]:
        """지수이동평균 (EMA)"""
        result = [None] * len(prices)
        if len(prices) < period:
            return result

        # 첫 EMA = SMA
        sma = sum(prices[:period]) / period
        result[period - 1] = sma

        multiplier = 2 / (period + 1)
        for i in range(period, len(prices)):
            result[i] = prices[i] * multiplier + result[i - 1] * (1 - multiplier)
        return result

    def calc_rsi(self, prices: List[float], period: int = 14) -> List[Optional[float]]:
        """RSI (Relative Strength Index)"""
        result = [None] * len(prices)
        if len(prices) < period + 1:
            return result

        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))

        # 초기 평균
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # 초기 RSI 값 설정
        if avg_loss == 0:
            result[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                result[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        return result

    def calc_macd(self, prices: List[float],
                  fast: int = 12, slow: int = 26,
                  signal_period: int = 9) -> Tuple[List, List, List]:
        """
        MACD 계산
        Returns: (macd_line, signal_line, histogram)
        """
        ema_fast = self.calc_ema(prices, fast)
        ema_slow = self.calc_ema(prices, slow)

        macd_line = [None] * len(prices)
        for i in range(len(prices)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line[i] = ema_fast[i] - ema_slow[i]

        # MACD 시그널 라인
        macd_values = [v for v in macd_line if v is not None]
        signal_line_raw = self.calc_ema(macd_values, signal_period)

        signal_line = [None] * len(prices)
        histogram = [None] * len(prices)

        macd_start = next(i for i, v in enumerate(macd_line) if v is not None)
        for j, val in enumerate(signal_line_raw):
            idx = macd_start + j
            if idx < len(prices):
                signal_line[idx] = val
                if macd_line[idx] is not None and val is not None:
                    histogram[idx] = macd_line[idx] - val

        return macd_line, signal_line, histogram

    def calc_bollinger_bands(self, prices: List[float],
                             period: int = 20,
                             std_dev: float = 2.0) -> Tuple[List, List, List]:
        """
        볼린저밴드 계산
        Returns: (upper_band, middle_band, lower_band)
        """
        middle = self.calc_sma(prices, period)
        upper = [None] * len(prices)
        lower = [None] * len(prices)

        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            mean = middle[i]
            if mean is not None:
                variance = sum((x - mean) ** 2 for x in window) / period
                std = math.sqrt(variance)
                upper[i] = mean + std_dev * std
                lower[i] = mean - std_dev * std

        return upper, middle, lower

    def calc_stochastic(self, highs: List[float], lows: List[float],
                        closes: List[float], k_period: int = 14,
                        d_period: int = 3) -> Tuple[List, List]:
        """스토캐스틱 %K, %D"""
        k_values = [None] * len(closes)

        for i in range(k_period - 1, len(closes)):
            high_max = max(highs[i - k_period + 1:i + 1])
            low_min = min(lows[i - k_period + 1:i + 1])
            if high_max != low_min:
                k_values[i] = (closes[i] - low_min) / (high_max - low_min) * 100
            else:
                k_values[i] = 50.0

        # %D = %K의 SMA
        k_valid = [v for v in k_values if v is not None]
        d_raw = self.calc_sma(k_valid, d_period)
        d_values = [None] * len(closes)
        k_start = next((i for i, v in enumerate(k_values) if v is not None), len(closes))
        for j, val in enumerate(d_raw):
            idx = k_start + j
            if idx < len(closes):
                d_values[idx] = val

        return k_values, d_values

    # --------------------------------------------------
    # 종합 매매 신호 생성
    # --------------------------------------------------
    def generate_signal(self, stock_code: str, stock_name: str,
                        daily_prices: List[Dict],
                        fundamental_score: float = 50.0,
                        commodity_score: float = 50.0,
                        news_score: float = 0.0) -> TradeSignal:
        """
        모든 지표를 종합하여 매매 신호 생성
        daily_prices: [{date, open, high, low, close, volume}, ...] (최신순)
        """
        if len(daily_prices) < 30:
            return TradeSignal(
                code=stock_code, name=stock_name,
                signal=Signal.HOLD, confidence=0,
                price=daily_prices[0]["close"] if daily_prices else 0,
                target_price=0, stop_loss_price=0,
                reasons=["데이터 부족 (최소 30일 필요)"],
                indicators={},
            )

        # 시간순 정렬 (오래된 → 최신)
        prices_asc = list(reversed(daily_prices))
        closes = [d["close"] for d in prices_asc]
        highs = [d["high"] for d in prices_asc]
        lows = [d["low"] for d in prices_asc]
        volumes = [d["volume"] for d in prices_asc]
        current_price = closes[-1]

        # 지표 계산
        rsi_values = self.calc_rsi(closes)
        macd_line, signal_line, histogram = self.calc_macd(closes)
        upper_bb, middle_bb, lower_bb = self.calc_bollinger_bands(closes)
        stoch_k, stoch_d = self.calc_stochastic(highs, lows, closes)
        sma_5 = self.calc_sma(closes, 5)
        sma_20 = self.calc_sma(closes, 20)
        sma_60 = self.calc_sma(closes, 60)

        # 현재 지표값
        rsi = rsi_values[-1]
        macd = macd_line[-1]
        macd_sig = signal_line[-1]
        macd_hist = histogram[-1]
        bb_upper = upper_bb[-1]
        bb_lower = lower_bb[-1]
        bb_mid = middle_bb[-1]
        sk = stoch_k[-1]
        sd = stoch_d[-1]

        # 점수 시스템 (-100 ~ +100)
        tech_score = 0.0
        reasons = []

        # --- RSI 분석 ---
        if rsi is not None:
            if rsi < self.config.rsi_oversold:
                tech_score += 25
                reasons.append(f"RSI 과매도 ({rsi:.1f}) → 반등 기대")
            elif rsi < 40:
                tech_score += 10
                reasons.append(f"RSI 저점권 ({rsi:.1f})")
            elif rsi > self.config.rsi_overbought:
                tech_score -= 25
                reasons.append(f"RSI 과매수 ({rsi:.1f}) → 조정 가능")
            elif rsi > 60:
                tech_score -= 5

        # --- MACD 분석 ---
        if macd is not None and macd_sig is not None:
            if macd > macd_sig and macd_hist is not None and macd_hist > 0:
                # 골든크로스 or 상승 추세
                if histogram[-2] is not None and histogram[-2] <= 0:
                    tech_score += 30
                    reasons.append("MACD 골든크로스 발생 → 강한 매수 시그널")
                else:
                    tech_score += 15
                    reasons.append("MACD 상승 추세 지속")
            elif macd < macd_sig and macd_hist is not None and macd_hist < 0:
                if histogram[-2] is not None and histogram[-2] >= 0:
                    tech_score -= 30
                    reasons.append("MACD 데드크로스 발생 → 매도 시그널")
                else:
                    tech_score -= 15
                    reasons.append("MACD 하락 추세")

        # --- 볼린저밴드 분석 ---
        if bb_lower is not None and bb_upper is not None:
            if current_price <= bb_lower:
                tech_score += 20
                reasons.append("볼린저밴드 하단 이탈 → 반등 기대")
            elif current_price >= bb_upper:
                tech_score -= 20
                reasons.append("볼린저밴드 상단 돌파 → 과열 주의")
            elif bb_mid and current_price > bb_mid:
                tech_score += 5

        # --- 이동평균선 분석 ---
        if sma_5[-1] and sma_20[-1]:
            if sma_5[-1] > sma_20[-1]:
                tech_score += 10
                if sma_5[-2] and sma_20[-2] and sma_5[-2] <= sma_20[-2]:
                    tech_score += 15
                    reasons.append("5일선 20일선 골든크로스")
            else:
                tech_score -= 10

        if sma_60[-1]:
            if current_price > sma_60[-1]:
                tech_score += 5
                reasons.append("60일선 위 → 중기 상승 추세")
            else:
                tech_score -= 5

        # --- 거래량 분석 ---
        if len(volumes) >= 20:
            avg_vol_20 = sum(volumes[-20:]) / 20
            current_vol = volumes[-1]
            if avg_vol_20 > 0:
                vol_ratio = current_vol / avg_vol_20
                if vol_ratio > 3.0 and closes[-1] > closes[-2]:
                    tech_score += 20
                    reasons.append(f"거래량 {vol_ratio:.1f}배 폭증 + 가격 상승 → 수급 유입")
                elif vol_ratio > 2.0:
                    tech_score += 10
                    reasons.append(f"거래량 {vol_ratio:.1f}배 증가")

        # --- 스토캐스틱 분석 ---
        if sk is not None and sd is not None:
            if sk < 20 and sd < 20:
                tech_score += 10
                reasons.append("스토캐스틱 과매도 구간")
            elif sk > 80 and sd > 80:
                tech_score -= 10

        # ==================================================
        # 종합 점수 (기술 + 펀더멘털 + 원자재 + 뉴스)
        # ==================================================
        # tech_score 클램핑 후 0 ~ 100 스케일로 변환
        tech_score = max(-100, min(100, tech_score))
        tech_normalized = (tech_score + 100) / 2

        final_score = (
            tech_normalized * self.config.technical_weight +
            fundamental_score * self.config.fundamental_weight +
            commodity_score * self.config.commodity_weight +
            ((news_score + 100) / 2) * self.config.news_weight
        )

        # 신호 결정
        if final_score >= 75:
            signal = Signal.STRONG_BUY
        elif final_score >= 60:
            signal = Signal.BUY
        elif final_score >= 40:
            signal = Signal.HOLD
        elif final_score >= 25:
            signal = Signal.SELL
        else:
            signal = Signal.STRONG_SELL

        # 목표가 / 손절가 계산
        if signal in (Signal.STRONG_BUY, Signal.BUY):
            target_price = int(current_price * (1 + self.config.take_profit_pct))
            stop_loss = int(current_price * (1 + self.config.stop_loss_pct))
        else:
            target_price = int(current_price * 0.95)  # 보수적 목표
            stop_loss = int(current_price * (1 + self.config.stop_loss_pct))

        confidence = min(100, abs(final_score - 50) * 2)

        indicators = {
            "RSI": round(rsi, 1) if rsi else 0,
            "MACD": round(macd, 2) if macd else 0,
            "MACD_Signal": round(macd_sig, 2) if macd_sig else 0,
            "BB_Upper": round(bb_upper, 0) if bb_upper else 0,
            "BB_Lower": round(bb_lower, 0) if bb_lower else 0,
            "SMA_5": round(sma_5[-1], 0) if sma_5[-1] else 0,
            "SMA_20": round(sma_20[-1], 0) if sma_20[-1] else 0,
            "SMA_60": round(sma_60[-1], 0) if sma_60[-1] else 0,
            "Stoch_K": round(sk, 1) if sk else 0,
            "종합점수": round(final_score, 1),
            "기술점수": round(tech_normalized, 1),
            "펀더멘털점수": round(fundamental_score, 1),
            "원자재점수": round(commodity_score, 1),
            "뉴스점수": round(news_score, 1),
        }

        return TradeSignal(
            code=stock_code,
            name=stock_name,
            signal=signal,
            confidence=round(confidence, 1),
            price=current_price,
            target_price=target_price,
            stop_loss_price=stop_loss,
            reasons=reasons,
            indicators=indicators,
        )

    def get_technical_score(self, daily_prices: List[Dict]) -> float:
        """기술적 분석 점수만 반환 (스크리너용) 0~100"""
        if len(daily_prices) < 30:
            return 50.0

        prices_asc = list(reversed(daily_prices))
        closes = [d["close"] for d in prices_asc]

        score = 50.0
        rsi = self.calc_rsi(closes)[-1]
        if rsi and rsi < 30:
            score += 20
        elif rsi and rsi > 70:
            score -= 20

        macd_line, signal_line, _ = self.calc_macd(closes)
        if macd_line[-1] and signal_line[-1]:
            if macd_line[-1] > signal_line[-1]:
                score += 15
            else:
                score -= 15

        sma5 = self.calc_sma(closes, 5)
        sma20 = self.calc_sma(closes, 20)
        if sma5[-1] and sma20[-1] and sma5[-1] > sma20[-1]:
            score += 10

        return max(0, min(100, score))
