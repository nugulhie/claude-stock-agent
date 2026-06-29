"""
========================================
뉴스 / 환율 / 원자재 분석 모듈
========================================
네이버 금융 뉴스, 환율, 국제 원자재 가격 수집 및 분석
"""

import re
import json
import datetime
from typing import Any, List, Dict, Tuple, Optional
from dataclasses import dataclass

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

try:
    import yfinance as yf
except Exception:
    yf = None


@dataclass
class NewsItem:
    """뉴스 아이템"""
    title: str
    url: str
    source: str
    date: str
    sentiment: float        # -1.0 ~ +1.0
    keywords: List[str]
    related_stocks: List[str]


@dataclass
class CommodityData:
    """원자재 데이터"""
    symbol: str
    name: str
    price: float
    change_pct: float
    trend: str              # "상승", "하락", "보합"


try:
    from modules.claude_client import ClaudeClient
except Exception:
    ClaudeClient = None


class MarketDataCollector:
    """시장 데이터 수집기"""

    # 감성 분석용 키워드 사전 (한국어)
    POSITIVE_KEYWORDS = [
        "급등", "상승", "호재", "최고", "돌파", "신고가", "수주", "흑자전환",
        "매출증가", "영업이익", "배당", "자사주", "목표가상향", "매수추천",
        "성장", "회복", "기대", "강세", "반등", "상한가", "대박",
        "수출호조", "실적개선", "사상최대", "턴어라운드", "호실적",
    ]
    NEGATIVE_KEYWORDS = [
        "급락", "하락", "악재", "최저", "적자", "손실", "하한가",
        "매도", "목표가하향", "부진", "하방", "약세", "폭락",
        "실적악화", "매출감소", "부채", "감자", "상폐", "워크아웃",
        "리스크", "경고", "위기", "불안", "조정", "투매",
    ]

    COMMODITY_NAMES = {
        "CL=F": "WTI 원유",
        "GC=F": "금",
        "SI=F": "은",
        "HG=F": "구리",
        "NG=F": "천연가스",
        "ZW=F": "밀",
    }

    def __init__(self):
        self._session = requests.Session() if requests else None
        if self._session:
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36"
            })
        # Claude 클라이언트 (API 키 없으면 None)
        self.claude = None
        try:
            if ClaudeClient:
                self.claude = ClaudeClient()
        except Exception:
            pass

    # --------------------------------------------------
    # 뉴스 수집 및 감성 분석
    # --------------------------------------------------
    def fetch_naver_finance_news(self, stock_code: Optional[str] = None,
                                 max_items: int = 20) -> List[NewsItem]:
        """네이버 금융 뉴스 수집"""
        news_items = []

        if stock_code:
            url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}"
        else:
            url = "https://finance.naver.com/news/mainnews.naver"

        if self._session is None or BeautifulSoup is None:
            return news_items

        try:
            res = self._session.get(url, timeout=10)
            res.encoding = "euc-kr"
            soup = BeautifulSoup(res.text, "html.parser")

            articles = soup.select(".type5 li, .newsList li, .relationNewsList li")
            for article in articles[:max_items]:
                link_tag = article.select_one("a")
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                if not href.startswith("http"):
                    href = "https://finance.naver.com" + href

                date_tag = article.select_one(".date, .wdate, span")
                date_str = date_tag.get_text(strip=True) if date_tag else ""

                sentiment = self._analyze_sentiment(title)
                keywords = self._extract_keywords(title)

                news_items.append(NewsItem(
                    title=title,
                    url=href,
                    source="네이버금융",
                    date=date_str,
                    sentiment=sentiment,
                    keywords=keywords,
                    related_stocks=[stock_code] if stock_code else [],
                ))
        except Exception as e:
            print(f"[뉴스 수집 오류] {e}")

        return news_items

    def _analyze_sentiment(self, text: str) -> float:
        """간이 감성 분석 (-1.0 ~ +1.0)"""
        pos_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        return (pos_count - neg_count) / total

    def _extract_keywords(self, text: str) -> List[str]:
        """주요 키워드 추출"""
        found = []
        all_keywords = self.POSITIVE_KEYWORDS + self.NEGATIVE_KEYWORDS
        for kw in all_keywords:
            if kw in text:
                found.append(kw)
        return found

    def get_news_sentiment_score(self, stock_code: str) -> Tuple[float, List[str]]:
        """
        종목 뉴스 감성 종합 점수
        Claude API 사용 (실패 시 키워드 매칭 fallback)
        Returns: (score: -100 ~ +100, summary_reasons)
        """
        news = self.fetch_naver_finance_news(stock_code, max_items=15)
        if not news:
            return 0.0, ["뉴스 데이터 없음"]

        # Claude 감성 분석 시도
        from config import STRATEGY
        if self.claude and STRATEGY.use_claude_sentiment:
            titles = [n.title for n in news]
            score, reasons = self.claude.analyze_news_sentiment(titles)
            if reasons and reasons[0] != "Claude 분석 실패 → 기본값":
                return score, reasons

        # Fallback: 기존 키워드 매칭
        avg_sentiment = sum(n.sentiment for n in news) / len(news)
        score = avg_sentiment * 100

        reasons = []
        positive_news = [n for n in news if n.sentiment > 0.3]
        negative_news = [n for n in news if n.sentiment < -0.3]

        if positive_news:
            reasons.append(f"호재 뉴스 {len(positive_news)}건")
        if negative_news:
            reasons.append(f"악재 뉴스 {len(negative_news)}건")
        if not positive_news and not negative_news:
            reasons.append("중립적 뉴스 분위기")

        return score, reasons

    # --------------------------------------------------
    # 환율 조회
    # --------------------------------------------------
    def get_exchange_rates(self) -> Dict[str, Dict]:
        """주요 환율 조회"""
        rates = {}
        pairs = {
            "USD/KRW": "USDKRW=X",
            "EUR/KRW": "EURKRW=X",
            "JPY/KRW": "JPYKRW=X",
            "CNY/KRW": "CNYKRW=X",
        }

        if yf is None:
            # yfinance 없을 경우 네이버 금융에서 가져오기
            return self._get_exchange_rates_naver()

        for name, symbol in pairs.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if not hist.empty and len(hist) >= 2:
                    current = hist["Close"].iloc[-1]
                    prev = hist["Close"].iloc[-2]
                    if prev == 0:
                        continue
                    change_pct = (current - prev) / prev * 100

                    rates[name] = {
                        "rate": round(current, 2),
                        "change_pct": round(change_pct, 2),
                        "trend": "원화약세" if change_pct > 0 else "원화강세",
                    }
            except Exception as e:
                print(f"[환율 조회 오류] {name}: {e}")

        return rates

    def _get_exchange_rates_naver(self) -> Dict[str, Dict]:
        """네이버에서 환율 가져오기 (yfinance 대체)"""
        rates = {}
        if self._session is None or BeautifulSoup is None:
            return rates

        try:
            url = "https://finance.naver.com/marketindex/"
            res = self._session.get(url, timeout=10)
            res.encoding = "euc-kr"
            soup = BeautifulSoup(res.text, "html.parser")

            # 달러/원 환율
            usd_elem = soup.select_one("#exchangeList .value")
            if usd_elem:
                rate = float(usd_elem.get_text(strip=True).replace(",", ""))
                change_elem = soup.select_one("#exchangeList .change")
                change = float(change_elem.get_text(strip=True).replace(",", "")) if change_elem else 0
                rates["USD/KRW"] = {
                    "rate": rate,
                    "change_pct": round(change / rate * 100, 2),
                    "trend": "원화약세" if change > 0 else "원화강세",
                }
        except Exception as e:
            print(f"[네이버 환율 오류] {e}")

        return rates

    # --------------------------------------------------
    # 원자재 가격 조회
    # --------------------------------------------------
    def get_commodity_prices(self) -> List[CommodityData]:
        """국제 원자재 가격 조회"""
        commodities = []

        if yf is None:
            print("[경고] yfinance 미설치 - pip install yfinance")
            return commodities

        for symbol in ["CL=F", "GC=F", "SI=F", "HG=F", "NG=F", "ZW=F"]:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if hist.empty:
                    continue

                current = hist["Close"].iloc[-1]
                if len(hist) < 2:
                    continue  # 변동률 계산 불가 시 스킵
                prev = hist["Close"].iloc[-2]
                if prev == 0:
                    continue
                change_pct = (current - prev) / prev * 100

                if change_pct > 0.5:
                    trend = "상승"
                elif change_pct < -0.5:
                    trend = "하락"
                else:
                    trend = "보합"

                commodities.append(CommodityData(
                    symbol=symbol,
                    name=self.COMMODITY_NAMES.get(symbol, symbol),
                    price=round(current, 2),
                    change_pct=round(change_pct, 2),
                    trend=trend,
                ))
            except Exception as e:
                print(f"[원자재 조회 오류] {symbol}: {e}")

        return commodities

    def get_commodity_changes(self) -> Dict[str, float]:
        """원자재 가격 변동률 딕셔너리 (신호생성기용, USD/KRW 포함)"""
        commodities = self.get_commodity_prices()
        changes = {c.symbol: c.change_pct for c in commodities}

        # USD/KRW 환율 변동도 포함
        rates = self.get_exchange_rates()
        if "USD/KRW" in rates:
            changes["X:USDKRW"] = rates["USD/KRW"].get("change_pct", 0)

        return changes

    # --------------------------------------------------
    # 시장 종합 분석
    # --------------------------------------------------
    def get_market_overview(self) -> Dict[str, Any]:
        """시장 전체 개요"""
        overview = {
            "timestamp": datetime.datetime.now().isoformat(),
            "exchange_rates": self.get_exchange_rates(),
            "commodities": [],
            "market_sentiment": "중립",
        }

        commodities = self.get_commodity_prices()
        overview["commodities"] = [
            {
                "name": c.name,
                "price": c.price,
                "change_pct": c.change_pct,
                "trend": c.trend,
            }
            for c in commodities
        ]

        # 원자재 전반 분위기 (기본)
        if commodities:
            avg_change = sum(c.change_pct for c in commodities) / len(commodities)
            if avg_change > 1:
                overview["market_sentiment"] = "원자재 강세"
            elif avg_change < -1:
                overview["market_sentiment"] = "원자재 약세"

        # Claude 시장 해석 추가
        from config import STRATEGY
        if self.claude and STRATEGY.use_claude_overview:
            try:
                claude_analysis = self.claude.interpret_market_overview(overview)
                overview["claude_analysis"] = claude_analysis
                if claude_analysis.get("sentiment"):
                    overview["market_sentiment"] = claude_analysis["sentiment"]
            except Exception as e:
                print(f"[Claude 시장 해석 오류] {e}")

        return overview
