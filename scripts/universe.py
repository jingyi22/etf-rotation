"""从 data/kl + data/universe.json 构建统一面板（宽表），供回测与线上信号共用。

- 剔除货币、债券类 ETF（它们不该按"超跌反弹"逻辑交易）
- 剔除非股票底层（黄金/商品/原油）——默认只做 A 股股票型 ETF，可配置
- 按"近 120 日收益相关系数 + 名称主干"聚类去重，每个指数簇保留成交额最大的一只
- 输出 panel.npz：dates、codes、open/close/amount 矩阵（np.float32）
"""
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, KL_DIR, PARAMS

PANEL_START = "2014-01-01"   # 面板统一起点：所有 ETF 从同一天起记，晚上市的留空

EXCLUDE_WORDS = ("货币", "债", "短融", "添益", "添利", "日利", "日日鑫", "快钱", "快线", "现金宝",
                 "财富宝", "现金", "理财", "收益宝", "保证金",
                 "黄金", "金ETF", "原油", "石油", "商品", "豆粕", "白银", "有色", "铜", "铝",
                 "REIT", "日经", "日本", "德国", "法国", "沙特", "美国", "道琼斯", "纳指",
                 "纳斯达克", "标普", "恒生", "港股", "香港", "中概", "亚太", "中韩", "东南亚",
                 "越南", "印度")


def norm_name(name):
    """名称主干：去掉基金公司后缀与 ETF 字样，用来在相关性之外做二次合并。"""
    s = name
    for suf in ("ETF", "etf"):
        s = s.replace(suf, "")
    # 去掉末尾 2~5 个字的基金公司名（如 华泰柏瑞/易方达/国泰/富国）
    companies = ["易方达", "华夏", "华泰柏瑞", "国泰", "广发", "南方", "嘉实", "博时", "富国",
                 "鹏华", "招商", "工银", "建信", "银华", "天弘", "汇添富", "景顺长城", "景顺",
                 "华宝", "华安", "国联安", "海富通", "万家", "平安", "大成", "国寿", "中银",
                 "鹏扬", "恒生前海", "西部利得", "国联", "融通", "华富", "中欧", "兴证全球"]
    for c in companies:
        if s.endswith(c):
            s = s[: -len(c)]
            break
    return s


def load_raw():
    uni = json.load(open(os.path.join(DATA_DIR, "universe.json"), encoding="utf-8"))
    out = {}
    for e in uni["etfs"]:
        p = os.path.join(KL_DIR, f"{e['code']}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        bars = [{"date": r[0], "open": r[1], "close": r[2], "amount": r[3]} for r in d["fmt"]
                if r[0] >= PANEL_START]
        if len(bars) < PARAMS["min_history"]:
            continue
        out[e["code"]] = {"name": e["name"], "bars": bars, "splits": d.get("splits", [])}
    return uni, out


def build_panel(codes, raw):
    dates = sorted({b["date"] for c in codes for b in raw[c]["bars"]})
    di = {d: i for i, d in enumerate(dates)}
    ci = {c: i for i, c in enumerate(codes)}
    n, m = len(dates), len(codes)
    O = np.full((n, m), np.nan, dtype=np.float64)
    C = np.full((n, m), np.nan, dtype=np.float64)
    A = np.full((n, m), np.nan, dtype=np.float64)
    for c in codes:
        j = ci[c]
        for b in raw[c]["bars"]:
            i = di.get(b["date"])
            if i is None:
                continue
            O[i, j], C[i, j], A[i, j] = b["open"], b["close"], b["amount"]
    return dates, codes, O, C, A


def recent_returns(C, k=PARAMS["dedupe_window"]):
    """近 k 日收益矩阵（n×m），用于相关性去重。"""
    r = np.full_like(C, np.nan)
    r[1:] = C[1:] / C[:-1] - 1
    return r


def dedupe(codes, names, C, A, rho=PARAMS["dedupe_rho"], window=PARAMS["dedupe_window"]):
    """按近 window 日收益相关 + 名称主干聚类；每簇保留近 20 日成交额中位最大的一只。
    返回 (保留 codes 列表, 每个保留 code 的簇成员 dict)。"""
    r = recent_returns(C, window)[-window:]
    liq = np.nanmedian(A[-20:], axis=0)
    # 名称主干分组
    by_stem = {}
    for j, n in enumerate(names):
        by_stem.setdefault(norm_name(n), []).append(j)
    parent = list(range(len(codes)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for js in by_stem.values():
        for j in js[1:]:
            union(js[0], j)
    # 相关性：先按成交额降序，只与"代表"比较，避免 O(n^2)
    order = np.argsort(-np.nan_to_num(liq))
    valid = ~np.all(np.isnan(r), axis=0)
    reps = []
    for j in order:
        if not valid[j]:
            continue
        rj = r[:, j]
        merged = False
        for k in reps:
            rk = r[:, k]
            ok = ~(np.isnan(rj) | np.isnan(rk))
            if ok.sum() < 60:
                continue
            a, b = rj[ok], rk[ok]
            sa, sb = a.std(), b.std()
            if sa == 0 or sb == 0:
                continue
            c = ((a - a.mean()) * (b - b.mean())).mean() / (sa * sb)
            if c > rho:
                union(k, j)
                merged = True
                break
        if not merged:
            reps.append(j)
    keep, clusters = [], {}
    for j in range(len(codes)):
        if not valid[j]:
            continue
        root = find(j)
        keep.append(root)
    keep = sorted(set(keep), key=lambda j: -np.nan_to_num(liq[j]))
    members = {}
    for j in range(len(codes)):
        members.setdefault(find(j), []).append(j)
    for j in keep:
        clusters[codes[j]] = [codes[k] for k in members.get(find(j), [j])]
    return [codes[j] for j in keep], clusters


def main():
    uni, raw = load_raw()
    codes_all = sorted(raw)
    names = [raw[c]["name"] for c in codes_all]
    sellable = [c for c in codes_all if not any(w in raw[c]["name"] for w in EXCLUDE_WORDS)]
    print(f"全量 {len(codes_all)} 只，剔除货币/债券/海外/商品后 {len(sellable)} 只")
    dates, codes, O, C, A = build_panel(sellable, raw)
    keep, clusters = dedupe(codes, [raw[c]["name"] for c in codes], C, A)
    print(f"按近 120 日相关性(>{PARAMS['dedupe_rho']})+名称主干去重后 {len(keep)} 只，"
          f"最大簇 {max(len(v) for v in clusters.values())} 只")
    np.savez_compressed(
        os.path.join(DATA_DIR, "panel.npz"),
        dates=np.array(dates), codes=np.array(keep),
        names=np.array([raw[c]["name"] for c in keep]),
        open=O[:, [codes.index(c) for c in keep]].astype(np.float32),
        close=C[:, [codes.index(c) for c in keep]].astype(np.float32),
        amount=A[:, [codes.index(c) for c in keep]].astype(np.float32),
    )
    json.dump({k: v for k, v in clusters.items() if len(v) > 1},
              open(os.path.join(DATA_DIR, "clusters.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"面板 {len(dates)} 个交易日 × {len(keep)} 只，写 data/panel.npz")


if __name__ == "__main__":
    main()
