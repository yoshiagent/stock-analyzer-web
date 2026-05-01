"""
Agent 2：基本面分析
分析 EPS、P/E、P/B、ROE、毛利率、營收成長等
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)


def run(data: dict) -> dict:
    """
    輸入 Agent 1 的輸出，回傳基本面分析結果
    """
    s = data["summary"]
    income = data.get("income_stmt", pd.DataFrame())
    balance = data.get("balance_sheet", pd.DataFrame())
    cashflow = data.get("cashflow", pd.DataFrame())
    quarterly = data.get("quarterly_income", pd.DataFrame())
    dividends = data.get("dividends", pd.Series(dtype=float))

    print(f"  [Agent 2] 開始基本面分析：{s['name']}...")

    metrics = {}

    # --- 估值指標 ---
    metrics["pe_ratio"] = s.get("pe_ratio")
    metrics["forward_pe"] = s.get("forward_pe")
    metrics["pb_ratio"] = s.get("pb_ratio")
    metrics["eps_ttm"] = s.get("eps_ttm")
    metrics["eps_forward"] = s.get("eps_forward")
    metrics["market_cap_b"] = _to_billion(s.get("market_cap"))  # 億元

    # --- 獲利能力 ---
    metrics["roe"] = s.get("roe")
    metrics["roa"] = s.get("roa")
    metrics["gross_margin"] = s.get("gross_margin")
    metrics["operating_margin"] = s.get("operating_margin")
    metrics["profit_margin"] = s.get("profit_margin")

    # --- 股利 ---
    metrics["dividend_yield"] = s.get("dividend_yield")
    metrics["dividend_rate"] = s.get("dividend_rate")
    metrics["dividend_3y"] = _calc_avg_dividend(dividends, years=3)

    # --- 財務健全度 ---
    metrics["debt_to_equity"] = s.get("debt_to_equity")
    metrics["current_ratio"] = s.get("current_ratio")
    metrics["beta"] = s.get("beta")

    # --- 年度營收／獲利成長（從損益表） ---
    revenue_growth = _calc_revenue_growth(income)
    metrics["revenue_yoy"] = revenue_growth.get("yoy")
    metrics["revenue_2y_avg"] = revenue_growth.get("avg_2y")
    metrics["annual_revenue"] = revenue_growth.get("latest")

    eps_growth = _calc_eps_growth(income)
    metrics["net_income_yoy"] = eps_growth.get("yoy")
    metrics["annual_net_income"] = eps_growth.get("latest")

    # --- 季度 EPS 趨勢 ---
    quarterly_eps = _quarterly_eps_trend(quarterly)
    metrics["quarterly_eps"] = quarterly_eps

    # --- 自由現金流 ---
    metrics["free_cashflow"] = _get_fcf(cashflow)

    # --- 評級 ---
    rating = _evaluate(metrics)
    metrics["rating"] = rating["score"]
    metrics["rating_label"] = rating["label"]
    metrics["rating_color"] = rating["color"]
    metrics["strengths"] = rating["strengths"]
    metrics["weaknesses"] = rating["weaknesses"]
    metrics["analysis_text"] = _generate_analysis(s["name"], metrics)

    print(f"  [Agent 2] 基本面分析完成：評級 {rating['label']}（{rating['score']}/100）")

    return metrics


# ── 輔助函式 ──────────────────────────────────────────────

def _to_billion(val):
    if val is None:
        return None
    try:
        return round(val / 1e8, 1)  # 轉億（台幣）
    except (TypeError, ValueError):
        return None


def _calc_avg_dividend(dividends: pd.Series, years: int = 3) -> float | None:
    if dividends.empty:
        return None
    try:
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
        recent = dividends[dividends.index >= cutoff]
        if recent.empty:
            return None
        yearly = recent.resample("YE").sum()
        return round(yearly.mean(), 2)
    except Exception:
        return None


def _calc_revenue_growth(income: pd.DataFrame) -> dict:
    result = {"yoy": None, "avg_2y": None, "latest": None}
    if income.empty:
        return result
    try:
        row_key = None
        for key in ["Total Revenue", "Revenue", "Net Revenue"]:
            if key in income.index:
                row_key = key
                break
        if row_key is None:
            return result
        rev = income.loc[row_key].dropna()
        if len(rev) >= 2:
            cols = sorted(rev.index, reverse=True)
            latest = float(rev[cols[0]])
            prev = float(rev[cols[1]])
            result["latest"] = round(latest / 1e8, 1)
            result["yoy"] = round((latest - prev) / abs(prev) * 100, 1) if prev else None
        if len(rev) >= 3:
            cols = sorted(rev.index, reverse=True)
            y0, y1, y2 = float(rev[cols[0]]), float(rev[cols[1]]), float(rev[cols[2]])
            g1 = (y0 - y1) / abs(y1) * 100 if y1 else 0
            g2 = (y1 - y2) / abs(y2) * 100 if y2 else 0
            result["avg_2y"] = round((g1 + g2) / 2, 1)
    except Exception as e:
        logger.debug(f"營收計算失敗: {e}")
    return result


def _calc_eps_growth(income: pd.DataFrame) -> dict:
    result = {"yoy": None, "latest": None}
    if income.empty:
        return result
    try:
        for key in ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"]:
            if key in income.index:
                ni = income.loc[key].dropna()
                if len(ni) >= 2:
                    cols = sorted(ni.index, reverse=True)
                    latest = float(ni[cols[0]])
                    prev = float(ni[cols[1]])
                    result["latest"] = round(latest / 1e8, 1)
                    result["yoy"] = round((latest - prev) / abs(prev) * 100, 1) if prev else None
                break
    except Exception as e:
        logger.debug(f"淨利計算失敗: {e}")
    return result


def _quarterly_eps_trend(quarterly: pd.DataFrame) -> list:
    """回傳最近4季 EPS 趨勢"""
    result = []
    if quarterly.empty:
        return result
    try:
        for key in ["Basic EPS", "Diluted EPS"]:
            if key in quarterly.index:
                eps_row = quarterly.loc[key].dropna()
                cols = sorted(eps_row.index, reverse=True)[:4]
                for col in reversed(cols):
                    q_label = col.strftime("%YQ") + str((col.month - 1) // 3 + 1)
                    result.append({"quarter": q_label, "eps": round(float(eps_row[col]), 2)})
                break
    except Exception as e:
        logger.debug(f"季度EPS計算失敗: {e}")
    return result


def _get_fcf(cashflow: pd.DataFrame) -> float | None:
    if cashflow.empty:
        return None
    try:
        op_keys = ["Operating Cash Flow", "Cash Flow From Operations", "Cash Flow from Operating Activities"]
        capex_keys = ["Capital Expenditure", "Capital Expenditures", "Purchase Of Property Plant And Equipment"]
        op_cf, capex = None, None
        for k in op_keys:
            if k in cashflow.index:
                vals = cashflow.loc[k].dropna()
                if not vals.empty:
                    op_cf = float(vals.iloc[0])
                break
        for k in capex_keys:
            if k in cashflow.index:
                vals = cashflow.loc[k].dropna()
                if not vals.empty:
                    capex = float(vals.iloc[0])
                break
        if op_cf is not None and capex is not None:
            return round((op_cf + capex) / 1e8, 1)  # capex 通常是負數
        elif op_cf is not None:
            return round(op_cf / 1e8, 1)
    except Exception as e:
        logger.debug(f"FCF計算失敗: {e}")
    return None


def _evaluate(m: dict) -> dict:
    score = 50  # 基礎分
    strengths = []
    weaknesses = []

    # P/E 評估
    pe = m.get("pe_ratio")
    if pe is not None:
        if pe < 15:
            score += 8; strengths.append(f"本益比（P/E）{pe:.1f}倍，估值偏低")
        elif pe < 25:
            score += 4; strengths.append(f"本益比（P/E）{pe:.1f}倍，估值合理")
        elif pe > 40:
            score -= 6; weaknesses.append(f"本益比（P/E）{pe:.1f}倍，估值偏高")

    # ROE 評估
    roe = m.get("roe")
    if roe is not None:
        if roe >= 20:
            score += 10; strengths.append(f"ROE {roe:.1f}%，獲利能力優異")
        elif roe >= 12:
            score += 5; strengths.append(f"ROE {roe:.1f}%，獲利能力良好")
        elif roe < 5:
            score -= 5; weaknesses.append(f"ROE {roe:.1f}%，獲利能力偏弱")

    # 毛利率
    gm = m.get("gross_margin")
    if gm is not None:
        if gm >= 50:
            score += 8; strengths.append(f"毛利率 {gm:.1f}%，護城河深厚")
        elif gm >= 30:
            score += 4; strengths.append(f"毛利率 {gm:.1f}%，獲利結構尚佳")
        elif gm < 10:
            score -= 4; weaknesses.append(f"毛利率 {gm:.1f}%，毛利空間薄")

    # 股利殖利率
    dy = m.get("dividend_yield")
    if dy is not None:
        if dy >= 4:
            score += 6; strengths.append(f"股利殖利率 {dy:.1f}%，配息吸引力高")
        elif dy >= 2:
            score += 3; strengths.append(f"股利殖利率 {dy:.1f}%，配息穩健")

    # 負債比
    de = m.get("debt_to_equity")
    if de is not None:
        if de < 50:
            score += 5; strengths.append(f"負債權益比 {de:.1f}%，財務結構穩健")
        elif de > 200:
            score -= 6; weaknesses.append(f"負債權益比 {de:.1f}%，財務槓桿較高")

    # 營收成長
    rev_yoy = m.get("revenue_yoy")
    if rev_yoy is not None:
        if rev_yoy >= 20:
            score += 7; strengths.append(f"年營收成長 {rev_yoy:.1f}%，高速成長")
        elif rev_yoy >= 5:
            score += 3; strengths.append(f"年營收成長 {rev_yoy:.1f}%，穩健成長")
        elif rev_yoy < -10:
            score -= 5; weaknesses.append(f"年營收衰退 {abs(rev_yoy):.1f}%，需關注")

    score = max(0, min(100, score))
    if score >= 80:
        label, color = "優質", "#22c55e"
    elif score >= 65:
        label, color = "良好", "#84cc16"
    elif score >= 50:
        label, color = "普通", "#eab308"
    elif score >= 35:
        label, color = "偏弱", "#f97316"
    else:
        label, color = "風險", "#ef4444"

    return {"score": score, "label": label, "color": color,
            "strengths": strengths, "weaknesses": weaknesses}


def _generate_analysis(name: str, m: dict) -> str:
    lines = []
    pe = m.get("pe_ratio")
    pb = m.get("pb_ratio")
    roe = m.get("roe")
    gm = m.get("gross_margin")
    dy = m.get("dividend_yield")
    rev_yoy = m.get("revenue_yoy")

    lines.append(f"{name} 基本面評估：")

    if pe and pb:
        lines.append(f"• 本益比（P/E）{pe}倍、股價淨值比（P/B）{pb}倍，"
                     + ("估值合理" if 10 < pe < 30 else "需留意估值水位"))

    if roe:
        lines.append(f"• 股東權益報酬率（ROE）{roe}%，" +
                     ("顯示管理層運用資本效率優異" if roe >= 15 else "獲利能力尚可"))

    if gm:
        lines.append(f"• 毛利率（Gross Margin）{gm}%，" +
                     ("具備較深的產品護城河" if gm >= 40 else "毛利空間屬正常水位"))

    if rev_yoy is not None:
        lines.append(f"• 年度營收年增率（YoY）{rev_yoy}%，" +
                     ("成長動能強勁" if rev_yoy >= 15 else
                      "成長穩定" if rev_yoy >= 0 else "面臨營收壓力"))

    if dy:
        lines.append(f"• 現金殖利率（Dividend Yield）{dy}%，" +
                     ("配息吸引力佳，適合存股族" if dy >= 4 else "配息穩健"))

    fcf = m.get("free_cashflow")
    if fcf is not None:
        lines.append(f"• 自由現金流（FCF）約 {fcf} 億元，" +
                     ("現金流充裕，財務彈性佳" if fcf > 0 else "現金流需持續觀察"))

    return "\n".join(lines)
