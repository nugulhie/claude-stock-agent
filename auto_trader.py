"""
========================================
자동매매 엔진 + 스케줄러
========================================
신호생성기 기반으로 장중 자동 매매 실행
- 장 시작 전: 시장 분석 & 매수 후보 선정
- 장중 (10분 간격): 보유 종목 모니터링 + 손절/익절 체크
- 장중 (30분 간격): 신규 매수 기회 탐색
- 장 마감 후: 일일 리포트 생성
"""

import os
import time
import json
import logging
import datetime
import schedule
from typing import List, Dict, Optional

from modules.kis_api import KISApi
from modules.screener import StockScreener
from modules.market_data import MarketDataCollector
from modules.technical import TechnicalAnalyzer, Signal
from modules.portfolio import PortfolioManager, DecisionLog
from config import STRATEGY, SECTORS

try:
    from modules.claude_client import ClaudeClient
except Exception:
    ClaudeClient = None

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/auto_trader.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("AutoTrader")


class AutoTrader:
    """
    신호생성기 기반 자동매매 엔진
    ─────────────────────────────
    매매 판단 흐름:
    1. 거래량 상위 + 원자재 관련주 + 관심 종목에서 후보군 추출
    2. 각 후보에 대해:
       - 재무제표 분석 (PER, PBR, ROE, 부채비율)
       - 기술적 분석 (RSI, MACD, 볼린저밴드, 이평선)
       - 원자재 연동 분석
       - 뉴스 감성 분석
    3. 종합 점수 60점 이상 → 매수 시그널 → 자동 매수
    4. 보유 종목 실시간 모니터링:
       - 손절 (-5%), 익절 (+15%), 트레일링 스탑 (최고가 -7%) → 자동 매도
    """

    def __init__(self, paper_trading: bool = True):
        """
        paper_trading=True: 모의투자 (실제 주문 X, 시뮬레이션)
        paper_trading=False: 실전투자 (실제 주문 실행)
        """
        self.paper_trading = paper_trading
        self.kis = KISApi()
        self.screener = StockScreener(self.kis)
        self.market = MarketDataCollector()
        self.tech = TechnicalAnalyzer()
        self.portfolio = PortfolioManager()

        self.watchlist: List[str] = []
        self.is_market_open = False
        self._current_overview: Dict = {}  # 장전 분석 시 캐시
        self.claude = None
        try:
            if ClaudeClient and STRATEGY.use_claude_decision:
                self.claude = ClaudeClient()
                log.info("Claude AI 연동 활성화")
        except Exception as e:
            log.warning(f"Claude 초기화 실패 (기계적 판단만 사용): {e}")
        self._build_watchlist()

        log.info("=" * 60)
        log.info(f"자동매매 엔진 초기화 완료")
        log.info(f"  모드: {'모의투자' if paper_trading else '⚠️ 실전투자'}")
        log.info(f"  자본금: {STRATEGY.initial_capital:,}원")
        log.info(f"  목표: {STRATEGY.target_capital:,}원")
        log.info(f"  손절: {STRATEGY.stop_loss_pct*100:.0f}% / 익절: {STRATEGY.take_profit_pct*100:.0f}%")
        log.info("=" * 60)

    def _build_watchlist(self):
        """관심 종목 리스트 구성"""
        # 원자재 관련주 추가
        for sector, codes in SECTORS.commodity_stocks.items():
            self.watchlist.extend(codes)
        # 중복 제거
        self.watchlist = list(set(self.watchlist))
        log.info(f"관심 종목 {len(self.watchlist)}개 등록")

    # ==================================================
    # 핵심 매매 로직
    # ==================================================

    def pre_market_analysis(self):
        """
        [08:30] 장 시작 전 분석
        - 원자재/환율 동향 파악
        - 거래량 급등 후보 탐색
        - 매수 후보 리스트 확정
        """
        log.info("━" * 50)
        log.info("📊 장 시작 전 분석 시작")

        # 1. 시장 개요 (Claude 해석 포함)
        overview = self.market.get_market_overview()
        self._current_overview = overview
        log.info(f"시장 분위기: {overview.get('market_sentiment', '중립')}")

        # Claude 시장 해석 로그
        claude_data = overview.get("claude_analysis", {})
        if claude_data.get("summary"):
            log.info(f"  [Claude] {claude_data['summary']}")
            for insight in claude_data.get("insights", []):
                log.info(f"    - {insight}")

        for rate_name, rate_info in overview.get("exchange_rates", {}).items():
            log.info(f"  {rate_name}: {rate_info['rate']:,.2f} ({rate_info['change_pct']:+.2f}%)")

        for comm in overview.get("commodities", []):
            log.info(f"  {comm['name']}: ${comm['price']:,.2f} ({comm['change_pct']:+.2f}%) {comm['trend']}")

        # 2. 원자재 변동 데이터
        commodity_changes = self.market.get_commodity_changes()

        # 3. 거래량 상위 종목 추가 탐색
        try:
            volume_leaders = self.kis.get_volume_rank(limit=20)
            for stock in volume_leaders:
                if stock["code"] not in self.watchlist:
                    self.watchlist.append(stock["code"])
            log.info(f"거래량 상위 {len(volume_leaders)}개 종목 추가 → 전체 {len(self.watchlist)}개")
        except Exception as e:
            log.warning(f"거래량 조회 실패: {e}")

        # 4. 각 후보 분석 (상위 스코어 추출)
        candidates = []
        for code in self.watchlist[:50]:  # 최대 50개 분석
            try:
                signal = self._analyze_stock(code, commodity_changes)
                if signal and signal.signal in (Signal.STRONG_BUY, Signal.BUY):
                    candidates.append(signal)
                    log.info(
                        f"  ✅ {signal.name}({signal.code}) "
                        f"[{signal.signal.value}] 점수:{signal.confidence:.0f} "
                        f"목표가:{signal.target_price:,}"
                    )
                time.sleep(0.2)  # API 호출 제한 대응
            except Exception as e:
                log.debug(f"  {code} 분석 오류: {e}")

        # 점수순 정렬
        candidates.sort(key=lambda s: s.confidence, reverse=True)

        log.info(f"매수 후보 {len(candidates)}개 확인됨")
        log.info("━" * 50)
        return candidates

    def monitor_positions(self):
        """
        [장중 10분마다] 보유 종목 손절/익절/장기보유/신호악화 체크
        """
        if not self.portfolio.positions:
            return

        log.info("🔍 보유 종목 모니터링...")

        for code in list(self.portfolio.positions.keys()):
            try:
                price_data = self.kis.get_current_price(code)
                current_price = price_data["price"]

                # 1) 가격 기반 탈출 (손절/익절/트레일링/장기횡보)
                sell_reason = self.portfolio.check_stop_conditions(code, current_price)
                if sell_reason:
                    log.warning(f"  🔴 {code} 매도 시그널: {sell_reason}")
                    self._execute_sell(code, current_price, sell_reason)
                else:
                    pos = self.portfolio.positions[code]
                    log.info(
                        f"  {pos.name}({code}): {current_price:,}원 "
                        f"({pos.profit_pct:+.1f}%)"
                    )
                time.sleep(0.1)
            except Exception as e:
                log.error(f"  {code} 모니터링 오류: {e}")

        # 2) 일일 손실한도 초과 시 최대 손실 포지션 정리
        if (not self.portfolio.check_daily_risk()
                and STRATEGY.daily_loss_close_positions):
            worst = self.portfolio.get_worst_losing_position()
            if worst and worst in self.portfolio.positions:
                try:
                    price_data = self.kis.get_current_price(worst)
                    reason = "일일 손실한도 초과 → 최대 손실 포지션 정리"
                    log.warning(f"  ⚠️ {worst} 강제 매도: {reason}")
                    self._execute_sell(worst, price_data["price"], reason)
                except Exception as e:
                    log.error(f"  {worst} 강제 매도 실패: {e}")

    def scan_buy_opportunities(self):
        """
        [장중 30분마다] 신규 매수 기회 탐색
        """
        if len(self.portfolio.positions) >= STRATEGY.max_positions:
            log.info("최대 보유 종목 수 도달 - 매수 스킵")
            return

        if not self.portfolio.check_daily_risk():
            log.warning("⚠️ 일일 손실 한도 도달 - 매수 중지")
            return

        log.info("🔎 매수 기회 탐색 중...")
        commodity_changes = self.market.get_commodity_changes()

        # 거래량 상위에서 탐색
        try:
            volume_leaders = self.kis.get_volume_rank(limit=15)
        except Exception:
            volume_leaders = []

        for stock in volume_leaders:
            code = stock["code"]
            if code in self.portfolio.positions:
                continue  # 이미 보유 중

            try:
                signal = self._analyze_stock(code, commodity_changes)
                if signal and signal.signal == Signal.STRONG_BUY and signal.confidence >= 70:
                    log.info(f"  💰 강력매수 시그널: {signal.name} (신뢰도 {signal.confidence:.0f})")
                    self._execute_buy(signal)
                time.sleep(0.2)
            except Exception as e:
                log.debug(f"  {code} 분석 실패: {e}")

    def reeval_positions(self):
        """
        [장중 1시간마다] 보유 종목 재분석 → 신호 악화 시 매도
        """
        if not self.portfolio.positions:
            return

        log.info("🔄 보유 종목 신호 재평가...")
        commodity_changes = self.market.get_commodity_changes()

        for code in list(self.portfolio.positions.keys()):
            try:
                signal = self._analyze_stock(code, commodity_changes, log_action="REEVAL")
                if not signal:
                    continue

                score = signal.indicators.get("종합점수", 50)
                if score <= STRATEGY.signal_exit_score:
                    reason = (f"신호 악화 매도 (종합 {score:.0f}점 "
                              f"< 기준 {STRATEGY.signal_exit_score:.0f}점)")
                    log.warning(f"  🔴 {signal.name}({code}): {reason}")
                    self._execute_sell(code, signal.price, reason)
                else:
                    log.info(f"  {signal.name}({code}): 종합 {score:.0f}점 → 유지")
                time.sleep(0.3)
            except Exception as e:
                log.error(f"  {code} 재평가 오류: {e}")

    def post_market_review(self):
        """
        [15:40] 장 마감 후 일일 리포트
        """
        log.info("=" * 60)
        log.info("📋 일일 리포트")
        log.info("=" * 60)

        summary = self.portfolio.get_portfolio_summary()
        for key, value in summary.items():
            if key == "보유종목":
                log.info(f"\n{'─'*40}")
                for pos in value:
                    log.info(f"  {pos['종목명']} | {pos['현재가']}원 | "
                             f"{pos['수익률']} | 비중 {pos['비중']}")
                log.info(f"{'─'*40}")
            else:
                log.info(f"  {key}: {value}")

        stats = self.portfolio.get_performance_stats()
        log.info("\n📈 매매 성과:")
        for key, value in stats.items():
            log.info(f"  {key}: {value}")

        log.info("=" * 60)

    # ==================================================
    # 내부 헬퍼
    # ==================================================

    def _analyze_stock(self, code: str, commodity_changes: Dict,
                       log_action: str = "SKIP") -> Optional[object]:
        """단일 종목 종합 분석 + 결정 근거 로그 저장"""
        # 현재가
        price_data = self.kis.get_current_price(code)
        if price_data["price"] == 0:
            return None

        # 일봉 데이터
        daily = self.kis.get_daily_prices(code, count=60)
        if len(daily) < 30:
            return None

        # 재무 데이터
        try:
            financial = self.kis.get_financial_data(code)
        except Exception:
            financial = {}

        # 기술적 점수
        tech_score = self.tech.get_technical_score(daily)

        # 스크리너 종합 점수
        stock_score = self.screener.comprehensive_screen(
            stock_code=code,
            stock_name=price_data.get("name", code),
            price_data=price_data,
            financial_data=financial,
            daily_prices=daily,
            commodity_changes=commodity_changes,
            technical_score=tech_score,
        )

        # 뉴스 감성
        news_score, news_reasons = self.market.get_news_sentiment_score(code)

        # 최종 신호 생성
        signal = self.tech.generate_signal(
            stock_code=code,
            stock_name=stock_score.name or code,
            daily_prices=daily,
            fundamental_score=stock_score.fundamental_score,
            commodity_score=stock_score.commodity_score,
            news_score=news_score,
        )

        # Claude 최종 판단
        claude_result = None
        if self.claude and STRATEGY.use_claude_decision:
            try:
                total_value = self.portfolio.get_total_value()
                cash_pct = (self.portfolio.cash / total_value * 100) if total_value > 0 else 100
                claude_data = {
                    "stock": {"code": code, "name": signal.name,
                              "price": signal.price,
                              "change_pct": price_data.get("change_pct", 0)},
                    "indicators": signal.indicators,
                    "fundamental_score": stock_score.fundamental_score,
                    "commodity_score": stock_score.commodity_score,
                    "news_score": news_score,
                    "news_reasons": news_reasons,
                    "mechanical_signal": signal.signal.value,
                    "mechanical_confidence": signal.confidence,
                    "reasons": signal.reasons + stock_score.reasons,
                    "risk_flags": stock_score.risk_flags,
                    "market_overview": self._current_overview.get("claude_analysis", {}),
                    "portfolio": {
                        "positions": len(self.portfolio.positions),
                        "cash_pct": cash_pct,
                        "daily_return_pct": 0,
                    },
                }
                claude_result = self.claude.make_trading_decision(claude_data)
                if claude_result:
                    cd = claude_result["decision"]
                    cc = claude_result["confidence"]
                    # Claude 판단으로 신호 오버라이드
                    if cd == "BUY" and cc >= 60:
                        signal.signal = Signal.STRONG_BUY if cc >= 80 else Signal.BUY
                        signal.confidence = cc
                    elif cd == "SELL":
                        signal.signal = Signal.SELL if cc < 80 else Signal.STRONG_SELL
                        signal.confidence = cc
                    elif cd == "HOLD":
                        signal.signal = Signal.HOLD
                        signal.confidence = cc
                    # Claude 근거 추가
                    if claude_result.get("reasoning"):
                        signal.reasons.insert(0, f"[Claude] {claude_result['reasoning']}")
                    # Claude 목표가/손절가 반영
                    if cd == "BUY" and claude_result.get("target_price"):
                        signal.target_price = claude_result["target_price"]
                    if cd == "BUY" and claude_result.get("stop_loss_price"):
                        signal.stop_loss_price = claude_result["stop_loss_price"]
                    log.info(f"  [Claude] {signal.name}: {cd} (신뢰도 {cc}%)")
            except Exception as e:
                log.warning(f"  [Claude] {code} 판단 실패 → 기계적 판단 유지: {e}")

        # 결정 근거 로그 저장
        decision = DecisionLog(
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            code=code,
            name=signal.name,
            signal=signal.signal.value,
            final_score=signal.indicators.get("종합점수", 0),
            confidence=signal.confidence,
            technical_score=signal.indicators.get("기술점수", 0),
            fundamental_score=stock_score.fundamental_score,
            commodity_score=stock_score.commodity_score,
            news_score=news_score,
            indicators=signal.indicators,
            reasons=signal.reasons + stock_score.reasons,
            risk_flags=stock_score.risk_flags,
            action=log_action,
            action_detail="",
            claude_decision=claude_result.get("decision") if claude_result else None,
            claude_reasoning=claude_result.get("reasoning") if claude_result else None,
            claude_confidence=claude_result.get("confidence") if claude_result else None,
        )
        self.portfolio.save_decision_log(decision)

        return signal

    def _execute_buy(self, signal):
        """매수 실행"""
        qty = self.portfolio.calculate_position_size(signal.price, signal.confidence)
        if qty <= 0:
            log.info(f"  매수 불가 (자금 부족 또는 포지션 한도)")
            return

        if self.paper_trading:
            # 모의투자: 포트폴리오에만 반영
            success = self.portfolio.execute_buy(
                code=signal.code,
                name=signal.name,
                price=signal.price,
                qty=qty,
                signal_score=signal.confidence,
                reason="; ".join(signal.reasons[:3]),
            )
            if success:
                log.info(f"  📗 [모의] 매수 {signal.name} {qty}주 @ {signal.price:,}원")
        else:
            # 실전: KIS API로 주문
            try:
                result = self.kis.place_order(signal.code, qty, side="buy")
                self.portfolio.execute_buy(
                    code=signal.code, name=signal.name,
                    price=signal.price, qty=qty,
                    signal_score=signal.confidence,
                    reason="; ".join(signal.reasons[:3]),
                )
                log.info(f"  📗 [실전] 매수 {signal.name} {qty}주 @ {signal.price:,}원")
            except Exception as e:
                log.error(f"  매수 주문 실패: {e}")

    def _execute_sell(self, code: str, price: int, reason: str):
        """매도 실행"""
        pos = self.portfolio.positions.get(code)
        if not pos:
            return

        if self.paper_trading:
            success = self.portfolio.execute_sell(code, price, reason=reason)
            if success:
                log.info(f"  📕 [모의] 매도 {pos.name} {pos.qty}주 @ {price:,}원 ({reason})")
        else:
            try:
                result = self.kis.place_order(code, pos.qty, side="sell")
                self.portfolio.execute_sell(code, price, reason=reason)
                log.info(f"  📕 [실전] 매도 {pos.name} {pos.qty}주 @ {price:,}원 ({reason})")
            except Exception as e:
                log.error(f"  매도 주문 실패: {e}")


# ==================================================
# 스케줄러
# ==================================================

def run_scheduler(paper_trading: bool = True):
    """
    자동매매 스케줄러 실행
    ──────────────────────
    - 08:30 장 시작 전 분석
    - 09:05 매수 후보 자동 매수
    - 09:10~15:20 (10분 간격) 보유종목 모니터링
    - 09:30~15:00 (30분 간격) 신규 매수 기회 탐색
    - 15:40 일일 리포트
    """
    os.makedirs("data", exist_ok=True)

    trader = AutoTrader(paper_trading=paper_trading)
    log.info("🚀 자동매매 스케줄러 시작")

    def morning_analysis():
        """장 시작 전 분석 + 초기 매수"""
        candidates = trader.pre_market_analysis()
        # 상위 3개 자동 매수
        for signal in candidates[:3]:
            if len(trader.portfolio.positions) < STRATEGY.max_positions:
                trader._execute_buy(signal)

    # 스케줄 등록
    schedule.every().day.at("08:30").do(morning_analysis)

    # 보유종목 모니터링 (10분 간격, 09:10 ~ 15:20)
    for hour in range(9, 16):
        for minute in [0, 10, 20, 30, 40, 50]:
            if hour == 9 and minute < 10:
                continue
            if hour == 15 and minute > 20:
                continue
            t = f"{hour:02d}:{minute:02d}"
            schedule.every().day.at(t).do(trader.monitor_positions)

    # 매수 기회 탐색 (30분 간격, 09:30 ~ 15:00)
    for hour in range(9, 15):
        for minute in [0, 30]:
            if hour == 9 and minute < 30:
                continue
            t = f"{hour:02d}:{minute:02d}"
            schedule.every().day.at(t).do(trader.scan_buy_opportunities)

    # 보유종목 신호 재평가 (1시간 간격, 10:00 ~ 14:00)
    for hour in range(10, 15):
        schedule.every().day.at(f"{hour:02d}:00").do(trader.reeval_positions)

    # 장 마감 리포트
    schedule.every().day.at("15:40").do(trader.post_market_review)

    log.info("📅 스케줄 등록 완료:")
    log.info("  08:30 - 장 시작 전 분석 + 매수")
    log.info("  09:10~15:20 (10분) - 보유종목 모니터링 (손절/익절/트레일링/횡보)")
    log.info("  09:30~15:00 (30분) - 매수 기회 탐색")
    log.info("  10:00~14:00 (1시간) - 보유종목 신호 재평가")
    log.info("  15:40 - 일일 리포트")
    log.info("")
    log.info("Ctrl+C 로 종료")

    # 메인 루프
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            log.info("\n🛑 자동매매 종료")
            trader.post_market_review()
            break
        except Exception as e:
            log.error(f"스케줄러 오류: {e}")
            time.sleep(10)


if __name__ == "__main__":
    import argparse
    os.makedirs("data", exist_ok=True)
    parser = argparse.ArgumentParser(description="한국 주식 자동매매")
    parser.add_argument("--live", action="store_true", help="실전투자 모드 (기본: 모의투자)")
    parser.add_argument("--once", action="store_true", help="1회 분석만 실행")
    args = parser.parse_args()

    if args.once:
        trader = AutoTrader(paper_trading=not args.live)
        candidates = trader.pre_market_analysis()
        for signal in candidates[:5]:
            print(f"\n{'='*50}")
            print(f"종목: {signal.name} ({signal.code})")
            print(f"신호: {signal.signal.value} (신뢰도: {signal.confidence:.0f}%)")
            print(f"현재가: {signal.price:,}원")
            print(f"목표가: {signal.target_price:,}원")
            print(f"손절가: {signal.stop_loss_price:,}원")
            print(f"근거:")
            for r in signal.reasons:
                print(f"  - {r}")
            print(f"지표: {json.dumps(signal.indicators, ensure_ascii=False, indent=2)}")
    else:
        run_scheduler(paper_trading=not args.live)
