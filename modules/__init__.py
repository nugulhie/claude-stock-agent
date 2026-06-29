"""Project module exports with lazy imports.

Importing a single submodule should not require optional runtime dependencies
from unrelated modules such as yfinance or pandas.
"""

__all__ = [
    "KISApi",
    "StockScreener",
    "StockScore",
    "MarketDataCollector",
    "NewsItem",
    "CommodityData",
    "TechnicalAnalyzer",
    "Signal",
    "TradeSignal",
    "PortfolioManager",
    "Position",
    "TradeLog",
    "DecisionLog",
    "ClaudeClient",
]


def __getattr__(name):
    if name == "KISApi":
        from .kis_api import KISApi
        return KISApi
    if name in {"StockScreener", "StockScore"}:
        from .screener import StockScreener, StockScore
        return {"StockScreener": StockScreener, "StockScore": StockScore}[name]
    if name in {"MarketDataCollector", "NewsItem", "CommodityData"}:
        from .market_data import MarketDataCollector, NewsItem, CommodityData
        return {
            "MarketDataCollector": MarketDataCollector,
            "NewsItem": NewsItem,
            "CommodityData": CommodityData,
        }[name]
    if name in {"TechnicalAnalyzer", "Signal", "TradeSignal"}:
        from .technical import TechnicalAnalyzer, Signal, TradeSignal
        return {
            "TechnicalAnalyzer": TechnicalAnalyzer,
            "Signal": Signal,
            "TradeSignal": TradeSignal,
        }[name]
    if name in {"PortfolioManager", "Position", "TradeLog", "DecisionLog"}:
        from .portfolio import PortfolioManager, Position, TradeLog, DecisionLog
        return {
            "PortfolioManager": PortfolioManager,
            "Position": Position,
            "TradeLog": TradeLog,
            "DecisionLog": DecisionLog,
        }[name]
    if name == "ClaudeClient":
        from .claude_client import ClaudeClient
        return ClaudeClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
