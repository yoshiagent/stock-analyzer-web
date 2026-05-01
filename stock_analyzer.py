#!/usr/bin/env python3
"""
股票多Agent分析系統 - 主Orchestrator
用法：
  python stock_analyzer.py 2330
  python stock_analyzer.py 台積電
"""

import sys
import os
import time
import threading
import traceback
from pathlib import Path

# 確保 agents 可被 import
sys.path.insert(0, str(Path(__file__).parent))

from utils.stock_lookup import resolve_stock
from agents import data_collector, fundamental_agent, chip_agent, technical_agent, report_agent


def banner():
    print("""
╔══════════════════════════════════════════════════════╗
║         台股多Agent分析系統  v1.0                    ║
║  Agent1:數據  Agent2:基本面  Agent3:籌碼  Agent4:技術 ║
║  Agent5:報告 → GitHub Pages 自動部署                 ║
╚══════════════════════════════════════════════════════╝""")


def main():
    banner()

    # ── 取得股票代碼/名稱 ──────────────────────────────
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = input("\n請輸入股票代碼或名稱（例：2330 或 台積電）：").strip()

    if not user_input:
        print("❌ 未輸入股票代碼，程式結束。")
        sys.exit(1)

    # ── STEP 0: 解析股票 ──────────────────────────────
    print(f"\n[搜尋] 解析股票：{user_input}...")
    try:
        stock_info = resolve_stock(user_input)
        print(f"[OK] 識別成功：{stock_info['name']}（{stock_info['ticker']}）[{stock_info['market']}]")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # ── STEP 1: 數據收集（必須先完成，其他 Agent 依賴此結果） ──
    print(f"\n{'─'*54}")
    print(f"▶ Agent 1 / 股票數據收集")
    print(f"{'─'*54}")
    t0 = time.time()
    try:
        raw_data = data_collector.run(stock_info)
    except Exception as e:
        print(f"[ERROR] Agent 1 失敗：{e}")
        traceback.print_exc()
        sys.exit(1)
    print(f"  ✅ Agent 1 完成（{time.time()-t0:.1f}s）")

    # ── STEP 2-4: 基本面、籌碼面、技術面 並行執行 ──────────
    print(f"\n{'─'*54}")
    print(f"▶ Agent 2 / 3 / 4 並行分析中...")
    print(f"{'─'*54}")

    results = {}
    errors = {}

    def run_agent(name: str, fn, data):
        try:
            t = time.time()
            results[name] = fn(data)
            print(f"  [OK] {name} 完成（{time.time()-t:.1f}s）")
        except Exception as e:
            errors[name] = str(e)
            print(f"  [WARN] {name} 發生錯誤：{e}")
            traceback.print_exc()
            results[name] = {}

    threads = [
        threading.Thread(target=run_agent, args=("Agent2-基本面", fundamental_agent.run, raw_data)),
        threading.Thread(target=run_agent, args=("Agent3-籌碼面", chip_agent.run, raw_data)),
        threading.Thread(target=run_agent, args=("Agent4-技術面", technical_agent.run, raw_data)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    fundamental = results.get("Agent2-基本面", {})
    chip = results.get("Agent3-籌碼面", {})
    technical = results.get("Agent4-技術面", {})

    # ── STEP 5: 產生報告並部署 ────────────────────────────
    print(f"\n{'─'*54}")
    print(f"▶ Agent 5 / 報告產生 + GitHub 部署")
    print(f"{'─'*54}")

    code = stock_info["code"]
    output_dir = str(Path(__file__).parent / "output" / code)
    os.makedirs(output_dir, exist_ok=True)

    try:
        t5 = time.time()
        summary = raw_data["summary"]
        # 補充基本面計算出的 market_cap_b
        if "market_cap_b" in fundamental:
            summary["market_cap_b"] = fundamental["market_cap_b"]

        deploy_result = report_agent.run(
            summary=summary,
            fundamental=fundamental,
            chip=chip,
            technical=technical,
            output_dir=output_dir,
        )
        print(f"  [OK] Agent 5 完成（{time.time()-t5:.1f}s）")
    except Exception as e:
        print(f"  [ERROR] Agent 5 失敗：{e}")
        traceback.print_exc()
        deploy_result = {"html_path": None, "github_url": None, "deploy_success": False}

    # ── 輸出摘要 ──────────────────────────────────────────
    total_time = time.time() - t0
    print(f"""
{'═'*54}
  分析完成！耗時 {total_time:.1f} 秒

  股票：{stock_info['name']}（{stock_info['ticker']}）
  現價：NT$ {raw_data['summary'].get('current_price','—')}
  整體評分：基本面 {fundamental.get('rating','-')}/100 ｜
            籌碼面 {chip.get('rating','-')}/100 ｜
            技術面 {technical.get('rating','-')}/100

  HTML 報告：{deploy_result.get('html_path','—')}
  GitHub Pages：{deploy_result.get('github_url','（部署中或失敗）')}
{'═'*54}""")

    return deploy_result


if __name__ == "__main__":
    main()
