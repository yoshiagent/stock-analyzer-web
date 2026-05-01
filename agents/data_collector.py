"""
Agent 1：股票數據收集
負責抓取所有原始數據，供其他 Agent 使用
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def run(stock_info: dict) -> dict:
    """
    stock_info: {"code": "2330", "ticker": "2330.TW", "name": "台積電", "market": "上市"}
    回傳完整原始數據字典
    """
    ticker = stock_info["ticker"]
    code = stock_info["code"]
    print(f"  [Agent 1] 開始收集 {stock_info['name']}（{ticker}）數據...")

    yf_ticker = yf.Ticker(ticker)

    # --- 基本資訊 ---
    info = {}
    try:
        info = yf_ticker.info
    except Exception as e:
        logger.warning(f"取得 info 失敗: {e}")

    # --- 歷史價格（1年） ---
    hist = pd.DataFrame()
    try:
        hist = yf_ticker.history(period="1y", auto_adjust=True)
        hist.index = pd.to_datetime(hist.index)
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
    except Exception as e:
        logger.warning(f"取得歷史價格失敗: {e}")

    # --- 財務報表 ---
    income_stmt = pd.DataFrame()
    balance_sheet = pd.DataFrame()
    cashflow = pd.DataFrame()
    try:
        income_stmt = yf_ticker.financials        # 年度損益表
        balance_sheet = yf_ticker.balance_sheet   # 資產負債表
        cashflow = yf_ticker.cashflow             # 現金流量表
    except Exception as e:
        logger.warning(f"取得財報失敗: {e}")

    # --- 季度財報 ---
    quarterly_income = pd.DataFrame()
    try:
        quarterly_income = yf_ticker.quarterly_financials
    except Exception as e:
        logger.warning(f"取得季報失敗: {e}")

    # --- 股利資訊 ---
    dividends = pd.Series(dtype=float)
    try:
        dividends = yf_ticker.dividends
        if dividends.index.tz is not None:
            dividends.index = dividends.index.tz_localize(None)
    except Exception as e:
        logger.warning(f"取得股利資料失敗: {e}")

    # --- TWSE 三大法人數據（近30個交易日） ---
    institutional = _fetch_institutional(code)

    # --- TWSE 融資融券 ---
    margin = _fetch_margin(code)

    # --- 整合當日關鍵數字 ---
    current_price = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice") or \
                    (hist["Close"].iloc[-1] if not hist.empty else None)
    prev_close = _safe(info, "previousClose") or (hist["Close"].iloc[-2] if len(hist) > 1 else None)
    change_pct = ((current_price - prev_close) / prev_close * 100) if (current_price and prev_close) else None

    summary = {
        "name": stock_info.get("name", _safe(info, "shortName", ticker)),
        "code": code,
        "ticker": ticker,
        "market": stock_info.get("market", "上市"),
        "current_price": _round(current_price),
        "prev_close": _round(prev_close),
        "change_pct": _round(change_pct),
        "open": _round(_safe(info, "open") or (hist["Open"].iloc[-1] if not hist.empty else None)),
        "high": _round(_safe(info, "dayHigh") or (hist["High"].iloc[-1] if not hist.empty else None)),
        "low": _round(_safe(info, "dayLow") or (hist["Low"].iloc[-1] if not hist.empty else None)),
        "volume": _safe(info, "volume") or (int(hist["Volume"].iloc[-1]) if not hist.empty else None),
        "avg_volume": _round(_safe(info, "averageVolume")),
        "market_cap": _safe(info, "marketCap"),
        "week52_high": _round(_safe(info, "fiftyTwoWeekHigh")),
        "week52_low": _round(_safe(info, "fiftyTwoWeekLow")),
        "pe_ratio": _round(_safe(info, "trailingPE")),
        "forward_pe": _round(_safe(info, "forwardPE")),
        "pb_ratio": _round(_safe(info, "priceToBook")),
        "eps_ttm": _round(_safe(info, "trailingEps")),
        "eps_forward": _round(_safe(info, "forwardEps")),
        "dividend_yield": _round((_safe(info, "dividendYield") or 0) * 100, 2),
        "dividend_rate": _round(_safe(info, "dividendRate")),
        "roe": _round((_safe(info, "returnOnEquity") or 0) * 100, 2),
        "roa": _round((_safe(info, "returnOnAssets") or 0) * 100, 2),
        "gross_margin": _round((_safe(info, "grossMargins") or 0) * 100, 2),
        "operating_margin": _round((_safe(info, "operatingMargins") or 0) * 100, 2),
        "profit_margin": _round((_safe(info, "profitMargins") or 0) * 100, 2),
        "debt_to_equity": _round(_safe(info, "debtToEquity")),
        "current_ratio": _round(_safe(info, "currentRatio")),
        "beta": _round(_safe(info, "beta")),
        "industry": _safe(info, "industry"),
        "sector": _safe(info, "sector"),
        "employees": _safe(info, "fullTimeEmployees"),
        "description": (_safe(info, "longBusinessSummary") or "")[:500],
    }

    print(f"  [Agent 1] 數據收集完成：現價 {current_price}，歷史 {len(hist)} 筆，法人 {len(institutional)} 筆")

    return {
        "summary": summary,
        "hist": hist,
        "income_stmt": income_stmt,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "quarterly_income": quarterly_income,
        "dividends": dividends,
        "institutional": institutional,
        "margin": margin,
        "raw_info": info,
    }


def _fetch_institutional(code: str) -> list:
    """從 TWSE 抓取近30日三大法人買賣超"""
    results = []
    try:
        import requests
        from datetime import datetime, timedelta

        # 嘗試最近幾個月的資料
        today = datetime.today()
        for months_back in range(0, 3):
            check_date = today - timedelta(days=months_back * 30)
            date_str = check_date.strftime("%Y%m%d")
            url = (f"https://www.twse.com.tw/fund/T86"
                   f"?response=json&date={date_str}&selectType=ALLBUT0999")
            try:
                resp = requests.get(url, timeout=10,
                                    headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()
                if data.get("stat") == "OK" and data.get("data"):
                    for row in data["data"]:
                        if len(row) >= 8 and row[0] == code:
                            results.append({
                                "date": data.get("date", date_str),
                                "foreign_net": _parse_tw_num(row[4]),
                                "trust_net": _parse_tw_num(row[7]),
                                "dealer_net": _parse_tw_num(row[10]) if len(row) > 10 else 0,
                                "total_net": _parse_tw_num(row[len(row)-1]),
                            })
                    if results:
                        break
            except Exception:
                continue

        # 如果上市資料找不到，嘗試 TWSE 個股法人
        if not results:
            results = _fetch_institutional_single(code)

    except Exception as e:
        logger.warning(f"三大法人資料取得失敗: {e}")

    return results


def _fetch_institutional_single(code: str) -> list:
    """用個股法人 API 抓近期資料"""
    results = []
    try:
        import requests
        from datetime import datetime, timedelta

        today = datetime.today()
        for months_back in range(0, 4):
            check_date = today - timedelta(days=months_back * 30)
            date_str = check_date.strftime("%Y%m%d")
            url = (f"https://www.twse.com.tw/fund/FMTQIK"
                   f"?response=json&date={date_str}&stockNo={code}")
            try:
                resp = requests.get(url, timeout=10,
                                    headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()
                if data.get("stat") == "OK" and data.get("data"):
                    for row in data["data"]:
                        if len(row) >= 5:
                            results.append({
                                "date": row[0],
                                "foreign_net": _parse_tw_num(row[1]),
                                "trust_net": _parse_tw_num(row[2]),
                                "dealer_net": _parse_tw_num(row[3]),
                                "total_net": _parse_tw_num(row[4]),
                            })
                    if results:
                        return results[-30:]  # 近30筆
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"個股法人 API 失敗: {e}")
    return results


def _fetch_margin(code: str) -> dict:
    """從 TWSE 抓融資融券資料"""
    try:
        import requests
        from datetime import datetime, timedelta

        today = datetime.today()
        date_str = today.strftime("%Y%m%d")
        url = (f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
               f"?response=json&date={date_str}&stockNo={code}")
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()
        if data.get("stat") == "OK" and data.get("data"):
            last = data["data"][-1]
            return {
                "date": last[0] if len(last) > 0 else "",
                "margin_buy": 0,
                "margin_sell": 0,
                "short_sell": 0,
                "short_cover": 0,
            }
    except Exception as e:
        logger.warning(f"融資融券資料失敗: {e}")
    return {}


def _safe(d: dict, key: str, default=None):
    val = d.get(key)
    if val in (None, "N/A", "", float("inf"), float("-inf")):
        return default
    try:
        if isinstance(val, float) and (val != val):  # NaN check
            return default
    except Exception:
        pass
    return val


def _round(val, digits=2):
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


def _parse_tw_num(s: str) -> int:
    """把台灣數字格式（含逗號、負號）轉成整數"""
    try:
        return int(str(s).replace(",", "").replace("+", "").strip())
    except (ValueError, AttributeError):
        return 0
