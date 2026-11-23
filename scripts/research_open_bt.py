"""开盘复核的组合回测（流动性池 ≥1 亿）：新买入的空位按集合竞价跳空重排（低开优先），保留/卖出不变。
开发期 2020-2023 选权重 w；留出期 2024+ 只检验。buy_slip 检验开盘成交价更差时是否还成立。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import backtest as B, common as CM, features as F
P = dict(PARAMS, min_amount=1e8, start="2020-01-01")
pn = CM.load_panel(); idx = CM.load_index(); f = F.compute(pn, P); Rf = F.ranked_features(f)
SEG = {"dev": ("2020-01-01", "2024-01-01"), "hold": ("2024-01-01", "2100")}
S = B.model_score(Rf, {"dist250": .6, "vol20": -.4}, 5)
base = B.run(pn, f, S, idx, P)
print(f"{'开盘复核权重':10s} {'加滑点':6s} | dev 年化 回撤 夏普 | hold 年化 回撤 夏普 | 换手 | 相对不复核的日收益差 t(dev/hold)")
for w in (0.0, 0.25, 0.5, 1.0):
    for slip in ((0.0, 0.001, 0.002) if w else (0.0,)):
        res = B.run(pn, f, S, idx, P, open_w=w, buy_slip=slip)
        E = B.evaluate(res, idx, SEG); d, o = E["dev"], E["hold"]
        dd = np.array(res["dates"]); diff = res["rets"] - base["rets"]
        ts = []
        for a, z in SEG.values():
            m = (dd >= a) & (dd < z); x = diff[m]
            ts.append(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else 0.0)
        print(f"{w:10.2f} {slip*100:5.1f}% | {d['cagr']:6.1%} {d['mdd']:6.1%} {d['sharpe']:4.2f} | "
              f"{o['cagr']:6.1%} {o['mdd']:6.1%} {o['sharpe']:4.2f} | {E['all']['turnover']:4.1f} | {ts[0]:+.2f} / {ts[1]:+.2f}")
