"""候选池门槛只看开发期（2016-2021）决定；同时打印留出期以便事后检查。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS
import common as CM, features as F, model as MD
pn = CM.load_panel(); dates = [str(d) for d in pn["dates"]]
dev = np.array(["2016" <= d < "2022" for d in dates]); hold = np.array([d >= "2022" for d in dates])
names = list(F.FEATURES)
for amt in (1e7, 2e7, 5e7):
    for hist in (60, 120):
        P = dict(PARAMS, min_amount=amt, min_history=hist)
        f = F.compute(pn, P); mask = f["tradable"]; Rf = F.ranked_features(f, names); X = MD.stack(Rf, names)
        y = F.labels(f, 10); st = MD.daily_stats(X, MD.label_rank(y, mask))
        dev_ic = np.nanmean(st["ic"][dev], 0)
        pre = {k: float(np.sign(v)) for k, v in zip(names, dev_ic) if abs(v) >= 0.02}
        S = sum(Rf[k] * v for k, v in pre.items())
        ic = MD.ic_of_scores(S, y); hit = MD.topk_hit(S, y, mask, 5)
        pool = mask.sum(1)
        def fmt(m): return f"IC {np.nanmean(ic[m]):+.3f} top5-池 {np.nanmean(hit[m,0]-hit[m,3])*100:+.2f}% 跑赢中位 {np.nanmean(hit[m,1]):.1%}"
        print(f"amt {amt/1e4:.0f}万 hist {hist}: 池中位 dev {int(np.median(pool[dev]))} hold {int(np.median(pool[hold]))} | 因子{len(pre)} | dev {fmt(dev)} | hold {fmt(hold)}")
