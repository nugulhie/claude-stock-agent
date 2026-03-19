"""TechnicalAnalyzer 유닛 테스트"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from modules.technical import TechnicalAnalyzer, Signal, TradeSignal


class TestSMA(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_basic_sma(self):
        prices = [10, 20, 30, 40, 50]
        result = self.ta.calc_sma(prices, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 20.0)  # (10+20+30)/3
        self.assertAlmostEqual(result[3], 30.0)  # (20+30+40)/3
        self.assertAlmostEqual(result[4], 40.0)  # (30+40+50)/3

    def test_sma_period_equals_length(self):
        prices = [10, 20, 30]
        result = self.ta.calc_sma(prices, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 20.0)

    def test_sma_period_exceeds_length(self):
        prices = [10, 20]
        result = self.ta.calc_sma(prices, 5)
        self.assertTrue(all(v is None for v in result))

    def test_sma_single_period(self):
        prices = [10, 20, 30]
        result = self.ta.calc_sma(prices, 1)
        self.assertEqual(result, [10, 20, 30])


class TestEMA(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_basic_ema(self):
        prices = [10, 20, 30, 40, 50]
        result = self.ta.calc_ema(prices, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 20.0)  # 첫 EMA = SMA
        # EMA = price * (2/(3+1)) + prev_ema * (1 - 2/(3+1))
        self.assertAlmostEqual(result[3], 40 * 0.5 + 20.0 * 0.5)
        self.assertAlmostEqual(result[4], 50 * 0.5 + result[3] * 0.5)

    def test_ema_insufficient_data(self):
        prices = [10, 20]
        result = self.ta.calc_ema(prices, 5)
        self.assertTrue(all(v is None for v in result))


class TestRSI(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_all_gains(self):
        """연속 상승 → RSI 100에 가까워야 함"""
        prices = list(range(1, 20))  # 1,2,3,...,18
        result = self.ta.calc_rsi(prices, period=14)
        last_rsi = result[-1]
        self.assertIsNotNone(last_rsi)
        self.assertGreater(last_rsi, 90)

    def test_all_losses(self):
        """연속 하락 → RSI 0에 가까워야 함"""
        prices = list(range(20, 1, -1))  # 20,19,...,2
        result = self.ta.calc_rsi(prices, period=14)
        last_rsi = result[-1]
        self.assertIsNotNone(last_rsi)
        self.assertLess(last_rsi, 10)

    def test_rsi_range(self):
        """RSI는 항상 0~100 사이"""
        prices = [100, 105, 98, 110, 95, 108, 102, 115, 90, 120,
                  85, 125, 80, 130, 75, 135, 70, 140, 100, 105]
        result = self.ta.calc_rsi(prices, period=14)
        for v in result:
            if v is not None:
                self.assertGreaterEqual(v, 0)
                self.assertLessEqual(v, 100)

    def test_rsi_initial_value_exists(self):
        """초기 RSI 값(period 인덱스)이 설정되어야 함"""
        prices = list(range(1, 20))
        result = self.ta.calc_rsi(prices, period=14)
        self.assertIsNotNone(result[14])

    def test_insufficient_data(self):
        prices = [10, 20, 30]
        result = self.ta.calc_rsi(prices, period=14)
        self.assertTrue(all(v is None for v in result))


class TestMACD(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_macd_output_length(self):
        prices = list(range(1, 51))  # 50개
        macd_line, signal_line, histogram = self.ta.calc_macd(prices)
        self.assertEqual(len(macd_line), 50)
        self.assertEqual(len(signal_line), 50)
        self.assertEqual(len(histogram), 50)

    def test_macd_values_exist(self):
        """26일 이후부터 MACD 값 존재해야 함"""
        prices = list(range(1, 51))
        macd_line, signal_line, histogram = self.ta.calc_macd(prices)
        # slow=26이므로 index 25부터 MACD 존재
        self.assertIsNotNone(macd_line[25])

    def test_uptrend_positive_macd(self):
        """지속 상승 → MACD 양수"""
        prices = [100 + i * 2 for i in range(50)]  # 꾸준한 상승
        macd_line, _, _ = self.ta.calc_macd(prices)
        last_macd = macd_line[-1]
        self.assertIsNotNone(last_macd)
        self.assertGreater(last_macd, 0)


class TestBollingerBands(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_bands_order(self):
        """upper > middle > lower"""
        prices = [100, 105, 98, 110, 95, 108, 102, 115, 90, 120,
                  100, 105, 98, 110, 95, 108, 102, 115, 90, 120,
                  100, 105]
        upper, middle, lower = self.ta.calc_bollinger_bands(prices, period=20)
        for i in range(len(prices)):
            if upper[i] is not None:
                self.assertGreater(upper[i], middle[i])
                self.assertGreater(middle[i], lower[i])

    def test_constant_prices(self):
        """모든 가격 동일 → upper == middle == lower"""
        prices = [100] * 25
        upper, middle, lower = self.ta.calc_bollinger_bands(prices, period=20)
        self.assertAlmostEqual(upper[-1], 100.0)
        self.assertAlmostEqual(middle[-1], 100.0)
        self.assertAlmostEqual(lower[-1], 100.0)


class TestStochastic(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def test_stochastic_range(self):
        """%K는 0~100 사이"""
        highs = [110, 115, 120, 108, 125, 130, 105, 140, 112, 118,
                 122, 128, 135, 115, 120, 125, 130, 135, 140, 145]
        lows  = [90, 95, 100, 88, 105, 110, 85, 120, 92, 98,
                 102, 108, 115, 95, 100, 105, 110, 115, 120, 125]
        closes = [100, 108, 115, 95, 118, 125, 90, 135, 105, 112,
                  115, 122, 128, 100, 115, 118, 125, 130, 135, 140]
        k_vals, d_vals = self.ta.calc_stochastic(highs, lows, closes)
        for v in k_vals:
            if v is not None:
                self.assertGreaterEqual(v, 0)
                self.assertLessEqual(v, 100)

    def test_at_high_gives_100(self):
        """종가가 14일 최고가일 때 %K = 100"""
        highs  = [100] * 14 + [200]
        lows   = [50]  * 14 + [50]
        closes = [75]  * 14 + [200]
        k_vals, _ = self.ta.calc_stochastic(highs, lows, closes)
        self.assertAlmostEqual(k_vals[-1], 100.0)


class TestGenerateSignal(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def _make_daily_prices(self, closes, base_volume=100000):
        """테스트용 daily_prices 생성 (최신순)"""
        result = []
        for i, close in enumerate(reversed(closes)):
            result.append({
                "date": f"2025{(i // 30 + 1):02d}{(i % 30 + 1):02d}",
                "open": close - 10,
                "high": close + 20,
                "low": close - 20,
                "close": close,
                "volume": base_volume,
            })
        return result

    def test_insufficient_data_returns_hold(self):
        daily = self._make_daily_prices([100] * 10)
        signal = self.ta.generate_signal("005490", "테스트", daily)
        self.assertEqual(signal.signal, Signal.HOLD)
        self.assertEqual(signal.confidence, 0)

    def test_strong_uptrend_bullish(self):
        """강한 상승 추세 → 매수 계열 신호"""
        closes = [1000 + i * 50 for i in range(60)]  # 꾸준한 상승
        daily = self._make_daily_prices(closes)
        signal = self.ta.generate_signal(
            "005490", "상승종목", daily,
            fundamental_score=80, commodity_score=70, news_score=50)
        self.assertIn(signal.signal, (Signal.STRONG_BUY, Signal.BUY))
        self.assertGreater(signal.confidence, 0)

    def test_strong_downtrend_bearish(self):
        """강한 하락 추세 → 매도 계열 신호"""
        closes = [5000 - i * 50 for i in range(60)]  # 꾸준한 하락
        daily = self._make_daily_prices(closes)
        signal = self.ta.generate_signal(
            "005490", "하락종목", daily,
            fundamental_score=20, commodity_score=30, news_score=-50)
        self.assertIn(signal.signal, (Signal.SELL, Signal.STRONG_SELL, Signal.HOLD))

    def test_target_and_stop_prices(self):
        """매수 신호 시 목표가 > 현재가 > 손절가"""
        closes = [1000 + i * 50 for i in range(60)]
        daily = self._make_daily_prices(closes)
        signal = self.ta.generate_signal(
            "005490", "테스트", daily,
            fundamental_score=90, commodity_score=80, news_score=80)
        if signal.signal in (Signal.STRONG_BUY, Signal.BUY):
            self.assertGreater(signal.target_price, signal.price)
            self.assertLess(signal.stop_loss_price, signal.price)

    def test_tech_score_clamping(self):
        """tech_score가 ±100 내로 클램핑되는지 확인"""
        # 극단적 상승 + 고거래량 → tech_score가 100 초과 가능했던 케이스
        closes = [1000 + i * 100 for i in range(60)]
        volumes = [100000] * 40 + [1000000] * 20  # 마지막 20일 거래량 폭증
        daily = []
        for i, close in enumerate(reversed(closes)):
            daily.append({
                "date": f"2025{(i // 30 + 1):02d}{(i % 30 + 1):02d}",
                "open": close - 50, "high": close + 100,
                "low": close - 100, "close": close,
                "volume": volumes[len(closes) - 1 - i] if (len(closes) - 1 - i) < len(volumes) else 100000,
            })
        signal = self.ta.generate_signal(
            "005490", "극단테스트", daily,
            fundamental_score=100, commodity_score=100, news_score=100)
        # 종합점수가 100을 크게 넘지 않아야 함
        self.assertLessEqual(signal.indicators["기술점수"], 100.0)
        self.assertGreaterEqual(signal.indicators["기술점수"], 0.0)

    def test_return_type(self):
        closes = [1000] * 60
        daily = self._make_daily_prices(closes)
        signal = self.ta.generate_signal("005490", "테스트", daily)
        self.assertIsInstance(signal, TradeSignal)
        self.assertIsInstance(signal.reasons, list)
        self.assertIsInstance(signal.indicators, dict)


class TestGetTechnicalScore(unittest.TestCase):
    def setUp(self):
        self.ta = TechnicalAnalyzer()

    def _make_daily(self, closes):
        return [{"date": "", "open": c, "high": c+10, "low": c-10,
                 "close": c, "volume": 100000} for c in reversed(closes)]

    def test_score_range(self):
        closes = [1000 + i * 10 for i in range(60)]
        daily = self._make_daily(closes)
        score = self.ta.get_technical_score(daily)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_insufficient_data(self):
        daily = self._make_daily([100] * 10)
        score = self.ta.get_technical_score(daily)
        self.assertEqual(score, 50.0)


if __name__ == "__main__":
    unittest.main()
