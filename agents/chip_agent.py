"""
Agent 3：籌碼面分析
分析三大法人買賣超、融資融券、大股東持股動向
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def run(data: dict) -> dict:
    """
    輸入 Agent 1 的輸出，回傳籌碼面分析結果
    """
    s = data["summary"]
    code = s["code"]
    institutional = data.get("institutional", [])
    hist = data.get("hist", pd.DataFrame())

    print(f"  [Agent 3] 開始籌碼面分析：{s['name']}...")

    metrics = {}

    # --- 三大法人 ---
    inst_metrics = _analyze_institutional(institutional)
    metrics.update(inst_metrics)

    # --- 融資融券（補充抓取） ---
    margin_metrics = _fetch_and_analyze_margin(code)
    metrics.update(margin_metrics)

    # --- 主力籌碼評估（用法人+量能分析） ---
    if not hist.empty and len(hist) >= 20:
        metrics["volume_ratio"] = _calc_volume_ratio(hist)
        metrics["big_money_trend"] = _estimate_big_money(hist)
    else:
        metrics["volume_ratio"] = None
        metrics["big_money_trend"] = "資料不足"

    # --- 評級 ---
    rating = _evaluate(metrics)
    metrics["rating"] = rating["score"]
    metrics["rating_label"] = rating["label"]
    metrics["rating_color"] = rating["color"]
    metrics["signals"] = rating["signals"]
    metrics["analysis_text"] = _generate_analysis(s["name"], metrics)

    print(f"  [Agent 3] 籌碼面分析完成：{rating['label']}（{rating['score']}/100）")

    return metrics


def _analyze_institutional(institutional: list) -> dict:
    """分析三大法人近期動向"""
    result = {
        "inst_data": institutional,
        "foreign_net_5d": 0, "trust_net_5d": 0, "dealer_net_5d": 0, "total_net_5d": 0,
        "foreign_net_20d": 0, "trust_net_20d": 0, "dealer_net_20d": 0, "total_net_20d": 0,
        "foreign_consecutive": 0, "trust_consecutive": 0,
        "inst_trend": "中性",
    }

    if not institutional:
        return result

    recent = institutional[-20:] if len(institutional) >= 20 else institutional
    recent5 = institutional[-5:] if len(institutional) >= 5 else institutional

    for day in recent5:
        result["foreign_net_5d"] += day.get("foreign_net", 0)
        result["trust_net_5d"] += day.get("trust_net", 0)
        result["dealer_net_5d"] += day.get("dealer_net", 0)
        result["total_net_5d"] += day.get("total_net", 0)

    for day in recent:
        result["foreign_net_20d"] += day.get("foreign_net", 0)
        result["trust_net_20d"] += day.get("trust_net", 0)
        result["dealer_net_20d"] += day.get("dealer_net", 0)
        result["total_net_20d"] += day.get("total_net", 0)

    # 計算外資連買/連賣天數
    result["foreign_consecutive"] = _calc_consecutive(
        [d.get("foreign_net", 0) for d in institutional])
    result["trust_consecutive"] = _calc_consecutive(
        [d.get("trust_net", 0) for d in institutional])

    # 趨勢判斷
    fn20 = result["foreign_net_20d"]
    tn20 = result["trust_net_20d"]
    if fn20 > 0 and tn20 > 0:
        result["inst_trend"] = "多方"
    elif fn20 < 0 and tn20 < 0:
        result["inst_trend"] = "空方"
    elif fn20 > 0 or tn20 > 0:
        result["inst_trend"] = "偏多"
    elif fn20 < 0 or tn20 < 0:
        result["inst_trend"] = "偏空"

    return result


def _fetch_and_analyze_margin(code: str) -> dict:
    """從 TWSE 抓融資融券資料"""
    result = {
        "margin_balance": None,
        "short_balance": None,
        "margin_ratio": None,
        "margin_trend": "資料不足",
    }
    try:
        today = datetime.today()
        # 試最近幾個月
        for days_back in [0, 7, 14, 30]:
            date = today - timedelta(days=days_back)
            date_str = date.strftime("%Y%m%d")
            url = (f"https://www.twse.com.tw/exchangeReport/MI_MARGN"
                   f"?response=json&date={date_str}&selectType=ALL")
            try:
                resp = requests.get(url, timeout=8,
                                    headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()
                if data.get("stat") == "OK" and data.get("data"):
                    for row in data["data"]:
                        if len(row) >= 6 and row[0] == code:
                            result["margin_balance"] = _parse_num(row[3])   # 融資餘額
                            result["short_balance"] = _parse_num(row[8]) if len(row) > 8 else None  # 融券餘額
                            if result["margin_balance"] and result["short_balance"]:
                                total = result["margin_balance"] + result["short_balance"]
                                result["margin_ratio"] = round(
                                    result["margin_balance"] / total * 100, 1) if total > 0 else None
                            result["margin_trend"] = _judge_margin(
                                result["margin_balance"], result["short_balance"])
                            return result
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"融資融券抓取失敗: {e}")
    return result


def _judge_margin(margin, short) -> str:
    if margin is None or short is None:
        return "資料不足"
    if short == 0:
        return "無融券壓力"
    ratio = margin / short if short > 0 else 999
    if ratio > 5:
        return "融資多、融券少（市場偏多）"
    elif ratio < 1:
        return "融券比率高（偏空）"
    else:
        return "融資融券平衡"


def _calc_volume_ratio(hist: pd.DataFrame) -> float | None:
    """近5日均量 / 20日均量"""
    try:
        vol = hist["Volume"].dropna()
        if len(vol) < 20:
            return None
        r5 = vol.iloc[-5:].mean()
        r20 = vol.iloc[-20:].mean()
        return round(r5 / r20, 2) if r20 > 0 else None
    except Exception:
        return None


def _estimate_big_money(hist: pd.DataFrame) -> str:
    """根據量價關係估計主力動向"""
    try:
        df = hist.copy().tail(20)
        df["price_change"] = df["Close"].pct_change()
        df["vol_pct"] = df["Volume"].pct_change()

        up_days = df[df["price_change"] > 0.005]
        down_days = df[df["price_change"] < -0.005]

        avg_up_vol = up_days["Volume"].mean() if not up_days.empty else 0
        avg_down_vol = down_days["Volume"].mean() if not down_days.empty else 0

        if avg_up_vol > avg_down_vol * 1.3:
            return "量升價漲，主力偏多操作"
        elif avg_down_vol > avg_up_vol * 1.3:
            return "量縮價跌，主力偏空觀望"
        else:
            return "量價走勢中性"
    except Exception:
        return "無法估算"


def _calc_consecutive(values: list) -> int:
    """計算最近連續買超或賣超天數（正=連買，負=連賣）"""
    if not values:
        return 0
    last = values[-1]
    if last == 0:
        return 0
    direction = 1 if last > 0 else -1
    count = 0
    for v in reversed(values):
        if (v > 0 and direction > 0) or (v < 0 and direction < 0):
            count += 1
        else:
            break
    return count * direction


def _evaluate(m: dict) -> dict:
    score = 50
    signals = []

    # 外資動向
    fn5 = m.get("foreign_net_5d", 0)
    fn20 = m.get("foreign_net_20d", 0)
    fn_con = m.get("foreign_consecutive", 0)

    if fn20 > 5000:
        score += 12; signals.append(f"外資近20日買超 {fn20:,} 張，籌碼積極偏多")
    elif fn20 > 0:
        score += 6; signals.append(f"外資近20日小幅買超 {fn20:,} 張")
    elif fn20 < -5000:
        score -= 10; signals.append(f"外資近20日賣超 {abs(fn20):,} 張，籌碼偏空")
    elif fn20 < 0:
        score -= 4; signals.append(f"外資近20日小幅賣超 {abs(fn20):,} 張")

    if fn_con >= 3:
        score += 5; signals.append(f"外資連續買超 {fn_con} 天")
    elif fn_con <= -3:
        score -= 5; signals.append(f"外資連續賣超 {abs(fn_con)} 天")

    # 投信動向
    tn20 = m.get("trust_net_20d", 0)
    if tn20 > 0:
        score += 6; signals.append(f"投信近20日買超 {tn20:,} 張")
    elif tn20 < -1000:
        score -= 5; signals.append(f"投信近20日賣超 {abs(tn20):,} 張")

    # 量能
    vr = m.get("volume_ratio")
    if vr is not None:
        if vr > 1.5:
            score += 5; signals.append(f"近5日均量是20日均量的 {vr}x，量能放大")
        elif vr < 0.6:
            score -= 3; signals.append(f"近5日均量萎縮（{vr}x 20日均量）")

    score = max(0, min(100, score))
    if score >= 70:
        label, color = "多頭籌碼", "#22c55e"
    elif score >= 55:
        label, color = "偏多", "#84cc16"
    elif score >= 45:
        label, color = "中性", "#eab308"
    elif score >= 30:
        label, color = "偏空", "#f97316"
    else:
        label, color = "空頭籌碼", "#ef4444"

    return {"score": score, "label": label, "color": color, "signals": signals}


def _generate_analysis(name: str, m: dict) -> str:
    lines = [f"{name} 籌碼面評估："]

    fn20 = m.get("foreign_net_20d", 0)
    tn20 = m.get("trust_net_20d", 0)
    fn_con = m.get("foreign_consecutive", 0)
    trend = m.get("inst_trend", "中性")

    lines.append(f"• 三大法人近20日：外資 {fn20:+,} 張、投信 {tn20:+,} 張")
    lines.append(f"• 整體法人趨勢：{trend}")

    if fn_con != 0:
        direction = "買超" if fn_con > 0 else "賣超"
        lines.append(f"• 外資連續{direction} {abs(fn_con)} 天，短線動能{'偏強' if fn_con > 0 else '偏弱'}")

    margin = m.get("margin_balance")
    short = m.get("short_balance")
    if margin is not None and short is not None:
        lines.append(f"• 融資餘額 {margin:,} 張、融券餘額 {short:,} 張")
        lines.append(f"• {m.get('margin_trend', '')}")

    big_money = m.get("big_money_trend", "")
    if big_money:
        lines.append(f"• 量價分析：{big_money}")

    return "\n".join(lines)


def _parse_num(s) -> int | None:
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None
