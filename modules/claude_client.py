"""
========================================
Claude AI 연동 모듈
========================================
뉴스 감성 분석, 시장 해석, 최종 매매 판단
"""

import re
import json
import logging
from typing import List, Dict, Tuple, Optional, Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

try:
    import anthropic
except ImportError:
    anthropic = None

log = logging.getLogger("ClaudeClient")


class ClaudeClient:
    """Claude API 클라이언트"""

    def __init__(self):
        if not anthropic:
            raise ImportError("pip install anthropic")
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY 환경변수를 설정하세요")
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL

    # --------------------------------------------------
    # 핵심 API 호출
    # --------------------------------------------------
    def _call_claude(self, system_prompt: str, user_prompt: str,
                     max_tokens: int = 1024) -> str:
        """Claude API 호출 (재시도 1회)"""
        for attempt in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text
            except Exception as e:
                if attempt == 0:
                    log.warning(f"Claude API 재시도: {e}")
                else:
                    raise

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Claude 응답에서 JSON 추출"""
        # 1) 코드 펜스 내부
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 2) 전체 텍스트
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 3) 첫 { ~ 마지막 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    # --------------------------------------------------
    # 1. 뉴스 감성 분석
    # --------------------------------------------------
    def analyze_news_sentiment(self, titles: List[str]) -> Tuple[float, List[str]]:
        """
        뉴스 제목 리스트 → 감성 점수 + 요약
        Returns: (overall_score: -100~+100, reasons: List[str])
        """
        if not titles:
            return 0.0, ["뉴스 없음"]

        system = """당신은 한국 주식 시장 뉴스 감성 분석 전문가입니다.
주어진 뉴스 제목들의 투자 심리 영향을 평가합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "overall_score": -100에서 +100 사이 정수,
  "summary": "전반적 뉴스 분위기 1~2문장",
  "key_news": ["가장 영향력 큰 뉴스 해석 1", "해석 2"]
}

점수 기준:
+80~+100: 매우 강한 호재 (사상최대 실적, 대규모 수주)
+40~+79: 호재 (실적 개선, 목표가 상향)
-39~+39: 중립
-79~-40: 악재 (실적 부진, 소송)
-100~-80: 매우 강한 악재 (상폐 위험, 대규모 적자)

한국 시장 맥락 반영: 외국인 순매수=호재, 공매도 증가=약한 악재, 정부 정책=맥락에 따라 판단."""

        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles[:15]))
        user = f"다음 뉴스 제목들을 분석해주세요:\n\n{numbered}"

        try:
            raw = self._call_claude(system, user, max_tokens=512)
            data = self._parse_json(raw)
            if data:
                score = max(-100, min(100, data.get("overall_score", 0)))
                reasons = data.get("key_news", [])
                summary = data.get("summary", "")
                if summary:
                    reasons = [summary] + reasons
                return float(score), reasons
        except Exception as e:
            log.warning(f"Claude 뉴스 분석 실패: {e}")

        return 0.0, ["Claude 분석 실패 → 기본값"]

    # --------------------------------------------------
    # 2. 시장 종합 해석
    # --------------------------------------------------
    def interpret_market_overview(self, overview: Dict) -> Dict:
        """
        환율/원자재 데이터 → Claude의 시장 해석
        Returns: {sentiment, score, insights, sector_implications, risks}
        """
        system = """당신은 한국 주식 시장 매크로 분석가입니다.
환율과 원자재 데이터를 종합 해석하여 한국 주식 투자 인사이트를 제공합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "sentiment": "강세" | "약세" | "중립" | "혼조",
  "score": -100에서 +100,
  "insights": ["핵심 인사이트 1~3개"],
  "sector_implications": {
    "철강": "한줄 영향 분석",
    "정유": "한줄 영향 분석",
    "화학": "한줄 영향 분석"
  },
  "risks": ["리스크 1~2개"],
  "summary": "전체 시장 상황 2~3문장"
}

중요:
- 환율과 원자재의 교차 영향 분석 (유가↑+원화약세 = 정유사 이중 수혜)
- 한국 수출 기업에 대한 영향 포함
- 당일 트레이딩에 실질적으로 유용한 인사이트만"""

        # 데이터 정리
        rates_str = ""
        for name, info in overview.get("exchange_rates", {}).items():
            rates_str += f"  {name}: {info['rate']:,.2f} ({info['change_pct']:+.2f}%)\n"

        comm_str = ""
        for c in overview.get("commodities", []):
            comm_str += f"  {c['name']}: ${c['price']:,.2f} ({c['change_pct']:+.2f}%) {c['trend']}\n"

        user = f"""오늘 시장 데이터:

[환율]
{rates_str or '  데이터 없음'}
[국제 원자재]
{comm_str or '  데이터 없음'}"""

        try:
            raw = self._call_claude(system, user, max_tokens=768)
            data = self._parse_json(raw)
            if data:
                return {
                    "sentiment": data.get("sentiment", "중립"),
                    "score": max(-100, min(100, data.get("score", 0))),
                    "insights": data.get("insights", []),
                    "sector_implications": data.get("sector_implications", {}),
                    "risks": data.get("risks", []),
                    "summary": data.get("summary", ""),
                }
        except Exception as e:
            log.warning(f"Claude 시장 해석 실패: {e}")

        return {"sentiment": "중립", "score": 0, "insights": [],
                "sector_implications": {}, "risks": [], "summary": ""}

    # --------------------------------------------------
    # 3. 최종 매매 판단
    # --------------------------------------------------
    def make_trading_decision(self, data: Dict) -> Optional[Dict]:
        """
        모든 분석 데이터 → Claude의 최종 BUY/SELL/HOLD 판단
        Returns: {decision, confidence, reasoning, ...} or None
        """
        system = """당신은 한국 주식 자동매매 시스템의 최종 투자 의사결정자입니다.
기계적 점수 + 시장 맥락 + 뉴스 + 포트폴리오 상태를 종합하여 판단합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0~100 정수,
  "position_size_pct": 0.0~0.4 (BUY 시 추천 투자 비율),
  "reasoning": "3~5문장 종합 판단 근거",
  "key_factors": ["핵심 판단 요인 1~3개"],
  "risk_assessment": "리스크 1~2문장",
  "target_price": 목표가 정수 (BUY 시, 아니면 0),
  "stop_loss_price": 손절가 정수 (BUY 시, 아니면 0),
  "time_horizon": "단기" | "중기" | "스윙"
}

투자 원칙:
- 보수적 판단. 확신 없으면 HOLD
- 리스크 플래그 2개 이상이면 BUY 금지
- 기계적 점수 60 미만이면 BUY confidence 70 이하로
- 동일 섹터 편중 회피
- 현금 비율 5% 이상 유지"""

        # 사용자 프롬프트 구성
        stock = data.get("stock", {})
        indicators = data.get("indicators", {})
        portfolio = data.get("portfolio", {})
        market = data.get("market_overview", {})

        user = f"""[종목 정보]
  종목: {stock.get('name', '')} ({stock.get('code', '')})
  현재가: {stock.get('price', 0):,}원
  등락률: {stock.get('change_pct', 0):+.2f}%

[기계적 분석 점수]
  종합점수: {indicators.get('종합점수', 0):.1f}/100
  기술점수: {indicators.get('기술점수', 0):.1f}
  펀더멘털: {data.get('fundamental_score', 0):.1f}
  원자재: {data.get('commodity_score', 0):.1f}
  뉴스점수: {data.get('news_score', 0):.1f}

[기술적 지표]
  RSI: {indicators.get('RSI', 0):.1f}
  MACD: {indicators.get('MACD', 0):.2f} (시그널: {indicators.get('MACD_Signal', 0):.2f})
  SMA5: {indicators.get('SMA_5', 0):,.0f} / SMA20: {indicators.get('SMA_20', 0):,.0f} / SMA60: {indicators.get('SMA_60', 0):,.0f}

[기계적 신호]
  신호: {data.get('mechanical_signal', '')}
  신뢰도: {data.get('mechanical_confidence', 0):.0f}%
  매매 근거: {'; '.join(data.get('reasons', [])[:5])}
  리스크: {'; '.join(data.get('risk_flags', []))}

[뉴스 감성 (Claude 분석)]
  {'; '.join(data.get('news_reasons', [])[:3]) or '없음'}

[시장 상황]
  {market.get('summary', '데이터 없음')}

[현재 포트폴리오]
  보유종목수: {portfolio.get('positions', 0)}개 / 최대 5개
  현금비율: {portfolio.get('cash_pct', 100):.0f}%
  일일 수익률: {portfolio.get('daily_return_pct', 0):+.1f}%"""

        try:
            raw = self._call_claude(system, user, max_tokens=768)
            result = self._parse_json(raw)
            if result and result.get("decision") in ("BUY", "SELL", "HOLD"):
                result["confidence"] = max(0, min(100, result.get("confidence", 50)))
                result["position_size_pct"] = max(0.0, min(0.4, result.get("position_size_pct", 0.1)))
                return result
        except Exception as e:
            log.warning(f"Claude 매매 판단 실패: {e}")

        return None
