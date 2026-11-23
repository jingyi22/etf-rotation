"""组合层面比较 8 个候选模型（开发期选择，留出期只看不选）。"""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS, CHALLENGERS
CHAMPION_V1 = next(c["weights"] for c in CHALLENGERS if c["name"] == "13因子等权")
import common as CM, features as F, backtest as B
pn = CM.load_panel(); idx = CM.load_index(); P = dict(PARAMS)
f = F.compute(pn, P); Rf = F.ranked_features(f)
SEG = {"dev": (P["dev_start"], P["holdout_start"]), "hold": (P["holdout_start"], "2100")}
C = {
 "趋势+低波(旧规则)": ({"dist250": .6, "vol20": -.4}, 0),
 "趋势+低波 平滑5": ({"dist250": .6, "vol20": -.4}, 5),
 "13因子等权": (CHAMPION_V1, 0),
 "13因子等权 平滑5": (CHAMPION_V1, 5),
 "13因子等权 平滑10": (CHAMPION_V1, 10),
 "趋势3": ({"dist250": 1, "dd250": 1, "dd60": 1}, 5),
 "低波3": ({"vol20": -1, "vol60": -1, "max20": -1}, 5),
 "高点距离+低波": ({"dd60": 1, "dd250": 1, "vol60": -1}, 5),
}
for nm, (w, sm) in C.items():
    S = B.model_score(Rf, w, sm); E = B.evaluate(B.run(pn, f, S, idx, P), idx, SEG); ev = E["dev"]; ho = E["hold"]
    print(f"{nm:16s} dev 年化{ev['cagr']:6.1%} 回撤{ev['mdd']:6.1%} 夏普{ev['sharpe']:5.2f} 换手{ev["turnover"]:5.1f} | hold 年化{ho["cagr"]:6.1%} 回撤{ho["mdd"]:6.1%} 夏普{ho["sharpe"]:5.2f}")
