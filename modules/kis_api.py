"""
========================================
KIS API 연동 모듈
========================================
한국투자증권 Open API를 통한 시세 조회, 주문, 잔고 조회
"""

import json
import os
import time
import datetime
import requests
from typing import Optional, Dict, List, Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_BASE_URL


_TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "kis_token.json")


class KISApi:
    """한국투자증권 Open API 클라이언트"""

    def __init__(self):
        self.base_url = KIS_BASE_URL
        self.app_key = KIS_APP_KEY
        self.app_secret = KIS_APP_SECRET
        self.account_no = KIS_ACCOUNT_NO.split("-")[0]
        self.account_cd = KIS_ACCOUNT_NO.split("-")[1] if "-" in KIS_ACCOUNT_NO else "01"
        self.access_token: Optional[str] = None
        self.token_expires: Optional[datetime.datetime] = None
        self._last_call_time: float = 0.0  # API 호출 간격 제어용
        self._load_token_cache()  # 파일에서 토큰 복원

    def _load_token_cache(self):
        """저장된 토큰 파일에서 복원"""
        try:
            with open(_TOKEN_CACHE_FILE, "r") as f:
                data = json.load(f)
            expires = datetime.datetime.fromisoformat(data["expires"])
            if datetime.datetime.now() < expires:
                self.access_token = data["token"]
                self.token_expires = expires
        except Exception:
            pass

    def _save_token_cache(self):
        """토큰을 파일에 저장"""
        try:
            os.makedirs(os.path.dirname(_TOKEN_CACHE_FILE), exist_ok=True)
            with open(_TOKEN_CACHE_FILE, "w") as f:
                json.dump({
                    "token": self.access_token,
                    "expires": self.token_expires.isoformat(),
                }, f)
        except Exception:
            pass

    def _rate_limit(self, interval: float = 0.2):
        """초당 5건 수준으로 보수적 간격 유지 (모의투자 서버 rate limit 대응)"""
        elapsed = time.time() - self._last_call_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_call_time = time.time()

    # --------------------------------------------------
    # 인증
    # --------------------------------------------------
    def get_access_token(self) -> str:
        """OAuth 접근 토큰 발급 (403 시 기존 토큰 재사용 또는 재시도)"""
        if self.access_token and self.token_expires and datetime.datetime.now() < self.token_expires:
            return self.access_token

        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        for attempt in range(3):
            try:
                res = requests.post(url, json=body, timeout=10)
                if res.status_code == 403:
                    # 모의투자 서버: 당일 토큰 재발급 제한 → 파일 캐시 또는 기존 토큰 재사용
                    if self.access_token:
                        self.token_expires = datetime.datetime.now() + datetime.timedelta(hours=6)
                        self._save_token_cache()
                        return self.access_token
                    raise requests.HTTPError(f"403 Forbidden: 토큰 발급 거부", response=res)
                res.raise_for_status()
                data = res.json()
                self.access_token = data["access_token"]
                self.token_expires = datetime.datetime.now() + datetime.timedelta(hours=12)
                self._save_token_cache()
                return self.access_token
            except requests.HTTPError as e:
                if "403" in str(e) and self.access_token:
                    self.token_expires = datetime.datetime.now() + datetime.timedelta(hours=6)
                    self._save_token_cache()
                    return self.access_token
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, 2s 재시도
                else:
                    raise

    def _headers(self, tr_id: str, hashkey: str = "") -> Dict[str, str]:
        """공통 헤더 생성"""
        token = self.get_access_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def _get_hashkey(self, body: dict) -> str:
        """해시키 발급"""
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        res = requests.post(url, json=body, headers=headers, timeout=10)
        return res.json().get("HASH", "")

    # --------------------------------------------------
    # 시세 조회
    # --------------------------------------------------
    def get_current_price(self, stock_code: str) -> Dict[str, Any]:
        """
        주식 현재가 조회
        Returns: {price, change, change_pct, volume, high, low, open, market_cap, per, pbr, ...}
        """
        self._rate_limit()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
        }
        headers = self._headers("FHKST01010100")
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json().get("output", {})

        return {
            "code": stock_code,
            "name": data.get("hts_kor_isnm", stock_code),
            "price": int(data.get("stck_prpr", 0)),
            "change": int(data.get("prdy_vrss", 0)),
            "change_pct": float(data.get("prdy_ctrt", 0)),
            "volume": int(data.get("acml_vol", 0)),
            "trade_amount": int(data.get("acml_tr_pbmn", 0)),
            "high": int(data.get("stck_hgpr", 0)),
            "low": int(data.get("stck_lwpr", 0)),
            "open": int(data.get("stck_oprc", 0)),
            "high_52w": int(data.get("w52_hgpr", 0) or data.get("stck_dryy_hgpr", 0)),
            "low_52w": int(data.get("w52_lwpr", 0) or data.get("stck_dryy_lwpr", 0)),
            "market_cap": int(data.get("hts_avls", 0)) * 100_000_000,  # 억원 → 원
            "per": float(data.get("per", 0) or 0),
            "pbr": float(data.get("pbr", 0) or 0),
            "eps": float(data.get("eps", 0) or 0),
            "bps": float(data.get("bps", 0) or 0),
        }

    def get_daily_prices(self, stock_code: str, period: str = "D",
                         count: int = 100) -> List[Dict]:
        """
        일봉/주봉/월봉 데이터 조회 (차트 데이터 엔드포인트 사용)
        period: D(일), W(주), M(월)
        """
        self._rate_limit()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        end_date = datetime.date.today().strftime("%Y%m%d")
        # 영업일 기준 count개 확보를 위한 달력일 계산 (영업일 ≈ 달력일×5/7)
        calendar_days = min(int(count * 1.5) + 10, 150)
        start_date = (datetime.date.today() - datetime.timedelta(days=calendar_days)).strftime("%Y%m%d")

        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0",  # 수정주가
        }
        headers = self._headers("FHKST03010100")
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        items = res.json().get("output2", [])

        result = []
        for item in items[:count]:
            result.append({
                "date": item.get("stck_bsop_date", ""),
                "open": int(item.get("stck_oprc", 0) or 0),
                "high": int(item.get("stck_hgpr", 0) or 0),
                "low": int(item.get("stck_lwpr", 0) or 0),
                "close": int(item.get("stck_clpr", 0) or 0),
                "volume": int(item.get("acml_vol", 0) or 0),
                "change_pct": float(item.get("prdy_ctrt", 0) or 0),
            })
        return result

    def get_volume_rank(self, limit: int = 30) -> List[Dict]:
        """거래량 상위 종목 조회"""
        self._rate_limit()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": "",
        }
        headers = self._headers("FHPST01710000")
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        items = res.json().get("output", [])

        result = []
        for item in items[:limit]:
            result.append({
                "code": item.get("mksc_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "price": int(item.get("stck_prpr", 0)),
                "change_pct": float(item.get("prdy_ctrt", 0) or 0),
                "volume": int(item.get("acml_vol", 0)),
                "trade_amount": int(item.get("acml_tr_pbmn", 0)),
            })
        return result

    # --------------------------------------------------
    # 매매 주문
    # --------------------------------------------------
    def place_order(self, stock_code: str, qty: int, price: int = 0,
                    side: str = "buy", order_type: str = "market") -> Dict:
        """
        주문 실행
        side: 'buy' | 'sell'
        order_type: 'market' (시장가) | 'limit' (지정가)
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
        ord_dvsn = "01" if order_type == "market" else "00"

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_cd,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price) if order_type == "limit" else "0",
        }

        hashkey = self._get_hashkey(body)
        headers = self._headers(tr_id, hashkey)

        res = requests.post(url, json=body, headers=headers, timeout=10)
        res.raise_for_status()
        return res.json()

    # --------------------------------------------------
    # 잔고 조회
    # --------------------------------------------------
    def get_balance(self) -> Dict[str, Any]:
        """계좌 잔고 및 보유 종목 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        headers = self._headers("TTTC8434R")
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()

        data = res.json()
        holdings = []
        for item in data.get("output1", []):
            if int(item.get("hldg_qty", 0)) > 0:
                holdings.append({
                    "code": item.get("pdno", ""),
                    "name": item.get("prdt_name", ""),
                    "qty": int(item.get("hldg_qty", 0)),
                    "avg_price": float(item.get("pchs_avg_pric", 0)),
                    "current_price": int(item.get("prpr", 0)),
                    "profit_pct": float(item.get("evlu_pfls_rt", 0)),
                    "profit_amt": int(item.get("evlu_pfls_amt", 0)),
                })

        summary = data.get("output2", [{}])[0] if data.get("output2") else {}
        return {
            "holdings": holdings,
            "total_eval": int(summary.get("tot_evlu_amt", 0)),
            "total_profit": int(summary.get("evlu_pfls_smtl_amt", 0)),
            "cash": int(summary.get("dnca_tot_amt", 0)),
            "total_buy_amt": int(summary.get("pchs_amt_smtl_amt", 0)),
        }

    # --------------------------------------------------
    # 테마 조회
    # --------------------------------------------------
    def get_theme_list(self) -> List[Dict]:
        """테마 목록 조회 (등락률 순)"""
        try:
            self._rate_limit()
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/theme"
            params = {
                "FID_COND_MRKT_CLS_CODE": "N",
                "FID_COND_SCR_DIV_CODE": "20174",
                "FID_RANK_SORT_CLS_CODE": "0",
            }
            headers = self._headers("FHKST01740000")
            res = requests.get(url, params=params, headers=headers, timeout=10)
            res.raise_for_status()
            items = res.json().get("output", [])
            result = []
            for item in items:
                result.append({
                    "code": item.get("idx_cd", ""),
                    "name": item.get("idx_kor_isnm", ""),
                    "change_pct": float(item.get("bstp_nmix_prdy_ctrt", 0) or 0),
                })
            return [t for t in result if t["code"]]
        except Exception:
            return []

    def get_theme_stocks(self, theme_code: str, limit: int = 50) -> List[Dict]:
        """테마 내 종목 조회"""
        try:
            self._rate_limit()
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/theme-detail"
            params = {
                "FID_COND_MRKT_CLS_CODE": "N",
                "FID_COND_SCR_DIV_CODE": "20175",
                "FID_RANK_SORT_CLS_CODE": "0",
                "FID_INPUT_ISCD": theme_code,
            }
            headers = self._headers("FHKST01740200")
            res = requests.get(url, params=params, headers=headers, timeout=10)
            res.raise_for_status()
            items = res.json().get("output", [])
            result = []
            for item in items[:limit]:
                code = item.get("mksc_shrn_iscd", "")
                if code:
                    result.append({
                        "code": code,
                        "name": item.get("hts_kor_isnm", ""),
                        "change_pct": float(item.get("prdy_ctrt", 0) or 0),
                    })
            return result
        except Exception:
            return []

    # --------------------------------------------------
    # 재무제표 조회
    # --------------------------------------------------
    def get_financial_data(self, stock_code: str) -> Dict:
        """종목 재무 정보 조회 (실패 시 빈 딕셔너리 반환)"""
        try:
            self._rate_limit()
            url = f"{self.base_url}/uapi/domestic-stock/v1/finance/financial-ratio"
            params = {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": stock_code,
            }
            headers = self._headers("FHKST66430300")
            res = requests.get(url, params=params, headers=headers, timeout=10)
            res.raise_for_status()
            items = res.json().get("output", [])

            if not items:
                return {}

            latest = items[0]
            return {
                "code": stock_code,
                "roe": float(latest.get("roe_val", 0) or 0),
                "roa": float(latest.get("roa_val", 0) or 0),
                "debt_ratio": float(latest.get("lblt_rate", 0) or 0),
                "operating_margin": float(latest.get("bsop_prfi_inrt", 0) or 0),
                "net_margin": float(latest.get("thtr_ntin_inrt", 0) or 0),
                "revenue_growth": float(latest.get("sles_inrt", 0) or 0),
                "current_ratio": float(latest.get("crnt_rate", 0) or 0),
            }
        except Exception:
            # 모의투자 서버에서 재무 API 미지원 시 빈 딕셔너리 반환
            return {}
