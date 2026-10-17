"""Black (1976) pricing on the forward and implied volatility inversion.

All prices here are *discounted* option prices unless a function says otherwise.
Black's formula on the forward:

    C = D * (F N(d1) - K N(d2)),   P = D * (K N(-d2) - F N(-d1))
    d1 = (ln(F/K) + w/2) / sqrt(w),  d2 = d1 - sqrt(w),  w = sigma^2 T
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

VOL_LO = 1e-4
VOL_HI = 5.0


def log_moneyness(K, F):
    return np.log(np.asarray(K, dtype=float) / np.asarray(F, dtype=float))


def black_price(F, K, T, sigma, D=1.0, is_call=True):
    """Discounted Black price. Vectorised over every argument."""
    F, K, T, sigma, D = (np.asarray(x, dtype=float) for x in (F, K, T, sigma, D))
    is_call = np.asarray(is_call, dtype=bool)
    sd = sigma * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * sd**2) / sd
        d2 = d1 - sd
        call = F * norm.cdf(d1) - K * norm.cdf(d2)
        put = K * norm.cdf(-d2) - F * norm.cdf(-d1)
    intrinsic_c = np.maximum(F - K, 0.0)
    intrinsic_p = np.maximum(K - F, 0.0)
    call = np.where(sd > 0, call, intrinsic_c)
    put = np.where(sd > 0, put, intrinsic_p)
    out = D * np.where(is_call, call, put)
    return out[()] if out.ndim == 0 else out


def black_vega(F, K, T, sigma, D=1.0):
    """dPrice/dsigma (same for calls and puts)."""
    F, K, T, sigma, D = (np.asarray(x, dtype=float) for x in (F, K, T, sigma, D))
    sd = sigma * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd**2) / sd
    out = D * F * norm.pdf(d1) * np.sqrt(T)
    return out[()] if out.ndim == 0 else out


def implied_vol(price, F, K, T, D=1.0, is_call=True, lo=VOL_LO, hi=VOL_HI, xtol=1e-12):
    """Invert Black's formula with Brent's method.

    Returns NaN when the price is outside the no-arbitrage bounds
    (below intrinsic or above the forward/strike bound) or when the root
    is not bracketed in [lo, hi].
    """
    if not np.isfinite(price) or price <= 0 or T <= 0:
        return np.nan
    undisc = price / D
    if is_call:
        lower, upper = max(F - K, 0.0), F
    else:
        lower, upper = max(K - F, 0.0), K
    if undisc <= lower or undisc >= upper:
        return np.nan

    def f(s):
        return black_price(F, K, T, s, 1.0, is_call) - undisc

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        return np.nan
    if f_hi < 0:
        return np.nan
    if f_lo == 0:
        return lo
    return brentq(f, lo, hi, xtol=xtol, rtol=1e-12, maxiter=200)


def implied_vol_vec(prices, F, K, T, D=1.0, is_call=True, **kw):
    """Element-wise implied_vol over broadcast arrays."""
    prices, F, K, T, D, is_call = np.broadcast_arrays(
        np.asarray(prices, float), np.asarray(F, float), np.asarray(K, float),
        np.asarray(T, float), np.asarray(D, float), np.asarray(is_call, bool),
    )
    out = np.empty(prices.shape, dtype=float)
    for idx in np.ndindex(prices.shape):
        out[idx] = implied_vol(prices[idx], F[idx], K[idx], T[idx], D[idx], bool(is_call[idx]), **kw)
    return out


def normalized_call(k, w):
    """Undiscounted call price divided by the forward, as a function of
    log-moneyness k and total variance w:  c = N(d1) - e^k N(d2)."""
    k, w = np.asarray(k, float), np.asarray(w, float)
    sw = np.sqrt(w)
    d1 = -k / sw + 0.5 * sw
    return norm.cdf(d1) - np.exp(k) * norm.cdf(d1 - sw)
