"""线上信号 + 回测结果，输出 data/signals.json 与 data/backtest.json（供 build_site.py 使用）。

口径与回测完全一致：
  1) 收盘出信号，次日开盘调仓；
  2) 单边成本 0.1% 在回测中扣除；
  3) 持仓变更规则：排名缓冲 + 最低持有期 + 与回测同一套去重后的候选池。
"""
import json
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")
from config import DATA_DIR, PARAMS
import common as CM
import backtest as B


def main():
    P = dict(PARAMS)
    pn = B.load_all(P)
    idx = B.load_index()
    dates = [str(d) for d in pn["dates"]]
    codes = [str(c) for c in pn["codes"]]
    names = [str(n) for n in pn["names"]]
    f = CM.compute_factors(pn, P)
    res = B.run(pn, P, dates, hs300=idx)
    st = B.evaluate(res, idx, P)

    # ---------- 回测结果 ----------
    # 净值曲线（逐日）
    nav = np.cumprod(1 + res["rets"])
    m = {d: c for d, c in zip(*idx)}
    b = np.array([m.get(d, np.nan) for d in res["dates"]])
    bnav = b / b[0]
    # 每 5 个交易日抽样，控制文件体积
    step = 2
    curve = [{"date": res["dates"][i], "nav": round(float(nav[i]), 6),
              "bench": round(float(bnav[i]), 6) if np.isfinite(bnav[i]) else None}
             for i in range(0, len(nav), step)]
    if curve[-1]["date"] != res["dates"][-1]:
        i = len(nav) - 1
        curve.append({"date": res["dates"][i], "nav": round(float(nav[i]), 6),
                      "bench": round(float(bnav[i]), 6) if np.isfinite(bnav[i]) else None})
    # 回撤曲线
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1
    dcurve = [{"date": res["dates"][i], "dd": round(float(dd[i]), 5)}
              for i in range(0, len(nav), step)]
    # 分段候选池数量（每半年一个点）
    candidates_per_chunk = []
    try:
        _f = CM.compute_factors(pn, P)
        t0 = dates.index(P["start"])
        for k in range(t0, len(dates), 122):
            candidates_per_chunk.append({"date": dates[k], "n": int(_f["tradable"][k].sum())})
    except Exception:
        pass
    first_full_year = None
    for k, d in enumerate(dates):
        if k >= 250 and int(np.isfinite(pn["close"][k]).sum()) >= 100:
            first_full_year = d[:4]
            break
    # 分区间（稳健性）：同一套参数，不同起点
    periods = []
    for tag, s0 in [("2015 起（完整）", "2015-01-01"), ("2017 起", "2017-01-01"),
                    ("2019 起", "2019-01-01"), ("2021 起", "2021-01-01"),
                    ("2024 起", "2024-01-01")]:
        Pp = dict(P, start=s0)
        if s0 == "2015-01-01":
            stp = st
        else:
            stp = B.evaluate(B.run(pn, Pp, dates, hs300=idx), idx, Pp)
        periods.append({"label": tag, "cagr": stp["cagr"], "mdd": stp["mdd"],
                        "sharpe": stp["sharpe"], "bench_cagr": stp["bench"]["cagr"],
                        "bench_mdd": stp["bench"]["mdd"]})
        Pp2 = dict(Pp)
        stq = B.evaluate(B.run(pn, Pp2, dates, hs300=None), idx, Pp2)
        periods[-1]["no_defense_cagr"] = stq["cagr"]
        periods[-1]["no_defense_mdd"] = stq["mdd"]

    out_bt = {
        "start": res["dates"][0], "end": res["dates"][-1],
        "params": {k: P[k] for k in ("n_hold", "rank_buffer", "min_amount", "min_amount_cap",
                                     "cap_from", "cost", "defense_ma", "defense_bond_w",
                                     "w_dist252", "w_vol20")},
        "coverage": {"first_full_year": first_full_year, "etfs_today": int(np.isfinite(pn["close"][-1]).sum())},
        "stats": {k: st[k] for k in ("nav", "cagr", "vol", "sharpe", "mdd", "win_rate",
                                     "node_win", "node_beat", "turnover")},
        "bench": {k: st["bench"][k] for k in ("nav", "cagr", "mdd", "sharpe")},
        "yearly": st["yearly"], "bench_yearly": st["bench"]["yearly"],
        "candidates_per_chunk": candidates_per_chunk,
        "periods": periods,
        "curve": curve, "dd": dcurve,
        "defense_days": st["events"].get("defense", 0),
        "risk_days": st["events"].get("risk", 0),
    }

    # ---------- 今日信号 ----------
    t = len(dates) - 1
    last_date = dates[t]
    seg = b[-int(P["defense_ma"]):]
    ma = float(np.nanmean(seg)) if np.isfinite(seg).sum() > 0.6 * len(seg) else None
    hs = float(b[-1])
    risk_on = bool(hs >= ma) if ma else True

    score, zs = CM.factor_score(f, P)
    ok = f["tradable"][t] & ~np.isnan(score[t])
    if P["defense_bond"] in codes:          # 国债 ETF 只作防守工具
        ok[codes.index(P["defense_bond"])] = False
    idxs = np.where(ok)[0]
    order = idxs[np.argsort(-score[t, idxs])]
    prev_hold = res["log"][-1]["hold"] if res["log"] else []
    prev_codes = {c for c, _ in prev_hold}

    if risk_on:
        picks = []
        for c, n in prev_hold:
            if c in codes:
                j = codes.index(c)
                rank = int(np.where(order == j)[0][0]) if j in order else 10 ** 6
                if rank < P["n_hold"] + P["rank_buffer"] and ok[j]:
                    picks.append((c, n))
        for j in order:
            if len(picks) >= P["n_hold"]:
                break
            c = codes[j]
            if c in {x[0] for x in picks}:
                continue
            if any(w in names[j] for w in ("债", "货币")):
                continue
            picks.append((c, names[j]))
        picks = picks[: P["n_hold"]]
        new_codes = [c for c, _ in picks]
        weights = {c: 1 / len(new_codes) for c in new_codes}
    else:
        defense = {P["defense_bond"]: P["defense_bond_w"]}
        for c in P["defense_defensive"]:
            defense[c] = (1 - P["defense_bond_w"]) / len(P["defense_defensive"])
        weights = defense

    def amt20(j):
        """近 20 日成交额中位数（亿元）：防守类 ETF 没有入选候选池，用它展示流动性。"""
        if j is None:
            return None
        t = len(pn["dates"]) - 1
        seg = pn["amount"][t - 19:t + 1, j]
        seg = seg[np.isfinite(seg)]
        return round(float(np.median(seg)) / 1e8, 2) if len(seg) else None

    holdings = []
    for c, w in weights.items():
        j = codes.index(c) if c in codes else None
        nm = names[j] if j is not None else c
        in_pool = j is not None and bool(ok[j])
        rank = (int(np.where(order == j)[0][0]) + 1) if in_pool else None
        sc = float(score[t, j]) if in_pool and np.isfinite(score[t, j]) else None
        row = {"code": c, "name": nm, "weight": round(w, 3), "in_pool": in_pool,
               "close": float(pn["close"][t, j]) if j is not None else None,
               "score": round(sc, 3) if sc is not None else None,
               "rank": rank,
               "is_new": c not in prev_codes,
               "dist252": round(float(f["dist252"][t, j]), 4) if j is not None and np.isfinite(f["dist252"][t, j]) else None,
               "vol20": round(float(f["vol20"][t, j]), 4) if j is not None and np.isfinite(f["vol20"][t, j]) else None,
               "amt_yi": amt20(j)}
        holdings.append(row)

    # 候选池前 15 名（供展示"打分榜"）
    top = []
    seen = set()
    for j in order:
        if any(w in names[j] for w in ("债", "货币")):
            continue
        seen.add(names[j])
        top.append({"code": codes[j], "name": names[j], "score": round(float(score[t, j]), 3),
                    "dist252": round(float(f["dist252"][t, j]), 4) if np.isfinite(f["dist252"][t, j]) else None,
                    "vol20": round(float(f["vol20"][t, j]), 4) if np.isfinite(f["vol20"][t, j]) else None,
                    "amt_yi": round(float(f["amt_ma20"][t, j]) / 1e8, 2) if np.isfinite(f["amt_ma20"][t, j]) else None,
                    "held": codes[j] in prev_codes})
        if len(top) >= 15:
            break

    # 最近调仓记录
    recent = []
    for k in range(max(0, len(res["log"]) - 30), len(res["log"])):
        lg = res["log"][k]
        prev = set(c for c, _ in (res["log"][k - 1]["hold"] if k > 0 else []))
        cur = set(c for c, _ in lg["hold"])
        if k == 0 or prev != cur or lg["state"] != res["log"][k - 1]["state"]:
            recent.append({"signal_date": lg["date"], "state": lg["state"],
                           "hold": [{"code": c, "name": n,
                                     "delta": ("buy" if c not in prev else "keep") if k > 0 else "init"}
                                    for c, n in lg["hold"]]})
    recent = recent[::-1][:12]

    sig = {
        "asof": last_date,
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "regime": {
            "risk_on": risk_on,
            "hs300": round(hs, 2), "ma250": round(ma, 2) if ma else None,
            "pct_from_ma": round(hs / ma - 1, 4) if ma else None,
        },
        "holdings": holdings,
        "top": top,
        "universe_size": int(ok.sum()),
        "recent": recent,
        "universe": [{"code": codes[j], "name": names[j],
                      "amt_yi": round(float(f["amt_ma20"][t, j]) / 1e8, 2)
                      if np.isfinite(f["amt_ma20"][t, j]) else None}
                     for j in np.where(f["tradable"][t])[0]],
    }
    json.dump(out_bt, open(os.path.join(DATA_DIR, "backtest.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump(sig, open(os.path.join(DATA_DIR, "signals.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"信号日期 {last_date}  状态 {'进攻' if risk_on else '防守'}  沪深300 {hs:.2f} "
          f"MA250 {ma:.2f}")
    for h in holdings:
        print(f"  {h['code']} {h['name']:16s} {h['weight']:.0%} 评分{h['score']} 排名{h['rank']} "
              f"距MA250 {h['dist252']:+.1%} 波动{h['vol20']:.1%} 成交额{h['amt_yi']}亿")
    s = out_bt["stats"]
    print(f"回测 {out_bt['start']}~{out_bt['end']}: 年化 {s['cagr']:.1%} 回撤 {s['mdd']:.1%} "
          f"夏普 {s['sharpe']:.2f} 换手 {s['turnover']:.1f} 5日胜率 {s['node_win']:.1%}")


if __name__ == "__main__":
    main()
