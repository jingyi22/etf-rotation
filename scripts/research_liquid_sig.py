"""流动性池候选 vs 现模型：开发期（2020-2023）差异是否显著。
①组合日收益差的 t 值；②10 日 Rank IC 差的 t 值（按 10 日重叠折算），与每日晋级规则同一口径。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import backtest as B, common as CM, features as F, model as MD
P = dict(PARAMS, min_amount=1e8, dev_start="2020-01-01", holdout_start="2024-01-01")
pn = CM.load_panel(); idx = CM.load_index(); f = F.compute(pn, P); Rf = F.ranked_features(f)
dates = np.array([str(d) for d in pn["dates"]]); dev = (dates >= "2020") & (dates < "2024")
y10 = F.labels(f, 10)
C = {"现模型": ({"dist250": .6, "vol20": -.4}, 5), "中期动量": ({"r60": 1, "r120": 1}, 5),
     "趋势3": ({"dist250": 1, "dd250": 1, "dd60": 1}, 5), "短期反转+低波": ({"r5": -1, "vol20": -1}, 3),
     "低波3": ({"vol20": -1, "vol60": -1, "max20": -1}, 5)}
R, IC = {}, {}
for nm, (w, sm) in C.items():
    S = B.model_score(Rf, w, sm)
    res = B.run(pn, f, S, idx, dict(P, start="2020-01-01", end="2023-12-31"))
    R[nm] = res["rets"]; IC[nm] = MD.ic_of_scores(S, y10)[dev]
base = "现模型"
for nm in C:
    if nm == base:
        continue
    d = R[nm] - R[base]; t1 = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    e = IC[nm] - IC[base]; e = e[np.isfinite(e)]; t2 = e.mean() / (e.std(ddof=1) / np.sqrt(len(e) / 10))
    print(f"{nm:10s} vs 现模型：日收益差 {d.mean()*244*100:+.1f}%/年 t={t1:+.2f} | 10日IC差 {e.mean():+.3f} t={t2:+.2f}")
