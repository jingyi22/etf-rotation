"""开盘反转效应的稳健性：是不是开盘价噪声（集合竞价成交稀少、买卖价差）造成的假象？
检验：①只看流动性好的 ETF；②收益改从当日收盘起算（不再用开盘价，噪声影响消失）；③分年稳定性。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import common as CM, features as F, model as MD
pn = CM.load_panel(); f = F.compute(pn, PARAMS)
dates = np.array([str(d) for d in pn["dates"]]); O, C = f["open"], f["close"]; T = len(dates)
def down(X):
    Y = np.full(X.shape, np.nan); Y[1:] = X[:-1]; return Y
a20 = down(f["a20"]); base = down(f["tradable"].astype(float)) > 0.5
gap = np.full(O.shape, np.nan); gap[1:] = O[1:] / C[:-1] - 1
intraday = C / O - 1
c2c = {h: np.concatenate([C[h:] / C[:-h] - 1, np.full((h, C.shape[1]), np.nan)]) for h in (1, 5)}  # close(d)->close(d+h)
dev = (dates >= "2016") & (dates < "2022"); hold = dates >= "2022"
def go(tag, mask):
    R = F.xs_rank(np.where(mask, -gap, np.nan), mask)
    for ln, y in (("开盘→当日收盘", intraday), ("当日收盘→次日收盘(不含开盘价)", c2c[1]), ("当日收盘→5日后收盘", c2c[5])):
        yv = np.where(mask, y, np.nan); ic = MD.ic_of_scores(R, yv); hit = MD.topk_hit(R, yv, mask, 5)
        print(f"  {tag:14s} {ln:20s} dev IC {np.nanmean(ic[dev]):+.3f} 跑赢中位 {np.nanmean(hit[dev,1]):.1%} | "
              f"hold IC {np.nanmean(ic[hold]):+.3f} 跑赢中位 {np.nanmean(hit[hold,1]):.1%}")
print("低开得分高（−gap）：")
go("全部候选", base)
go("成交额≥1亿", base & (np.nan_to_num(a20) >= 1e8))
go("成交额≥5亿", base & (np.nan_to_num(a20) >= 5e8))
print("\n分年 IC（全部候选，开盘→当日收盘）：")
R = F.xs_rank(np.where(base, -gap, np.nan), base); ic = MD.ic_of_scores(R, np.where(base, intraday, np.nan))
print("  " + "  ".join(f"{y}:{np.nanmean(ic[[d.startswith(y) for d in dates]]):+.3f}" for y in map(str, range(2016, 2027))))

print("\n能否当成日内策略交易（开盘买低开最多的 5 只、收盘卖；扣双边 0.2% 成本）：")
for tag, m in (("全部候选", base), ("成交额≥1亿", base & (np.nan_to_num(a20) >= 1e8))):
    R = F.xs_rank(np.where(m, -gap, np.nan), m)
    hit = MD.topk_hit(R, np.where(m, intraday, np.nan), m, 5)
    for nm, s in (("dev", dev), ("hold", hold)):
        g = np.nanmean(hit[s, 0]); p = np.nanmean(hit[s, 3])
        print(f"  {tag:10s} {nm:4s} 前5 每日 {g*100:+.3f}%  池均 {p*100:+.3f}%  扣 0.2% 成本后 {(g-0.002)*100:+.3f}%/日")
