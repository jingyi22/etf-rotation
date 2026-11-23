"""特征与标签。全部只用 t 日收盘及之前的数据；标签按实际成交口径（t+1 开盘买入）计算。

特征在每个交易日的候选池内做横截面百分位排名（-0.5 ~ +0.5），模型只比较"同一天谁更好"，
不预测大盘涨跌（大盘交给年线防守开关）。
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import PARAMS

warnings.filterwarnings("ignore", category=RuntimeWarning)

# 特征库：名称 → 中文说明。方向由模型从历史数据中学，不预设
FEATURES = {
    "r5": "5日涨跌",
    "r20": "20日涨跌",
    "r60": "60日涨跌",
    "r120": "120日涨跌",
    "dist20": "距20日均线",
    "dist60": "距60日均线",
    "dist250": "距250日均线",
    "dd60": "距60日高点",
    "dd250": "距250日高点",
    "vol20": "20日波动",
    "vol60": "60日波动",
    "max20": "20日最大单日涨幅",
    "amt_trend": "成交额 20日/120日",
    "liq": "20日成交额",
}


def load_frames(pn):
    idx = pd.Index([str(d) for d in pn["dates"]])
    cols = [str(c) for c in pn["codes"]]
    C = pd.DataFrame(pn["close"].astype(float), index=idx, columns=cols)
    O = pd.DataFrame(pn["open"].astype(float), index=idx, columns=cols)
    A = pd.DataFrame(pn["amount"].astype(float), index=idx, columns=cols)
    return C, O, A


def compute(pn, P=None):
    """返回 dict：特征名 → (T,M) ndarray（原始值），以及 tradable 掩码、标签等。"""
    P = P or PARAMS
    C, O, A = load_frames(pn)
    Cf = C.ffill(limit=5)                      # 短暂停牌用前值，避免窗口断开
    ret = Cf.pct_change(fill_method=None)
    feats = {}
    for n in (5, 20, 60, 120):
        feats[f"r{n}"] = Cf / Cf.shift(n) - 1
    for n in (20, 60, 250):
        feats[f"dist{n}"] = Cf / Cf.rolling(n, min_periods=int(n * 0.8)).mean() - 1
    feats["dd60"] = Cf / Cf.rolling(60, min_periods=48).max() - 1
    feats["dd250"] = Cf / Cf.rolling(250, min_periods=200).max() - 1
    feats["vol20"] = ret.rolling(20, min_periods=15).std()
    feats["vol60"] = ret.rolling(60, min_periods=45).std()
    feats["max20"] = ret.rolling(20, min_periods=15).max()
    a20 = A.rolling(20, min_periods=10).mean()
    a120 = A.rolling(120, min_periods=60).mean()
    feats["amt_trend"] = np.log(a20 / a120)
    feats["liq"] = np.log(a20)

    T, M = C.shape
    has = C.notna().values
    first = np.where(has.any(0), has.argmax(0), T)
    alive = np.arange(T)[:, None] - first[None, :]
    tradable = has & (a20.fillna(0).values > P["min_amount"]) & (alive >= P["min_history"])
    # 国债/防守资产只用于防守，不进候选池
    codes = list(C.columns)
    for c in [P["defense_bond"]]:
        if c in codes:
            tradable[:, codes.index(c)] = False
    # 同一指数主干当日只留成交额最大的一只（point-in-time，不用未来信息）
    tradable = point_in_time_dedupe(tradable, a20.values, [str(s) for s in pn["stems"]])

    out = {k: v.values for k, v in feats.items()}
    out["tradable"] = tradable
    out["ret"] = ret.values
    out["a20"] = a20.values
    out["close"] = C.values
    out["open"] = O.values
    return out


def point_in_time_dedupe(tradable, a20, stems):
    """每天在同一 stem 内只保留 a20 最大的一只。"""
    tr = tradable.copy()
    groups = {}
    for j, s in enumerate(stems):
        groups.setdefault(s, []).append(j)
    multi = [js for js in groups.values() if len(js) > 1]
    liq = np.where(tr, np.nan_to_num(a20, nan=-1.0), -np.inf)
    for js in multi:
        sub = liq[:, js]
        best = np.argmax(sub, axis=1)
        keep = np.zeros_like(sub, dtype=bool)
        keep[np.arange(len(best)), best] = True
        tr[:, js] = tr[:, js] & keep
    return tr


def labels(f, h):
    """未来收益标签：t 日收盘出信号，t+1 开盘买入，t+1+h 开盘卖出。"""
    O = f["open"]
    T = O.shape[0]
    y = np.full(O.shape, np.nan)
    if T > h + 1:
        y[: T - h - 1] = O[1 + h:] / O[1: T - h] - 1
    return y


def xs_rank(X, mask):
    """候选池内横截面百分位排名，映射到 [-0.5, 0.5]；池外为 NaN。"""
    Xm = np.where(mask & np.isfinite(X), X, np.nan)
    R = pd.DataFrame(Xm).rank(axis=1, pct=True).values
    n = np.isfinite(Xm).sum(1, keepdims=True)
    R = np.where(n >= 5, R - 0.5, np.nan)
    return R


def ranked_features(f, names=None):
    names = names or list(FEATURES)
    m = f["tradable"]
    return {k: xs_rank(f[k], m) for k in names}
