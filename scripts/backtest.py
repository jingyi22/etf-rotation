"""组合回测引擎（日频检查、次日开盘成交、扣单边成本）。回测与每日推荐共用 decide()。

timing（只用 t 日收盘及之前的数据）：
  t 日收盘：算分、排名、决定目标持仓 target(t)
  t+1 开盘：按 target(t) 调仓；t+1 当日收益 = 昨收持仓吃隔夜 + 新持仓吃 open→close
"""
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import common as CM
import features as F

warnings.filterwarnings("ignore")


def model_score(Rf, weights, smooth=0):
    """横截面排名特征 × 权重；任一启用特征缺失则 NaN。
    smooth > 0：对分数做半衰期为 smooth 个交易日的指数平滑（只用过去数据），降低换手。"""
    S = None
    for k, w in weights.items():
        if not w:
            continue
        S = Rf[k] * w if S is None else S + Rf[k] * w
    if smooth:
        import pandas as pd
        raw = pd.DataFrame(S)
        S = np.where(np.isfinite(S), raw.ewm(halflife=smooth, ignore_na=True).mean().values, np.nan)
    return S


def regime(pn, idx, P):
    """沪深300 是否在 MA 之上（True = 进攻）。"""
    dates = [str(d) for d in pn["dates"]]
    m = dict(zip(*idx))
    hs = np.array([m.get(d, np.nan) for d in dates], dtype=float)
    n = int(P["defense_ma"])
    ma = np.full(len(dates), np.nan)
    for t in range(n - 1, len(dates)):
        w = hs[t - n + 1: t + 1]
        if np.isfinite(w).sum() > n * 0.6:
            ma[t] = np.nanmean(w)
    risk_on = np.where(np.isfinite(hs) & np.isfinite(ma), hs >= ma, True)
    return risk_on, hs, ma


def decide(t, S, f, held, P, codes):
    """t 日收盘的目标持仓（进攻模式）。返回 (picks, order, rank_of)。
    规则：已持有且排名 < n_hold + buffer 的保留；空位按分数从高到低补，
    跳过与已选 ETF 近 60 日收益相关 > corr_cap 的。"""
    s = S[t]
    ok = f["tradable"][t] & np.isfinite(s)
    idx = np.where(ok)[0]
    order = idx[np.argsort(-s[idx])]
    rank_of = {j: r for r, j in enumerate(order)}
    n, buf = P["n_hold"], P["rank_buffer"]
    picks = [j for j in sorted(held, key=lambda j: rank_of.get(j, 10 ** 6))
             if rank_of.get(j, 10 ** 6) < n + buf][:n]
    R = f["ret"][max(0, t - 59): t + 1]

    def corr(a, b):
        x, y = R[:, a], R[:, b]
        v = np.isfinite(x) & np.isfinite(y)
        if v.sum() < 30:
            return 0.0
        x, y = x[v] - x[v].mean(), y[v] - y[v].mean()
        d = np.sqrt((x * x).sum() * (y * y).sum())
        return float((x * y).sum() / d) if d > 0 else 0.0

    for j in order:
        if len(picks) >= n:
            break
        if j in picks:
            continue
        if any(corr(j, k) > P["corr_cap"] for k in picks):
            continue
        picks.append(j)
    return picks, order, rank_of


def defense_target(t, f, P, codes):
    """防守仓位；防守资产当日无价格的，权重转给国债 ETF。"""
    O, C = f["open"], f["close"]
    bond = codes.index(P["defense_bond"])
    wts = {bond: P["defense_bond_w"]}
    each = (1 - P["defense_bond_w"]) / len(P["defense_defensive"])
    for c in P["defense_defensive"]:
        j = codes.index(c) if c in codes else None
        if j is not None and np.isfinite(C[t, j]):
            wts[j] = each
        else:
            wts[bond] += each
    return wts


def run(pn, f, S, idx, P, use_defense=True):
    dates = [str(d) for d in pn["dates"]]
    codes = [str(c) for c in pn["codes"]]
    names = [str(n) for n in pn["names"]]
    O, C = f["open"], f["close"]
    T = len(dates)
    i0 = max(250, next(i for i, d in enumerate(dates) if d >= P["start"]))
    i1 = (max(i for i, d in enumerate(dates) if d <= P["end"]) + 1) if P.get("end") else T
    risk_on, _, _ = regime(pn, idx, P)
    if not use_defense:
        risk_on = np.ones(T, dtype=bool)

    def last_px(t, j):
        for k in (t, t - 1, t - 2, t - 3, t - 4):
            if k >= 0 and np.isfinite(C[k, j]) and C[k, j] > 0:
                return C[k, j]
        return np.nan

    def px_open(t, j):
        v = O[t, j]
        return v if np.isfinite(v) and v > 0 else last_px(t - 1, j)

    def px_close(t, j):
        v = C[t, j]
        return v if np.isfinite(v) and v > 0 else px_open(t, j)

    held, pending, w_prev = set(), None, {}
    rets, states, turn, log = [], [], [], []
    state_exec = "warmup"
    for t in range(i0, i1):
        if pending is not None:
            r_gap = 0.0
            for j, w in w_prev.items():
                p0 = last_px(t - 1, j)
                if np.isfinite(p0):
                    r_gap += w * (px_open(t, j) / p0 - 1)
            tv = sum(abs(pending.get(j, 0) - w_prev.get(j, 0)) for j in set(pending) | set(w_prev)) / 2
            r_gap -= tv * P["cost"]
            r_int = sum(w * (px_close(t, j) / px_open(t, j) - 1) for j, w in pending.items())
            rets.append((1 + r_gap) * (1 + r_int) - 1)
            turn.append(tv)
            w_prev = dict(pending)
        else:
            rets.append(0.0)
            turn.append(0.0)
        states.append(state_exec)
        if t >= i1 - 1:
            break
        if risk_on[t]:
            picks, _, _ = decide(t, S, f, held, P, codes)
            target = {j: 1.0 / len(picks) for j in picks} if picks else defense_target(t, f, P, codes)
            state_exec = "risk"
        else:
            target = defense_target(t, f, P, codes)
            state_exec = "defense"
        held = set(target) if state_exec == "risk" else set()
        pending = target
        log.append({"date": dates[t], "state": state_exec,
                    "hold": [(codes[j], names[j]) for j in target]})
    return {"dates": dates[i0:i0 + len(rets)], "rets": np.array(rets), "states": states,
            "turn": np.array(turn), "log": log}


def evaluate(res, idx, segments=None):
    """全区间与分段统计；基准为沪深300（价格指数）。"""
    dates, r = res["dates"], res["rets"]
    m = dict(zip(*idx))
    b = np.array([m.get(d, np.nan) for d in dates], dtype=float)
    br = np.concatenate([[0.0], b[1:] / b[:-1] - 1])
    br = np.where(np.isfinite(br), br, 0.0)

    def seg(mask):
        rr, bb = r[mask], br[mask]
        if len(rr) < 20:
            return None
        s = CM.stats_from_returns(rr)
        sb = CM.stats_from_returns(bb)
        n5 = len(rr) // 5
        nodes = rr[: n5 * 5].reshape(n5, 5)
        bnodes = bb[: n5 * 5].reshape(n5, 5)
        s.update(bench_cagr=sb["cagr"], bench_mdd=sb["mdd"],
                 node_win=float(((1 + nodes).prod(1) > 1).mean()),
                 node_beat=float(((1 + nodes).prod(1) > (1 + bnodes).prod(1)).mean()),
                 turnover=float(res["turn"][mask].sum() / max(s["yrs"], 1e-9)))
        return s

    d = np.array(dates)
    out = {"all": seg(np.ones(len(d), dtype=bool))}
    for name, (a, z) in (segments or {}).items():
        out[name] = seg((d >= a) & (d < z))
    out["yearly"] = CM.yearly_returns(dates, r)
    out["bench_yearly"] = CM.yearly_returns(dates, br)
    return out
