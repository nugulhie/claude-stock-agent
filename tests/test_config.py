"""config.py 유닛 테스트"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from config import StrategyConfig, SectorConfig, NewsConfig, STRATEGY, SECTORS, NEWS


class TestStrategyConfig(unittest.TestCase):
    def test_weights_sum_to_one(self):
        """분석 가중치 합이 1.0"""
        s = StrategyConfig()
        total = s.commodity_weight + s.news_weight + s.technical_weight + s.fundamental_weight
        self.assertAlmostEqual(total, 1.0)

    def test_stop_loss_negative(self):
        s = StrategyConfig()
        self.assertLess(s.stop_loss_pct, 0)

    def test_take_profit_positive(self):
        s = StrategyConfig()
        self.assertGreater(s.take_profit_pct, 0)

    def test_position_pct_order(self):
        s = StrategyConfig()
        self.assertGreater(s.max_position_pct, s.min_position_pct)

    def test_market_cap_order(self):
        s = StrategyConfig()
        self.assertGreater(s.max_market_cap, s.min_market_cap)

    def test_rsi_thresholds(self):
        s = StrategyConfig()
        self.assertLess(s.rsi_oversold, s.rsi_overbought)
        self.assertGreater(s.rsi_oversold, 0)
        self.assertLess(s.rsi_overbought, 100)

    def test_target_exceeds_initial(self):
        s = StrategyConfig()
        self.assertGreater(s.target_capital, s.initial_capital)


class TestSectorConfig(unittest.TestCase):
    def test_all_sectors_have_codes(self):
        s = SectorConfig()
        for sector, codes in s.commodity_stocks.items():
            self.assertGreater(len(codes), 0, f"{sector} 섹터에 종목 없음")

    def test_codes_are_6digit_strings(self):
        s = SectorConfig()
        for sector, codes in s.commodity_stocks.items():
            for code in codes:
                self.assertEqual(len(code), 6, f"{sector}:{code} 길이 오류")
                self.assertTrue(code.isdigit(), f"{sector}:{code} 숫자 아님")

    def test_no_duplicate_codes(self):
        s = SectorConfig()
        all_codes = []
        for codes in s.commodity_stocks.values():
            all_codes.extend(codes)
        self.assertEqual(len(all_codes), len(set(all_codes)), "중복 종목코드 존재")

    def test_commodities_to_track(self):
        s = SectorConfig()
        self.assertGreater(len(s.commodities_to_track), 0)
        self.assertIn("CL=F", s.commodities_to_track)


class TestNewsConfig(unittest.TestCase):
    def test_sources_not_empty(self):
        n = NewsConfig()
        self.assertGreater(len(n.sources), 0)

    def test_threshold_order(self):
        n = NewsConfig()
        self.assertGreater(n.sentiment_threshold_positive, n.sentiment_threshold_negative)


class TestGlobalInstances(unittest.TestCase):
    def test_instances_exist(self):
        self.assertIsInstance(STRATEGY, StrategyConfig)
        self.assertIsInstance(SECTORS, SectorConfig)
        self.assertIsInstance(NEWS, NewsConfig)


if __name__ == "__main__":
    unittest.main()
