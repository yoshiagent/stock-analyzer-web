"""
Agent 4：技術面分析
計算均線、KD、MACD、RSI、布林通道等技術指標
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def run(data: dict) -> dict:
    """
    輸入 Agent 1 的輸出，回傳技術面分析結果
    """
    s = data["summary"]
    hist = data.get("hist", pd.DataFrame())

    print(f"  [Agent 4] 開始技術面分析：{s['name']}...")

    if hist.empty or len(hist) < 10:
        return {
            "error": "歷史價格資料不足，無法進行技術分析",
            "rating": 50, "rating_label": "資料不足", "rating_color": "#94a3b8",
            "signals": [], "analysis_text": "歷史資料不足，技術面無法評估"
        }

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    metrics = {}

    # --- 均線（MA） ---
    metrics["ma5"] = _round(close.rolling(5).mean().iloc[-1])
    metrics["ma10"] = _round(close.rolling(10).mean().iloc[-1])
    metrics["ma20"] = _round(close.rolling(20).mean().iloc[-1])
    metrics["ma60"] = _round(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else None
    metrics["current_price"] = _round(close.iloc[-1])

    # --- MA位置關係 ---
    cp = metrics["current_price"]
    metrics["above_ma5"] = cp > metrics["ma5"] if metrics["ma5"] else None
    metrics["above_ma20"] = cp > metrics["ma20"] if metrics["ma20"] else None
    metrics["above_ma60"] = cp > metrics["ma60"] if metrics["ma60"] else None
    metrics["ma_alignment"] = _ma_alignment(metrics)  # 多頭排列/空頭排列

    # --- RSI (14) ---
    metrics["rsi14"] = _round(_calc_rsi(close, 14))

    # --- MACD (12, 26, 9) ---
    macd_result = _calc_macd(close)
    metrics["macd"] = _round(macd_result.get("macd"))
    metrics["macd_signal"] = _round(macd_result.get("signal"))
    metrics["macd_hist"] = _round(macd_result.get("hist"))
    metrics["macd_cross"] = macd_result.get("cross")  # "golden_cross" / "death_cross" / None

    # --- KD (9,3,3) ---
    kd_result = _calc_kd(high, low, close, 9, 3, 3)
    metrics["k_value"] = _round(kd_result.get("k"))
    metrics["d_value"] = _round(kd_result.get("d"))
    metrics["kd_cross"] = kd_result.get("cross")

    # --- 布林通道 (20日, 2σ) ---
    bb = _calc_bollinger(close, 20, 2)
    metrics["bb_upper"] = _round(bb.get("upper"))
    metrics["bb_middle"] = _round(bb.get("middle"))
    metrics["bb_lower"] = _round(bb.get("lower"))
    metrics["bb_width"] = _round(bb.get("width"))
    metrics["bb_position"] = bb.get("position")  # "overbought" / "oversold" / "normal"
    metrics["bb_pct"] = _round(bb.get("pct"), 3)  # 在通道中的位置 0~1

    # --- 成交量分析 ---
    metrics["vol5_avg"] = int(volume.iloc[-5:].mean()) if len(volume) >= 5 else None
    metrics["vol20_avg"] = int(volume.iloc[-20:].mean()) if len(volume) >= 20 else None
    metrics["vol_ratio"] = _round(metrics["vol5_avg"] / metrics["vol20_avg"], 2) \
        if (metrics["vol5_avg"] and metrics["vol20_avg"]) else None
    metrics["vol_trend"] = _judge_vol_trend(volume)

    # --- 支撐壓力位 ---
    sr = _calc_support_resistance(high, low, close)
    metrics["support1"] = _round(sr.get("support1"))
    metrics["support2"] = _round(sr.get("support2"))
    metrics["resistance1"] = _round(sr.get("resistance1"))
    metrics["resistance2"] = _round(sr.get("resistance2"))

    # --- 52週高低 ---
    metrics["week52_high"] = _round(high.max())
    metrics["week52_low"] = _round(low.min())
    metrics["from_52high_pct"] = _round((cp - high.max()) / high.max() * 100, 1)
    metrics["from_52low_pct"] = _round((cp - low.min()) / low.min() * 100, 1)

    # --- 歷史數據（for 圖表） ---
    chart_data = _prepare_chart_data(hist, metrics)
    metrics["chart_data"] = chart_data

    # --- 評級 ---
    rating = _evaluate(metrics)
    metrics["rating"] = rating["score"]
    metrics["rating_label"] = rating["label"]
    metrics["rating_color"] = rating["color"]
    metrics["signals"] = rating["signals"]
    metrics["analysis_text"] = _generate_analysis(s["name"], metrics)

    print(f"  [Agent 4] 技術面分析完成：{rating['label']}（{rating['score']}/100）"
          f"  RSI={metrics['rsi14']} KD=({metrics['k_value']},{metrics['d_value']})")

    return metrics


# ── 技術指標計算 ──────────────────────────────────────────

def _calc_rsi(close: pd.Series, period: int = 14) -> float | None:
    try:
        delta = close.diff().dropna()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return None


def _calc_macd(close: pd.Series, fast=12, slow=26, signal=9) -> dict:
    try:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist_line = macd_line - signal_line

        cross = None
        if len(hist_line) >= 2:
            if hist_line.iloc[-2] < 0 and hist_line.iloc[-1] > 0:
                cross = "golden_cross"
            elif hist_line.iloc[-2] > 0 and hist_line.iloc[-1] < 0:
                cross = "death_cross"

        return {
            "macd": float(macd_line.iloc[-1]),
            "signal": float(signal_line.iloc[-1]),
            "hist": float(hist_line.iloc[-1]),
            "cross": cross,
        }
    except Exception:
        return {}


def _calc_kd(high: pd.Series, low: pd.Series, close: pd.Series,
             n: int = 9, m1: int = 3, m2: int = 3) -> dict:
    try:
        low_n = low.rolling(n).min()
        high_n = high.rolling(n).max()
        rsv = (close - low_n) / (high_n - low_n + 1e-10) * 100
        k = rsv.ewm(com=m1 - 1, adjust=False).mean()
        d = k.ewm(com=m2 - 1, adjust=False).mean()

        cross = None
        if len(k) >= 2 and len(d) >= 2:
            if k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
                cross = "golden_cross"
            elif k.iloc[-2] > d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
                cross = "death_cross"

        return {"k": float(k.iloc[-1]), "d": float(d.iloc[-1]), "cross": cross}
    except Exception:
        return {}


def _calc_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2) -> dict:
    try:
        ma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = ma + std_dev * std
        lower = ma - std_dev * std
        width = (upper - lower) / ma * 100

        cp = float(close.iloc[-1])
        u = float(upper.iloc[-1])
        l = float(lower.iloc[-1])
        m = float(ma.iloc[-1])
        w = float(width.iloc[-1])

        pct = (cp - l) / (u - l) if (u - l) > 0 else 0.5
        position = "overbought" if pct > 0.85 else "oversold" if pct < 0.15 else "normal"

        return {"upper": u, "middle": m, "lower": l, "width": w, "pct": pct, "position": position}
    except Exception:
        return {}


def _ma_alignment(m: dict) -> str:
    ma5 = m.get("ma5")
    ma10 = m.get("ma10")
    ma20 = m.get("ma20")
    ma60 = m.get("ma60")

    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            return "多頭排列（短均 > 中均 > 長均）"
        elif ma5 < ma10 < ma20:
            return "空頭排列（短均 < 中均 < 長均）"
    return "均線糾結"


def _calc_support_resistance(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    """用近期高低點估算支撐壓力"""
    try:
        recent_high = high.iloc[-60:] if len(high) >= 60 else high
        recent_low = low.iloc[-60:] if len(low) >= 60 else low
        cp = float(close.iloc[-1])

        # 壓力：歷史高點中高於現價的最近點
        highs_above = recent_high[recent_high > cp].nsmallest(2)
        lows_below = recent_low[recent_low < cp].nlargest(2)

        return {
            "resistance1": float(highs_above.iloc[0]) if len(highs_above) > 0 else None,
            "resistance2": float(highs_above.iloc[1]) if len(highs_above) > 1 else None,
            "support1": float(lows_below.iloc[0]) if len(lows_below) > 0 else None,
            "support2": float(lows_below.iloc[1]) if len(lows_below) > 1 else None,
        }
    except Exception:
        return {}


def _judge_vol_trend(volume: pd.Series) -> str:
    try:
        vol5 = volume.iloc[-5:].mean()
        vol20 = volume.iloc[-20:].mean()
        if vol5 > vol20 * 1.5:
            return "量能大幅放大"
        elif vol5 > vol20 * 1.1:
            return "量能溫和放大"
        elif vol5 < vol20 * 0.6:
            return "量能萎縮明顯"
        else:
            return "量能平穩"
    except Exception:
        return "無法判斷"


def _prepare_chart_data(hist: pd.DataFrame, metrics: dict) -> dict:
    """整理圖表所需資料（JSON-serializable）"""
    try:
        df = hist.tail(60).copy()
        dates = [d.strftime("%Y-%m-%d") for d in df.index]
        closes = [_round(v) for v in df["Close"].tolist()]
        volumes = [int(v) for v in df["Volume"].tolist()]
        opens = [_round(v) for v in df["Open"].tolist()]
        highs = [_round(v) for v in df["High"].tolist()]
        lows = [_round(v) for v in df["Low"].tolist()]

        # MA資料
        ma5 = [_round(v) for v in df["Close"].rolling(5).mean().tolist()]
        ma20 = [_round(v) for v in df["Close"].rolling(20).mean().tolist()]
        ma60 = [_round(v) for v in df["Close"].rolling(60).mean().tolist()]

        # RSI
        rsi_series = []
        try:
            delta = df["Close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.ewm(com=13, min_periods=14).mean()
            avg_loss = loss.ewm(com=13, min_periods=14).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi_series = [_round(v) for v in rsi.tolist()]
        except Exception:
            rsi_series = [None] * len(dates)

        # MACD
        macd_vals, signal_vals, hist_vals = [], [], []
        try:
            ema12 = df["Close"].ewm(span=12, adjust=False).mean()
            ema26 = df["Close"].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            hist_line = macd_line - signal_line
            macd_vals = [_round(v) for v in macd_line.tolist()]
            signal_vals = [_round(v) for v in signal_line.tolist()]
            hist_vals = [_round(v) for v in hist_line.tolist()]
        except Exception:
            pass

        # Bollinger Bands
        bb_upper, bb_lower = [], []
        try:
            ma20_s = df["Close"].rolling(20).mean()
            std20 = df["Close"].rolling(20).std()
            bb_upper = [_round(v) for v in (ma20_s + 2 * std20).tolist()]
            bb_lower = [_round(v) for v in (ma20_s - 2 * std20).tolist()]
        except Exception:
            pass

        return {
            "dates": dates, "closes": closes, "opens": opens,
            "highs": highs, "lows": lows, "volumes": volumes,
            "ma5": ma5, "ma20": ma20, "ma60": ma60,
            "rsi": rsi_series,
            "macd": macd_vals, "macd_signal": signal_vals, "macd_hist": hist_vals,
            "bb_upper": bb_upper, "bb_lower": bb_lower,
        }
    except Exception as e:
        logger.warning(f"圖表數據準備失敗: {e}")
        return {}


def _evaluate(m: dict) -> dict:
    score = 50
    signals = []

    cp = m.get("current_price", 0)

    # RSI
    rsi = m.get("rsi14")
    if rsi is not None:
        if rsi < 30:
            score += 8; signals.append(f"RSI {rsi:.1f}，超賣區，潛在反彈機會")
        elif rsi < 45:
            score += 3; signals.append(f"RSI {rsi:.1f}，偏弱但未超賣")
        elif rsi > 70:
            score -= 6; signals.append(f"RSI {rsi:.1f}，超買區，短線留意回調")
        elif rsi > 55:
            score += 5; signals.append(f"RSI {rsi:.1f}，動能偏強")

    # MACD
    macd_cross = m.get("macd_cross")
    macd_hist = m.get("macd_hist")
    if macd_cross == "golden_cross":
        score += 10; signals.append("MACD 出現黃金交叉，買進訊號")
    elif macd_cross == "death_cross":
        score -= 10; signals.append("MACD 出現死亡交叉，賣出訊號")
    elif macd_hist is not None:
        if macd_hist > 0:
            score += 4; signals.append(f"MACD 柱狀正值（{macd_hist:.3f}），多方動能")
        else:
            score -= 3; signals.append(f"MACD 柱狀負值（{macd_hist:.3f}），空方動能")

    # KD
    kd_cross = m.get("kd_cross")
    k = m.get("k_value")
    d = m.get("d_value")
    if kd_cross == "golden_cross":
        score += 8; signals.append(f"KD 黃金交叉（K={k:.1f}, D={d:.1f}），買進參考")
    elif kd_cross == "death_cross":
        score -= 8; signals.append(f"KD 死亡交叉（K={k:.1f}, D={d:.1f}），賣出參考")
    elif k is not None and d is not None:
        if k < 20 and d < 20:
            score += 6; signals.append(f"KD 超低（K={k:.1f}, D={d:.1f}），深度超賣")
        elif k > 80 and d > 80:
            score -= 5; signals.append(f"KD 超高（K={k:.1f}, D={d:.1f}），超買區")

    # 均線位置
    ma_align = m.get("ma_alignment", "")
    if "多頭" in ma_align:
        score += 8; signals.append(f"均線多頭排列，趨勢向上")
    elif "空頭" in ma_align:
        score -= 8; signals.append(f"均線空頭排列，趨勢向下")

    # 布林通道
    bb_pos = m.get("bb_position")
    if bb_pos == "oversold":
        score += 5; signals.append("股價觸及布林通道下緣，超賣訊號")
    elif bb_pos == "overbought":
        score -= 4; signals.append("股價觸及布林通道上緣，短線壓力")

    # 成交量
    vol_trend = m.get("vol_trend", "")
    if "放大" in vol_trend:
        score += 3; signals.append(f"成交量{vol_trend}，留意方向確認")

    score = max(0, min(100, score))
    if score >= 70:
        label, color = "強勢", "#22c55e"
    elif score >= 58:
        label, color = "偏多", "#84cc16"
    elif score >= 43:
        label, color = "中性", "#eab308"
    elif score >= 30:
        label, color = "偏空", "#f97316"
    else:
        label, color = "弱勢", "#ef4444"

    return {"score": score, "label": label, "color": color, "signals": signals}


def _generate_analysis(name: str, m: dict) -> str:
    lines = [f"{name} 技術面評估："]

    cp = m.get("current_price")
    ma20 = m.get("ma20")
    ma60 = m.get("ma60")
    rsi = m.get("rsi14")
    k = m.get("k_value")
    d = m.get("d_value")

    if cp and ma20:
        rel = "站上" if cp > ma20 else "跌破"
        lines.append(f"• 現價 {cp}，{rel} 20日均線（MA20={ma20}）")

    if ma60:
        rel60 = "站上" if cp > ma60 else "跌破"
        lines.append(f"• 60日均線（MA60={ma60}），現價{rel60}長期均線")

    ma_align = m.get("ma_alignment", "")
    if ma_align:
        lines.append(f"• 均線排列：{ma_align}")

    if rsi is not None:
        status = "超買" if rsi > 70 else "超賣" if rsi < 30 else "中性"
        lines.append(f"• RSI(14) = {rsi:.1f}，目前處於{status}區")

    if k is not None and d is not None:
        kd_status = "超買" if k > 80 else "超賣" if k < 20 else "中性"
        lines.append(f"• KD 指標：K={k:.1f} / D={d:.1f}，{kd_status}水位")

    macd = m.get("macd")
    signal = m.get("macd_signal")
    if macd is not None and signal is not None:
        cross = m.get("macd_cross")
        cross_text = "（黃金交叉！）" if cross == "golden_cross" else \
                     "（死亡交叉！）" if cross == "death_cross" else ""
        lines.append(f"• MACD = {macd:.3f} / Signal = {signal:.3f} {cross_text}")

    support = m.get("support1")
    resistance = m.get("resistance1")
    if support and resistance:
        lines.append(f"• 近期支撐：{support}，壓力：{resistance}")

    return "\n".join(lines)


def _round(val, digits=2):
    if val is None or (isinstance(val, float) and (val != val)):
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None
