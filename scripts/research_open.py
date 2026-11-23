"""检验"结合开盘情况"能否改善推荐。

决策时点从"前一日收盘"挪到"当日开盘"：开盘时已知 gap = open(d)/close(d-1) - 1。
问题 1：gap 本身对之后收益有没有预测力？（开盘→收盘、开盘→h 日后开盘）
问题 2：把 gap 加进现有模型分数，排序有没有变好？
问题 3：市场层面的开盘强弱（候选池平均 gap）能不能改善进攻/防守切换？
开发期 2016-2021 用于判断，留出期 2022+ 只看不选。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import backtest as B
import common as CM
import features as F
import model as MD
import track as TR

pn = CM.load_panel()
f = F.compute(pn, PARAMS)
Rf = F.ranked_features(f)
dates = np.array([str(d) for d in pn["dates"]])
O, C = f["open"], f["close"]
T = len(dates)
mask = f["tradable"]
dev = (dates >= "2016") & (dates < "2022")
hold = dates >= "2022"

champ = TR.load_state()["champion"]
S_prev = B.model_score(Rf, champ["weights"], champ.get("smooth", 0))   # 前一日收盘算的分

# 对齐到"开盘日 d"：行 d 的信息 = 前一日收盘分 S_prev[d-1] + 当日开盘 gap[d]
def shift_down(X):
    Y = np.full_like(X, np.nan, dtype=float)
    Y[1:] = X[:-1]
    return Y

S_open = shift_down(S_prev)
mask_d = shift_down(mask.astype(float)) > 0.5
gap = np.full(O.shape, np.nan)
gap[1:] = O[1:] / C[:-1] - 1
gap = np.where(mask_d & np.isfinite(gap), gap, np.nan)
R_gap = F.xs_rank(gap, mask_d)
R_S = F.xs_rank(S_open, mask_d)

# 标签（从开盘日 d 的开盘价买入）
intraday = C / O - 1                                     # open(d) -> close(d)
def open_fwd(h):
    y = np.full(O.shape, np.nan)
    y[: T - h] = O[h:] / O[: T - h] - 1                 # open(d) -> open(d+h)
    return y

labels = {"当日开盘→收盘": intraday, "开盘买 持1日": open_fwd(1), "开盘买 持5日": open_fwd(5),
          "开盘买 持10日": open_fwd(10)}


def report(name, S):
    out = []
    for ln, y in labels.items():
        yv = np.where(mask_d, y, np.nan)
        ic = MD.ic_of_scores(S, yv)
        hit = MD.topk_hit(S, yv, mask_d, 5)
        cell = []
        for m in (dev, hold):
            cell.append(f"IC {np.nanmean(ic[m]):+.3f} 前5-池 {np.nanmean(hit[m, 0] - hit[m, 3]) * 100:+.2f}% "
                        f"跑赢中位 {np.nanmean(hit[m, 1]):.1%}")
        out.append(f"   {ln:10s} dev {cell[0]} | hold {cell[1]}")
    print(f"\n## {name}")
    print("\n".join(out))


print("=== 问题 1：开盘跳空本身的预测力 ===")
report("gap（高开得分高 = 追涨）", R_gap)
report("−gap（低开得分高 = 抄低开）", -R_gap)

print("\n=== 问题 2：现有模型 + 开盘信息 ===")
report("现有模型（前一日收盘分，开盘买）", R_S)
for w in (0.25, 0.5):
    report(f"现有模型 + {w} × gap", R_S + w * R_gap)
    report(f"现有模型 − {w} × gap", R_S - w * R_gap)

print("\n=== 问题 3：市场开盘强弱 → 当日池平均收益 ===")
pool_gap = np.nanmean(gap, 1)
pool_intra = np.nanmean(np.where(mask_d, intraday, np.nan), 1)
pool_fwd5 = np.nanmean(np.where(mask_d, open_fwd(5), np.nan), 1)
for nm, m in (("dev", dev), ("hold", hold)):
    v = m & np.isfinite(pool_gap) & np.isfinite(pool_intra)
    g, a, b5 = pool_gap[v], pool_intra[v], pool_fwd5[v]
    q = np.quantile(g, [0.2, 0.8])
    lo, hi = g <= q[0], g >= q[1]
    c1 = np.corrcoef(g, a)[0, 1]
    v5 = np.isfinite(b5)
    c5 = np.corrcoef(g[v5], b5[v5])[0, 1]
    print(f"  {nm}: 池平均gap 与 当日开盘→收盘 相关 {c1:+.3f}，与 之后5日 相关 {c5:+.3f}；"
          f"低开20%日 当日 {np.mean(a[lo]) * 100:+.2f}% / 高开20%日 当日 {np.mean(a[hi]) * 100:+.2f}%")
