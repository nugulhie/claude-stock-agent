"""PortfolioManager 유닛 테스트"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
import datetime
from modules.portfolio import PortfolioManager, Position, TradeLog


class TestPositionSizing(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)

    def test_high_confidence_large_position(self):
        """신뢰도 80↑ → 최대 비중(40%)"""
        qty = self.pm.calculate_position_size(price=10000, signal_confidence=85)
        max_invest = 300_000 * 0.40  # 120,000
        available = min(max_invest, 300_000 * 0.95)  # min(120000, 285000) = 120000
        expected = int(available / 10000)  # 12
        self.assertEqual(qty, expected)

    def test_medium_confidence(self):
        """신뢰도 60~80 → 25% 비중"""
        qty = self.pm.calculate_position_size(price=10000, signal_confidence=65)
        position_pct = (0.40 + 0.10) / 2  # 25%
        max_invest = 300_000 * position_pct
        expected = int(max_invest * 0.95 / 10000)
        self.assertEqual(qty, expected)

    def test_low_confidence_small_position(self):
        """신뢰도 60↓ → 최소 비중(10%)"""
        qty = self.pm.calculate_position_size(price=10000, signal_confidence=40)
        max_invest = 300_000 * 0.10  # 30,000
        available = min(max_invest, 300_000 * 0.95)  # min(30000, 285000) = 30000
        expected = int(available / 10000)  # 3
        self.assertEqual(qty, expected)

    def test_max_positions_reached(self):
        """최대 보유 종목 수 도달 → 0"""
        for i in range(5):
            self.pm.positions[f"code{i}"] = Position(
                code=f"code{i}", name=f"종목{i}", qty=1, avg_price=10000,
                current_price=10000, entry_date="", highest_price=10000,
                signal_score=70, stop_loss=9500, take_profit=11500)
        qty = self.pm.calculate_position_size(price=10000, signal_confidence=90)
        self.assertEqual(qty, 0)

    def test_zero_price(self):
        qty = self.pm.calculate_position_size(price=0, signal_confidence=80)
        self.assertEqual(qty, 0)

    def test_no_cash(self):
        self.pm.cash = 0
        qty = self.pm.calculate_position_size(price=10000, signal_confidence=80)
        self.assertEqual(qty, 0)

    def test_expensive_stock_does_not_exceed_position_cap(self):
        """1주 가격이 최대 비중을 넘으면 매수하지 않음"""
        qty = self.pm.calculate_position_size(price=250_000, signal_confidence=90)
        self.assertEqual(qty, 0)


class TestExecuteBuy(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)

    def test_basic_buy(self):
        success = self.pm.execute_buy("005490", "POSCO", 10000, 5, 75, "테스트 매수")
        self.assertTrue(success)
        self.assertIn("005490", self.pm.positions)
        self.assertEqual(self.pm.positions["005490"].qty, 5)
        self.assertEqual(self.pm.positions["005490"].avg_price, 10000)
        self.assertEqual(self.pm.cash, 300_000 - 50000)

    def test_buy_reduces_cash(self):
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "")
        self.assertEqual(self.pm.cash, 200_000)

    def test_buy_exceeds_cash_adjusts_qty(self):
        """자금 부족 시 수량 자동 조정"""
        success = self.pm.execute_buy("A", "종목A", 100000, 10, 70, "")  # 100만원 필요
        self.assertTrue(success)
        pos = self.pm.positions["A"]
        self.assertEqual(pos.qty, 3)  # 300,000 / 100,000 = 3
        self.assertEqual(self.pm.cash, 0)

    def test_buy_zero_qty_fails(self):
        """수량 0 → 실패"""
        success = self.pm.execute_buy("A", "종목A", 500000, 0, 70, "")
        self.assertFalse(success)

    def test_additional_buy_averages_price(self):
        """추가 매수 → 평균 단가 재계산"""
        self.pm.execute_buy("A", "종목A", 10000, 5, 70, "1차")
        self.pm.execute_buy("A", "종목A", 12000, 5, 70, "2차")
        pos = self.pm.positions["A"]
        self.assertEqual(pos.qty, 10)
        self.assertAlmostEqual(pos.avg_price, 11000)  # (10000*5 + 12000*5) / 10

    def test_additional_buy_recalculates_risk_prices(self):
        """추가 매수 후 손절/익절 기준은 새 평균단가 기준"""
        self.pm.execute_buy("A", "종목A", 10000, 5, 70, "1차")
        self.pm.execute_buy("A", "종목A", 20000, 5, 70, "2차")
        pos = self.pm.positions["A"]
        self.assertAlmostEqual(pos.avg_price, 15000)
        self.assertEqual(pos.stop_loss, int(15000 * 0.95))
        self.assertEqual(pos.take_profit, int(15000 * 1.15))
        self.assertEqual(pos.highest_price, 20000)

    def test_stop_loss_price_set(self):
        self.pm.execute_buy("A", "종목A", 10000, 5, 70, "")
        pos = self.pm.positions["A"]
        self.assertEqual(pos.stop_loss, int(10000 * 0.95))   # -5%
        self.assertEqual(pos.take_profit, int(10000 * 1.15))  # +15%

    def test_trade_logged(self):
        self.pm.execute_buy("A", "종목A", 10000, 5, 70, "로그 테스트")
        self.assertEqual(len(self.pm.trade_history), 1)
        self.assertEqual(self.pm.trade_history[0].side, "BUY")
        self.assertEqual(self.pm.trade_history[0].code, "A")


class TestExecuteSell(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "매수")

    def test_full_sell(self):
        """전량 매도"""
        success = self.pm.execute_sell("A", 12000, reason="익절")
        self.assertTrue(success)
        self.assertNotIn("A", self.pm.positions)
        self.assertEqual(self.pm.cash, 300_000 - 100_000 + 120_000)

    def test_partial_sell(self):
        """부분 매도"""
        success = self.pm.execute_sell("A", 12000, qty=5, reason="부분 매도")
        self.assertTrue(success)
        self.assertIn("A", self.pm.positions)
        self.assertEqual(self.pm.positions["A"].qty, 5)

    def test_sell_nonexistent_fails(self):
        success = self.pm.execute_sell("XXXXX", 10000)
        self.assertFalse(success)

    def test_sell_profit_logged(self):
        self.pm.execute_sell("A", 12000, reason="익절")
        sell_log = [t for t in self.pm.trade_history if t.side == "SELL"][0]
        self.assertIsNotNone(sell_log.profit_pct)
        self.assertAlmostEqual(sell_log.profit_pct, 20.0)  # (12000-10000)/10000*100

    def test_sell_updates_cash(self):
        before = self.pm.cash
        self.pm.execute_sell("A", 11000, qty=5, reason="")
        self.assertEqual(self.pm.cash, before + 55000)


class TestStopConditions(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "매수")

    def test_stop_loss_triggered(self):
        """-5% 이하 → 손절"""
        result = self.pm.check_stop_conditions("A", 9400)
        self.assertIsNotNone(result)
        self.assertIn("손절", result)

    def test_take_profit_triggered(self):
        """+15% 이상 → 익절"""
        result = self.pm.check_stop_conditions("A", 11600)
        self.assertIsNotNone(result)
        self.assertIn("익절", result)

    def test_trailing_stop_triggered(self):
        """고점 대비 -7% → 트레일링 스탑"""
        # 먼저 가격을 12000까지 올린다
        self.pm.check_stop_conditions("A", 12000)
        self.assertEqual(self.pm.positions["A"].highest_price, 12000)
        # 12000 * 0.93 = 11160, 11100이면 트리거
        result = self.pm.check_stop_conditions("A", 11100)
        self.assertIsNotNone(result)
        self.assertIn("트레일링", result)

    def test_no_trigger_normal(self):
        """정상 범위 → None"""
        result = self.pm.check_stop_conditions("A", 10500)
        self.assertIsNone(result)

    def test_highest_price_updated(self):
        self.pm.check_stop_conditions("A", 11000)
        self.assertEqual(self.pm.positions["A"].highest_price, 11000)
        self.pm.check_stop_conditions("A", 10500)
        self.assertEqual(self.pm.positions["A"].highest_price, 11000)  # 갱신 안 됨

    def test_nonexistent_code(self):
        result = self.pm.check_stop_conditions("XXXXX", 10000)
        self.assertIsNone(result)


class TestDailyRisk(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)

    def test_no_positions_ok(self):
        self.assertTrue(self.pm.check_daily_risk())

    def test_small_loss_ok(self):
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "")
        self.pm.positions["A"].current_price = 9800  # -2%
        self.assertTrue(self.pm.check_daily_risk())

    def test_large_loss_blocked(self):
        """큰 미실현 손실 → 거래 불가"""
        self.pm.execute_buy("A", "종목A", 10000, 20, 70, "")  # 200,000원 투자
        self.pm.positions["A"].current_price = 8000  # -20%, 손실 40,000원
        # daily_loss_limit = 300,000 * 0.10 = 30,000원
        self.assertFalse(self.pm.check_daily_risk())


class TestPortfolioSummary(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)

    def test_empty_portfolio(self):
        summary = self.pm.get_portfolio_summary()
        self.assertEqual(summary["보유종목수"], 0)
        self.assertEqual(summary["보유종목"], [])
        self.assertIn("300,000", summary["총평가금액"])

    def test_with_positions(self):
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "")
        self.pm.positions["A"].current_price = 11000
        summary = self.pm.get_portfolio_summary()
        self.assertEqual(summary["보유종목수"], 1)
        self.assertEqual(len(summary["보유종목"]), 1)

    def test_total_value(self):
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "")
        self.pm.positions["A"].current_price = 12000
        total = self.pm.get_total_value()
        expected = (300_000 - 100_000) + (10 * 12000)
        self.assertEqual(total, expected)


class TestPerformanceStats(unittest.TestCase):
    def setUp(self):
        self.pm = PortfolioManager(initial_capital=300_000)

    def test_no_trades(self):
        stats = self.pm.get_performance_stats()
        self.assertEqual(stats["총매매횟수"], 0)

    def test_with_trades(self):
        self.pm.execute_buy("A", "종목A", 10000, 10, 70, "")
        self.pm.execute_sell("A", 12000, reason="익절")
        self.pm.execute_buy("B", "종목B", 5000, 10, 70, "")
        self.pm.execute_sell("B", 4000, reason="손절")

        stats = self.pm.get_performance_stats()
        self.assertEqual(stats["총매매횟수"], 2)
        self.assertIn("%", stats["승률"])


class TestPosition(unittest.TestCase):
    def test_profit_pct(self):
        pos = Position(code="A", name="A", qty=10, avg_price=10000,
                       current_price=11000, entry_date="", highest_price=11000,
                       signal_score=70, stop_loss=9500, take_profit=11500)
        self.assertAlmostEqual(pos.profit_pct, 10.0)

    def test_profit_pct_zero_avg(self):
        pos = Position(code="A", name="A", qty=10, avg_price=0,
                       current_price=11000, entry_date="", highest_price=11000,
                       signal_score=70, stop_loss=0, take_profit=0)
        self.assertEqual(pos.profit_pct, 0.0)

    def test_market_value(self):
        pos = Position(code="A", name="A", qty=10, avg_price=10000,
                       current_price=11000, entry_date="", highest_price=11000,
                       signal_score=70, stop_loss=9500, take_profit=11500)
        self.assertEqual(pos.market_value, 110000)

    def test_profit_amount(self):
        pos = Position(code="A", name="A", qty=10, avg_price=10000,
                       current_price=11000, entry_date="", highest_price=11000,
                       signal_score=70, stop_loss=9500, take_profit=11500)
        self.assertEqual(pos.profit_amount, 10000)


if __name__ == "__main__":
    unittest.main()
