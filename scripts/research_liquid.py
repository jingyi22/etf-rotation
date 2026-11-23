"""在流动性好的候选池（近 20 日日均成交额 ≥ 1 亿元）里重新选模型。

1 亿门槛下 2016-2019 每天只有 3-9 只候选，排序检验没有意义。改为：
  开发期 2020-01 ~ 2023-12（候选池 10-48 只）—— 用于选择
  留出期 2024-01 起（34-83 只）—— 只检验
单因子 IC → 预注册方向；组合候选 → 组合回测，开发期夏普最高者胜出。
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import backtest as B, common as CM, features as F, model as MD

P = dict(PARAMS, min_amount=1e8, dev_start="2020-01-01", holdout_start="2024-01-01")
pn = CM.load_panel(); idx = CM.load_index()
f = F.compute(pn, P); names = list(F.FEATURES); Rf = F.ranked_features(f, names); X = MD.stack(Rf, names)
dates = np.array([str(d) for d in pn["dates"]]); mask = f["tradable"]
dev = (dates >= P["dev_start"]) & (dates < P["holdout_start"]); hold = dates >= P["holdout_start"]

print("=== 单因子 Rank IC（开盘买入，持有 h 日） dev 2020-23 | hold 2024+ ===")
ics = {}
for h in (5, 10, 20):
    y = F.labels(f, h); st = MD.daily_stats(X, MD.label_rank(y, mask)); ics[h] = st["ic"]
print(f"  {'因子':12s}" + "".join(f"   h={h:<2d} dev / hold  " for h in (5, 10, 20)))
for k, nm in enumerate(names):
    print(f"  {F.FEATURES[nm]:12s}" + "".join(f"  {np.nanmean(ics[h][dev, k]):+.3f} / {np.nanmean(ics[h][hold, k]):+.3f}  " for h in (5, 10, 20)))
dev10 = np.nanmean(ics[10][dev], 0)
pre = {k: float(np.sign(v)) for k, v in zip(names, dev10) if abs(v) >= 0.02}
print("\n预注册（dev 10 日 |IC|≥0.02，按符号等权）:", {F.FEATURES[k]: int(v) for k, v in pre.items()})

C = {
    "现模型 距年线+低波": ({"dist250": .6, "vol20": -.4}, 5),
    "预注册等权": (pre, 5),
    "趋势3": ({"dist250": 1, "dd250": 1, "dd60": 1}, 5),
    "低波3": ({"vol20": -1, "vol60": -1, "max20": -1}, 5),
    "高点距离+低波": ({"dd60": 1, "dd250": 1, "vol60": -1}, 5),
    "中期动量": ({"r60": 1, "r120": 1}, 5),
    "短期反转+低波": ({"r5": -1, "vol20": -1}, 3),
    "无选股(候选池等权前5=按成交额)": ({"liq": 1}, 0),
}
SEG = {"dev": (P["dev_start"], P["holdout_start"]), "hold": (P["holdout_start"], "2100")}
print("\n=== 组合回测（扣 0.1% 单边，次日开盘成交，年线防守） ===")
for nm, (w, sm) in C.items():
    if not w:
        continue
    S = B.model_score(Rf, w, sm)
    E = B.evaluate(B.run(pn, f, S, idx, dict(P, start="2020-01-01")), idx, SEG)
    y10 = F.labels(f, 10); hit = MD.topk_hit(S, y10, mask, 5)
    d, o = E["dev"], E["hold"]
    print(f"  {nm:22s} dev 年化{d['cagr']:6.1%} 回撤{d['mdd']:6.1%} 夏普{d['sharpe']:5.2f} 跑赢中位{np.nanmean(hit[dev,1]):.1%} | "
          f"hold 年化{o['cagr']:6.1%} 回撤{o['mdd']:6.1%} 夏普{o['sharpe']:5.2f} 跑赢中位{np.nanmean(hit[hold,1]):.1%} | 换手{E['all']['turnover']:.1f}")
