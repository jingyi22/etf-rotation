"""从 data/kl + data/universe.json 构建统一面板（宽表），供特征、模型、回测、每日推荐共用。

- 剔除货币、债券、黄金商品、跨境类 ETF（只做 A 股股票型 ETF）
- 不做"按今天的相关性"去重（那会把未来信息带进历史，且链式合并会把不相关的 ETF 并成一簇）
  去重改在每个交易日按当时数据做：同一指数主干（名称中 "ETF" 之前的部分）只留当日成交额最大的一只，
  选样时再加相关性上限。见 features.point_in_time_dedupe / model.pick_with_corr_cap
- 输出 panel.npz：dates、codes、names、stems、open/close/amount（float32）
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, KL_DIR, PARAMS

PANEL_START = "2014-01-01"   # 面板统一起点

EXCLUDE_WORDS = ("货币", "债", "短融", "添益", "添利", "日利", "日日鑫", "快钱", "快线", "现金宝",
                 "财富宝", "现金", "理财", "收益宝", "保证金",
                 "黄金", "金ETF", "原油", "石油", "商品", "豆粕", "白银", "有色金属期货", "REIT",
                 "日经", "日本", "德国", "法国", "沙特", "美国", "道琼斯", "纳指", "纳斯达克", "标普",
                 "恒生", "港股", "香港", "中概", "亚太", "中韩", "东南亚", "越南", "印度", "海外",
                 "全球", "欧洲", "巴西", "新加坡", "H股")


def stem(name):
    """指数主干：名称中 'ETF' 之前的部分（'沪深300ETF华泰柏瑞' → '沪深300'）。"""
    s = name.split("ETF")[0].strip()
    return s or name


def load_raw():
    uni = json.load(open(os.path.join(DATA_DIR, "universe.json"), encoding="utf-8"))
    out = {}
    for e in uni["etfs"]:
        p = os.path.join(KL_DIR, f"{e['code']}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        rows = [r for r in d["fmt"] if r[0] >= PANEL_START]
        if len(rows) < PARAMS["min_history"]:
            continue
        out[e["code"]] = {"name": e["name"], "rows": rows}
    return out


def main():
    raw = load_raw()
    codes = sorted(c for c in raw if not any(w in raw[c]["name"] for w in EXCLUDE_WORDS))
    # 防守资产即使被排除也要进面板（只用于防守，不进候选池）
    for c in [PARAMS["defense_bond"]] + PARAMS["defense_defensive"]:
        if c in raw and c not in codes:
            codes.append(c)
    dates = sorted({r[0] for c in codes for r in raw[c]["rows"]})
    di = {d: i for i, d in enumerate(dates)}
    T, M = len(dates), len(codes)
    O = np.full((T, M), np.nan, dtype=np.float32)
    C = np.full((T, M), np.nan, dtype=np.float32)
    A = np.full((T, M), np.nan, dtype=np.float32)
    for j, c in enumerate(codes):
        for d, o, cl, a in raw[c]["rows"]:
            i = di[d]
            O[i, j], C[i, j], A[i, j] = o, cl, a
    names = [raw[c]["name"] for c in codes]
    np.savez_compressed(os.path.join(DATA_DIR, "panel.npz"),
                        dates=np.array(dates), codes=np.array(codes), names=np.array(names),
                        stems=np.array([stem(n) for n in names]),
                        open=O, close=C, amount=A)
    print(f"全量 {len(raw)} 只；股票型 A 股 ETF {M} 只（含防守资产）；面板 {T} 个交易日")


if __name__ == "__main__":
    main()
