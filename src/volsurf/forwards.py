"""Forward and discount factor from put-call parity.

For European options at the same strike and expiry,

    C(K) - P(K) = D * (F - K) = D*F - D*K

so a regression of (C - P) on K across many strikes gives slope -D and
intercept D*F. Using many strikes averages out quote noise; a robust second
pass drops strikes whose residual is more than 3 MADs from the fit.

Where the slope is not identified (very short expiries, where a few cents of
parity residual move the rate a lot), D can instead be fixed from a discount
curve built from the other expiries, and only F is fitted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ForwardFit:
    F: float
    D: float
    n_pairs: int
    n_used: int
    resid_std: float

    def rate(self, T: float) -> float:
        """Continuously compounded rate implied by D."""
        return -np.log(self.D) / T if T > 0 else np.nan


def _wls(x, y, wts, slope=None):
    """Weighted least squares of y on x; with ``slope`` given only the intercept is fitted."""
    if slope is not None:
        return np.sum(wts * (y - slope * x)) / np.sum(wts), slope
    W = np.sqrt(wts)
    A = np.column_stack([np.ones_like(x), x]) * W[:, None]
    coef, *_ = np.linalg.lstsq(A, y * W, rcond=None)
    return coef  # intercept, slope


def fit_forward(K, call_mid, put_mid, weights=None, mad_cut=3.0, D=None) -> ForwardFit:
    """Fit F and D by parity regression, or only F when ``D`` is given."""
    K = np.asarray(K, float)
    y = np.asarray(call_mid, float) - np.asarray(put_mid, float)
    wts = np.ones_like(K) if weights is None else np.asarray(weights, float)
    if len(K) < 3:
        raise ValueError(f"need at least 3 call/put pairs to fit a forward, got {len(K)}")
    if D is not None and not D > 0:
        raise ValueError(f"fixed discount factor must be positive, got {D}")
    fixed = None if D is None else -float(D)

    intercept, slope = _wls(K, y, wts, fixed)
    resid = y - (intercept + slope * K)
    mad = np.median(np.abs(resid - np.median(resid)))
    keep = np.ones_like(K, dtype=bool)
    if mad > 0:
        keep = np.abs(resid - np.median(resid)) <= mad_cut * 1.4826 * mad
        if keep.sum() >= 3:
            intercept, slope = _wls(K[keep], y[keep], wts[keep], fixed)
        else:
            keep[:] = True
    D = -slope
    if D <= 0:
        raise ValueError(f"put-call parity regression gave a non-positive discount factor {D:.4f}")
    F = intercept / D
    resid = y[keep] - (intercept + slope * K[keep])
    return ForwardFit(F=float(F), D=float(D), n_pairs=int(len(K)), n_used=int(keep.sum()),
                      resid_std=float(np.std(resid)))


def discount_from_curve(T: float, T_ref, D_ref) -> float:
    """D at ``T`` from reference discount factors: log-linear in T between them (and
    from D = 1 at T = 0, so a flat rate before the first), flat rate after the last."""
    T_ref, D_ref = np.asarray(T_ref, float), np.asarray(D_ref, float)
    if len(T_ref) == 0:
        raise ValueError("need at least one reference expiry")
    order = np.argsort(T_ref)
    T_ref, logD = T_ref[order], np.log(D_ref[order])
    if T > T_ref[-1]:
        return float(np.exp(logD[-1] / T_ref[-1] * T))
    return float(np.exp(np.interp(T, np.r_[0.0, T_ref], np.r_[0.0, logD])))
