"""
股票代碼 / 名稱解析工具
支援台股（上市 .TW、上櫃 .TWO）
"""

import re
import requests

# 常見台股對照表（名稱 → 代碼）
COMMON_STOCKS = {
    "台積電": "2330", "聯發科": "2454", "鴻海": "2317", "台塑": "1301",
    "南亞": "1303", "台化": "1326", "中華電": "2412", "富邦金": "2881",
    "國泰金": "2882", "玉山金": "2884", "兆豐金": "2886", "台新金": "2887",
    "第一金": "2892", "永豐金": "2890", "元大金": "2885", "合庫金": "5880",
    "聯電": "2303", "日月光": "3711", "瑞昱": "2379", "廣達": "2382",
    "仁寶": "2324", "英業達": "2356", "緯創": "3231", "和碩": "4938",
    "大立光": "3008", "台達電": "2308", "研華": "2395", "台灣大": "3045",
    "遠傳": "4904", "亞泥": "1102", "台泥": "1101", "統一": "1216",
    "統一超": "2912", "全家": "5903", "台汽電": "8926", "中鋼": "2002",
    "燿華": "2367", "友達": "2409", "群創": "3481", "彩晶": "6116",
    "華碩": "2357", "宏碁": "2353", "微星": "2377", "技嘉": "2376",
    "欣興": "3037", "臻鼎": "4958", "華通": "2313", "楠梓電": "2316",
    "嘉澤": "3533", "信驊": "5274", "矽力": "6415", "祥碩": "5269",
    "力積電": "6770", "世界先進": "5347", "穩懋": "3105", "宏捷科": "8086",
    "聯詠": "3034", "奇景": "3008", "創意": "3443", "金像電": "2368",
}

def resolve_stock(user_input: str) -> dict:
    """
    輸入股票代碼或名稱 → 回傳 {"code": "2330", "ticker": "2330.TW", "name": "台積電", "market": "上市"}
    """
    user_input = user_input.strip()

    # 純數字 → 直接當代碼
    if re.match(r"^\d{4,6}$", user_input):
        code = user_input
        ticker, market = _detect_market(code)
        name = _fetch_name(ticker)
        return {"code": code, "ticker": ticker, "name": name, "market": market}

    # 中文名稱 → 查對照表
    if user_input in COMMON_STOCKS:
        code = COMMON_STOCKS[user_input]
        ticker, market = _detect_market(code)
        return {"code": code, "ticker": ticker, "name": user_input, "market": market}

    # 嘗試從名稱模糊搜尋
    for name, code in COMMON_STOCKS.items():
        if user_input in name or name in user_input:
            ticker, market = _detect_market(code)
            return {"code": code, "ticker": ticker, "name": name, "market": market}

    # 最後嘗試直接用 Yahoo Finance 格式
    if user_input.endswith(".TW") or user_input.endswith(".TWO"):
        ticker = user_input.upper()
        code = ticker.split(".")[0]
        market = "上市" if ticker.endswith(".TW") else "上櫃"
        name = _fetch_name(ticker)
        return {"code": code, "ticker": ticker, "name": name, "market": market}

    raise ValueError(f"無法識別股票：{user_input}。請輸入4位數代碼（如 2330）或股票名稱（如 台積電）")


def _detect_market(code: str) -> tuple:
    """嘗試判斷上市或上櫃，回傳 (ticker, market)"""
    import yfinance as yf
    # 先試上市
    ticker_tw = f"{code}.TW"
    try:
        info = yf.Ticker(ticker_tw).fast_info
        price = info.last_price
        if price and price > 0:
            return ticker_tw, "上市"
    except Exception:
        pass

    # 再試上櫃
    ticker_two = f"{code}.TWO"
    try:
        info = yf.Ticker(ticker_two).fast_info
        price = info.last_price
        if price and price > 0:
            return ticker_two, "上櫃"
    except Exception:
        pass

    # 預設返回上市
    return ticker_tw, "上市"


def _fetch_name(ticker: str) -> str:
    """從 yfinance 取得股票短名稱"""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker
