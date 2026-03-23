"""
========================================
포트폴리오 및 리스크 관리 모듈
========================================
포지션 사이징, 손절/익절 관리, 일일 리스크 한도
"""

import json
import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import STRATEGY


@dataclass
class Position:
    """보유 포지션"""
    code: str
    name: str
    qty: int
    avg_price: float
    current_price: float
    entry_date: str
    highest_price: float        # 진입 후 최고가 (트레일링 스탑용)
    signal_score: float         # 진입 시 신호 점수
    stop_loss: float            # 손절가
    take_profit: float          # 익절가

    @property
    def profit_pct(self) -> float:
        if self.avg_price <= 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price * 100

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def profit_amount(self) -> float:
        return self.qty * (self.current_price - self.avg_price)


@dataclass
class TradeLog:
    """매매 기록"""
    timestamp: str
    code: str
    name: str
    side: str               # "BUY" or "SELL"
    qty: int
    price: int
    reason: str
    signal_score: float
    profit_pct: Optional[float] = None  # 매도 시에만


@dataclass
class DecisionLog:
    """매매 판단 근거 기록"""
    timestamp: str
    code: str
    name: str
    signal: str                 # "강력매수", "매수", "보유", "매도", "강력매도"
    final_score: float
    confidence: float
    # 4가지 서브 점수
    technical_score: float
    fundamental_score: float
    commodity_score: float
    news_score: float
    # 핵심 지표
    indicators: Dict[str, float]
    # 판단 근거 + 리스크
    reasons: List[str]
    risk_flags: List[str]
    # 결과
    action: str                 # "BUY", "SELL", "SKIP"
    action_detail: str = ""     # 매수/매도/스킵 사유
    # Claude 판단 (사용 시)
    claude_decision: Optional[str] = None       # "BUY"/"SELL"/"HOLD"
    claude_reasoning: Optional[str] = None      # Claude 판단 근거
    claude_confidence: Optional[float] = None   # Claude 신뢰도


class PortfolioManager:
    """포트폴리오 & 리스크 관리"""

    def __init__(self, initial_capital: int = None):
        self.config = STRATEGY
        self.initial_capital = initial_capital or self.config.initial_capital
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeLog] = []
        self.decision_history: List[DecisionLog] = []
        self.daily_loss_limit = self.initial_capital * 0.10  # 일일 최대 손실 10%
        self.daily_loss = 0.0
        self._data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        self.log_file = os.path.join(self._data_dir, "trades.json")
        self.decision_log_file = os.path.join(self._data_dir, "decisions.jsonl")

    # --------------------------------------------------
    # 포지션 사이징
    # --------------------------------------------------
    def calculate_position_size(self, price: int, signal_confidence: float) -> int:
        """
        신호 신뢰도 기반 포지션 크기 결정
        Returns: 매수 수량
        """
        total_value = self.get_total_value()

        # 포지션 수에 따른 최대 비율 조절
        num_positions = len(self.positions)
        if num_positions >= self.config.max_positions:
            return 0

        remaining_slots = self.config.max_positions - num_positions

        # 신뢰도가 높을수록 큰 포지션
        if signal_confidence >= 80:
            position_pct = self.config.max_position_pct
        elif signal_confidence >= 60:
            position_pct = (self.config.max_position_pct + self.config.min_position_pct) / 2
        else:
            position_pct = self.config.min_position_pct

        # 최대 투자 금액
        max_invest = total_value * position_pct
        # 현금 한도
        available = min(max_invest, self.cash * 0.95)  # 5% 현금 유지

        if available <= 0 or price <= 0:
            return 0

        qty = int(available / price)

        # 비율 한도 내 수량이 0이라도 현금으로 최소 1주 살 수 있으면 1주 매수
        if qty == 0 and self.cash * 0.95 >= price:
            qty = 1

        return max(0, qty)

    # --------------------------------------------------
    # 매수 / 매도 실행
    # --------------------------------------------------
    def execute_buy(self, code: str, name: str, price: int, qty: int,
                    signal_score: float, reason: str) -> bool:
        """매수 실행"""
        cost = price * qty
        if cost > self.cash:
            qty = int(self.cash / price)
            cost = price * qty
        if qty <= 0:
            return False

        self.cash -= cost

        if code in self.positions:
            # 추가 매수 (평균 단가 업데이트)
            pos = self.positions[code]
            total_qty = pos.qty + qty
            pos.avg_price = (pos.avg_price * pos.qty + price * qty) / total_qty
            pos.qty = total_qty
            pos.current_price = price
        else:
            self.positions[code] = Position(
                code=code,
                name=name,
                qty=qty,
                avg_price=price,
                current_price=price,
                entry_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                highest_price=price,
                signal_score=signal_score,
                stop_loss=int(price * (1 + self.config.stop_loss_pct)),
                take_profit=int(price * (1 + self.config.take_profit_pct)),
            )

        self._log_trade("BUY", code, name, qty, price, reason, signal_score)
        return True

    def execute_sell(self, code: str, price: int, qty: int = 0,
                     reason: str = "") -> bool:
        """매도 실행"""
        if code not in self.positions:
            return False

        pos = self.positions[code]
        sell_qty = qty if qty > 0 else pos.qty
        sell_qty = min(sell_qty, pos.qty)

        if sell_qty <= 0:
            return False

        proceeds = price * sell_qty
        self.cash += proceeds

        profit_pct = (price - pos.avg_price) / pos.avg_price * 100
        self._log_trade("SELL", code, pos.name, sell_qty, price, reason,
                        pos.signal_score, profit_pct)

        if sell_qty >= pos.qty:
            del self.positions[code]
        else:
            pos.qty -= sell_qty

        return True

    # --------------------------------------------------
    # 리스크 관리 체크
    # --------------------------------------------------
    def check_stop_conditions(self, code: str, current_price: int) -> Optional[str]:
        """
        손절/익절/트레일링스탑 체크
        Returns: 매도 사유 or None
        """
        if code not in self.positions:
            return None

        pos = self.positions[code]
        pos.current_price = current_price

        # 최고가 업데이트
        if current_price > pos.highest_price:
            pos.highest_price = current_price

        profit_pct = pos.profit_pct

        # 1) 손절
        if profit_pct <= self.config.stop_loss_pct * 100:
            return f"손절 ({profit_pct:.1f}% < {self.config.stop_loss_pct*100:.0f}%)"

        # 2) 익절
        if profit_pct >= self.config.take_profit_pct * 100:
            return f"익절 ({profit_pct:.1f}% > {self.config.take_profit_pct*100:.0f}%)"

        # 3) 트레일링 스탑
        if pos.highest_price > pos.avg_price:
            drawdown_from_high = (current_price - pos.highest_price) / pos.highest_price
            if drawdown_from_high <= -self.config.trailing_stop_pct:
                return (f"트레일링 스탑 (최고가 대비 "
                        f"{drawdown_from_high*100:.1f}%)")

        # 4) 장기 횡보 보유
        try:
            entry = datetime.datetime.strptime(pos.entry_date, "%Y-%m-%d %H:%M")
            days_held = (datetime.datetime.now() - entry).days
            if (days_held >= self.config.max_holding_days
                    and abs(profit_pct) < self.config.sideways_threshold_pct):
                return (f"장기 횡보 ({days_held}일 보유, "
                        f"수익률 {profit_pct:+.1f}%)")
        except (ValueError, AttributeError):
            pass

        return None

    def get_worst_losing_position(self) -> Optional[str]:
        """가장 큰 손실 포지션 코드 반환 (일일 손실한도 초과 시 정리용)"""
        losers = {code: pos for code, pos in self.positions.items()
                  if pos.profit_amount < 0}
        if not losers:
            return None
        return min(losers, key=lambda c: losers[c].profit_amount)

    def check_daily_risk(self) -> bool:
        """일일 손실 한도 체크 (True면 거래 가능)"""
        total_unrealized = sum(
            min(0, p.profit_amount) for p in self.positions.values()
        )
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        today_realized_loss = sum(
            (t.price - t.price / (1 + (t.profit_pct or 0) / 100)) * t.qty
            for t in self.trade_history
            if t.side == "SELL"
            and t.timestamp.startswith(today_str)
            and (t.profit_pct or 0) < 0
        )
        total_loss = abs(total_unrealized) + abs(today_realized_loss)
        return total_loss < self.daily_loss_limit

    # --------------------------------------------------
    # 포트폴리오 상태
    # --------------------------------------------------
    def get_total_value(self) -> float:
        """총 평가금액"""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """포트폴리오 현황"""
        total = self.get_total_value()
        total_profit = total - self.initial_capital
        total_profit_pct = total_profit / self.initial_capital * 100

        positions_info = []
        for code, pos in self.positions.items():
            positions_info.append({
                "종목코드": pos.code,
                "종목명": pos.name,
                "보유수량": pos.qty,
                "평균단가": f"{pos.avg_price:,.0f}",
                "현재가": f"{pos.current_price:,.0f}",
                "수익률": f"{pos.profit_pct:+.1f}%",
                "평가손익": f"{pos.profit_amount:+,.0f}원",
                "비중": f"{pos.market_value / total * 100:.1f}%",
            })

        return {
            "초기자본": f"{self.initial_capital:,}원",
            "총평가금액": f"{total:,.0f}원",
            "총손익": f"{total_profit:+,.0f}원",
            "총수익률": f"{total_profit_pct:+.1f}%",
            "현금": f"{self.cash:,.0f}원",
            "현금비율": f"{self.cash / total * 100:.1f}%",
            "보유종목수": len(self.positions),
            "보유종목": positions_info,
            "목표달성률": f"{total / self.config.target_capital * 100:.1f}%",
        }

    # --------------------------------------------------
    # 거래 기록
    # --------------------------------------------------
    def _log_trade(self, side: str, code: str, name: str, qty: int,
                   price: int, reason: str, signal_score: float,
                   profit_pct: float = None):
        """거래 기록 저장"""
        log = TradeLog(
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            code=code, name=name, side=side, qty=qty,
            price=price, reason=reason, signal_score=signal_score,
            profit_pct=profit_pct,
        )
        self.trade_history.append(log)
        self._save_history()

    def _save_history(self):
        """거래 기록 파일 저장"""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            records = []
            for t in self.trade_history:
                records.append({
                    "timestamp": t.timestamp,
                    "code": t.code,
                    "name": t.name,
                    "side": t.side,
                    "qty": t.qty,
                    "price": t.price,
                    "reason": t.reason,
                    "signal_score": t.signal_score,
                    "profit_pct": t.profit_pct,
                })
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[거래기록 저장 오류] {e}")

    def save_decision_log(self, decision: DecisionLog):
        """매매 판단 근거를 JSONL로 저장"""
        self.decision_history.append(decision)
        try:
            os.makedirs(os.path.dirname(self.decision_log_file), exist_ok=True)
            record = {
                "timestamp": decision.timestamp,
                "code": decision.code,
                "name": decision.name,
                "signal": decision.signal,
                "final_score": decision.final_score,
                "confidence": decision.confidence,
                "scores": {
                    "technical": decision.technical_score,
                    "fundamental": decision.fundamental_score,
                    "commodity": decision.commodity_score,
                    "news": decision.news_score,
                },
                "indicators": decision.indicators,
                "reasons": decision.reasons,
                "risk_flags": decision.risk_flags,
                "action": decision.action,
                "action_detail": decision.action_detail,
                "claude_decision": decision.claude_decision,
                "claude_reasoning": decision.claude_reasoning,
                "claude_confidence": decision.claude_confidence,
            }
            with open(self.decision_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[결정로그 저장 오류] {e}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """매매 성과 통계"""
        sells = [t for t in self.trade_history if t.side == "SELL"]
        if not sells:
            return {"총매매횟수": 0, "승률": "N/A"}

        wins = [t for t in sells if (t.profit_pct or 0) > 0]
        losses = [t for t in sells if (t.profit_pct or 0) < 0]

        avg_win = sum(t.profit_pct for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.profit_pct for t in losses) / len(losses) if losses else 0

        return {
            "총매매횟수": len(sells),
            "승률": f"{len(wins) / len(sells) * 100:.1f}%",
            "평균수익": f"{avg_win:+.1f}%",
            "평균손실": f"{avg_loss:+.1f}%",
            "손익비": f"{abs(avg_win / avg_loss):.2f}" if avg_loss else "N/A",
            "최대수익": f"{max((t.profit_pct or 0) for t in sells):+.1f}%",
            "최대손실": f"{min((t.profit_pct or 0) for t in sells):+.1f}%",
        }
