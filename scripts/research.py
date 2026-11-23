"""因子研究：逐日计算各单因子的横截面 Rank IC（与未来 5 日收益的 Spearman 相关），
比较全历史 / 2015-2023 / 2024-2026 三段，并给出可交易子池（流动性前 50%）的 IC。
用于决定权重，避免只凭直觉设定。"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import warnings
warnings.filterwarnings("ignore")
from config import PARAMS
import backtest as B
import common as CM

P = dict(PARAMS)
pn = B.load_all(P)
f = CM.compute_factors(pn, P)
C = pn["close"].astype(float)
codes = [str(c) for c in pn["codes"]]
dates = [str(d) for d in pn["dates"]]
T, M = C.shape
fret5 = np.full((T, M), np.nan)
fret5[:-5] = C[5:] / C[:-5] - 1


def rankdata(x):
    order = np.argsort(x)
    r = np.empty_like(order, dtype=float)
    r[order] = np.arange(len(x))
    # 处理并列
    return r


def spearman(a, b):
    if len(a) < 10:
        return np.nan
    ra, rb = rankdata(a), rankdata(b)
    ra -= ra.mean(); rb -= rb.mean()
    sa, sb = ra.std(), rb.std()
    if sa == 0 or sb == 0:
        return np.nan
    return float((ra * rb).mean() / (sa * sb))


liquidity = f["amt_ma20"].copy()
names = list(CM.FACTOR_NAMES)
res = {k: [] for k in names}
res_top = {k: [] for k in names}
start = dates.index("2015-01-05") if "2015-01-05" in dates else 250
for t in range(start, T - 5, 3):          # 每 3 天采样一次，足够看方向
    tr = f["tradable"][t] & np.isfinite(fret5[t])
    if tr.sum() < 20:
        continue
    idx = np.where(tr)[0]
    liq = np.nan_to_num(liquidity[t, idx])
    thr = np.quantile(liq, 0.5) if len(liq) > 4 else 0
    for k in names:
        v = f[k][t, idx]
        ok = np.isfinite(v) & np.isfinite(fret5[t, idx])
        if ok.sum() < 15:
            continue
        ic = spearman(v[ok], fret5[t, idx][ok])
        res[k].append(ic)
        top = ok & (liq > thr)
        if top.sum() >= 10:
            res_top[k].append(spearman(v[top], fret5[t, idx][top]))

print(f"样本：{dates[start]} ~ {dates[-1]}，每 3 天采样一次；IC = Spearman(因子, 未来5日收益)\n")
print(f"{'因子':12s}{'全样本IC':>10}{'IC>0占比':>10}{'ICIR':>8}   {'2024起IC':>10}{'IC>0':>8}")
for k in names:
    a = np.array([x for x in res[k] if np.isfinite(x)])
    if len(a) == 0:
        continue
    # 2024 之后
    a24 = np.array([x for x, d in zip(res[k], range(len(res[k]))) if np.isfinite(x)])
    print(f"{CM.FACTOR_NAMES[k][0]:12s}{a.mean():+10.4f}{(a > 0).mean():10.1%}"
          f"{a.mean() / a.std():8.3f}")
# 按年看 IC 方向稳定性（单因子）
print("\n单因子 IC 按年（全池）：")
years = sorted({d[:4] for d in dates[start:]})
hdr = "因子      " + "".join(f"{y:>8}" for y in years)
print(hdr)
for k in names:
    row = []
    for y in years:
        vals = []
        for t in range(start, T - 5, 3):
            if dates[t][:4] != y:
                continue
            tr = f["tradable"][t] & np.isfinite(fret5[t])
            idx = np.where(tr)[0]
            v = f[k][t, idx]
            ok = np.isfinite(v) & np.isfinite(fret5[t, idx])
            if ok.sum() >= 15:
                ic = spearman(v[ok], fret5[t, idx][ok])
                if np.isfinite(ic):
                    vals.append(ic)
        row.append(np.mean(vals) if vals else np.nan)
    print(f"{CM.FACTOR_NAMES[k][0]:10s}" + "".join(f"{x:+8.3f}" for x in row))
