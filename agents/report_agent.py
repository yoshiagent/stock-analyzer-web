"""
Agent 5：統整結果，產生 HTML 報告，部署到 GitHub Pages
"""

import json
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

GITHUB_USER = "yoshiagent"
REPO_NAME = "stock-analysis-report"
DEPLOY_EMAIL = "hwangprobot@gmail.com"


def run(summary: dict, fundamental: dict, chip: dict, technical: dict,
        output_dir: str = None) -> dict:
    """
    整合四個 Agent 的結果，產生 HTML 並部署到 GitHub
    """
    name = summary.get("name", "未知股票")
    code = summary.get("code", "0000")

    print(f"  [Agent 5] 開始產生報告：{name}（{code}）...")

    # 輸出路徑：根目錄是 output/，每隻股票在 output/{code}/
    base_output = Path(__file__).parent.parent / "output"
    if output_dir is None:
        output_dir = str(base_output / code)
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, "index.html")
    # robots.txt 放在 output/ 根目錄
    robots_path = str(base_output / "robots.txt")

    # 產生 HTML
    html_content = _generate_html(summary, fundamental, chip, technical)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # robots.txt
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")

    print(f"  [Agent 5] HTML 報告已產生：{html_path}")

    # 部署到 GitHub
    deploy_result = _deploy_to_github(output_dir, name, code)

    return {
        "html_path": html_path,
        "github_url": deploy_result.get("url"),
        "deploy_success": deploy_result.get("success", False),
        "deploy_message": deploy_result.get("message", ""),
    }


def _deploy_to_github(output_dir: str, name: str, code: str) -> dict:
    """更新 output/ 根目錄的 GitHub repo 並推送"""
    try:
        repo_full = f"{GITHUB_USER}/{REPO_NAME}"
        repo_url = f"https://github.com/{repo_full}"
        # git repo 在 output/ 根目錄，而非個股目錄
        git_dir = str(Path(output_dir).parent)

        def run_cmd(cmd, cwd=None, check=True):
            result = subprocess.run(
                cmd, shell=True, cwd=cwd or git_dir,
                capture_output=True, text=True, encoding="utf-8"
            )
            return result

        # 初始化 git repo（若尚未初始化）
        if not os.path.exists(os.path.join(git_dir, ".git")):
            run_cmd("git init")
            run_cmd(f'git config user.email "{DEPLOY_EMAIL}"')
            run_cmd(f'git config user.name "{GITHUB_USER}"')

        # 設定 remote（若不存在則建立 GitHub repo）
        remote_check = run_cmd("git remote get-url origin", check=False)
        if remote_check.returncode != 0:
            # 嘗試建立 GitHub repo
            create_result = run_cmd(
                f'gh repo create {repo_full} --public --source=. --remote=origin',
                check=False
            )
            if create_result.returncode != 0:
                # repo 可能已存在，直接加 remote
                run_cmd(
                    f'git remote add origin https://github.com/{repo_full}.git',
                    check=False
                )

        # Stage + Commit + Push
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        run_cmd("git add -A", cwd=git_dir)
        commit_result = run_cmd(
            f'git commit -m "分析報告：{name}（{code}）{today}"',
            check=False
        )
        if commit_result.returncode != 0 and "nothing to commit" in commit_result.stdout:
            pass  # 無變更也視為成功

        # 確保在 main branch
        run_cmd("git branch -M main", check=False)

        push_result = run_cmd("git push -u origin main", check=False)

        # 啟用 GitHub Pages
        pages_result = run_cmd(
            f'gh api repos/{repo_full}/pages -X POST '
            f'-f source[branch]=main -f source[path]=/',
            check=False
        )

        pages_url = f"https://{GITHUB_USER}.github.io/{REPO_NAME}/"
        print(f"  [Agent 5] 部署完成：{pages_url}")

        return {
            "success": True,
            "url": pages_url,
            "message": f"已推送到 {repo_url}，GitHub Pages：{pages_url}",
        }

    except Exception as e:
        logger.error(f"GitHub 部署失敗: {e}")
        return {
            "success": False,
            "url": None,
            "message": f"部署失敗：{e}",
        }


def _generate_html(summary: dict, fundamental: dict, chip: dict, technical: dict) -> str:
    """產生完整的深色主題 HTML 報告"""

    name = summary.get("name", "未知股票")
    code = summary.get("code", "0000")
    market = summary.get("market", "上市")
    today = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    cp = summary.get("current_price", "N/A")
    change_pct = summary.get("change_pct")
    change_color = "#22c55e" if (change_pct or 0) >= 0 else "#ef4444"
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"

    # 整體評分
    f_score = fundamental.get("rating", 50)
    c_score = chip.get("rating", 50)
    t_score = technical.get("rating", 50)
    overall = round((f_score * 0.4 + c_score * 0.3 + t_score * 0.3))
    overall_label, overall_color = _score_to_label(overall)

    # 圖表數據
    chart = technical.get("chart_data", {})
    chart_json = json.dumps(chart, ensure_ascii=False)

    # 三大法人數據
    inst_data = chip.get("inst_data", [])
    inst_json = json.dumps(inst_data[-20:], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}（{code}）股票分析報告 | {today}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #080e18;
    --card: #131f2e;
    --border: #2d3f55;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #3b82f6;
    --orange: #fb923c;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #eab308;
    --callout-bg: #0f2040;
    --code-bg: #07111e;
  }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    line-height: 1.7;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #0d1b2e 0%, #131f2e 100%);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
    position: sticky; top: 0; z-index: 100;
  }}
  .header-inner {{
    max-width: 1200px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    flex-wrap: wrap;
  }}
  .stock-title {{ display: flex; align-items: center; gap: 16px; }}
  .stock-badge {{
    background: var(--accent); color: white;
    padding: 4px 12px; border-radius: 6px;
    font-size: 13px; font-weight: 600;
  }}
  .stock-name {{ font-size: 26px; font-weight: 700; }}
  .stock-meta {{ font-size: 13px; color: var(--muted); }}
  .price-area {{ text-align: right; }}
  .price-main {{ font-size: 32px; font-weight: 700; }}
  .price-change {{ font-size: 16px; font-weight: 600; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 24px; }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  @media (max-width: 900px) {{
    .grid-3, .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (max-width: 600px) {{
    .grid-3, .grid-4, .grid-2 {{ grid-template-columns: 1fr; }}
    .price-main {{ font-size: 24px; }}
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }}
  .card-title {{
    font-size: 13px; font-weight: 600;
    color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.05em; margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
  }}
  .card-title .dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent);
  }}
  .metric-val {{
    font-size: 24px; font-weight: 700; color: var(--text);
  }}
  .metric-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .score-ring {{
    display: flex; flex-direction: column; align-items: center;
    gap: 8px;
  }}
  .ring-container {{ position: relative; width: 90px; height: 90px; }}
  .ring-svg {{ transform: rotate(-90deg); }}
  .ring-text {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 20px; font-weight: 700; text-align: center;
  }}
  .ring-label {{ font-size: 14px; font-weight: 600; }}
  .section-title {{
    font-size: 18px; font-weight: 700;
    color: var(--text);
    border-left: 4px solid var(--accent);
    padding-left: 12px;
    margin: 32px 0 16px;
  }}
  .kv-table {{ width: 100%; border-collapse: collapse; }}
  .kv-table tr {{ border-bottom: 1px solid var(--border); }}
  .kv-table tr:last-child {{ border-bottom: none; }}
  .kv-table td {{ padding: 8px 4px; font-size: 14px; }}
  .kv-table td:first-child {{ color: var(--muted); width: 50%; }}
  .kv-table td:last-child {{ font-weight: 600; text-align: right; }}
  .signal-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
  .signal-item {{
    display: flex; align-items: flex-start; gap: 8px;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
  }}
  .signal-positive {{ background: rgba(34,197,94,0.1); color: #86efac; border: 1px solid rgba(34,197,94,0.2); }}
  .signal-negative {{ background: rgba(239,68,68,0.1); color: #fca5a5; border: 1px solid rgba(239,68,68,0.2); }}
  .signal-neutral {{ background: rgba(234,179,8,0.1); color: #fde68a; border: 1px solid rgba(234,179,8,0.2); }}
  .analysis-box {{
    background: var(--callout-bg);
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 10px;
    padding: 16px 20px;
    font-size: 14px;
    line-height: 1.8;
    white-space: pre-line;
    color: #93c5fd;
    margin-top: 16px;
  }}
  .chart-wrap {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .chart-title {{
    font-size: 14px; font-weight: 600; color: var(--muted);
    margin-bottom: 16px;
  }}
  canvas {{ max-width: 100%; }}
  .inst-bars {{ display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }}
  .inst-row {{ display: flex; align-items: center; gap: 8px; font-size: 12px; }}
  .inst-label {{ width: 40px; color: var(--muted); flex-shrink: 0; }}
  .inst-bar-wrap {{ flex: 1; height: 16px; background: rgba(45,63,85,0.5); border-radius: 4px; overflow: hidden; position: relative; }}
  .inst-bar {{ height: 100%; border-radius: 4px; }}
  .inst-val {{ width: 80px; text-align: right; font-weight: 600; }}
  .overall-card {{
    background: linear-gradient(135deg, var(--card) 0%, #0d1929 100%);
    border: 2px solid var(--accent);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 32px;
    flex-wrap: wrap;
  }}
  .overall-score-big {{
    font-size: 72px;
    font-weight: 900;
    line-height: 1;
  }}
  .overall-info {{ flex: 1; min-width: 200px; }}
  .overall-label-big {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  .overall-desc {{ font-size: 14px; color: var(--muted); }}
  .tag {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(59,130,246,0.15);
    color: #93c5fd;
    border: 1px solid rgba(59,130,246,0.25);
    margin: 2px;
  }}
  footer {{
    border-top: 1px solid var(--border);
    padding: 24px 32px;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
    margin-top: 48px;
  }}
  .divider {{ height: 1px; background: var(--border); margin: 24px 0; }}
</style>
</head>
<body>

<!-- ── HEADER ── -->
<div class="header">
  <div class="header-inner">
    <div class="stock-title">
      <span class="stock-badge">{market}</span>
      <div>
        <div class="stock-name">{name} <span style="color:var(--muted);font-size:18px;">（{code}）</span></div>
        <div class="stock-meta">{today} 更新 &nbsp;|&nbsp; {summary.get("industry","—")} &nbsp;|&nbsp; {summary.get("sector","—")}</div>
      </div>
    </div>
    <div class="price-area">
      <div class="price-main">NT$ {cp}</div>
      <div class="price-change" style="color:{change_color}">{change_str}</div>
    </div>
  </div>
</div>

<div class="container">

  <!-- ── 整體評分 ── -->
  <div class="section-title">整體分析評分</div>
  <div class="overall-card">
    <div class="overall-score-big" style="color:{overall_color}">{overall}</div>
    <div class="overall-info">
      <div class="overall-label-big" style="color:{overall_color}">{overall_label}</div>
      <div class="overall-desc">基本面 × 0.4 ＋ 籌碼面 × 0.3 ＋ 技術面 × 0.3</div>
    </div>
    <div style="display:flex;gap:24px;flex-wrap:wrap;">
      {_score_ring("基本面", f_score, fundamental.get("rating_color","#3b82f6"))}
      {_score_ring("籌碼面", c_score, chip.get("rating_color","#3b82f6"))}
      {_score_ring("技術面", t_score, technical.get("rating_color","#3b82f6"))}
    </div>
  </div>

  <!-- ── 關鍵數字 ── -->
  <div class="section-title">關鍵數字一覽</div>
  <div class="grid-4">
    {_kv_card("市值（億）", _fmt(summary.get("market_cap_b") or (summary.get("market_cap") or 0) / 1e8, suffix="億"), "Market Cap")}
    {_kv_card("本益比（P/E）", _fmt(summary.get("pe_ratio")), "TTM P/E")}
    {_kv_card("EPS（TTM）", _fmt(summary.get("eps_ttm"), prefix="NT$"), "Trailing EPS")}
    {_kv_card("ROE", _fmt(summary.get("roe"), suffix="%"), "Return on Equity")}
    {_kv_card("股利殖利率", _fmt(summary.get("dividend_yield"), suffix="%"), "Dividend Yield")}
    {_kv_card("毛利率", _fmt(summary.get("gross_margin"), suffix="%"), "Gross Margin")}
    {_kv_card("52週高", _fmt(summary.get("week52_high")), "52-Week High")}
    {_kv_card("52週低", _fmt(summary.get("week52_low")), "52-Week Low")}
  </div>

  <!-- ── 股價走勢圖 ── -->
  <div class="section-title">股價走勢（近60日）</div>
  <div class="chart-wrap">
    <div class="chart-title">收盤價 + 均線（MA5 / MA20 / MA60）+ 布林通道</div>
    <canvas id="priceChart" height="120"></canvas>
  </div>

  <!-- ── 成交量 ── -->
  <div class="chart-wrap">
    <div class="chart-title">成交量（張）</div>
    <canvas id="volChart" height="60"></canvas>
  </div>

  <!-- ── 技術指標圖 ── -->
  <div class="grid-2">
    <div class="chart-wrap" style="margin-bottom:0;">
      <div class="chart-title">RSI（14）</div>
      <canvas id="rsiChart" height="100"></canvas>
    </div>
    <div class="chart-wrap" style="margin-bottom:0;">
      <div class="chart-title">MACD（12/26/9）</div>
      <canvas id="macdChart" height="100"></canvas>
    </div>
  </div>
  <div style="margin-bottom:24px;"></div>

  <!-- ── 基本面 ── -->
  <div class="section-title">基本面分析（Fundamental Analysis）</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title"><span class="dot"></span>估值指標</div>
      <table class="kv-table">
        <tr><td>本益比（P/E）</td><td>{_fmt(fundamental.get("pe_ratio"), suffix="倍")}</td></tr>
        <tr><td>預估本益比（Forward P/E）</td><td>{_fmt(fundamental.get("forward_pe"), suffix="倍")}</td></tr>
        <tr><td>股價淨值比（P/B）</td><td>{_fmt(fundamental.get("pb_ratio"), suffix="倍")}</td></tr>
        <tr><td>EPS（TTM）</td><td>{_fmt(fundamental.get("eps_ttm"), prefix="NT$")}</td></tr>
        <tr><td>EPS（預估）</td><td>{_fmt(fundamental.get("eps_forward"), prefix="NT$")}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot"></span>獲利能力</div>
      <table class="kv-table">
        <tr><td>股東權益報酬率（ROE）</td><td>{_fmt(fundamental.get("roe"), suffix="%")}</td></tr>
        <tr><td>資產報酬率（ROA）</td><td>{_fmt(fundamental.get("roa"), suffix="%")}</td></tr>
        <tr><td>毛利率（Gross Margin）</td><td>{_fmt(fundamental.get("gross_margin"), suffix="%")}</td></tr>
        <tr><td>營業利益率（OPM）</td><td>{_fmt(fundamental.get("operating_margin"), suffix="%")}</td></tr>
        <tr><td>淨利率（Net Margin）</td><td>{_fmt(fundamental.get("profit_margin"), suffix="%")}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:var(--orange)"></span>財務結構</div>
      <table class="kv-table">
        <tr><td>負債權益比（D/E）</td><td>{_fmt(fundamental.get("debt_to_equity"), suffix="%")}</td></tr>
        <tr><td>流動比率（Current Ratio）</td><td>{_fmt(fundamental.get("current_ratio"))}</td></tr>
        <tr><td>自由現金流（FCF）</td><td>{_fmt(fundamental.get("free_cashflow"), suffix=" 億")}</td></tr>
        <tr><td>市值</td><td>{_fmt(fundamental.get("market_cap_b"), suffix=" 億")}</td></tr>
        <tr><td>年度營收</td><td>{_fmt(fundamental.get("annual_revenue"), suffix=" 億")}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:#a78bfa"></span>成長與股利</div>
      <table class="kv-table">
        <tr><td>年營收成長率（YoY）</td><td>{_fmt(fundamental.get("revenue_yoy"), suffix="%")}</td></tr>
        <tr><td>年淨利成長率（YoY）</td><td>{_fmt(fundamental.get("net_income_yoy"), suffix="%")}</td></tr>
        <tr><td>現金股利殖利率</td><td>{_fmt(fundamental.get("dividend_yield"), suffix="%")}</td></tr>
        <tr><td>每股現金股利</td><td>{_fmt(fundamental.get("dividend_rate"), prefix="NT$")}</td></tr>
        <tr><td>近3年平均股利</td><td>{_fmt(fundamental.get("dividend_3y"), prefix="NT$")}</td></tr>
      </table>
    </div>
  </div>
  {_strengths_weaknesses(fundamental.get("strengths",[]), fundamental.get("weaknesses",[]))}
  <div class="analysis-box">{fundamental.get("analysis_text","")}</div>

  <!-- ── 籌碼面 ── -->
  <div class="section-title">籌碼面分析（Chip Analysis）</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title"><span class="dot" style="background:var(--orange)"></span>三大法人近20日買賣超（張）</div>
      <table class="kv-table">
        <tr><td>外資（Foreign）近5日</td><td style="color:{_signed_color(chip.get('foreign_net_5d',0))}">{_signed(chip.get("foreign_net_5d",0))}</td></tr>
        <tr><td>外資（Foreign）近20日</td><td style="color:{_signed_color(chip.get('foreign_net_20d',0))}">{_signed(chip.get("foreign_net_20d",0))}</td></tr>
        <tr><td>投信（Trust）近20日</td><td style="color:{_signed_color(chip.get('trust_net_20d',0))}">{_signed(chip.get("trust_net_20d",0))}</td></tr>
        <tr><td>自營商（Dealer）近20日</td><td style="color:{_signed_color(chip.get('dealer_net_20d',0))}">{_signed(chip.get("dealer_net_20d",0))}</td></tr>
        <tr><td>三大合計近20日</td><td style="color:{_signed_color(chip.get('total_net_20d',0))}"><strong>{_signed(chip.get("total_net_20d",0))}</strong></td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:#a78bfa"></span>籌碼動向</div>
      <table class="kv-table">
        <tr><td>外資連續動作</td><td>{_consecutive_text(chip.get("foreign_consecutive",0))}</td></tr>
        <tr><td>投信連續動作</td><td>{_consecutive_text(chip.get("trust_consecutive",0))}</td></tr>
        <tr><td>法人趨勢</td><td><strong>{chip.get("inst_trend","—")}</strong></td></tr>
        <tr><td>融資餘額（張）</td><td>{_fmt(chip.get("margin_balance"))}</td></tr>
        <tr><td>融券餘額（張）</td><td>{_fmt(chip.get("short_balance"))}</td></tr>
        <tr><td>量能比（5日/20日）</td><td>{_fmt(chip.get("volume_ratio"))}</td></tr>
      </table>
    </div>
  </div>
  <!-- 法人走勢圖 -->
  <div class="chart-wrap">
    <div class="chart-title">三大法人每日買賣超（近20日）</div>
    <canvas id="instChart" height="80"></canvas>
  </div>
  {_signals_section(chip.get("signals",[]))}
  <div class="analysis-box">{chip.get("analysis_text","")}</div>

  <!-- ── 技術面 ── -->
  <div class="section-title">技術面分析（Technical Analysis）</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title"><span class="dot"></span>均線指標（Moving Average）</div>
      <table class="kv-table">
        <tr><td>現價</td><td><strong>NT$ {technical.get("current_price","—")}</strong></td></tr>
        <tr><td>MA5（5日均線）</td><td>{_fmt(technical.get("ma5"))}</td></tr>
        <tr><td>MA10（10日均線）</td><td>{_fmt(technical.get("ma10"))}</td></tr>
        <tr><td>MA20（20日均線）</td><td>{_fmt(technical.get("ma20"))}</td></tr>
        <tr><td>MA60（60日均線）</td><td>{_fmt(technical.get("ma60"))}</td></tr>
        <tr><td>均線排列</td><td><strong>{technical.get("ma_alignment","—")}</strong></td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:var(--orange)"></span>震盪指標</div>
      <table class="kv-table">
        <tr><td>RSI（14）</td><td>{_fmt(technical.get("rsi14"))}</td></tr>
        <tr><td>K 值（KD 9,3,3）</td><td>{_fmt(technical.get("k_value"))}</td></tr>
        <tr><td>D 值（KD 9,3,3）</td><td>{_fmt(technical.get("d_value"))}</td></tr>
        <tr><td>MACD</td><td>{_fmt(technical.get("macd"), digits=3)}</td></tr>
        <tr><td>MACD Signal</td><td>{_fmt(technical.get("macd_signal"), digits=3)}</td></tr>
        <tr><td>KD 交叉</td><td>{_cross_text(technical.get("kd_cross"))}</td></tr>
        <tr><td>MACD 交叉</td><td>{_cross_text(technical.get("macd_cross"))}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:#a78bfa"></span>布林通道（Bollinger Bands 20,2）</div>
      <table class="kv-table">
        <tr><td>上軌（Upper）</td><td>{_fmt(technical.get("bb_upper"))}</td></tr>
        <tr><td>中軌（Middle/MA20）</td><td>{_fmt(technical.get("bb_middle"))}</td></tr>
        <tr><td>下軌（Lower）</td><td>{_fmt(technical.get("bb_lower"))}</td></tr>
        <tr><td>通道寬度（%）</td><td>{_fmt(technical.get("bb_width"), suffix="%")}</td></tr>
        <tr><td>位置狀態</td><td>{_bb_position_text(technical.get("bb_position"))}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="dot" style="background:var(--green)"></span>支撐壓力 &amp; 成交量</div>
      <table class="kv-table">
        <tr><td>壓力1</td><td>{_fmt(technical.get("resistance1"))}</td></tr>
        <tr><td>壓力2</td><td>{_fmt(technical.get("resistance2"))}</td></tr>
        <tr><td>支撐1</td><td>{_fmt(technical.get("support1"))}</td></tr>
        <tr><td>支撐2</td><td>{_fmt(technical.get("support2"))}</td></tr>
        <tr><td>成交量趨勢</td><td>{technical.get("vol_trend","—")}</td></tr>
        <tr><td>量能比（5日/20日）</td><td>{_fmt(technical.get("vol_ratio"))}</td></tr>
      </table>
    </div>
  </div>
  {_signals_section(technical.get("signals",[]))}
  <div class="analysis-box">{technical.get("analysis_text","")}</div>

  <!-- ── 公司簡介 ── -->
  {_company_desc(summary)}

</div><!-- /container -->

<footer>
  <p>資料來源：Yahoo Finance、臺灣證券交易所（TWSE）&nbsp;|&nbsp; 產生時間：{today}</p>
  <p style="margin-top:6px;">本報告由 AI 自動分析產生，僅供參考，不構成投資建議。投資有風險，請自行評估。</p>
</footer>

<script>
const chartData = {chart_json};
const instData = {inst_json};

const gridColor = 'rgba(45,63,85,0.5)';
const textColor = '#94a3b8';
const baseFont = {{ family: 'system-ui, sans-serif', size: 11 }};

Chart.defaults.color = textColor;
Chart.defaults.font = baseFont;
Chart.defaults.plugins.legend.labels.boxWidth = 12;

// ── 價格圖 ────────────────────────────────
if (chartData.dates && chartData.closes) {{
  const priceCtx = document.getElementById('priceChart').getContext('2d');
  new Chart(priceCtx, {{
    type: 'line',
    data: {{
      labels: chartData.dates,
      datasets: [
        {{ label: '收盤價', data: chartData.closes, borderColor: '#e2e8f0', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: false, order: 1 }},
        {{ label: 'MA5', data: chartData.ma5, borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, borderDash: [] }},
        {{ label: 'MA20', data: chartData.ma20, borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false }},
        {{ label: 'MA60', data: chartData.ma60, borderColor: '#a78bfa', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false }},
        {{ label: 'BB上軌', data: chartData.bb_upper, borderColor: 'rgba(251,146,60,0.4)', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, borderDash: [4,4] }},
        {{ label: 'BB下軌', data: chartData.bb_lower, borderColor: 'rgba(251,146,60,0.4)', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: '-1', backgroundColor: 'rgba(251,146,60,0.05)', borderDash: [4,4] }},
      ]
    }},
    options: {{
      responsive: true, interaction: {{ intersect: false, mode: 'index' }},
      plugins: {{ legend: {{ position: 'top' }}, tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.raw?.toFixed(2) ?? '—') }} }} }},
      scales: {{
        x: {{ grid: {{ color: gridColor }}, ticks: {{ maxTicksLimit: 10 }} }},
        y: {{ grid: {{ color: gridColor }}, position: 'right' }}
      }}
    }}
  }});
}}

// ── 成交量圖 ──────────────────────────────
if (chartData.volumes) {{
  const volCtx = document.getElementById('volChart').getContext('2d');
  new Chart(volCtx, {{
    type: 'bar',
    data: {{
      labels: chartData.dates,
      datasets: [{{ label: '成交量', data: chartData.volumes, backgroundColor: 'rgba(59,130,246,0.5)', borderColor: 'rgba(59,130,246,0.8)', borderWidth: 1 }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ color: gridColor }}, ticks: {{ maxTicksLimit: 10 }} }},
        y: {{ grid: {{ color: gridColor }}, position: 'right', ticks: {{ callback: v => v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }}
      }}
    }}
  }});
}}

// ── RSI 圖 ───────────────────────────────
if (chartData.rsi && chartData.rsi.some(v => v !== null)) {{
  const rsiCtx = document.getElementById('rsiChart').getContext('2d');
  new Chart(rsiCtx, {{
    type: 'line',
    data: {{
      labels: chartData.dates,
      datasets: [
        {{ label: 'RSI(14)', data: chartData.rsi, borderColor: '#f59e0b', borderWidth: 2, pointRadius: 0, tension: 0.1 }},
        {{ label: '超買(70)', data: Array(chartData.dates.length).fill(70), borderColor: 'rgba(239,68,68,0.5)', borderWidth: 1, pointRadius: 0, borderDash: [6,3] }},
        {{ label: '超賣(30)', data: Array(chartData.dates.length).fill(30), borderColor: 'rgba(34,197,94,0.5)', borderWidth: 1, pointRadius: 0, borderDash: [6,3] }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top' }} }},
      scales: {{
        x: {{ grid: {{ color: gridColor }}, ticks: {{ maxTicksLimit: 8 }} }},
        y: {{ grid: {{ color: gridColor }}, min: 0, max: 100, position: 'right' }}
      }}
    }}
  }});
}}

// ── MACD 圖 ──────────────────────────────
if (chartData.macd && chartData.macd.length) {{
  const macdCtx = document.getElementById('macdChart').getContext('2d');
  new Chart(macdCtx, {{
    type: 'bar',
    data: {{
      labels: chartData.dates,
      datasets: [
        {{ type: 'bar', label: 'MACD柱', data: chartData.macd_hist, backgroundColor: ctx => (ctx.raw >= 0) ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)', order: 2 }},
        {{ type: 'line', label: 'MACD', data: chartData.macd, borderColor: '#3b82f6', borderWidth: 2, pointRadius: 0, fill: false, order: 1 }},
        {{ type: 'line', label: 'Signal', data: chartData.macd_signal, borderColor: '#f97316', borderWidth: 2, pointRadius: 0, fill: false, order: 1 }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top' }} }},
      scales: {{
        x: {{ grid: {{ color: gridColor }}, ticks: {{ maxTicksLimit: 8 }} }},
        y: {{ grid: {{ color: gridColor }}, position: 'right' }}
      }}
    }}
  }});
}}

// ── 法人買賣超圖 ──────────────────────────
if (instData && instData.length > 0) {{
  const instCtx = document.getElementById('instChart').getContext('2d');
  const instDates = instData.map(d => d.date || '');
  const foreignData = instData.map(d => d.foreign_net || 0);
  const trustData = instData.map(d => d.trust_net || 0);
  const dealerData = instData.map(d => d.dealer_net || 0);
  new Chart(instCtx, {{
    type: 'bar',
    data: {{
      labels: instDates,
      datasets: [
        {{ label: '外資', data: foreignData, backgroundColor: ctx => ctx.raw >= 0 ? 'rgba(59,130,246,0.7)' : 'rgba(239,68,68,0.7)' }},
        {{ label: '投信', data: trustData, backgroundColor: ctx => ctx.raw >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.5)' }},
        {{ label: '自營商', data: dealerData, backgroundColor: 'rgba(167,139,250,0.6)' }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top' }} }},
      scales: {{
        x: {{ stacked: false, grid: {{ color: gridColor }}, ticks: {{ maxTicksLimit: 10 }} }},
        y: {{ grid: {{ color: gridColor }}, position: 'right',
             ticks: {{ callback: v => v >= 1000 ? (v/1000).toFixed(0)+'K' : v >= -1000 ? (v/-1000).toFixed(0)+'K' : v }} }}
      }}
    }}
  }});
}}
</script>
</body>
</html>"""


# ── HTML 輔助元件 ─────────────────────────────────────────

def _fmt(val, prefix="", suffix="", digits=2) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{prefix}{float(val):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return f"{prefix}{val}{suffix}"


def _kv_card(label: str, val: str, sub: str = "") -> str:
    return f"""<div class="card">
      <div class="card-title"><span class="dot"></span>{label}</div>
      <div class="metric-val">{val}</div>
      <div class="metric-sub">{sub}</div>
    </div>"""


def _score_ring(label: str, score: int, color: str) -> str:
    r = 38
    circumference = 2 * 3.14159 * r
    filled = circumference * score / 100
    gap = circumference - filled
    return f"""<div class="score-ring">
      <div class="ring-container">
        <svg class="ring-svg" viewBox="0 0 90 90" width="90" height="90">
          <circle cx="45" cy="45" r="{r}" fill="none" stroke="#2d3f55" stroke-width="8"/>
          <circle cx="45" cy="45" r="{r}" fill="none" stroke="{color}" stroke-width="8"
            stroke-dasharray="{filled:.1f} {gap:.1f}" stroke-linecap="round"/>
        </svg>
        <div class="ring-text" style="color:{color}">{score}</div>
      </div>
      <div class="ring-label" style="color:{color}">{label}</div>
    </div>"""


def _signed(val: int | float) -> str:
    if val is None:
        return "—"
    try:
        v = int(val)
        return f"{v:+,}"
    except (TypeError, ValueError):
        return "—"


def _signed_color(val) -> str:
    try:
        return "#22c55e" if float(val) >= 0 else "#ef4444"
    except (TypeError, ValueError):
        return "#94a3b8"


def _consecutive_text(val: int) -> str:
    if val is None or val == 0:
        return "—"
    if val > 0:
        return f'<span style="color:#22c55e">連買 {val} 天</span>'
    return f'<span style="color:#ef4444">連賣 {abs(val)} 天</span>'


def _cross_text(val: str | None) -> str:
    if val == "golden_cross":
        return '<span style="color:#22c55e;font-weight:700">⬆ 黃金交叉</span>'
    elif val == "death_cross":
        return '<span style="color:#ef4444;font-weight:700">⬇ 死亡交叉</span>'
    return "—"


def _bb_position_text(val: str | None) -> str:
    if val == "overbought":
        return '<span style="color:#ef4444">觸及上軌（超買）</span>'
    elif val == "oversold":
        return '<span style="color:#22c55e">觸及下軌（超賣）</span>'
    return "通道中段"


def _strengths_weaknesses(strengths: list, weaknesses: list) -> str:
    if not strengths and not weaknesses:
        return ""
    items = ""
    for s in strengths:
        items += f'<li class="signal-item signal-positive">✓ {s}</li>\n'
    for w in weaknesses:
        items += f'<li class="signal-item signal-negative">✗ {w}</li>\n'
    return f'<ul class="signal-list" style="margin-top:16px;">{items}</ul>'


def _signals_section(signals: list) -> str:
    if not signals:
        return ""
    items = ""
    for sig in signals:
        cls = "signal-positive" if any(k in sig for k in ["買", "多", "超賣", "積極", "黃金"]) else \
              "signal-negative" if any(k in sig for k in ["賣", "空", "超買", "死亡", "賣超"]) else \
              "signal-neutral"
        items += f'<li class="signal-item {cls}">• {sig}</li>\n'
    return f'<ul class="signal-list" style="margin-top:16px;">{items}</ul>'


def _company_desc(summary: dict) -> str:
    desc = summary.get("description", "")
    emp = summary.get("employees")
    industry = summary.get("industry", "")
    sector = summary.get("sector", "")
    if not desc and not emp:
        return ""
    emp_text = f"<br>員工人數：{emp:,} 人" if emp else ""
    return f"""<div class="section-title">公司簡介</div>
<div class="card">
  <div style="font-size:13px;color:var(--muted);margin-bottom:8px;">{sector} &gt; {industry}{emp_text}</div>
  <p style="font-size:14px;line-height:1.8;">{desc}</p>
</div>"""


def _score_to_label(score: int) -> tuple:
    if score >= 80:
        return "強力推薦", "#22c55e"
    elif score >= 65:
        return "值得關注", "#84cc16"
    elif score >= 50:
        return "中性觀望", "#eab308"
    elif score >= 35:
        return "偏弱留意", "#f97316"
    else:
        return "高風險慎入", "#ef4444"
