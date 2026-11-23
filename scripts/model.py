"""滚动（walk-forward）选 ETF 模型。

核心约束：t 日使用的模型权重只能由 t 日之前"已经兑现"的标签估计出来。
  标签 y_h(d) = open(d+1+h) / open(d+1) - 1，在 d+1+h 日开盘才知道；
  所以 t 日收盘拟合时只用 d <= t-h-1 的样本。每天重新估计一次权重（成本很低）。

三种模型：
  fixed  : 固定权重（人工设定，作参照）
  ic     : 各特征过去 W 日的平均 Rank IC 作为权重（只保留与长期方向一致的特征）
  ridge  : 横截面排名特征对横截面排名标签做岭回归（逐日累积 X'X、X'y，滚动求和）
"""
import numpy as np

from features import FEATURES


def stack(Rf, names):
    """(T, M, K) float32，NaN 保留。"""
    return np.stack([Rf[k] for k in names], axis=-1).astype(np.float32)


def label_rank(y, mask):
    """标签横截面排名（-0.5~0.5），只在候选池内。"""
    from features import xs_rank
    return xs_rank(y, mask)


def daily_stats(X, Y):
    """逐日统计量：每个特征的 Rank IC、X'X、X'y、样本数。X: (T,M,K) 排名特征，Y: (T,M) 排名标签。"""
    T, M, K = X.shape
    valid = np.isfinite(Y)[:, :, None] & np.isfinite(X)
    Xz = np.where(valid, X, 0.0).astype(np.float64)
    Yz = np.where(np.isfinite(Y), Y, 0.0).astype(np.float64)
    vrow = np.isfinite(Y) & np.all(np.isfinite(X), axis=-1)          # 全特征齐全的样本
    Xr = np.where(vrow[:, :, None], Xz, 0.0)
    Yr = np.where(vrow, Yz, 0.0)
    n = vrow.sum(1).astype(float)
    XtX = np.einsum("tmi,tmj->tij", Xr, Xr)
    Xty = np.einsum("tmi,tm->ti", Xr, Yr)
    # Rank IC（Pearson on ranks；排名已在候选池内居中）
    ic = np.full((T, K), np.nan)
    for k in range(K):
        v = valid[:, :, k]
        x = np.where(v, Xz[:, :, k], np.nan)
        y = np.where(v, Yz, np.nan)
        cnt = v.sum(1)
        xm = np.nanmean(x, 1, keepdims=True)
        ym = np.nanmean(y, 1, keepdims=True)
        cov = np.nanmean((x - xm) * (y - ym), 1)
        sx = np.nanstd(x, 1)
        sy = np.nanstd(y, 1)
        with np.errstate(all="ignore"):
            ic[:, k] = np.where(cnt >= 10, cov / (sx * sy), np.nan)
    return {"ic": ic, "XtX": XtX, "Xty": Xty, "n": n}


def rolling_weights(stats, h, W, method, lam=1.0, min_days=250, fixed=None, names=None):
    """返回 (T, K) 权重：t 日权重只用 d <= t-h-1 的统计量，窗口 W 日（W=None 为扩展窗口）。"""
    ic, XtX, Xty, n = stats["ic"], stats["XtX"], stats["Xty"], stats["n"]
    T, K = ic.shape
    Wt = np.full((T, K), np.nan)
    if method == "fixed":
        w = np.array([fixed.get(k, 0.0) for k in names], dtype=float)
        Wt[:] = w
        return Wt
    icz = np.nan_to_num(ic)
    icn = np.isfinite(ic).astype(float)
    c_ic = np.cumsum(icz, 0)
    c_ic2 = np.cumsum(icz ** 2, 0)
    c_icn = np.cumsum(icn, 0)
    c_xx = np.cumsum(XtX, 0)
    c_xy = np.cumsum(Xty, 0)
    c_n = np.cumsum(n)

    def wsum(c, hi, lo):
        return c[hi] - (c[lo - 1] if lo > 0 else 0)

    for t in range(T):
        hi = t - h - 1
        if hi < 0:
            continue
        lo = 0 if W is None else max(0, hi - W + 1)
        days = wsum(c_icn, hi, lo)
        if np.min(days) < min_days:
            continue
        if method == "sign":
            # 方向投票：扩展窗口 IC 的 t 统计量 |t| >= tmin 的特征取 ±1，其余为 0（等权）
            m = wsum(c_ic, hi, lo) / days
            v = wsum(c_ic2, hi, lo) / days - m ** 2
            tstat = m / np.sqrt(np.maximum(v, 1e-12) / days) / np.sqrt(h)   # 重叠标签按 h 折算有效样本
            Wt[t] = np.where(np.abs(tstat) >= lam, np.sign(m), 0.0)
        elif method == "ic":
            m = wsum(c_ic, hi, lo) / days
            # 只保留在长期（扩展窗口）上同方向的特征，避免短窗口噪声翻转符号
            m_long = c_ic[hi] / np.maximum(c_icn[hi], 1)
            m = np.where(np.sign(m) == np.sign(m_long), m, 0.0)
            Wt[t] = m
        elif method == "ridge":
            XX = wsum(c_xx, hi, lo)
            Xy = wsum(c_xy, hi, lo)
            N = wsum(c_n, hi, lo)
            # 排名特征方差约 1/12；lam 是相对于样本信息量的收缩强度
            Wt[t] = np.linalg.solve(XX + lam * (N / 12.0) * np.eye(K), Xy)
    return Wt


def scores(X, Wt):
    """S[t, m] = sum_k X[t,m,k] * W[t,k]；任一特征缺失则 NaN。"""
    S = np.einsum("tmk,tk->tm", np.nan_to_num(X), np.nan_to_num(Wt))
    bad = ~np.all(np.isfinite(X), axis=-1) | ~np.all(np.isfinite(Wt), axis=-1)[:, None]
    return np.where(bad, np.nan, S)


def ic_of_scores(S, Y):
    """逐日 Rank IC（S 与排名标签）。"""
    from features import xs_rank
    mask = np.isfinite(S) & np.isfinite(Y)
    Sr = xs_rank(S, mask)
    Yr = xs_rank(Y, mask)
    v = np.isfinite(Sr) & np.isfinite(Yr)
    x = np.where(v, Sr, np.nan)
    y = np.where(v, Yr, np.nan)
    xm, ym = np.nanmean(x, 1, keepdims=True), np.nanmean(y, 1, keepdims=True)
    with np.errstate(all="ignore"):
        r = np.nanmean((x - xm) * (y - ym), 1) / (np.nanstd(x, 1) * np.nanstd(y, 1))
    return np.where(v.sum(1) >= 10, r, np.nan)


def topk_hit(S, y, mask, k=5):
    """逐日：前 k 名的未来平均收益、跑赢池中位数的比例、绝对上涨比例、池平均收益。"""
    T = S.shape[0]
    out = np.full((T, 4), np.nan)
    for t in range(T):
        v = mask[t] & np.isfinite(S[t]) & np.isfinite(y[t])
        if v.sum() < 2 * k:
            continue
        idx = np.where(v)[0]
        top = idx[np.argsort(-S[t, idx])[:k]]
        med = np.median(y[t, idx])
        out[t] = [y[t, top].mean(), (y[t, top] > med).mean(), (y[t, top] > 0).mean(), y[t, idx].mean()]
    return out
