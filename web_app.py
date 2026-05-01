#!/usr/bin/env python3
"""
股票多Agent分析系統 - Web Orchestrator
執行：python -X utf8 web_app.py
瀏覽器自動開啟 http://localhost:5001
"""

import os
import sys
import json
import queue
import subprocess
import threading
import time
import glob
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, Response, send_from_directory, jsonify

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__, template_folder="templates")
app.config["JSON_AS_ASCII"] = False

# 每個 job 的進度 queue：{job_id: Queue}
job_queues: dict[str, queue.Queue] = {}
job_status: dict[str, dict] = {}   # {job_id: {"code", "status", "report_url"}}


# ── 路由 ────────────────────────────────────────────────────

@app.route("/")
def index():
    reports = _list_reports()
    return render_template("index.html", reports=reports)


@app.route("/analyze", methods=["POST"])
def start_analyze():
    stock_input = request.form.get("stock", "").strip()
    if not stock_input:
        return jsonify({"error": "請輸入股票代碼或名稱"}), 400

    job_id = f"{int(time.time()*1000)}"
    q = queue.Queue()
    job_queues[job_id] = q
    job_status[job_id] = {"input": stock_input, "status": "running", "report_url": None}

    thread = threading.Thread(target=_run_analysis, args=(job_id, stock_input, q), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    """Server-Sent Events 串流分析進度"""
    def generate():
        q = job_queues.get(job_id)
        if not q:
            yield "data: {\"line\": \"[ERROR] 找不到任務\", \"done\": true}\n\n"
            return
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("done"):
                    break
            except queue.Empty:
                yield "data: {\"line\": \"...\", \"done\": false}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/report/<code>")
def view_report(code):
    """嵌入顯示已生成的報告"""
    report_path = OUTPUT_DIR / code / "index.html"
    if not report_path.exists():
        return "報告不存在", 404
    # 讀取報告內容，嵌入 iframe 外框頁面
    return render_template("report_view.html", code=code)


@app.route("/report/<code>/raw")
def raw_report(code):
    """直接提供原始報告 HTML"""
    report_dir = str(OUTPUT_DIR / code)
    return send_from_directory(report_dir, "index.html")


@app.route("/api/reports")
def api_reports():
    return jsonify(_list_reports())


# ── 分析執行 ─────────────────────────────────────────────────

def _run_analysis(job_id: str, stock_input: str, q: queue.Queue):
    """在子執行緒中啟動 stock_analyzer.py 並轉發輸出"""
    try:
        python = sys.executable
        script = str(BASE_DIR / "stock_analyzer.py")
        cmd = [python, "-X", "utf8", script, stock_input]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(BASE_DIR),
        )

        code = None
        report_url = None

        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if not line:
                continue

            # 嘗試解析股票代碼
            if "識別成功" in line and "（" in line and ".TW" in line:
                import re
                m = re.search(r"（(\d+)\.TW", line)
                if m:
                    code = m.group(1)

            # 嘗試解析 GitHub Pages URL
            if "github.io" in line:
                import re
                m = re.search(r"https://[^\s]+", line)
                if m:
                    report_url = m.group(0)

            # 判斷訊息類型
            line_type = "info"
            if "[OK]" in line or "完成" in line:
                line_type = "success"
            elif "[ERROR]" in line or "失敗" in line:
                line_type = "error"
            elif "[WARN]" in line or "警告" in line:
                line_type = "warn"
            elif "Agent" in line and "分析" in line:
                line_type = "agent"
            elif "╔" in line or "╚" in line or "═" in line:
                line_type = "banner"

            q.put({"line": line, "type": line_type, "done": False})

        proc.wait()

        # 更新 job 狀態
        local_report = f"/report/{code}" if code else None
        job_status[job_id] = {
            "input": stock_input,
            "status": "done" if proc.returncode == 0 else "error",
            "code": code,
            "report_url": report_url,
            "local_report": local_report,
        }

        q.put({
            "line": "── 分析完成 ──",
            "type": "done",
            "done": True,
            "code": code,
            "report_url": report_url,
            "local_report": local_report,
        })

    except Exception as e:
        q.put({"line": f"[ERROR] 執行失敗：{e}", "type": "error", "done": True})
        job_status[job_id]["status"] = "error"


def _list_reports() -> list:
    """掃描 output 目錄，回傳已生成的報告清單"""
    reports = []
    for html_file in sorted(OUTPUT_DIR.glob("*/index.html"), key=os.path.getmtime, reverse=True):
        code = html_file.parent.name
        mtime = datetime.fromtimestamp(os.path.getmtime(html_file))

        # 從 HTML 抓取股票名稱
        name = code
        try:
            with open(html_file, encoding="utf-8") as f:
                content = f.read(2000)
            import re
            m = re.search(r"<title>(.+?)（\d+）", content)
            if m:
                name = m.group(1).strip()
        except Exception:
            pass

        reports.append({
            "code": code,
            "name": name,
            "updated": mtime.strftime("%Y-%m-%d %H:%M"),
            "url": f"/report/{code}",
        })
    return reports


# ── 啟動 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5001
    url = f"http://localhost:{port}"
    print(f"\n股票分析系統 Web Orchestrator 啟動中...")
    print(f"網址：{url}")
    print(f"按 Ctrl+C 停止\n")

    # 延遲開啟瀏覽器
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
