"""Forward and discount factor from put-call parity.

For European options at the same strike and expiry,

    C(K) - P(K) = D * (F - K) = D*F - D*K

so a regression of (C - P) on K across many strikes gives slope -D and
intercept D*F. Using many strikes averages out quote noise; a robust second
pass drops strikes whose residual is more than 3 MADs from the fit.
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


def _wls(x, y, wts):
    W = np.sqrt(wts)
    A = np.column_stack([np.ones_like(x), x]) * W[:, None]
    coef, *_ = np.linalg.lstsq(A, y * W, rcond=None)
    return coef  # intercept, slope


def fit_forward(K, call_mid, put_mid, weights=None, mad_cut=3.0) -> ForwardFit:
    K = np.asarray(K, float)
    y = np.asarray(call_mid, float) - np.asarray(put_mid, float)
    wts = np.ones_like(K) if weights is None else np.asarray(weights, float)
    if len(K) < 3:
        raise ValueError(f"need at least 3 call/put pairs to fit a forward, got {len(K)}")

    intercept, slope = _wls(K, y, wts)
    resid = y - (intercept + slope * K)
    mad = np.median(np.abs(resid - np.median(resid)))
    keep = np.ones_like(K, dtype=bool)
    if mad > 0:
        keep = np.abs(resid - np.median(resid)) <= mad_cut * 1.4826 * mad
        if keep.sum() >= 3:
            intercept, slope = _wls(K[keep], y[keep], wts[keep])
        else:
            keep[:] = True
    D = -slope
    if D <= 0:
        raise ValueError(f"put-call parity regression gave a non-positive discount factor {D:.4f}")
    F = intercept / D
    resid = y[keep] - (intercept + slope * K[keep])
    return ForwardFit(F=float(F), D=float(D), n_pairs=int(len(K)), n_used=int(keep.sum()),
                      resid_std=float(np.std(resid)))
