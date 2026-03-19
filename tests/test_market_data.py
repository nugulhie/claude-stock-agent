"""MarketDataCollector 유닛 테스트"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from modules.market_data import MarketDataCollector, NewsItem, CommodityData


class TestSentimentAnalysis(unittest.TestCase):
    def setUp(self):
        self.mc = MarketDataCollector()

    def test_positive_sentiment(self):
        text = "삼성전자 급등 신고가 돌파 강세 반등"
        score = self.mc._analyze_sentiment(text)
        self.assertGreater(score, 0)

    def test_negative_sentiment(self):
        text = "주가 급락 폭락 적자 실적악화 위기"
        score = self.mc._analyze_sentiment(text)
        self.assertLess(score, 0)

    def test_neutral_sentiment(self):
        text = "오늘 날씨가 좋습니다"
        score = self.mc._analyze_sentiment(text)
        self.assertEqual(score, 0.0)

    def test_mixed_sentiment(self):
        text = "급등 이후 급락"
        score = self.mc._analyze_sentiment(text)
        # 호재 1 + 악재 1 → 0
        self.assertEqual(score, 0.0)

    def test_sentiment_range(self):
        """항상 -1.0 ~ +1.0"""
        text = "급등 상승 호재 최고 돌파 신고가 강세 반등 상한가 대박"
        score = self.mc._analyze_sentiment(text)
        self.assertGreaterEqual(score, -1.0)
        self.assertLessEqual(score, 1.0)

    def test_empty_text(self):
        score = self.mc._analyze_sentiment("")
        self.assertEqual(score, 0.0)


class TestExtractKeywords(unittest.TestCase):
    def setUp(self):
        self.mc = MarketDataCollector()

    def test_finds_keywords(self):
        text = "삼성전자 급등 신고가 달성"
        keywords = self.mc._extract_keywords(text)
        self.assertIn("급등", keywords)
        self.assertIn("신고가", keywords)

    def test_no_keywords(self):
        text = "별다른 뉴스 없음"
        keywords = self.mc._extract_keywords(text)
        self.assertEqual(len(keywords), 0)

    def test_both_positive_negative(self):
        text = "급등 후 급락"
        keywords = self.mc._extract_keywords(text)
        self.assertIn("급등", keywords)
        self.assertIn("급락", keywords)


class TestNewsSentimentScore(unittest.TestCase):
    def setUp(self):
        self.mc = MarketDataCollector()

    def test_no_news_returns_zero(self):
        """뉴스 없으면 0점"""
        # 실제 크롤링 없이 빈 리스트 반환하도록 mock
        original = self.mc.fetch_naver_finance_news
        self.mc.fetch_naver_finance_news = lambda *args, **kwargs: []
        score, reasons = self.mc.get_news_sentiment_score("000000")
        self.assertEqual(score, 0.0)
        self.assertTrue(any("없음" in r for r in reasons))
        self.mc.fetch_naver_finance_news = original

    def test_score_range(self):
        """점수는 -100 ~ +100"""
        # 모두 긍정 뉴스 mock
        positive_news = [
            NewsItem("급등 신고가 돌파", "", "test", "", 0.8, ["급등"], [])
            for _ in range(10)
        ]
        self.mc.fetch_naver_finance_news = lambda *args, **kwargs: positive_news
        score, _ = self.mc.get_news_sentiment_score("005490")
        self.assertGreaterEqual(score, -100)
        self.assertLessEqual(score, 100)
        self.assertGreater(score, 0)


class TestCommodityData(unittest.TestCase):
    def test_dataclass(self):
        cd = CommodityData(symbol="CL=F", name="WTI 원유", price=75.5,
                           change_pct=2.3, trend="상승")
        self.assertEqual(cd.symbol, "CL=F")
        self.assertEqual(cd.trend, "상승")


class TestNewsItem(unittest.TestCase):
    def test_dataclass(self):
        ni = NewsItem(title="테스트", url="http://test.com", source="test",
                      date="2025-01-01", sentiment=0.5, keywords=["급등"],
                      related_stocks=["005490"])
        self.assertEqual(ni.title, "테스트")
        self.assertEqual(len(ni.keywords), 1)


class TestCommodityNames(unittest.TestCase):
    def setUp(self):
        self.mc = MarketDataCollector()

    def test_all_symbols_named(self):
        expected = ["CL=F", "GC=F", "SI=F", "HG=F", "NG=F", "ZW=F"]
        for sym in expected:
            self.assertIn(sym, self.mc.COMMODITY_NAMES)


if __name__ == "__main__":
    unittest.main()
