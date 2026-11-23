"""开盘复核：每个交易日 09:25 集合竞价结束后运行一次（本机），对前一日收盘给出的推荐做开盘调整。

只依赖已发布的 docs/today.json（不需要 50MB 行情缓存），所以本机、任何电脑都能跑：
  1) 取新浪实时行情（09:25 后 open 字段就是集合竞价成交价）
  2) 规则（config.OPEN_REVIEW，研究见 research_open*.py）：
     - 继续持有的 ETF 不动（卖出由收盘信号决定，开盘不改）
     - 需要新买入的空位：按收盘排名依次检查，集合竞价高开 > skip_gap 的跳过，由后面的名次补位；
       仍跳过与已选 ETF 60 日相关 > 0.9 的（相关性在收盘时已算好，存在 today.json 的 open_ctx）
     - 防守模式不做调整（防守资产是国债和红利低波，不追高这条没有意义）
  3) 追加 track/open_review.jsonl（只追加），写 docs/open.json，提交并推送
用法：python scripts/open_review.py [--force] [--no-push]
  --force    忽略时间窗口检查（测试用）
  --no-push  只打印结果，不写台账、不提交（测试用）
退出码：0 完成或无需运行（非交易日、已做过）；2 行情获取失败（调用方可重试）
时间窗口到 11:30：09:30 之后新浪 open 字段仍是集合竞价成交价，晚跑不影响规则判定，
只是来不及按它操作；台账记录了实际复核时间，页面照实显示。
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from config import DOCS_DIR, OPEN_REVIEW, ROOT, TRACK_DIR

CST = timezone(timedelta(hours=8))
LEDGER = os.path.join(TRACK_DIR, "open_review.jsonl")


def sym(code):
    return ("sh" if code[0] in "56" else "sz") + code


def quotes(codes):
    out = {}
    for i in range(0, len(codes), 80):
        url = "https://hq.sinajs.cn/list=" + ",".join(sym(c) for c in codes[i:i + 80])
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn/",
                                                   "User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=20).read().decode("gbk", "ignore")
        for line in raw.strip().split("\n"):
            if '"' not in line:
                continue
            code = line.split("=")[0][-6:]
            v = line.split('"')[1].split(",")
            if len(v) < 32:
                continue
            pre, op = float(v[2] or 0), float(v[1] or 0)
            out[code] = {"name": v[0], "pre": pre, "open": op, "date": v[30], "time": v[31],
                         "gap": (op / pre - 1) if pre > 0 and op > 0 else None}
    return out


def review(today, q, skip_gap):
    ctx = today["open_ctx"]
    rank = {r["code"]: r for r in today["ranking"]}
    hold_close = [h["code"] for h in today["hold"]]
    if today["mode"] != "risk":
        return hold_close, [], "防守模式：开盘不调整"
    kept = list(ctx["kept"])
    picks, skipped = list(kept), []
    hi = ctx["high_corr_pairs"]

    def too_corr(a, b):
        return f"{a}|{b}" in hi or f"{b}|{a}" in hi

    for code in ctx["head"]:
        if len(picks) >= ctx["n_hold"]:
            break
        if code in picks:
            continue
        g = (q.get(code) or {}).get("gap")
        if g is None:
            skipped.append({"code": code, "name": rank[code]["name"], "why": "无竞价成交"})
            continue
        if g > skip_gap:
            skipped.append({"code": code, "name": rank[code]["name"], "why": f"高开 {g:+.2%}"})
            continue
        if any(too_corr(code, k) for k in picks):
            continue
        picks.append(code)
    note = "无需调整" if set(picks) == set(hold_close) else "已调整"
    return picks, skipped, note


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-notify", action="store_true", help="不发桌面通知（CI 兜底用）")
    a = ap.parse_args()
    now = datetime.now(CST)
    lo, hi = OPEN_REVIEW["window"]
    if not a.force and not (lo <= now.strftime("%H:%M:%S") <= hi and now.weekday() < 5):
        print(f"{now:%H:%M:%S} 不在开盘复核窗口 {lo}~{hi}（或非工作日），退出")
        return 0
    if not a.no_push:
        git("pull", "--rebase", "--autostash", "-q")
    today = json.load(open(os.path.join(DOCS_DIR, "today.json"), encoding="utf-8"))
    need = sorted(set(today["open_ctx"]["head"]) | {h["code"] for h in today["hold"]} | {"510300"})
    try:
        q = quotes(need)
    except Exception as e:  # noqa: BLE001
        print(f"行情获取失败：{type(e).__name__}: {e}")
        return 2
    trade_date = q.get("510300", {}).get("date")
    if trade_date is None or trade_date <= today["signal_date"]:
        print(f"行情日期 {trade_date} 不晚于信号日 {today['signal_date']}：今天不是交易日或行情未更新，退出")
        return 0
    done = set()
    if os.path.exists(LEDGER):
        done = {json.loads(x)["trade_date"] for x in open(LEDGER, encoding="utf-8") if x.strip()}
    if trade_date in done:
        print(f"{trade_date} 已做过开盘复核，退出（台账只追加，不重复写）")
        return 0
    picks, skipped, note = review(today, q, OPEN_REVIEW["skip_gap"])
    rank = {r["code"]: r for r in today["ranking"]}
    names = {**{r["code"]: r["name"] for r in today["ranking"]}, **{h["code"]: h["name"] for h in today["hold"]}}
    w = 1.0 / len(picks) if picks else 0
    hold_close = {h["code"]: h["weight"] for h in today["hold"]}
    if today["mode"] != "risk":
        weights = hold_close
    else:
        weights = {c: w for c in picks}
    rec = {
        "trade_date": trade_date, "signal_date": today["signal_date"], "mode": today["mode"],
        "model": today["model"], "rule": f"新买入高开>{OPEN_REVIEW['skip_gap']:.0%}不追，顺延下一名",
        "reviewed_at": now.isoformat(timespec="seconds"), "quote_time": q["510300"]["time"],
        "note": note,
        "hold": [{"code": c, "name": names.get(c, c), "weight": round(weights[c], 4),
                  "gap": None if q.get(c, {}).get("gap") is None else round(q[c]["gap"], 4),
                  "open": q.get(c, {}).get("open"),
                  "rank": rank[c]["rank"] if c in rank else None,
                  "changed": c not in hold_close} for c in weights],
        "dropped": [{"code": c, "name": names.get(c, c)} for c in hold_close if c not in weights],
        "skipped": skipped, "_no_notify": a.no_notify,
    }
    print(f"{trade_date} 开盘复核（{q['510300']['time']}）：{note}")
    for h in rec["hold"]:
        print(f"   {'新' if h['changed'] else ' '} {h['code']} {h['name']:14s} {h['weight']:.0%} 竞价 {h['gap']}")
    for s in skipped:
        print(f"   跳过 {s['code']} {s['name']}：{s['why']}")
    if a.no_push:
        print("（--no-push：未写台账）")
        summarize_out(rec, today, q)
        return 0
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    json.dump(rec, open(os.path.join(DOCS_DIR, "open.json"), "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    git("add", "track/open_review.jsonl", "docs/open.json")
    git("commit", "-q", "-m", f"Open review {trade_date} {q['510300']['time']}")
    r = git("push", "-q")
    if r.returncode != 0:
        git("pull", "--rebase", "--autostash", "-q")
        r = git("push", "-q")
    print("推送", "成功" if r.returncode == 0 else f"失败：{r.stderr.strip()}")
    summarize_out(rec, today, q)
    return 0


def notify(title, msg):
    """Windows 托盘通知（本机计划任务用，不依赖第三方模块）。非 Windows 时只打印。"""
    if sys.platform != "win32":
        print(f"[notify] {title}：{msg}")
        return
    import base64
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true;"
        f"$n.ShowBalloonTip(20000,'{title}','{msg}',[System.Windows.Forms.ToolTipIcon]::Info);"
        "Start-Sleep -Seconds 6; $n.Dispose()"
    )
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    try:
        subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc], timeout=40,
                       capture_output=True)
    except Exception as e:  # noqa: BLE001
        print(f"[notify] 失败：{e}")


def summarize_out(rec, today, q):
    """复核完成后：有调整 → 桌面通知；无调整 → 只在日志和 CI 摘要里留一行。
    每项：'名称 13%：低开 0.8%'；被替换掉的与跳过的也写清楚。"""
    if rec["note"] == "防守模式：开盘不调整":
        return
    changed = [h for h in rec["hold"] if h["changed"]]
    lines = [f"{h['name']} {h['weight'] * 100:.0f}% 竞价 {(h['gap'] or 0) * 100:+.2f}%" for h in rec["hold"]]
    if rec["note"] == "无需调整" or not changed:
        print("[通知] 无调整，不推送提醒")
    else:
        msg = "已调整：" + "、".join(h["name"] for h in changed) + " 换入"
        if rec["dropped"]:
            msg += "；" + "、".join(x["name"] for x in rec["dropped"]) + " 未买"
        if rec["skipped"]:
            msg += "（" + "、".join(f"{s['name']}{s['why']}" for s in rec["skipped"]) + "）"
        print("[通知] " + msg)
        if not rec.get("_no_notify"):
            notify(f"ETF 开盘复核 {rec['trade_date']} 已调整", msg)
    # GitHub Actions 摘要（本机运行时无效，不影响）
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as fh:
            fh.write(f"### 开盘复核 {rec['trade_date']} {rec['quote_time']}：{rec['note']}\n\n")
            fh.write("| 代码 | 名称 | 权重 | 竞价涨跌 |\n|---|---|---|---|\n")
            for h in rec["hold"]:
                fh.write(f"| {h['code']} | {h['name']} | {h['weight'] * 100:.0f}% | {(h['gap'] or 0) * 100:+.2f}% |\n")


if __name__ == "__main__":
    sys.exit(main())
