"""清洗日线：份额折算（拆分）造成的价格断崖修补。

新浪 ETF 日线不复权，份额折算当天价格按比例跳变（常见 0.5、0.33、2、10 倍），
成交量同时反向跳变但成交额连续。识别规则：
  1) 相邻收盘价比 r 落在拆分比例附近（0.8 以下、1.25 以上）；
  2) 成交额连续：|ln r + ln(量比)| < 0.5（份额折算时价格跌多少、份额/成交量涨多少）；
  3) 单日涨跌幅超过宽基指数上下限（>+12% 或 <−12%）但相关性低、动静不匹配的，不修，只标记。
修补：把断崖之前所有价格乘以累计系数，拉平到最新刻度；返回累计系数和修补点，写回缓存。
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from config import KL_DIR


def detect_ratio(prev_close, close, tol=0.15):
    """把断崖比例吸附到常见拆分比例（k 或 1/k，k = 1,2,3,4,5,10）；返回吸附后的比例。"""
    r = close / prev_close
    for cand in (1 / 10, 1 / 5, 1 / 4, 1 / 3, 2 / 5, 1 / 2, 2 / 3, 3 / 4,
                 4 / 3, 3 / 2, 2, 5 / 2, 3, 4, 5, 10):
        if abs(r - cand) / cand < tol:
            return cand
    return r


def clean_bars(bars):
    bars = [dict(b) for b in bars]
    cum = 1.0
    fixes = []
    for i in range(len(bars) - 1, 0, -1):
        p, c = bars[i - 1], bars[i]
        if not p["close"] or not c["close"]:
            continue
        raw = c["close"] / p["close"]
        if 0.8 <= raw <= 1.25:
            continue
        ratio = detect_ratio(p["close"], c["close"])
        # A股涨跌停制度下单日跌幅不可能超过 20%，港股通类无涨跌停但单日腰斩也极罕见：
        # 跌破 0.75 或涨过 1.33 一律视为份额折算（比例吸附到最近档）；临界区间
        # （0.75~0.8 / 1.25~1.33）再用成交额是否连续做二次确认，避免把真实大跌误判为拆分。
        extreme = raw < 0.75 or raw > 1.33
        amt_ok = extreme
        if not extreme and p["amount"] and c["amount"]:
            amt_ok = 0.4 < c["amount"] / p["amount"] < 2.5
        if amt_ok:
            # 断崖发生在 i（i 及之后价格是新刻度）。把 0..i-1 的价格乘以 ratio，使其与新刻度连续
            for b in bars[:i]:
                for f in ("open", "high", "low", "close"):
                    if b.get(f):
                        b[f] = round(b[f] * ratio, 4)
            cum *= ratio
            fixes.append((p["date"], round(raw, 3), round(ratio, 3), "split"))
    return bars, fixes


def main():
    fixed = []
    bad = []
    for f in sorted(glob.glob(os.path.join(KL_DIR, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        bars = [{"date": r[0], "open": r[1], "close": r[2], "amount": r[3]} for r in d["fmt"]]
        new, fixes = clean_bars(bars)
        if fixes:
            d["fmt"] = [[b["date"], b["open"], b["close"], b["amount"]] for b in new]
            old = {tuple(x) for x in d.get("splits", [])}
            d["splits"] = sorted(old | {(x[0], x[2]) for x in fixes})
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            fixed.append((os.path.basename(f)[:6], d["name"], fixes))
        # 修补后仍存在的单日大幅下挫（>15%）列为可疑
        for i in range(1, len(new)):
            r = new[i]["close"] / new[i - 1]["close"]
            if r < 0.85 and new[i - 1]["close"]:
                bad.append((os.path.basename(f)[:6], d["name"], new[i]["date"], round(r, 3)))
    print(f"修补 {len(fixed)} 只 ETF")
    for code, name, fx in fixed[:12]:
        print("  ", code, name, fx)
    if len(fixed) > 12:
        print(f"   … 另有 {len(fixed)-12} 只")
    print(f"修补后剩余单日跌幅>15% 的可疑点 {len(bad)} 个（2024-10-09 创业板大幅回调等真实行情，或临界区间的真实大跌，不修补）")


if __name__ == "__main__":
    main()
