"""预注册规则：方向与入选只用开发期（2016-2021，h=10）IC 决定，|IC|>=0.02 入选、等权；再测留出期。
同时测"扩展窗口 IC 符号 + 等权"（每天自动更新方向，不设门槛）。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import common as CM, features as F, model as MD
pn = CM.load_panel(); f = F.compute(pn, PARAMS)
names = list(F.FEATURES); Rf = F.ranked_features(f, names); X = MD.stack(Rf, names)
dates = [str(d) for d in pn["dates"]]; mask = f["tradable"]
dev = np.array(["2016" <= d < "2022" for d in dates]); hold = np.array([d >= "2022" for d in dates])
y10 = F.labels(f, 10); st10 = MD.daily_stats(X, MD.label_rank(y10, mask))
dev_ic = np.nanmean(st10["ic"][dev], 0)
pre = {k: float(np.sign(v)) for k, v in zip(names, dev_ic) if abs(v) >= 0.02}
print("预注册因子:", {F.FEATURES[k]: int(v) for k, v in pre.items()})
for h in (5, 10, 20):
    y = F.labels(f, h); st = MD.daily_stats(X, MD.label_rank(y, mask))
    rows = {}
    S1 = sum(Rf[k] * v for k, v in pre.items()); rows["预注册等权"] = S1
    Wt = MD.rolling_weights(st, h, None, "sign", lam=0.0, min_days=250, names=names); rows["扩展窗口符号等权"] = MD.scores(X, Wt)
    Wt = MD.rolling_weights(st, h, None, "ic", min_days=250, names=names); rows["扩展窗口IC加权"] = MD.scores(X, Wt)
    for nm, S in rows.items():
        ic = MD.ic_of_scores(S, y); hit = MD.topk_hit(S, y, mask, 5)
        def fmt(m): return f"IC {np.nanmean(ic[m]):+.3f} 正比{np.nanmean(ic[m]>0):.0%} top5-池 {np.nanmean(hit[m,0]-hit[m,3])*100:+.2f}% 跑赢中位 {np.nanmean(hit[m,1]):.1%}"
        print(f"h={h:2d} {nm:10s} dev {fmt(dev)} | hold {fmt(hold)}")
