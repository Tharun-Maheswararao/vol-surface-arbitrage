"""Raw SVI slices and the quasi-explicit calibration of Zeliade (2009).

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

Quasi-explicit idea: with y = (k - m) / sigma the slice is linear in
(a, c, d) = (a, b*sigma, rho*b*sigma):

    w = a + d*y + c*sqrt(y^2 + 1)

so for fixed (m, sigma) the inner problem is a small constrained weighted
linear least squares, and only (m, sigma) are searched numerically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass
class SVIParams:
    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def to_dict(self):
        return asdict(self)

    def min_variance(self) -> float:
        return self.a + self.b * self.sigma * np.sqrt(1 - self.rho**2)


def svi_w(k, p: SVIParams):
    x = np.asarray(k, float) - p.m
    return p.a + p.b * (p.rho * x + np.sqrt(x**2 + p.sigma**2))


def svi_dw(k, p: SVIParams):
    x = np.asarray(k, float) - p.m
    return p.b * (p.rho + x / np.sqrt(x**2 + p.sigma**2))


def svi_d2w(k, p: SVIParams):
    x = np.asarray(k, float) - p.m
    return p.b * p.sigma**2 / (x**2 + p.sigma**2) ** 1.5


def satisfies_constraints(p: SVIParams, tol: float = 1e-10) -> bool:
    return (p.b >= -tol and -1 < p.rho < 1 and p.sigma > 0
            and p.min_variance() >= -tol and p.b * (1 + abs(p.rho)) <= 4 + tol)


# ----------------------------------------------------------------------------- inner solve


def _inner(y, w, wt, sigma):
    """Weighted LS for (a, c, d) subject to
    0 <= c,  |d| <= c,  c + |d| <= 4 sigma   (b >= 0, |rho| <= 1, Lee: b(1+|rho|) <= 4)
    a + sqrt(c^2 - d^2) >= 0                (non-negative minimum variance)."""
    z = np.sqrt(y**2 + 1.0)
    X = np.column_stack([np.ones_like(y), y, z])  # columns: a, d, c
    sw = np.sqrt(wt)
    Xw, ww = X * sw[:, None], w * sw

    def feasible(v):
        a, d, c = v
        return (c >= 0 and abs(d) <= c and c + abs(d) <= 4 * sigma
                and a + np.sqrt(max(c * c - d * d, 0.0)) >= 0)

    v, *_ = np.linalg.lstsq(Xw, ww, rcond=None)
    if feasible(v):
        return v, float(np.sum((Xw @ v - ww) ** 2))

    def obj(v):
        r = Xw @ v - ww
        return r @ r

    def jac(v):
        return 2 * Xw.T @ (Xw @ v - ww)

    cons = [
        {"type": "ineq", "fun": lambda v: v[2] - v[1]},
        {"type": "ineq", "fun": lambda v: v[2] + v[1]},
        {"type": "ineq", "fun": lambda v: 4 * sigma - v[2] - v[1]},
        {"type": "ineq", "fun": lambda v: 4 * sigma - v[2] + v[1]},
        {"type": "ineq", "fun": lambda v: v[0] + np.sqrt(max(v[2] ** 2 - v[1] ** 2, 0.0))},
    ]
    c0 = min(max(abs(v[2]), 1e-6), 2 * sigma)
    d0 = float(np.clip(v[1], -0.9 * c0, 0.9 * c0))
    x0 = np.array([max(v[0], 0.0), d0, c0])
    res = minimize(obj, x0, jac=jac, constraints=cons, method="SLSQP",
                   options={"maxiter": 200, "ftol": 1e-14})
    v = res.x
    v[2] = max(v[2], 0.0)
    v[1] = float(np.clip(v[1], -v[2], v[2]))
    return v, float(obj(v))


def _params_from_inner(v, m, sigma) -> SVIParams:
    a, d, c = v
    b = c / sigma
    rho = d / c if c > 0 else 0.0
    return SVIParams(a=float(a), b=float(b), rho=float(np.clip(rho, -0.999999, 0.999999)),
                     m=float(m), sigma=float(sigma))


def fit_svi(k, w, weights=None, sigma_bounds=(1e-3, 2.0)):
    """Quasi-explicit SVI fit of total variance w(k).

    Returns (SVIParams, info) where info holds the weighted objective and the
    number of outer function evaluations.
    """
    k, w = np.asarray(k, float), np.asarray(w, float)
    wt = np.ones_like(k) if weights is None else np.asarray(weights, float)
    wt = wt / wt.mean()
    kmin, kmax = k.min(), k.max()
    m_lo, m_hi = kmin - 0.5 * (kmax - kmin), kmax + 0.5 * (kmax - kmin)
    bounds = [(m_lo, m_hi), sigma_bounds]
    nfev = 0

    def outer(x):
        nonlocal nfev
        nfev += 1
        m, s = x
        _, sse = _inner((k - m) / s, w, wt, s)
        return sse

    best = None
    k_atm = k[np.argmin(w)]
    for m0 in (k_atm, 0.0, 0.5 * kmin, 0.5 * kmax):
        for s0 in (0.05, 0.15, 0.4):
            r = minimize(outer, x0=[m0, s0], method="Nelder-Mead", bounds=bounds,
                         options={"xatol": 1e-7, "fatol": 1e-14, "maxiter": 2000})
            if best is None or r.fun < best.fun:
                best = r
    m, s = best.x
    v, sse = _inner((k - m) / s, w, wt, s)
    return _params_from_inner(v, m, s), {"objective": sse, "nfev": nfev}
