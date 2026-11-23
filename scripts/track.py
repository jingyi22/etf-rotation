"""每日推荐 + 推荐台账 + 自动验证与模型晋级。

每个交易日收盘后运行一次（幂等：同一信号日重复运行不会改写已记录的推荐）：
  1) 用当前冠军模型生成"下一交易日开盘"的目标持仓与完整排名；挑战者也各自记录前 5 名
  2) 把推荐追加到 track/predictions.jsonl（一行一天，记录后不再修改 —— 这就是实盘样本外记录）
  3) 对已经到期的历史推荐，用真实开盘价计算 1/5/10 日收益、相对候选池与沪深300 的超额，写 track/scored.json
  4) 滚动比较冠军与挑战者的逐日 Rank IC（最近 eval_window 个已兑现交易日），满足晋级规则就切换冠军，
     变更写进 track/model_state.json 的 history，网站展示
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import CHALLENGERS, CHAMPION_INIT, MODEL_RULES, PARAMS, TRACK_DIR, UNIVERSE_VERSION
import backtest as B
import common as CM
import features as F
import model as MD

CST = timezone(timedelta(hours=8))
PRED_PATH = os.path.join(TRACK_DIR, "predictions.jsonl")
STATE_PATH = os.path.join(TRACK_DIR, "model_state.json")
SCORED_PATH = os.path.join(TRACK_DIR, "scored.json")


# ----------------------------------------------------------------------------- state
def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH, encoding="utf-8"))
    return {"champion": dict(CHAMPION_INIT), "since": None, "history": [
        {"date": None, "event": "init", "to": CHAMPION_INIT["name"],
         "reason": "启用「趋势+低波」：开发期 2016–2021 的 8 个候选里组合回测夏普最高（选择过程见 config.py 注释）"}]}


def save_state(st):
    os.makedirs(TRACK_DIR, exist_ok=True)
    json.dump(st, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_predictions():
    out = []
    if os.path.exists(PRED_PATH):
        for line in open(PRED_PATH, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def all_models(state):
    champ = state["champion"]
    models = [dict(champ, role="champion")]
    for c in CHALLENGERS:
        if c["name"] != champ["name"]:
            models.append(dict(c, role="challenger"))
    if champ["name"] != CHAMPION_INIT["name"]:
        models.append(dict(CHAMPION_INIT, role="challenger"))
    return models


# ----------------------------------------------------------------------------- recommend
def recommend(pn, f, Rf, idx, state, prev_hold_codes, prev_mode="risk"):
    """t = 最后一个交易日收盘，生成下一交易日开盘的目标持仓。
    prev_hold_codes：上一信号日的目标持仓（用于标注买入/继续持有/卖出）；
    排名缓冲只对上一日处于进攻模式的持仓生效，与回测一致。"""
    P = PARAMS
    dates = [str(d) for d in pn["dates"]]
    codes = [str(c) for c in pn["codes"]]
    names = [str(n) for n in pn["names"]]
    t = len(dates) - 1
    risk_on, hs, ma = B.regime(pn, idx, P)
    champ = state["champion"]
    S = B.model_score(Rf, champ["weights"], champ.get("smooth", 0))
    held = {codes.index(c) for c in prev_hold_codes if c in codes} if prev_mode == "risk" else set()
    picks, order, rank_of = B.decide(t, S, f, held, P, codes)
    if risk_on[t]:
        target = {j: 1.0 / len(picks) for j in picks}
        mode = "risk"
    else:
        target = B.defense_target(t, f, P, codes)
        mode = "defense"

    def feat_row(j):
        out = {}
        for k in champ["weights"]:
            raw = f[k][t, j]
            out[k] = {"label": F.FEATURES[k], "value": None if not np.isfinite(raw) else round(float(raw), 4),
                      "pct": None if not np.isfinite(Rf[k][t, j]) else round(float(Rf[k][t, j] + 0.5), 3),
                      "w": champ["weights"][k]}
        return out

    ranking = []
    for r, j in enumerate(order[:max(30, P["n_hold"] + P["rank_buffer"])]):
        ranking.append({"rank": r + 1, "code": codes[j], "name": names[j],
                        "score": round(float(S[t, j]), 4), "close": round(float(f["close"][t, j]), 4),
                        "amt_yi": round(float(f["a20"][t, j]) / 1e8, 2),
                        "r5": round(float(f["r5"][t, j]), 4) if np.isfinite(f["r5"][t, j]) else None,
                        "r20": round(float(f["r20"][t, j]), 4) if np.isfinite(f["r20"][t, j]) else None,
                        "factors": feat_row(j), "pick": j in picks, "held": j in held})
    prev = set(prev_hold_codes)
    hold = []
    for j, w in target.items():
        hold.append({"code": codes[j], "name": names[j], "weight": round(w, 4),
                     "rank": (rank_of[j] + 1) if j in rank_of else None,
                     "score": round(float(S[t, j]), 4) if np.isfinite(S[t, j]) else None,
                     "action": "hold" if codes[j] in prev else "buy",
                     "close": round(float(f["close"][t, j]), 4)})
    sells = [{"code": c, "name": names[codes.index(c)] if c in codes else c,
              "rank": (rank_of[codes.index(c)] + 1) if c in codes and codes.index(c) in rank_of else None}
             for c in prev if c not in {h["code"] for h in hold}]
    # 挑战者前 5（只记录，不交易）
    others = {}
    for m in all_models(state):
        if m["role"] == "champion":
            continue
        Sm = B.model_score(Rf, m["weights"], m.get("smooth", 0))
        ok = f["tradable"][t] & np.isfinite(Sm[t])
        ix = np.where(ok)[0]
        top = ix[np.argsort(-Sm[t, ix])[:5]]
        others[m["name"]] = [codes[j] for j in top]
    head = [j for j in order[: P["n_hold"] + P["rank_buffer"]]]
    R = f["ret"][max(0, t - 59): t + 1]
    corr = {}
    for a_ in head:
        for b_ in head:
            if a_ < b_:
                x, y = R[:, a_], R[:, b_]
                v = np.isfinite(x) & np.isfinite(y)
                if v.sum() >= 30:
                    cc = np.corrcoef(x[v], y[v])[0, 1]
                    if np.isfinite(cc) and cc > P["corr_cap"]:
                        corr[f"{codes[a_]}|{codes[b_]}"] = round(float(cc), 3)
    open_ctx = {"kept": [codes[j] for j in picks if j in held], "head": [codes[j] for j in head],
                "high_corr_pairs": corr, "n_hold": P["n_hold"], "risk_on": bool(risk_on[t])}
    return {
        "open_ctx": open_ctx,
        "signal_date": dates[t], "exec": "下一交易日开盘", "model": champ["name"],
        "mode": mode, "hs300": round(float(hs[t]), 2), "ma250": round(float(ma[t]), 2) if np.isfinite(ma[t]) else None,
        "pool": int(f["tradable"][t].sum()),
        "hold": hold, "sells": sells, "ranking": ranking,
        # 台账字段：冠军进攻模式下的前 5（无论是否防守都记，用来验证"排序本身"的准确度）
        "top5": [codes[j] for j in order[:5]],
        "challengers_top5": others,
    }


# ----------------------------------------------------------------------------- scoring
def score_predictions(preds, pn, f, idx):
    """对每条推荐计算已兑现的 h 日收益（t+1 开盘买入，t+1+h 开盘卖出）。"""
    dates = [str(d) for d in pn["dates"]]
    di = {d: i for i, d in enumerate(dates)}
    codes = [str(c) for c in pn["codes"]]
    ci = {c: j for j, c in enumerate(codes)}
    O = f["open"]
    io_dates, io_open = CM.load_index("open")
    hs_open = dict(zip(io_dates, io_open))
    rows = []
    for p in preds:
        t = di.get(p["signal_date"])
        if t is None:
            continue
        row = {"signal_date": p["signal_date"], "model": p["model"], "mode": p["mode"], "h": {}}
        for h in MODEL_RULES["horizons"]:
            if t + 1 + h >= len(dates):
                continue
            a, z = t + 1, t + 1 + h

            def r(code):
                j = ci.get(code)
                if j is None or not (np.isfinite(O[a, j]) and np.isfinite(O[z, j]) and O[a, j] > 0):
                    return None
                return float(O[z, j] / O[a, j] - 1)

            pool = [j for j in np.where(f["tradable"][t])[0] if np.isfinite(O[a, j]) and np.isfinite(O[z, j])]
            pool_r = O[z, pool] / O[a, pool] - 1
            top = [x for x in (r(c) for c in p["top5"]) if x is not None]
            port = [(r(hh["code"]), hh["weight"]) for hh in p["hold"]]
            port = [(x, w) for x, w in port if x is not None]
            b0, b1 = hs_open.get(dates[a]), hs_open.get(dates[z])
            ch = {}
            for nm, cs in p.get("challengers_top5", {}).items():
                xs = [x for x in (r(c) for c in cs) if x is not None]
                if xs:
                    ch[nm] = float(np.mean(xs))
            row["h"][str(h)] = {
                "end_date": dates[z],
                "top5": float(np.mean(top)) if top else None,
                "top5_up": float(np.mean([x > 0 for x in top])) if top else None,
                "top5_beat_med": float(np.mean([x > np.median(pool_r) for x in top])) if top and len(pool) else None,
                "pool": float(np.mean(pool_r)) if len(pool) else None,
                "port": float(sum(x * w for x, w in port) / sum(w for _, w in port)) if port else None,
                "hs300": float(b1 / b0 - 1) if b0 and b1 else None,
                "challengers": ch,
            }
        rows.append(row)
    return rows


def score_open_reviews(preds, pn, f):
    """开盘复核台账 vs 收盘版：同一交易日，从当天开盘价买入，持有 1/5/10 日后开盘卖出（复核版按集合竞价价买入，
    收盘版也按同一开盘价，差别只来自持仓不同）。"""
    path = os.path.join(TRACK_DIR, "open_review.jsonl")
    if not os.path.exists(path):
        return {"n": 0, "rows": [], "summary": {}}
    reviews = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    by_sig = {p["signal_date"]: p for p in preds}
    dates = [str(d) for d in pn["dates"]]
    di = {d: i for i, d in enumerate(dates)}
    ci = {str(c): j for j, c in enumerate(pn["codes"])}
    O = f["open"]
    rows = []
    for rv in reviews:
        a = di.get(rv["trade_date"])
        p = by_sig.get(rv["signal_date"])
        if a is None or p is None:
            rows.append({"trade_date": rv["trade_date"], "note": rv["note"], "h": {}})
            continue
        row = {"trade_date": rv["trade_date"], "note": rv["note"], "changed": rv["note"] == "已调整", "h": {}}
        for h in MODEL_RULES["horizons"]:
            z = a + h
            if z >= len(dates):
                continue

            def port(hold):
                xs = [(O[z, ci[x["code"]]] / O[a, ci[x["code"]]] - 1, x["weight"]) for x in hold
                      if x["code"] in ci and np.isfinite(O[a, ci[x["code"]]]) and np.isfinite(O[z, ci[x["code"]]])]
                return float(sum(r * w for r, w in xs) / sum(w for _, w in xs)) if xs else None

            row["h"][str(h)] = {"open": port(rv["hold"]), "close": port(p["hold"])}
        rows.append(row)
    summ = {}
    for h in MODEL_RULES["horizons"]:
        xs = [r["h"][str(h)] for r in rows if str(h) in r["h"] and None not in r["h"][str(h)].values()]
        ch = [r["h"][str(h)] for r in rows if r.get("changed") and str(h) in r["h"]
              and None not in r["h"][str(h)].values()]
        summ[str(h)] = {"n": len(xs), "n_changed": len(ch),
                        "open": float(np.mean([x["open"] for x in xs])) if xs else None,
                        "close": float(np.mean([x["close"] for x in xs])) if xs else None,
                        "diff_changed": float(np.mean([x["open"] - x["close"] for x in ch])) if ch else None}
    return {"n": len(reviews), "n_changed": sum(1 for r in reviews if r["note"] == "已调整"),
            "rows": rows[-15:][::-1], "summary": summ}


def summarize(rows):
    out = {}
    for h in MODEL_RULES["horizons"]:
        hs = [r["h"][str(h)] for r in rows if str(h) in r["h"]]
        if not hs:
            out[str(h)] = {"n": 0}
            continue

        def m(key):
            v = [x[key] for x in hs if x.get(key) is not None]
            return (float(np.mean(v)), len(v)) if v else (None, 0)

        top, n = m("top5")
        pool, _ = m("pool")
        port, _ = m("port")
        b, _ = m("hs300")
        up, _ = m("top5_up")
        bm, _ = m("top5_beat_med")
        beat_pool = [x["top5"] > x["pool"] for x in hs if x.get("top5") is not None and x.get("pool") is not None]
        beat_hs = [x["port"] > x["hs300"] for x in hs if x.get("port") is not None and x.get("hs300") is not None]
        out[str(h)] = {"n": n, "top5": top, "pool": pool, "port": port, "hs300": b, "top5_up": up,
                       "top5_beat_med": bm,
                       "days_top5_beat_pool": float(np.mean(beat_pool)) if beat_pool else None,
                       "days_port_beat_hs300": float(np.mean(beat_hs)) if beat_hs else None}
    return out


# ----------------------------------------------------------------------------- validation
def validate(pn, f, Rf, state):
    """模型监控：滚动窗口内冠军与每个挑战者的逐日 Rank IC（未来 horizon 日），以及晋级判定。
    只用已经兑现的标签（截至最后一个交易日开盘可知的收益），在每个交易日重算。"""
    R = MODEL_RULES
    h = PARAMS["horizon"]
    y = F.labels(f, h)
    dates = [str(d) for d in pn["dates"]]
    T = len(dates)
    hi = T - h - 2                 # 最后一个已兑现标签的信号日
    lo = max(0, hi - R["eval_window"] + 1)
    sl = slice(lo, hi + 1)
    res = {}
    for m in all_models(state):
        S = B.model_score(Rf, m["weights"], m.get("smooth", 0))
        ic = MD.ic_of_scores(S, y)[sl]
        hit = MD.topk_hit(S, y, f["tradable"], 5)[sl]
        res[m["name"]] = {"role": m["role"], "ic": ic, "ic_mean": float(np.nanmean(ic)),
                          "ic_pos": float(np.nanmean(ic > 0)),
                          "top5_minus_pool": float(np.nanmean(hit[:, 0] - hit[:, 3])),
                          "top5_beat_med": float(np.nanmean(hit[:, 1]))}
    champ = state["champion"]["name"]
    c_ic = res[champ]["ic"]
    best, decision = None, None
    for nm, r in res.items():
        if nm == champ:
            continue
        d = r["ic"] - c_ic
        d = d[np.isfinite(d)]
        if len(d) < 60:
            r["t_vs_champ"] = None
            continue
        tval = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d) / h))) if d.std() > 0 else 0.0
        r["t_vs_champ"] = tval
        r["gap"] = float(d.mean())
        if tval >= R["promote_t"] and d.mean() >= R["promote_min_gap"]:
            if best is None or tval > res[best]["t_vs_champ"]:
                best = nm
    last_change = next((x["date"] for x in reversed(state["history"]) if x["date"]), None)
    days_since = (T - 1 - dates.index(last_change)) if last_change in dates else 10 ** 6
    if best and days_since >= R["cooldown"]:
        new = next(m for m in all_models(state) if m["name"] == best)
        decision = {"date": dates[-1], "event": "promote", "from": champ, "to": best,
                    "reason": f"近 {R['eval_window']} 个已兑现交易日 {h} 日 Rank IC 均值 "
                              f"{res[best]['ic_mean']:+.3f} vs 冠军 {res[champ]['ic_mean']:+.3f}，"
                              f"差值 t={res[best]['t_vs_champ']:.2f} ≥ {R['promote_t']}"}
        state["champion"] = {k: new[k] for k in ("name", "weights", "smooth")}
        state["since"] = dates[-1]
        state["history"].append(decision)
    summary = {nm: {k: v for k, v in r.items() if k != "ic"} for nm, r in res.items()}
    return {"window": [dates[lo], dates[hi]], "horizon": h, "models": summary, "decision": decision,
            "rule": f"挑战者 {h} 日 Rank IC 均值高出冠军 ≥ {R['promote_min_gap']} 且差值 t ≥ {R['promote_t']}，"
                    f"距上次变更 ≥ {R['cooldown']} 个交易日，才自动晋级"}


def simulated_accuracy(pn, f, Rf, state):
    """历史逐日推荐的准确度（模拟）：冠军模型在开发期 / 留出期，每天的前 5 名在未来 h 日的表现。
    这是回测口径，用来在实盘台账攒够样本之前给出参考；网站上与实盘记录分开展示。"""
    dates = np.array([str(d) for d in pn["dates"]])
    champ = state["champion"]
    S = B.model_score(Rf, champ["weights"], champ.get("smooth", 0))
    segs = {"dev": (PARAMS["dev_start"], PARAMS["holdout_start"]), "holdout": (PARAMS["holdout_start"], "2100")}
    out = {}
    for h in MODEL_RULES["horizons"]:
        y = F.labels(f, h)
        hit = MD.topk_hit(S, y, f["tradable"], 5)
        ic = MD.ic_of_scores(S, y)
        for seg, (a, z) in segs.items():
            m = (dates >= a) & (dates < z) & np.isfinite(hit[:, 0])
            out.setdefault(seg, {})[str(h)] = {
                "days": int(m.sum()),
                "top5": float(np.mean(hit[m, 0])), "pool": float(np.mean(hit[m, 3])),
                "top5_up": float(np.mean(hit[m, 2])), "top5_beat_med": float(np.mean(hit[m, 1])),
                "days_top5_beat_pool": float(np.mean(hit[m, 0] > hit[m, 3])),
                "ic": float(np.nanmean(ic[m])), "ic_pos": float(np.nanmean(ic[m] > 0))}
    return {"model": champ["name"], "segments": segs, "by": out}


# ----------------------------------------------------------------------------- main
def main():
    os.makedirs(TRACK_DIR, exist_ok=True)
    pn = CM.load_panel()
    idx = CM.load_index()
    f = F.compute(pn, PARAMS)
    Rf = F.ranked_features(f)
    state = load_state()
    preds = load_predictions()
    dates = [str(d) for d in pn["dates"]]
    last = dates[-1]

    # 1) 验证与晋级（先于今日推荐，今天的推荐用验证后的冠军）
    val = validate(pn, f, Rf, state)
    if state.get("since") is None:
        state["since"] = last
    if state.get("universe") != UNIVERSE_VERSION:
        state["history"].append({"date": last, "event": "universe", "from": state.get("universe"),
                                 "to": UNIVERSE_VERSION,
                                 "reason": f"候选池改为{UNIVERSE_VERSION}：原 1000 万门槛下的超额主要来自冷门 ETF，"
                                           f"在流动性池重新比较 8 个候选后保留「{state['champion']['name']}」，中期动量加入挑战者"})
        state["universe"] = UNIVERSE_VERSION
    save_state(state)

    # 2) 今日推荐（幂等：同一信号日已记录则沿用已记录的持仓，不改写台账）
    before = [p for p in preds if p["signal_date"] < last]
    if before:
        prev_hold, prev_mode = [h["code"] for h in before[-1]["hold"]], before[-1]["mode"]
    else:
        # 台账第一天：用回测在上一交易日的持仓作为起点，避免第一天全部显示为新买入
        S = B.model_score(Rf, state["champion"]["weights"], state["champion"].get("smooth", 0))
        res = B.run(pn, f, S, idx, dict(PARAMS, start=dates[-260]))
        prev_hold, prev_mode = [c for c, _ in res["log"][-2]["hold"]], res["log"][-2]["state"]
    rec = recommend(pn, f, Rf, idx, state, prev_hold, prev_mode)
    logged = next((p for p in preds if p["signal_date"] == last), None)
    if logged:
        rec["hold"], rec["sells"], rec["logged"] = logged["hold"], logged["sells"], True
    else:
        entry = {k: rec[k] for k in ("signal_date", "model", "mode", "hs300", "ma250", "pool",
                                     "hold", "sells", "top5", "challengers_top5")}
        entry["logged_at"] = datetime.now(CST).isoformat(timespec="seconds")
        with open(PRED_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        preds.append(entry)
        rec["logged"] = False

    # 3) 兑现评分
    rows = score_predictions(preds, pn, f, idx)
    summ = summarize(rows)
    json.dump({"rows": rows[-120:], "summary": summ, "n_predictions": len(preds),
               "first": preds[0]["signal_date"] if preds else None},
              open(SCORED_PATH, "w", encoding="utf-8"), ensure_ascii=False)

    sim = simulated_accuracy(pn, f, Rf, state)
    out = {"recommendation": rec, "validation": val, "state": state, "simulated": sim,
           "open_review": score_open_reviews(preds, pn, f),
           "live": {"summary": summ, "n": len(preds), "first": preds[0]["signal_date"] if preds else None,
                    "recent": rows[-30:][::-1]}}
    json.dump(out, open(os.path.join(os.path.dirname(PRED_PATH), "..", "data", "daily.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, default=float)
    print(f"信号日 {last}  冠军 {state['champion']['name']}  模式 {rec['mode']}  候选池 {rec['pool']}")
    for hh in rec["hold"]:
        print(f"  {hh['action']:4s} {hh['code']} {hh['name']:14s} {hh['weight']:.0%} 排名 {hh['rank']}")
    for s_ in rec["sells"]:
        print(f"  sell {s_['code']} {s_['name']}")
    print(f"  验证窗口 {val['window'][0]}~{val['window'][1]}（{val['horizon']} 日）：")
    for nm, r in val["models"].items():
        t = r.get("t_vs_champ")
        print(f"    {nm:12s} {r['role']:10s} IC {r['ic_mean']:+.3f}  前5-池 {r['top5_minus_pool']*100:+.2f}%  "
              f"跑赢中位 {r['top5_beat_med']:.1%}  t={t if t is None else round(t, 2)}")
    if val["decision"]:
        print("  >>> 模型晋级：", val["decision"])
    print(f"  台账 {len(preds)} 条（自 {preds[0]['signal_date']}）")


if __name__ == "__main__":
    main()
