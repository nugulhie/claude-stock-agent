"""
========================================
Streamlit 분석 대시보드
========================================
실시간 시장 현황, 포트폴리오, 매매 신호를 한눈에
streamlit run dashboard.py
"""

import json
import datetime
import sys
import os
import time
import logging

# 에러 로그 설정
os.makedirs("data", exist_ok=True)
logging.basicConfig(
    filename="data/dashboard_errors.log",
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

sys.path.insert(0, os.path.dirname(__file__))

try:
    import streamlit as st
    import pandas as pd
except ImportError:
    print("pip install streamlit pandas --break-system-packages")
    sys.exit(1)

from modules.kis_api import KISApi
from modules.screener import StockScreener
from modules.market_data import MarketDataCollector
from modules.technical import TechnicalAnalyzer, Signal
from modules.portfolio import PortfolioManager
from config import STRATEGY, SECTORS

# 주요 종목 코드→이름 정적 매핑 (API 호출 없이 즉시 표시)
_STOCK_NAME_CACHE: dict = {
    "005490": "POSCO홀딩스", "004020": "현대제철", "001230": "동국제강",
    "010950": "S-Oil", "096770": "SK이노베이션", "267250": "HD현대",
    "051910": "LG화학", "010060": "OCI홀딩스", "011170": "롯데케미칼",
    "018470": "조일알미늄", "104700": "한국철강",
    "003670": "포스코퓨처엠", "005070": "코스모신소재",
    "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
    "035720": "카카오", "006400": "삼성SDI", "051900": "LG생활건강",
    "028260": "삼성물산", "012330": "현대모비스", "066570": "LG전자",
    "009150": "삼성전기", "032830": "삼성생명", "086790": "하나금융지주",
    "055550": "신한지주", "105560": "KB금융", "316140": "우리금융지주",
    "034730": "SK", "017670": "SK텔레콤", "030200": "KT",
    "000270": "기아", "005380": "현대차", "207940": "삼성바이오로직스",
    "068270": "셀트리온", "091990": "셀트리온헬스케어",
}


@st.cache_data(ttl=3600)
def lookup_stock_name(code: str) -> str:
    """종목코드로 종목명 조회 (캐시 1시간)"""
    if code in _STOCK_NAME_CACHE:
        return _STOCK_NAME_CACHE[code]
    try:
        price = kis.get_current_price(code)
        name = price.get("name", code)
        if name and name != code:
            _STOCK_NAME_CACHE[code] = name
            return name
    except Exception:
        pass
    return code


def show_code_names(codes_str: str):
    """입력된 종목코드들의 이름을 한 줄로 표시"""
    codes = [c.strip() for c in codes_str.split(",") if c.strip()]
    if not codes:
        return
    parts = []
    for code in codes:
        name = lookup_stock_name(code)
        parts.append(f"`{code}` {name}")
    st.caption("  ·  ".join(parts))


# --------------------------------------------------
# 페이지 설정
# --------------------------------------------------
st.set_page_config(
    page_title="한국주식 자동매매 대시보드",
    page_icon="📈",
    layout="wide",
)

st.title("📈 한국주식 자동매매 대시보드")
st.caption(f"업데이트: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# --------------------------------------------------
# 초기화 (세션 상태)
# --------------------------------------------------
@st.cache_resource
def init_modules():
    kis = KISApi()
    screener = StockScreener(kis)
    market = MarketDataCollector()
    tech = TechnicalAnalyzer()
    portfolio = PortfolioManager()
    return kis, screener, market, tech, portfolio


kis, screener, market, tech, portfolio = init_modules()


# --------------------------------------------------
# 사이드바
# --------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")
    mode = st.selectbox("매매 모드", ["모의투자", "실전투자"])
    st.metric("초기 자본", f"{STRATEGY.initial_capital:,}원")
    st.metric("목표 금액", f"{STRATEGY.target_capital:,}원")
    st.divider()

    st.subheader("전략 파라미터")
    st.text(f"손절: {STRATEGY.stop_loss_pct*100:.0f}%")
    st.text(f"익절: {STRATEGY.take_profit_pct*100:.0f}%")
    st.text(f"트레일링 스탑: {STRATEGY.trailing_stop_pct*100:.0f}%")
    st.text(f"최대 보유: {STRATEGY.max_positions}종목")
    st.divider()

    st.subheader("분석 가중치")
    st.text(f"기술적: {STRATEGY.technical_weight*100:.0f}%")
    st.text(f"펀더멘털: {STRATEGY.fundamental_weight*100:.0f}%")
    st.text(f"원자재: {STRATEGY.commodity_weight*100:.0f}%")
    st.text(f"뉴스: {STRATEGY.news_weight*100:.0f}%")

    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()


# --------------------------------------------------
# 탭 구성
# --------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌍 시장 현황", "📊 매매 신호", "💼 포트폴리오",
    "🔍 종목 분석", "📜 매매 기록", "🧠 분석 이력"
])


# --------------------------------------------------
# 탭1: 시장 현황
# --------------------------------------------------
with tab1:
    st.subheader("환율 현황")
    try:
        rates = market.get_exchange_rates()
        if rates:
            cols = st.columns(len(rates))
            for i, (name, info) in enumerate(rates.items()):
                delta = f"{info['change_pct']:+.2f}%"
                cols[i].metric(name, f"{info['rate']:,.2f}", delta)
        else:
            st.info("환율 데이터를 불러오는 중입니다...")
    except Exception as e:
        st.error(f"환율 조회 실패: {e}")

    st.divider()
    st.subheader("국제 원자재")
    try:
        commodities = market.get_commodity_prices()
        if commodities:
            cols = st.columns(min(len(commodities), 6))
            for i, c in enumerate(commodities):
                color = "🟢" if c.change_pct > 0 else "🔴" if c.change_pct < 0 else "⚪"
                cols[i % 6].metric(
                    f"{color} {c.name}",
                    f"${c.price:,.2f}",
                    f"{c.change_pct:+.2f}%"
                )
        else:
            st.info("원자재 데이터 로딩 중... (yfinance 필요)")
    except Exception as e:
        st.error(f"원자재 조회 실패: {e}")

    st.divider()
    st.subheader("거래량 상위 종목")
    try:
        vol_rank = kis.get_volume_rank(limit=15)
        if vol_rank:
            df = pd.DataFrame(vol_rank)
            df = df.rename(columns={
                "code": "종목코드", "name": "종목명", "price": "현재가",
                "change_pct": "등락률(%)", "volume": "거래량", "trade_amount": "거래대금",
            })
            df["현재가"] = df["현재가"].apply(lambda x: f"{x:,}")
            df["거래량"] = df["거래량"].apply(lambda x: f"{x:,}")
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"거래량 조회 실패 (API 키 확인 필요): {e}")


# --------------------------------------------------
# 탭2: 매매 신호
# --------------------------------------------------
with tab2:
    st.subheader("실시간 매매 신호")

    analysis_codes = st.text_input(
        "분석할 종목 코드 (쉼표 구분)",
        value=",".join(list(SECTORS.commodity_stocks.values())[0][:3]),
        help="예: 005490,010950,051910"
    )
    show_code_names(analysis_codes)

    if st.button("🔍 신호 생성", type="primary"):
        codes = [c.strip() for c in analysis_codes.split(",") if c.strip()]
        commodity_changes = market.get_commodity_changes()

        signals = []
        progress = st.progress(0)

        for i, code in enumerate(codes):
            # 종목 간 딜레이 (rate limit 방지)
            if i > 0:
                time.sleep(1.0)
            try:
                price_data = kis.get_current_price(code)
                stock_name = price_data.get("name", code)
                daily = kis.get_daily_prices(code, count=60)
                financial = kis.get_financial_data(code)
                tech_score = tech.get_technical_score(daily)
                news_score, _ = market.get_news_sentiment_score(code)

                # 실제 펀더멘털/원자재 점수 계산
                fund_score, _, _ = screener.screen_fundamentals(code, price_data, financial)
                comm_score, _ = screener.analyze_commodity_sensitivity(code, commodity_changes)

                signal = tech.generate_signal(
                    stock_code=code,
                    stock_name=stock_name,
                    daily_prices=daily,
                    fundamental_score=fund_score,
                    commodity_score=comm_score,
                    news_score=news_score,
                )
                signals.append(signal)
            except Exception as e:
                logging.warning(f"매매신호 오류 [{code}]: {e}")
                st.warning(f"{code}: {e}")

            progress.progress((i + 1) / len(codes))

        if signals:
            for sig in sorted(signals, key=lambda s: s.confidence, reverse=True):
                color = {
                    Signal.STRONG_BUY: "🟢🟢",
                    Signal.BUY: "🟢",
                    Signal.HOLD: "🟡",
                    Signal.SELL: "🔴",
                    Signal.STRONG_SELL: "🔴🔴",
                }.get(sig.signal, "⚪")

                with st.expander(
                    f"{color} {sig.name} ({sig.code}) - {sig.signal.value} "
                    f"[신뢰도 {sig.confidence:.0f}%]"
                ):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("현재가", f"{sig.price:,}원")
                    col2.metric("목표가", f"{sig.target_price:,}원")
                    col3.metric("손절가", f"{sig.stop_loss_price:,}원")

                    st.markdown("**매수/매도 근거:**")
                    for r in sig.reasons:
                        st.markdown(f"- {r}")

                    st.markdown("**기술 지표:**")
                    indicators_df = pd.DataFrame(
                        [sig.indicators], index=["값"]
                    ).T
                    st.dataframe(indicators_df, use_container_width=True)


# --------------------------------------------------
# 탭3: 포트폴리오
# --------------------------------------------------
with tab3:
    st.subheader("포트폴리오 현황")

    summary = portfolio.get_portfolio_summary()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 평가금액", summary["총평가금액"])
    col2.metric("총 손익", summary["총손익"])
    col3.metric("수익률", summary["총수익률"])
    col4.metric("목표 달성률", summary["목표달성률"])

    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("현금", summary["현금"])
    col2.metric("보유 종목 수", summary["보유종목수"])

    if summary["보유종목"]:
        st.subheader("보유 종목")
        df = pd.DataFrame(summary["보유종목"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("매매 성과")
    stats = portfolio.get_performance_stats()
    if stats["총매매횟수"] > 0:
        cols = st.columns(4)
        cols[0].metric("승률", stats["승률"])
        cols[1].metric("평균 수익", stats["평균수익"])
        cols[2].metric("평균 손실", stats["평균손실"])
        cols[3].metric("손익비", stats["손익비"])


# --------------------------------------------------
# 탭4: 개별 종목 분석
# --------------------------------------------------
with tab4:
    st.subheader("종목 상세 분석")

    stock_code = st.text_input("종목 코드 입력", value="005490", help="예: 005490 (POSCO홀딩스)")
    show_code_names(stock_code)

    if st.button("📊 상세 분석", type="primary"):
        # 첫 호출 실패 시 1회 재시도
        for attempt in range(2):
            try:
                with st.spinner("분석 중..."):
                    price = kis.get_current_price(stock_code)
                    stock_name = price.get("name", stock_code)
                    daily = kis.get_daily_prices(stock_code, count=100)
                    financial = kis.get_financial_data(stock_code)

                    # 기본 정보 (종목코드 + 종목명)
                    st.markdown(f"### {stock_name} ({stock_code})")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("현재가", f"{price['price']:,}원",
                               f"{price['change_pct']:+.2f}%")
                    col2.metric("거래량", f"{price['volume']:,}")
                    col3.metric("PER", f"{price['per']:.1f}")
                    col4.metric("PBR", f"{price['pbr']:.2f}")

                    # 재무 정보
                    if financial:
                        st.subheader("재무 지표")
                        fin_cols = st.columns(4)
                        fin_cols[0].metric("ROE", f"{financial.get('roe', 0):.1f}%")
                        fin_cols[1].metric("부채비율", f"{financial.get('debt_ratio', 0):.0f}%")
                        fin_cols[2].metric("영업이익률", f"{financial.get('operating_margin', 0):.1f}%")
                        fin_cols[3].metric("매출성장률", f"{financial.get('revenue_growth', 0):.1f}%")

                    # 차트 (종가 추이)
                    if daily:
                        st.subheader("주가 추이 (최근 100일)")
                        chart_data = pd.DataFrame(list(reversed(daily)))
                        chart_data["date"] = pd.to_datetime(chart_data["date"], format="%Y%m%d")
                        chart_data.set_index("date", inplace=True)
                        st.line_chart(chart_data["close"])

                        st.subheader("거래량 추이")
                        st.bar_chart(chart_data["volume"])
                break  # 성공 시 루프 종료
            except Exception as e:
                logging.warning(f"종목분석 오류 [{stock_code}] 시도{attempt+1}: {e}")
                if attempt == 0:
                    time.sleep(1.5)  # 1.5초 후 재시도
                else:
                    st.error(f"분석 실패: {e}")


# --------------------------------------------------
# 탭5: 매매 기록
# --------------------------------------------------
with tab5:
    st.subheader("매매 기록")

    log_path = os.path.join(os.path.dirname(__file__), "data", "trades.json")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            trades = json.load(f)

        if trades:
            df = pd.DataFrame(trades)
            df = df.rename(columns={
                "timestamp": "시간", "code": "종목코드", "name": "종목명",
                "side": "구분", "qty": "수량", "price": "가격",
                "reason": "사유", "signal_score": "신호점수", "profit_pct": "수익률",
            })
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("매매 기록이 없습니다.")
    else:
        st.info("아직 매매 기록이 없습니다. 자동매매를 실행하면 여기에 기록됩니다.")


# --------------------------------------------------
# 탭6: 분석 이력
# --------------------------------------------------
with tab6:
    st.subheader("종목 분석 이력")

    dec_path = os.path.join(os.path.dirname(__file__), "data", "decisions.jsonl")
    if not os.path.exists(dec_path):
        st.info("아직 분석 이력이 없습니다.")
    else:
        records = []
        with open(dec_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

        if not records:
            st.info("분석 이력이 없습니다.")
        else:
            # 필터
            col1, col2 = st.columns(2)
            signal_filter = col1.multiselect(
                "신호 필터",
                ["강력매수", "매수", "보유", "매도", "강력매도"],
                default=["강력매수", "매수"],
            )
            show_all = col2.checkbox("전체 보기", value=False)

            # 데이터 변환
            rows = []
            for r in reversed(records):  # 최신순
                sig = r.get("signal", "")
                if not show_all and signal_filter and sig not in signal_filter:
                    continue
                rows.append({
                    "시간": r.get("timestamp", ""),
                    "종목코드": r.get("code", ""),
                    "종목명": r.get("name", ""),
                    "신호": sig,
                    "종합점수": round(r.get("final_score", 0), 1),
                    "신뢰도": f"{r.get('confidence', 0):.0f}%",
                    "기술": round(r.get("scores", {}).get("technical", 0), 1),
                    "펀더멘털": round(r.get("scores", {}).get("fundamental", 0), 1),
                    "원자재": round(r.get("scores", {}).get("commodity", 0), 1),
                    "뉴스": round(r.get("scores", {}).get("news", 0), 1),
                    "Claude판단": r.get("claude_decision", "-") or "-",
                    "액션": r.get("action", ""),
                })

            if not rows:
                st.info("해당 신호 조건의 분석 이력이 없습니다.")
            else:
                st.caption(f"총 {len(records)}건 분석 / 표시: {len(rows)}건")
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # 선택한 종목 상세 보기
                st.divider()
                st.subheader("판단 근거 상세")
                selected_idx = st.number_input("행 번호 (0부터)", min_value=0, max_value=max(0, len(rows)-1), value=0)
                if rows:
                    r = list(reversed(records))
                    # 필터된 rows의 selected_idx번째에 해당하는 원본 record 찾기
                    filtered = [rec for rec in reversed(records)
                                if (show_all or not signal_filter or rec.get("signal", "") in signal_filter)]
                    if selected_idx < len(filtered):
                        rec = filtered[selected_idx]
                        st.markdown(f"**{rec.get('name', rec.get('code'))} ({rec.get('code')})** — {rec.get('timestamp')}")
                        st.markdown("**근거:**")
                        for reason in rec.get("reasons", []):
                            st.markdown(f"- {reason}")
                        if rec.get("risk_flags"):
                            st.markdown("**리스크:**")
                            for flag in rec.get("risk_flags", []):
                                st.markdown(f"- ⚠️ {flag}")
                        if rec.get("claude_reasoning"):
                            st.markdown(f"**Claude 판단:** {rec['claude_reasoning']}")


# --------------------------------------------------
# 푸터
# --------------------------------------------------
st.divider()
st.caption(
    "⚠️ 이 도구는 투자 보조 도구이며 투자 권유가 아닙니다. "
    "모든 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다."
)
