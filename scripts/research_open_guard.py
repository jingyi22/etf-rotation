"""开盘"不追高"规则：新买入候选若集合竞价高开超过阈值，则跳过、由下一名补位。保留/卖出不变。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import backtest as B, common as CM, features as F
P = dict(PARAMS, min_amount=1e8, start="2020-01-01")
pn = CM.load_panel(); idx = CM.load_index(); f = F.compute(pn, P); Rf = F.ranked_features(f)
SEG = {"dev": ("2020-01-01", "2024-01-01"), "hold": ("2024-01-01", "2100")}
S = B.model_score(Rf, {"dist250": .6, "vol20": -.4}, 5)
base = B.run(pn, f, S, idx, P); dd = np.array(base["dates"])
orig = B.open_adjust
for thr in (0.01, 0.02, 0.03):
    def guard(t_exec, f_, P_, w, thr=thr):
        O, C = f_["open"], f_["close"]
        g = O[t_exec] / C[t_exec - 1] - 1
        return {int(j): -1e6 for j in np.where(f_["tradable"][t_exec - 1] & np.isfinite(g) & (g > thr))[0]}
    B.open_adjust = guard
    res = B.run(pn, f, S, idx, P, open_w=1.0)
    B.open_adjust = orig
    E = B.evaluate(res, idx, SEG); diff = res["rets"] - base["rets"]; ts = []
    for a, z in SEG.values():
        m = (dd >= a) & (dd < z); x = diff[m]; ts.append(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else 0)
    print(f"高开>{thr:.0%}不买: dev 年化{E['dev']['cagr']:6.1%} 夏普{E['dev']['sharpe']:.2f} | hold 年化{E['hold']['cagr']:6.1%} 夏普{E['hold']['sharpe']:.2f} | t {ts[0]:+.2f}/{ts[1]:+.2f}")
g = f["open"][1:] / f["close"][:-1] - 1
m = f["tradable"][:-1] & np.isfinite(g)
print("流动性池单只 ETF 开盘跳空分布：|gap|>1% 占", f"{np.mean(np.abs(g[m])>0.01):.1%}", " >2% 占", f"{np.mean(g[m]>0.02):.1%}", " >3% 占", f"{np.mean(g[m]>0.03):.1%}")
