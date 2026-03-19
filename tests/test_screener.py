"""StockScreener 유닛 테스트"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock
from modules.screener import StockScreener, StockScore


class TestScreenFundamentals(unittest.TestCase):
    def setUp(self):
        self.screener = StockScreener(MagicMock())

    def test_excellent_fundamentals(self):
        """우량 종목 → 높은 점수"""
        price_data = {"per": 8, "pbr": 0.8}
        financial = {"roe": 20, "debt_ratio": 50, "operating_margin": 15, "revenue_growth": 25}
        score, reasons, flags = self.screener.screen_fundamentals("005490", price_data, financial)
        self.assertGreaterEqual(score, 80)
        self.assertGreater(len(reasons), 0)
        self.assertEqual(len(flags), 0)

    def test_poor_fundamentals(self):
        """부실 종목 → 낮은 점수 + 리스크 플래그"""
        price_data = {"per": -5, "pbr": 4.0}
        financial = {"roe": -10, "debt_ratio": 300, "operating_margin": -5, "revenue_growth": -15}
        score, reasons, flags = self.screener.screen_fundamentals("999999", price_data, financial)
        self.assertLessEqual(score, 20)
        self.assertGreater(len(flags), 0)

    def test_per_ranges(self):
        financial = {"roe": 10, "debt_ratio": 100, "operating_margin": 10, "revenue_growth": 10}
        # 저PER
        s1, r1, _ = self.screener.screen_fundamentals("A", {"per": 5, "pbr": 1.5}, financial)
        # 적정PER
        s2, r2, _ = self.screener.screen_fundamentals("A", {"per": 20, "pbr": 1.5}, financial)
        # 고PER
        s3, r3, _ = self.screener.screen_fundamentals("A", {"per": 50, "pbr": 1.5}, financial)
        self.assertGreater(s1, s2)
        self.assertGreater(s2, s3)

    def test_pbr_zero_no_score(self):
        """PBR=0 → 점수 부여 안 함"""
        price_data = {"per": 10, "pbr": 0}
        financial = {"roe": 10, "debt_ratio": 100, "operating_margin": 10, "revenue_growth": 10}
        score_zero, _, _ = self.screener.screen_fundamentals("A", price_data, financial)

        price_data2 = {"per": 10, "pbr": 0.5}
        score_low, _, _ = self.screener.screen_fundamentals("A", price_data2, financial)
        self.assertGreater(score_low, score_zero)

    def test_negative_per_flag(self):
        """적자 기업(PER<0) → 플래그"""
        price_data = {"per": -10, "pbr": 1.5}
        financial = {"roe": 10, "debt_ratio": 100, "operating_margin": 10, "revenue_growth": 10}
        _, _, flags = self.screener.screen_fundamentals("A", price_data, financial)
        self.assertTrue(any("적자" in f for f in flags))

    def test_score_clamped_0_100(self):
        """점수는 항상 0~100 범위"""
        # 극단적 나쁜 데이터
        price_data = {"per": -100, "pbr": 10}
        financial = {"roe": -50, "debt_ratio": 500, "operating_margin": -20, "revenue_growth": -30}
        score, _, _ = self.screener.screen_fundamentals("A", price_data, financial)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class TestCommoditySensitivity(unittest.TestCase):
    def setUp(self):
        self.screener = StockScreener(MagicMock())

    def test_steel_copper_up(self):
        """구리↑ → 철강 호재"""
        changes = {"HG=F": 3.0, "CL=F": 0, "GC=F": 0}
        score, reasons = self.screener.analyze_commodity_sensitivity("005490", changes)  # POSCO
        self.assertGreater(score, 50)
        self.assertTrue(any("호재" in r for r in reasons))

    def test_steel_oil_up(self):
        """유가↑ → 철강 악재 (비용 상승)"""
        changes = {"HG=F": 0, "CL=F": 3.0, "GC=F": 0}
        score, _ = self.screener.analyze_commodity_sensitivity("005490", changes)
        self.assertLess(score, 50)

    def test_oil_refinery_oil_up(self):
        """유가↑ → 정유 호재"""
        changes = {"CL=F": 5.0, "NG=F": 0}
        score, reasons = self.screener.analyze_commodity_sensitivity("010950", changes)  # S-Oil
        self.assertGreater(score, 50)

    def test_chemical_oil_up(self):
        """유가↑ → 화학 악재 (원가 상승)"""
        changes = {"CL=F": 5.0, "NG=F": 0}
        score, _ = self.screener.analyze_commodity_sensitivity("051910", changes)  # LG화학
        self.assertLess(score, 50)

    def test_non_commodity_stock(self):
        """원자재 무관 종목 → 50점 고정"""
        changes = {"CL=F": 10.0, "HG=F": 10.0}
        score, reasons = self.screener.analyze_commodity_sensitivity("000000", changes)
        self.assertEqual(score, 50.0)
        self.assertTrue(any("일반 종목" in r for r in reasons))

    def test_usd_krw_impact(self):
        """원화약세 → 정유/화학 수출 영향"""
        changes = {"CL=F": 0, "NG=F": 0, "X:USDKRW": 2.0}
        score, reasons = self.screener.analyze_commodity_sensitivity("010950", changes)  # 정유
        self.assertGreater(score, 50)

    def test_score_clamped(self):
        """극단적 변동에도 0~100 범위"""
        changes = {"CL=F": 50.0, "HG=F": 50.0, "GC=F": 50.0}
        score, _ = self.screener.analyze_commodity_sensitivity("010950", changes)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class TestSmallCapMomentum(unittest.TestCase):
    def setUp(self):
        self.screener = StockScreener(MagicMock())

    def _make_daily(self, closes, volumes=None):
        result = []
        for i, c in enumerate(closes):
            result.append({
                "date": "", "open": c, "high": c + 10, "low": c - 10,
                "close": c, "volume": (volumes[i] if volumes else 100000),
            })
        return result

    def test_ideal_small_cap(self):
        """적정 시총 + 거래량 급증 + 상승 모멘텀"""
        stock_data = {
            "market_cap": 500_000_000_000,  # 5000억
            "volume": 500000,
            "change_pct": 5.0,
            "price": 10000,
            "high_52w": 15000,
            "low_52w": 5000,
        }
        closes = [9000 + i * 50 for i in range(25)]  # 완만한 상승
        volumes = [100000] * 25
        daily = self._make_daily(closes, volumes)
        score, reasons, flags = self.screener.screen_small_cap_momentum(stock_data, daily)
        self.assertGreater(score, 30)

    def test_micro_cap_flag(self):
        """극소형주 → 리스크 플래그"""
        stock_data = {"market_cap": 10_000_000_000, "volume": 100000,
                      "change_pct": 0, "price": 1000, "high_52w": 2000, "low_52w": 500}
        daily = self._make_daily([1000] * 25)
        _, _, flags = self.screener.screen_small_cap_momentum(stock_data, daily)
        self.assertTrue(any("극소형주" in f for f in flags))

    def test_overheated_momentum_flag(self):
        """5일 +36% → 과열 플래그"""
        # screen_small_cap_momentum은 daily[0]이 최신 데이터
        # daily[4]가 5일전 데이터
        stock_data = {"market_cap": 500_000_000_000, "volume": 100000,
                      "change_pct": 0, "price": 15000, "high_52w": 20000, "low_52w": 5000}
        # 최신순: [15000, 13000, 12000, 11000, 10000, ...]
        closes_newest_first = [15000, 13000, 12000, 11000, 10000] + [10000] * 20
        daily = self._make_daily(closes_newest_first)
        # 모멘텀 = (15000 - 10000) / 10000 * 100 = 50% → 과열
        _, _, flags = self.screener.screen_small_cap_momentum(stock_data, daily)
        has_overheated = any("과열" in f for f in flags)
        self.assertTrue(has_overheated)


class TestComprehensiveScreen(unittest.TestCase):
    def setUp(self):
        self.screener = StockScreener(MagicMock())

    def test_returns_stock_score(self):
        price_data = {"per": 10, "pbr": 1.0, "price": 10000,
                      "market_cap": 500_000_000_000, "volume": 200000,
                      "change_pct": 3.0, "high_52w": 15000, "low_52w": 5000}
        financial = {"roe": 12, "debt_ratio": 80, "operating_margin": 10, "revenue_growth": 15}
        daily = [{"date": "", "open": 10000, "high": 10100, "low": 9900,
                  "close": 10000, "volume": 100000}] * 30
        changes = {"CL=F": 1.0}

        result = self.screener.comprehensive_screen(
            "005490", "POSCO", price_data, financial, daily, changes, 60.0)
        self.assertIsInstance(result, StockScore)
        self.assertGreaterEqual(result.total_score, 0)
        self.assertLessEqual(result.total_score, 100)
        self.assertEqual(result.code, "005490")
        self.assertEqual(result.name, "POSCO")


if __name__ == "__main__":
    unittest.main()
