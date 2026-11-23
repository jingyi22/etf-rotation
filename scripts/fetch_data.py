"""抓取数据：ETF 列表、全量日线（增量缓存于 data/kl/）、沪深300指数日线。

数据源：新浪财经（不依赖东财，东财接口经常整站拒连）。
- ETF 列表：akshare fund_etf_category_sina("ETF基金")
- ETF 日线：akshare fund_etf_hist_sina(symbol="sh510300")，不复权，份额折算处由 clean.py 修补
- 沪深300：akshare stock_zh_index_daily（新浪）
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HISTORY_START = "2014-01-01"     # 统一保留起点：所有 ETF 从同一天起进面板，避免"数据越早越有优势"的隐形前视偏差


import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, KL_DIR, ROOT

os.makedirs(KL_DIR, exist_ok=True)
LAST_CLOSE = None


def last_trade_date():
    """最近一个已收盘交易日（北京时间）：>=15:30 取今天，否则取昨天；周末回退到周五。
    CI 运行在 UTC，这里显式按北京时间算，避免日期错一天。节假日由数据本身兜底：
    若没有新日线，所有缓存保持不变，track.py 发现信号日已记录就不会重复写台账。"""
    now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    d = now.date()
    if now.weekday() >= 5:
        d -= timedelta(days=now.weekday() - 4)
    elif now.hour * 60 + now.minute < 15 * 60 + 30:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.isoformat()


def index_daily(symbol):
    """沪深300 等指数日线。akshare 新版本把 stock_zh_index_daily 重命名为
    index_zh_daily_sina，两个都兼容。"""
    fns = [getattr(ak, "index_zh_daily_sina", None), getattr(ak, "stock_zh_index_daily", None)]
    err = None
    for fn in fns:
        if fn is None:
            continue
        try:
            df = fn(symbol=symbol)
            df = df.rename(columns={c: c.lower() for c in df.columns})
            return df[["date", "open", "high", "low", "close"]]
        except Exception as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f"指数 {symbol} 拉取失败: {err}")


def fetch_index(symbol, name):
    """沪深300等指数日线，缓存到 data/index_{symbol}.json。"""
    path = os.path.join(ROOT, "data", f"index_{symbol}.json")
    df = index_daily(symbol)
    df["date"] = df["date"].astype(str)
    df = df[df["date"] >= "2013-01-01"]          # 只保留回测起点前两年，控制仓库体积
    df = df.astype({"open": float, "high": float, "low": float, "close": float})            .round({"open": 2, "high": 2, "low": 2, "close": 2})
    rows = df.to_dict("records")
    json.dump({"name": name, "bars": rows}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  指数 {name}: {len(rows)} 条，至 {rows[-1]['date']}")
    return rows


def _norm(df):
    df = df[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
    df["date"] = df["date"].astype(str)
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    df = df[(df["close"] > 0) & (df["open"] > 0)]
    return df.drop_duplicates("date", keep="last").sort_values("date")


def fetch_one(item):
    """返回 (code, info, err)。增量抓取，缓存到 data/kl/{code}.json（2014 年起）。
    新浪接口内部用 py_mini_racer（V8），多线程并发会崩溃，必须串行。"""
    code_raw, name, ref = item
    code = code_raw[-6:]
    path = os.path.join(KL_DIR, f"{code}.json")
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
            if (old.get("fmt") and old["fmt"][-1][0] >= LAST_CLOSE
                    and old["fmt"][0][0] <= "2014-03-01"):
                return code, {"fmt": old["fmt"], "from_cache": True}, None
        except Exception:
            pass
    try:
        df = _norm(ak.fund_etf_hist_sina(symbol=code_raw))
        df = df[df["date"] >= HISTORY_START]

        bars = df.astype({"open": float, "high": float, "low": float, "close": float,
                          "volume": float, "amount": float}).round({"open": 4, "high": 4, "low": 4,
                                                                    "close": 4}).to_dict("records")
        if not bars:
            return code, None, "empty"
        compact = [[b["date"], round(b["open"], 3), round(b["close"], 3), int(b["amount"])]
                   for b in bars if b["amount"] > 0]
        if not compact:
            return code, None, "no rows after 2014"
        json.dump({"name": name, "fmt": compact}, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        return code, {"fmt": compact}, None
    except Exception as e:  # noqa: BLE001
        return code, None, f"{type(e).__name__}: {str(e)[:80]}"


def main():
    global LAST_CLOSE
    LAST_CLOSE = last_trade_date()
    print(f"目标交易日：{LAST_CLOSE}")

    print("[1/3] ETF 列表")
    lst = ak.fund_etf_category_sina(symbol="ETF基金")
    items = []
    seen = set()
    for _, r in lst.iterrows():
        raw = str(r["代码"]).strip().lower()
        if not (raw.startswith("sh") or raw.startswith("sz")):
            continue
        code = raw[-6:]
        if code in seen:
            continue
        seen.add(code)
        items.append((raw, str(r["名称"]).strip(), r.get("成交额")))
    print(f"  {len(items)} 只 ETF")

    print("[2/3] ETF 日线（增量，串行）")
    t0 = time.time()
    res = []
    for k, it in enumerate(items):
        res.append(fetch_one(it))
        if (k + 1) % 100 == 0:
            print(f"   {k+1}/{len(items)} … {time.time()-t0:.0f}s")
    universe, errs = [], []
    for (raw, name, _), (code, info, err) in zip(items, res):
        if info is None:
            errs.append((code, name, err))
            continue
        universe.append({"code": code, "symbol": raw, "name": name,
                         "last": info["fmt"][-1][0], "rows": len(info["fmt"])})
    print(f"  成功 {len(universe)} 只，失败 {len(errs)} 只，用时 {time.time() - t0:.0f}s")
    if errs[:5]:
        print("  失败样例：", errs[:5])

    print("[3/3] 沪深300")
    fetch_index("sh000300", "沪深300")

    json.dump({"asof_target": LAST_CLOSE, "generated_at": datetime.now().isoformat(timespec="seconds"),
               "etfs": universe, "errors": errs[:50]},
              open(os.path.join(DATA_DIR, "universe.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"写入 {os.path.join(DATA_DIR, 'universe.json')}")


if __name__ == "__main__":
    main()
