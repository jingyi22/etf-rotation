"""组合回测（当前冠军模型）→ data/backtest.json，供 build_site.py 使用。

口径：收盘出信号、次日开盘成交、单边成本 0.1%、排名缓冲 + 相关性上限、沪深300 跌破年线切防守。
开发期（选模型用）与留出期（只检验）分开报告。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, PARAMS
import backtest as B
import common as CM
import features as F
import track as TR


def main():
    P = dict(PARAMS)
    pn = CM.load_panel()
    idx = CM.load_index()
    f = F.compute(pn, P)
    Rf = F.ranked_features(f)
    champ = TR.load_state()["champion"]
    S = B.model_score(Rf, champ["weights"], champ.get("smooth", 0))
    SEG = {"dev": (P["dev_start"], P["holdout_start"]), "holdout": (P["holdout_start"], "2100")}
    res = B.run(pn, f, S, idx, P)
    ev = B.evaluate(res, idx, SEG)
    ev_nd = B.evaluate(B.run(pn, f, S, idx, P, use_defense=False), idx, SEG)

    nav = np.cumprod(1 + res["rets"])
    m = dict(zip(*idx))
    b = np.array([m.get(d, np.nan) for d in res["dates"]], dtype=float)
    b = b / b[np.isfinite(b)][0]
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1
    step = 2
    curve = [{"date": res["dates"][i], "nav": round(float(nav[i]), 5),
              "bench": round(float(b[i]), 5) if np.isfinite(b[i]) else None}
             for i in list(range(0, len(nav), step)) + [len(nav) - 1]]
    dcurve = [{"date": res["dates"][i], "dd": round(float(dd[i]), 5)}
              for i in list(range(0, len(nav), step)) + [len(nav) - 1]]
    periods = []
    for label, key in (("完整区间", "all"), ("开发期 2016–2021", "dev"), ("留出期 2022 起", "holdout")):
        s, s2 = ev[key], ev_nd[key]
        periods.append({"label": label, "cagr": s["cagr"], "mdd": s["mdd"], "sharpe": s["sharpe"],
                        "node_win": s["node_win"], "node_beat": s["node_beat"], "turnover": s["turnover"],
                        "no_defense_cagr": s2["cagr"], "no_defense_mdd": s2["mdd"],
                        "bench_cagr": s["bench_cagr"], "bench_mdd": s["bench_mdd"]})
    pool = f["tradable"].sum(1)
    dates = [str(d) for d in pn["dates"]]
    cands = [{"date": dates[k], "n": int(pool[k])} for k in range(dates.index(res["dates"][0]), len(dates), 61)]
    # 最近调仓（回测口径，台账攒够之前作参考）
    recent = []
    lg = res["log"]
    for k in range(len(lg) - 1, 0, -1):
        cur, prv = {c: n for c, n in lg[k]["hold"]}, {c: n for c, n in lg[k - 1]["hold"]}
        if set(cur) != set(prv) or lg[k]["state"] != lg[k - 1]["state"]:
            recent.append({"signal_date": lg[k]["date"], "state": lg[k]["state"],
                           "switch": lg[k]["state"] != lg[k - 1]["state"],
                           "buy": [{"code": c, "name": n} for c, n in cur.items() if c not in prv],
                           "sell": [{"code": c, "name": n} for c, n in prv.items() if c not in cur]})
            if len(recent) >= 12:
                break
    out = {"model": champ, "start": res["dates"][0], "end": res["dates"][-1],
           "params": {k: P[k] for k in ("n_hold", "rank_buffer", "corr_cap", "min_amount", "min_history",
                                        "cost", "defense_ma", "defense_bond_w", "dev_start", "holdout_start")},
           "stats": ev["all"], "periods": periods, "yearly": ev["yearly"], "bench_yearly": ev["bench_yearly"],
           "curve": curve, "dd": dcurve, "candidates_per_chunk": cands, "recent": recent}
    json.dump(out, open(os.path.join(DATA_DIR, "backtest.json"), "w", encoding="utf-8"), ensure_ascii=False)
    for p in periods:
        print(f"{p['label']:14s} 年化 {p['cagr']:6.1%} 回撤 {p['mdd']:6.1%} 夏普 {p['sharpe']:.2f} "
              f"5日胜率 {p['node_win']:.0%} 换手 {p['turnover']:.1f} | 不防守 {p['no_defense_cagr']:6.1%} "
              f"| 沪深300 {p['bench_cagr']:6.1%}")


if __name__ == "__main__":
    main()
