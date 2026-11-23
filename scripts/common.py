"""公共：数据载入、因子计算、指标。回测与线上信号共用，保证口径一致。"""
import json
import os
import sys
import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, PARAMS


def load_panel():
    pn = np.load(os.path.join(DATA_DIR, "panel.npz"), allow_pickle=True)
    return {k: pn[k] for k in pn.files}


def load_index():
    d = json.load(open(os.path.join(DATA_DIR, "index_sh000300.json"), encoding="utf-8"))
    bars = d["bars"]
    return [b["date"] for b in bars], np.array([b["close"] for b in bars], dtype=float)


def _nanagg(x, n, fn):
    """沿时间轴的滚动聚合，忽略 NaN；窗口内有效值不足 n//2 时返回 NaN。"""
    T, M = x.shape
    out = np.full((T, M), np.nan)
    if n <= 1:
        return x.astype(float).copy()
    pad = np.concatenate([np.full((n - 1, M), np.nan), x.astype(float)], axis=0)
    win = sliding_window_view(pad, n, axis=0)          # (T, M, n)
    valid = ~np.isnan(win)
    cnt = valid.sum(axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        val = getattr(np, fn)(np.where(valid, win, np.nan), axis=-1)
    out = np.where(cnt >= max(1, n // 2), val, np.nan)
    return out


def rolling_mean(x, n):
    return _nanagg(x, n, "nanmean")


def rolling_std(x, n):
    return _nanagg(x, n, "nanstd")


def rolling_max(x, n):
    return _nanagg(x, n, "nanmax")


def pct_change(C, n):
    out = np.full(C.shape, np.nan, dtype=np.float64)
    out[n:] = C[n:] / C[:-n] - 1
    return out


def zscore(X):
    """按行（横截面）z-score；全 NaN 的行保持 NaN。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mu = np.nanmean(X, axis=1, keepdims=True)
        sd = np.nanstd(X, axis=1, keepdims=True)
        Z = (X - mu) / sd
    Z[~np.isfinite(Z)] = np.nan
    return Z


def compute_factors(pn, P=None):
    P = P or PARAMS
    C, A = pn["close"].astype(float), pn["amount"].astype(float)
    T, M = C.shape
    ret = np.full_like(C, np.nan)
    ret[1:] = C[1:] / C[:-1] - 1

    r20 = pct_change(C, 20)
    r120 = pct_change(C, 120)
    ma250 = rolling_mean(C, 250)
    dist252 = C / ma250 - 1
    amt_ma20_ = rolling_mean(A, 20)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        amt_rank = (amt_ma20_ > 0).astype(float) * 0  # 占位，下面按横截面排名
    dd60 = C / rolling_max(C, 60) - 1           # ≤0，越深越负
    ma60 = rolling_mean(C, 60)
    dist60 = C / ma60 - 1
    vol20 = rolling_std(ret, 20)
    amt_ma20 = rolling_mean(A, 20)
    amt_std60 = rolling_std(A, 60)
    with np.errstate(all="ignore"):
        turnz = (A - amt_ma20) / amt_std60       # 成交额相对自身历史放大程度
    amt_recent = _nanagg(A, 20, "nanmean")
    has_data = ~np.isnan(C)
    first = np.argmax(has_data, axis=0)
    first = np.where(has_data.any(axis=0), first, T)
    days_alive = np.arange(T)[:, None] - first[None, :]
    cap_from = str(pn["dates"][0]).replace("2014", "2014") if False else None
    dstr = np.array([str(d) for d in pn["dates"]])[:, None]
    min_amt = np.where(dstr >= P.get("cap_from", "2020-01-01"),
                       float(P.get("min_amount_cap", P["min_amount"])), float(P["min_amount"]))
    tradable = (has_data & (amt_recent > min_amt) & (days_alive >= P["min_history"])
                & (C > 0))
    # 成交额分位：横截面（当日）排名，0~1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        amt_rank = np.argsort(np.argsort(np.where(tradable, amt_ma20, np.nan), axis=1), axis=1)
        amt_rank = amt_rank / np.maximum(tradable.sum(axis=1, keepdims=True) - 1, 1)
    amt_rank = np.where(tradable, amt_rank, np.nan)
    return {"ret": ret, "r20": r20, "r120": r120, "dist252": dist252, "dd60": dd60,
            "dist60": dist60, "vol20": vol20, "turnz": turnz, "amt_rank": amt_rank,
            "tradable": tradable, "amt_ma20": amt_ma20}


FACTOR_NAMES = {"r20": ("20日涨跌", "w_ret20"), "dd60": ("60日回撤", "w_dd60"),
                "dist60": ("距60日均线", "w_dist60"), "vol20": ("20日波动", "w_vol20"),
                "turnz": ("成交额放大", "w_turnz"), "r120": ("120日动量", "w_ret120"),
                "dist252": ("距250日均线", "w_dist252"), "amt_rank": ("成交额分位", "w_amt_rank")}


def factor_score(f, P=None):
    """横截面 z-score 加权合成分。返回最后一日逐因子 z 与合成分。"""
    P = P or PARAMS
    parts = [(k, P.get(key, 0.0)) for k, (_, key) in FACTOR_NAMES.items()]
    total = 0.0
    score = np.zeros_like(f["r20"], dtype=float)
    zs = {}
    for name, w in parts:
        if w == 0:
            continue
        Zi = zscore(f[name])
        zs[name] = Zi
        score = score + w * np.nan_to_num(Zi)
        total += abs(w)
    if total:
        score /= total
    valid = np.ones_like(f["r20"], dtype=bool)
    for name, w in parts:
        if w != 0:
            valid &= ~np.isnan(zs.get(name, np.full_like(f["r20"], np.nan)))
    score = np.where(valid, score, np.nan)
    return score, {k: zs[k][-1] for k in zs}


def stats_from_returns(rets):
    rets = np.asarray(rets, dtype=float)
    nav = np.cumprod(1 + rets)
    nav_full = np.concatenate([[1.0], nav])
    peak = np.maximum.accumulate(nav_full)
    dd = nav_full / peak - 1
    yrs = len(rets) / 244.0
    mu, sd = rets.mean(), (rets.std(ddof=1) if len(rets) > 1 else 0.0)
    return {"nav": float(nav_full[-1]),
            "cagr": float(nav_full[-1] ** (1 / yrs) - 1) if yrs > 0 else 0.0,
            "vol": float(sd * np.sqrt(244)),
            "sharpe": float((mu * 244 - 0.015) / (sd * np.sqrt(244))) if sd > 0 else 0.0,
            "mdd": float(dd.min()),
            "win_rate": float((rets > 0).mean()),
            "yrs": yrs}


def yearly_returns(dates, rets):
    by = {}
    for d, r in zip(dates, rets):
        y = d[:4]
        by[y] = by.get(y, 1.0) * (1 + r)
    return {y: v - 1 for y, v in sorted(by.items())}
