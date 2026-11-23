"""回测引擎（日频检查、次日开盘成交、扣单边成本）。

timing 约定（全部只用 t 日收盘及之前的数据）：
  t 日收盘：计算因子与排名，得到目标持仓 target(t)
  t+1 开盘：按 target(t) 调仓；t+1 当日收益 = 开盘前持仓吃隔夜 + 开盘后目标持仓吃日内
"""
import json
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from common import compute_factors, factor_score, load_panel, load_index, stats_from_returns, \
    yearly_returns

warnings.filterwarnings("ignore")

DEFENSE_CODES = ["511010", "515300", "515450", "515100"]


def load_all(P):
    pn = load_panel()
    codes = [str(c) for c in pn["codes"]]
    # 防守资产（国债/红利低波）可能被 universe 过滤掉，从 kl 缓存补进来
    need = [P["defense_bond"]] + P["defense_defensive"]
    import json as _j
    from config import KL_DIR
    for c in need:
        if c in codes:
            continue
        p = os.path.join(KL_DIR, f"{c}.json")
        if not os.path.exists(p):
            continue
        d = _j.load(open(p, encoding="utf-8"))
        bars = {r[0]: r for r in d["fmt"]}
        arr = np.full(len(pn["dates"]), np.nan, dtype=np.float32)
        for i, dt in enumerate(pn["dates"]):
            b = bars.get(str(dt))
            if b:
                arr[i] = b[2]
        for k in ("open", "close"):
            pn[k] = np.column_stack([pn[k], arr])              # 防守 ETF 只用收盘价计算
        pn["amount"] = np.column_stack([pn["amount"],
                                        np.full(len(pn["dates"]), np.nan, dtype=np.float32)])
        codes.append(c)
        pn["names"] = np.append(pn["names"], d["name"])
    pn["codes"] = np.array(codes)
    return pn


def rank_picks(score, tradable, t, n_hold, held, buffer, min_hold_ok):
    """t 日按合成分排序取前 n；已持有且仍在 n+buffer 内的保留。返回代码下标列表。"""
    s = score[t].copy()
    ok = tradable[t] & ~np.isnan(s)
    idx = np.where(ok)[0]
    order = idx[np.argsort(-s[idx])]
    rank = {j: r for r, j in enumerate(order)}
    picks = []
    # 先放能保留的老仓（按分数从高到低，在 n+buffer 之内、且满最低持有期）
    for j in sorted(held, key=lambda x: -s[x] if not np.isnan(s[x]) else 1e9):
        if min_hold_ok(j) and rank.get(j, 10 ** 6) < n_hold + buffer:
            picks.append(j)
    for j in order:
        if len(picks) >= n_hold:
            break
        if j in picks or not min_hold_ok(j):
            continue
        picks.append(j)
    return picks[:n_hold], rank, order


def run(pn, P, dates, hs300=None, verbose=False):
    f = compute_factors(pn, P)
    score, _ = factor_score(f, P)
    C, O = pn["close"].astype(float), pn["open"].astype(float)
    codes = [str(c) for c in pn["codes"]]
    T = len(dates)
    if P["start"] not in dates:
        P = dict(P, start=next(d for d in dates if d >= P["start"]))
    if P.get("end") and P["end"] not in dates:
        prev = [d for d in dates if d <= P["end"]]
        P = dict(P, end=prev[-1] if prev else dates[-1])
    i0 = max(0, dates.index(P["start"]))
    i0 = max(i0, 250)
    # 数据起点（2014 年）之前没有价格：从"已覆盖全市场的第一个交易日"开始记账
    cov = np.isfinite(pn["close"]).sum(axis=1)
    full = np.isfinite(pn["close"]).any(axis=1) & (pn["dates"] >= "2014-01-01")
    i0 = max(i0, int(np.argmax(full)))
    i1 = dates.index(P["end"]) + 1 if P.get("end") else len(dates)

    # 市场状态：沪深300 与 MA250
    if hs300 is not None:
        d_idx, close300 = hs300
        m = {d: c for d, c in zip(d_idx, close300)}
        hs = np.array([m.get(str(d), np.nan) for d in dates])
        n_ma = int(P.get("defense_ma", 250))
        ma = np.full(T, np.nan)
        for t in range(n_ma - 1, T):
            w = hs[t - n_ma + 1: t + 1]
            if np.isfinite(w).sum() > n_ma * 0.6:
                ma[t] = np.nanmean(w)
        risky = np.where(np.isfinite(hs) & np.isfinite(ma), hs >= ma, True)
    else:
        risky = np.ones(T, dtype=bool)

    defense = {P["defense_bond"]: P["defense_bond_w"]}
    for c in P["defense_defensive"]:
        defense[c] = (1 - P["defense_bond_w"]) / len(P["defense_defensive"])
    defense_idx = [codes.index(c) for c in defense if c in codes]

    def defense_target(t):
        """防守仓位；防御资产尚未上市或当日无价格的，权重顺延给国债ETF。"""
        wts, bond_j = {}, codes.index(P["defense_bond"])
        extra = 0.0
        for c, w in defense.items():
            j = codes.index(c)
            if not np.isfinite(O[t, j]) or not np.isfinite(C[t, j]):
                extra += w
            else:
                wts[j] = w
        if extra and bond_j in wts:
            wts[bond_j] += extra
        elif extra:
            wts[bond_j] = extra
        return wts

    def last_px(t, j):
        """t 日或之前最近一个有效收盘价（用于停牌日）。"""
        for k in (t, t - 1, t - 2):
            if k >= 0 and np.isfinite(C[k, j]) and C[k, j] > 0:
                return C[k, j]
        return np.nan

    def px_open(t, j):
        """执行日开盘价；当天停牌就用前一日收盘（相当于当天没能成交，按昨收记账）。"""
        v = O[t, j]
        return v if np.isfinite(v) and v > 0 else last_px(t - 1, j)

    def px_close(t, j):
        v = C[t, j]
        return v if np.isfinite(v) and v > 0 else px_open(t, j)

    # held 状态：j -> 买入日下标
    held = {}
    pending = None            # (target_weights dict, decided_at)
    exec_state = "risk"
    nav, rets, states, trade_log = 1.0, [], [], []
    weights_prev = {}
    turn = []
    hold_counter = {}

    for t in range(i0, i1):
        # ---- t 日开盘：执行 t-1 收盘决定的 pending ----
        if pending is not None:
            target = pending
            # 隔夜：昨收持仓吃 open(t)/close(t-1)
            r_gap = 0.0
            for j, w in weights_prev.items():
                p0 = last_px(t - 1, j)
                if np.isfinite(p0):
                    r_gap += w * (px_open(t, j) / p0 - 1)
            # 换手成本
            allj = set(target) | set(weights_prev)
            tv = sum(abs(target.get(j, 0.0) - weights_prev.get(j, 0.0)) for j in allj) / 2
            r_gap -= tv * P["cost"]
            # 日内：新持仓 open->close
            r_int = 0.0
            for j, w in target.items():
                r_int += w * (px_close(t, j) / px_open(t, j) - 1)
            r_day = (1 + r_gap) * (1 + r_int) - 1
            weights_prev = dict(target)
            turn.append(tv)
            nav *= 1 + r_day
            rets.append(r_day)
            states.append(exec_state)
        else:
            rets.append(0.0)
            states.append("warmup")

        # ---- t 日收盘：生成明日目标 ----
        if t >= T - 1 or t >= i1 - 1:
            break
        if risky[t]:
            def min_hold_ok(j, _t=t):
                return (P["min_hold_days"] == 0) or (_t - hold_counter.get(j, -10 ** 6) >= P["min_hold_days"])
            picked, rank, order = rank_picks(score, f["tradable"], t, P["n_hold"], held,
                                             P["rank_buffer"], min_hold_ok)
            target = {j: 1.0 / P["n_hold"] for j in picked}
            state = "risk"
        else:
            picked, target, state = [], defense_target(t), "defense"
        exec_state = state
        # 记录买入日
        for j in target:
            if j not in held:
                hold_counter[j] = t
        held = set(target)
        pending = target
        trade_log.append({"date": dates[t], "state": state,
                          "hold": [(codes[j], pn["names"][j]) for j in target]})
    rets = np.array(rets)
    return {"dates": dates[i0:i1], "rets": rets, "states": states, "turn": np.array(turn),
            "log": trade_log}


def evaluate(res, hs300, P, defense_daily=None):
    dates = res["dates"]
    st = stats_from_returns(res["rets"])
    st.update({"yearly": yearly_returns(dates, res["rets"]),
               "turnover": float(res["turn"].sum() / st["yrs"]) if st["yrs"] else 0,
               "trades": len(res["log"])})
    d_idx, close300 = hs300
    m = {d: c for d, c in zip(d_idx, close300)}
    b = np.array([m.get(str(d), np.nan) for d in dates])
    br = b[1:] / b[:-1] - 1
    ok = np.isfinite(br)
    st["bench"] = stats_from_returns(br[ok])
    st["bench"]["yearly"] = yearly_returns([d for d, o in zip(dates[1:], ok) if o], br[ok])
    # 5 日节点胜率
    r = res["rets"]
    nodes = [r[k:k + 5].sum() for k in range(0, len(r) - 5, 5)]
    bn = [br[ok][k:k + 5].sum() for k in range(0, len(br[ok]) - 5, 5)]
    st["node_win"] = float(np.mean([x > 0 for x in nodes]))
    st["node_beat"] = float(np.mean([a > b for a, b in zip(nodes, bn)]))
    st["events"] = {}
    for d, s in zip(dates, res["states"]):
        if s in ("risk", "defense"):
            st["events"][s] = st["events"].get(s, 0) + 1
    if defense_daily is not None:
        st["bench"]["cagr"] = defense_daily["cagr"]
        st["bench"]["mdd"] = defense_daily["mdd"]
        st["bench"]["nav"] = defense_daily["nav"]
        st["bench"]["sharpe"] = defense_daily["sharpe"]
    return st


def main():
    from config import PARAMS
    P = dict(PARAMS)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_hold", type=int)
    ap.add_argument("--min_hold", type=int)
    ap.add_argument("--buffer", type=int)
    ap.add_argument("--no_defense", action="store_true")
    ap.add_argument("--start")
    ap.add_argument("--cost", type=float)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.n_hold is not None:
        P["n_hold"] = a.n_hold
    if a.min_hold is not None:
        P["min_hold_days"] = a.min_hold
    if a.buffer is not None:
        P["rank_buffer"] = a.buffer
    if a.start:
        P["start"] = a.start
    if a.cost is not None:
        P["cost"] = a.cost
    pn = load_all(P)
    idx = load_index()
    hs = (idx[0], idx[1]) if not a.no_defense else None
    res = run(pn, P, list(pn["dates"]), hs300=idx if not a.no_defense else None)
    st = evaluate(res, idx, P)
    print(f"区间 {res['dates'][0]} ~ {res['dates'][-1]}  参数 n_hold={P['n_hold']} "
          f"min_hold={P['min_hold_days']} buffer={P['rank_buffer']} cost={P['cost']:.2%} "
          f"defense={'off' if a.no_defense else 'on'}")
    for name, s in [("策略", st), ("沪深300", dict(st["bench"], turnover=0, trades=0,
                                                   node_win=0, node_beat=0, events={}))]:
        print(f"  {name:6} 终值{s['nav']:6.2f} 年化{s['cagr']:7.1%} 波动{s['vol']:6.1%} "
              f"夏普{s['sharpe']:5.2f} 回撤{s['mdd']:7.1%} 日胜率{s['win_rate']:5.1%} "
              f"5日胜率{s['node_win']:5.1%} 跑赢{s['node_beat']:5.1%}")
    print(f"  年单边换手 {st['turnover']:.1f} 倍，决策次数 {st['trades']}，"
          f"防守天数 {st['events'].get('defense', 0)}")
    print("  分年 策略 vs 沪深300：")
    for y in st["yearly"]:
        b = st["bench"]["yearly"].get(y, float("nan"))
        print(f"    {y}  {st['yearly'][y]:+7.1%}  vs {b:+7.1%}")
    print("  当前持仓：", [(c, n) for c, n in res["log"][-1]["hold"]], res["log"][-1]["state"])
    if a.out:
        json.dump({"stats": st, "state": res["log"][-1]["state"],
                   "hold": res["log"][-1]["hold"],
                   "dates": res["dates"][-700:], "rets": res["rets"][-700:].tolist()},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
