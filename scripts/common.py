"""公共：数据载入与绩效指标。"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, PARAMS


def load_panel():
    pn = np.load(os.path.join(DATA_DIR, "panel.npz"), allow_pickle=True)
    return {k: pn[k] for k in pn.files}


def load_index(field="close"):
    d = json.load(open(os.path.join(DATA_DIR, "index_sh000300.json"), encoding="utf-8"))
    bars = d["bars"]
    return [b["date"] for b in bars], np.array([b[field] for b in bars], dtype=float)


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
