"""Arbitrage-free SVI surface: raw SVI slices refitted one at a time from an SSVI start.

Source read: Gatheral and Jacquier, "Arbitrage-free SVI volatility surfaces",
arXiv:1204.0646v4 (21 March 2013), section 5.2. Their recipe is:

1. fit a square-root SVI surface, phi(theta) = eta/sqrt(theta), as the initial guess;
2. starting from that guess, refit raw SVI one slice at a time, minimising the fit
   error plus a "big penalty" for crossing the previous or the next slice.

They measure crossing with *crossedness* (Definition 5.1): the largest shortfall
max(0, w_1 - w_2) at test points placed between the points where the two slices
cross. Section 5.2 has no butterfly step; section 5.3 states that the resulting
smiles are butterfly-free. What this module does differently:

* The objective is the pipeline's weighted total-variance error (the one SVI, SSVI
  and eSSVI use), not squared price differences.
* Slices are refitted from the shortest expiry, and each is penalised only against
  the slice already refitted before it, not the next one.
* Crossedness is measured on a fixed k grid (``CHECK_GRID``), not from the crossing
  roots. The penalty is the mean squared shortfall over the grid.
* A second penalty does the same for g(k) < 0, so each slice is butterfly-free on
  the grid. GJ14 section 5.2 does not specify one.
* Two conditions are imposed exactly, through the parametrisation. The asymptotic
  wing slopes L = b(1 - rho) and R = b(1 + rho) may not fall from one expiry to the
  next, which no crossing at k -> +-inf needs. Both stay at or below
  svi.WING_MAX = 1.999, Lee's bound being 2. With v = a + b*sigma*sqrt(1 - rho^2),
  the minimum variance, each slice is

      (v, L, R, m, sigma),   L in [L_prev, WING_MAX],  R in [R_prev, WING_MAX],  v > 0,

  which are box bounds for ``least_squares``.

The grid penalties have small margins. Where a fit still ends up infeasible on the
grid, it is re-run from that fit with a penalty 100 times heavier, up to
``MAX_ROUNDS`` times. The checks below are grid checks, like the rest of the pipeline.
They prove nothing between grid points or beyond the grid, but the margins and the
wing-slope order make a violation there unlikely.

Interpolation in T follows GJ14 Lemma 5.1. Normalised call prices at fixed k are
mixed with weight alpha = (sqrt(theta_2) - sqrt(theta_t)) / (sqrt(theta_2) - sqrt(theta_1)),
with theta the ATM total variance, linear in T. Before the first expiry the same
mixing runs from intrinsic value at T = 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import norm

from .arbitrage import g_function
from .essvi import essvi_w
from .pricing import normalized_call
from .ssvi import atm_total_variance
from .svi import WING_MAX, SVIParams, svi_d2w, svi_dw, svi_w

# Grid for the penalties and checks: dense where quotes and K_GRID live, coarse far out.
# The dense part has the pipeline's K_GRID spacing of 0.001, so K_GRID points lie on it.
CHECK_GRID = np.concatenate([np.linspace(-15.0, -4.0, 111)[:-1], np.linspace(-4.0, 2.0, 6001),
                             np.linspace(2.0, 15.0, 131)[1:]])
PENALTY = 1e4        # weight on mean squared shortfall, relative to the fit residuals
MAX_ROUNDS = 6       # each round multiplies the penalty by 100
CAL_MARGIN = 1e-6    # required w_i - w_{i-1}, relative to the slice's ATM variance
G_MARGIN = 1e-5      # required g(k)
V_MIN = 1e-8         # floor on minimum variance, so w > 0 and g is finite
SIGMA_BOUNDS = (1e-3, 2.0)
SLOPE_MIN = 1e-6     # first slice's wing slopes, keeping b > 0 and |rho| < 1


@dataclass
class SVIArbFreeParams:
    slices: list                  # SVIParams per expiry, sorted by T
    Ts: np.ndarray
    expiries: list = field(default_factory=list)

    def to_dict(self):
        return {"slices": [s.to_dict() for s in self.slices], "Ts": [float(x) for x in self.Ts],
                "expiries": list(self.expiries)}

    @classmethod
    def from_dict(cls, d):
        return cls(slices=[SVIParams(**s) for s in d["slices"]], Ts=np.array(d["Ts"]),
                   expiries=d.get("expiries", []))

    def slice(self, i) -> SVIParams:
        return self.slices[i]

    def thetas(self):
        """ATM total variance of each fitted slice."""
        return np.array([float(svi_w(0.0, s)) for s in self.slices])

    def w_at(self, k, T):
        """Total variance at any 0 < T <= T_n (GJ14 Lemma 5.1; see module docstring)."""
        k, T = np.asarray(k, float), float(T)
        if not 0 < T <= self.Ts[-1] * (1 + 1e-9):
            raise ValueError(f"T = {T} outside (0, {self.Ts[-1]}]")
        j = min(int(np.searchsorted(self.Ts, T)), len(self.Ts) - 1)
        if np.isclose(T, self.Ts[j], rtol=1e-9, atol=0):
            return svi_w(k, self.slices[j])
        # Mixed as out-of-the-money prices: they differ from calls by the same intrinsic
        # value on both slices, so the mix is the same and keeps its precision.
        th = self.thetas()
        w2 = svi_w(k, self.slices[j])
        o2 = otm_price(k, w2)
        if j == 0:
            T1, th1, o1 = 0.0, 0.0, np.zeros_like(k)
        else:
            T1, th1 = self.Ts[j - 1], th[j - 1]
            o1 = otm_price(k, svi_w(k, self.slices[j - 1]))
        T2, th2 = self.Ts[j], th[j]
        th_t = th1 + (th2 - th1) * (T - T1) / (T2 - T1)
        alpha = (np.sqrt(th2) - np.sqrt(th_t)) / (np.sqrt(th2) - np.sqrt(th1))
        return implied_total_variance(k, alpha * o1 + (1 - alpha) * o2, w_hi=float(w2.max()))


def otm_price(k, w):
    """Undiscounted out-of-the-money option price over the forward: the put for k < 0,
    the call otherwise. Equals normalized_call(k, w) - max(1 - e^k, 0)."""
    k, w = np.asarray(k, float), np.asarray(w, float)
    sw = np.sqrt(w)
    d1 = -k / sw + 0.5 * sw
    put = np.exp(k) * norm.cdf(-(d1 - sw)) - norm.cdf(-d1)
    return np.where(k < 0, put, normalized_call(k, w))


def implied_total_variance(k, price, w_hi=1.0, iters=80):
    """Invert otm_price(k, w) = price for w by bisection in sqrt(w), element-wise."""
    k, price = np.broadcast_arrays(np.asarray(k, float), np.asarray(price, float))
    lo, hi = np.zeros(k.shape), np.full(k.shape, np.sqrt(max(w_hi, 1e-12)) * 1.5 + 1e-6)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        up = otm_price(k, mid**2) < price
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
    return (0.5 * (lo + hi)) ** 2


# ----------------------------------------------------------------------------- square-root SSVI


def sqrt_ssvi_slice(theta, rho, eta) -> SVIParams:
    """Raw SVI form of the square-root SSVI slice, psi = theta*phi = eta*sqrt(theta)
    (GJ14 Lemma 3.3 with phi = eta/sqrt(theta))."""
    phi = eta / np.sqrt(theta)
    return SVIParams(a=float(0.5 * theta * (1 - rho**2)), b=float(0.5 * theta * phi), rho=float(rho),
                     m=float(-rho / phi), sigma=float(np.sqrt(1 - rho**2) / phi))


def fit_sqrt_ssvi(slices):
    """Square-root SSVI on every expiry at once, with the objective of ``ssvi.fit_ssvi``.

    phi = eta/sqrt(theta) with eta = 2s/(1 + |rho|), s in (0, 1], and theta a cumulative
    sum of non-negative increments. By GJ14 Thms 4.1 and 4.2 that is free of static
    arbitrage for theta < 4: d(theta*phi)/dtheta = phi/2, theta*phi^2*(1 + |rho|) = 2*s*eta
    <= 4 and theta*phi*(1 + |rho|) = 2*s*sqrt(theta) < 4. Returns (rho, eta, thetas).
    """
    n = len(slices)
    th0 = np.maximum.accumulate([max(atm_total_variance(s["k"], s["w"]), 1e-6) for s in slices])
    inc0 = np.maximum(np.diff(np.concatenate([[0.0], th0])), 1e-8)
    sw = [_slice_weights(s, t0) for s, t0 in zip(slices, th0)]

    def unpack(x):
        rho, s = x[0], x[1]
        return rho, 2 * s / (1 + abs(rho)), np.cumsum(x[2:])

    def resid(x):
        rho, eta, thetas = unpack(x)
        return np.concatenate([sw[i] * (essvi_w(s["k"], thetas[i], rho, eta * np.sqrt(thetas[i])) - s["w"])
                               for i, s in enumerate(slices)])

    lb = np.concatenate([[-0.999, 1e-4, 1e-8], np.zeros(n - 1)])
    ub = np.concatenate([[0.999, 1.0], np.full(n, 3.9 / n)])
    best = None
    for rho0 in (-0.8, -0.5):
        for s0 in (0.4, 0.9):
            x0 = np.clip(np.concatenate([[rho0, s0], inc0]), lb + 1e-12, ub - 1e-12)
            r = least_squares(resid, x0, bounds=(lb, ub), method="trf", x_scale="jac",
                              ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=5000)
            if best is None or r.cost < best.cost:
                best = r
    rho, eta, thetas = unpack(best.x)
    return float(rho), float(eta), thetas


# ----------------------------------------------------------------------------- slice refit


def _slice_weights(s, theta0):
    wt = np.ones(len(s["k"])) if s.get("weights") is None else np.asarray(s["weights"], float)
    return np.sqrt(wt / wt.mean()) / theta0


def _to_svi(x) -> SVIParams:
    v, L, R, m, sigma = x
    b = 0.5 * (L + R)
    return SVIParams(a=float(v - sigma * np.sqrt(L * R)), b=float(b), rho=float((R - L) / (R + L)),
                     m=float(m), sigma=float(sigma))


def _from_svi(p: SVIParams):
    L, R = p.wing_slopes()
    return np.array([p.min_variance(), L, R, p.m, p.sigma])


def _g(p: SVIParams, k=CHECK_GRID):
    return g_function(k, svi_w(k, p), svi_dw(k, p), svi_d2w(k, p))


def _fit_slice(k, w, sw, theta0, prev, starts, butterfly=True, calendar=True):
    """Refit one raw SVI slice. ``prev`` is the slice before it (None for the first)."""
    span = k.max() - k.min()
    L_prev, R_prev = prev.wing_slopes() if (prev is not None and calendar) else (SLOPE_MIN, SLOPE_MIN)
    lb = np.array([V_MIN, min(L_prev, WING_MAX - 1e-9), min(R_prev, WING_MAX - 1e-9),
                   k.min() - 0.5 * span, SIGMA_BOUNDS[0]])
    ub = np.array([5.0, WING_MAX, WING_MAX, k.max() + 0.5 * span, SIGMA_BOUNDS[1]])
    w_floor = svi_w(CHECK_GRID, prev) + CAL_MARGIN * theta0 if (prev is not None and calendar) else None
    scale = 1 / np.sqrt(len(CHECK_GRID))

    def resid(x, lam):
        p = _to_svi(x)
        out = [sw * (svi_w(k, p) - w)]
        if w_floor is not None:
            out.append(np.sqrt(lam) * scale / theta0 * np.maximum(w_floor - svi_w(CHECK_GRID, p), 0.0))
        if butterfly:
            out.append(np.sqrt(lam) * scale * np.maximum(G_MARGIN - _g(p), 0.0))
        return np.concatenate(out)

    def feasible(x):
        p = _to_svi(x)
        ok = not butterfly or _g(p).min() >= 0
        if w_floor is not None:
            ok = ok and (svi_w(CHECK_GRID, p) - svi_w(CHECK_GRID, prev)).min() >= 0
        return bool(ok)

    def solve(x0, lam):
        return least_squares(resid, np.clip(x0, lb, ub), bounds=(lb, ub), args=(lam,), method="trf",
                             x_scale="jac", ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=3000)

    lam = PENALTY
    runs = [solve(_from_svi(s), lam) for s in starts]
    ok = [r for r in runs if feasible(r.x)]
    best = min(ok or runs, key=lambda r: r.cost)
    rounds = 0
    while not feasible(best.x) and rounds < MAX_ROUNDS:
        lam *= 100
        rounds += 1
        best = solve(best.x, lam)
    p = _to_svi(best.x)
    info = {"objective": float(np.sum((sw * (svi_w(k, p) - w)) ** 2)), "penalty": float(lam),
            "feasible": feasible(best.x), "nfev": int(sum(r.nfev for r in runs) + rounds)}
    return p, info


def fit_svi_arbfree(slices, svi_starts=None, butterfly=True, calendar=True):
    """Fit the surface described in the module docstring.

    ``slices`` is a list of dicts with keys T, k, w, weights (and optionally expiry).
    ``svi_starts`` optionally gives a per-slice SVI fit for each slice, in T order,
    used as an extra start next to the square-root SSVI slice and the refitted
    previous slice. ``butterfly=False`` or ``calendar=False`` drops that penalty
    (and, for calendar, the wing-slope order). They exist only to measure what each
    condition costs.
    """
    order = np.argsort([s["T"] for s in slices])
    slices = [slices[i] for i in order]
    if svi_starts is not None:
        svi_starts = [svi_starts[i] for i in order]
    rho, eta, thetas = fit_sqrt_ssvi(slices)
    th0 = np.maximum.accumulate([max(atm_total_variance(s["k"], s["w"]), 1e-6) for s in slices])

    fitted, infos, prev = [], [], None
    for i, s in enumerate(slices):
        k, w = np.asarray(s["k"], float), np.asarray(s["w"], float)
        starts = [sqrt_ssvi_slice(thetas[i], rho, eta)]
        if svi_starts is not None:
            starts.append(svi_starts[i])
        if prev is not None:
            starts.append(prev)
        p, info = _fit_slice(k, w, _slice_weights(s, th0[i]), th0[i], prev, starts,
                             butterfly=butterfly, calendar=calendar)
        fitted.append(p)
        infos.append({"expiry": s.get("expiry", ""), **info})
        prev = p
    params = SVIArbFreeParams(slices=fitted, Ts=np.array([s["T"] for s in slices]),
                              expiries=[s.get("expiry", "") for s in slices])
    info = {"objective": float(sum(r["objective"] for r in infos)),
            "all_feasible": all(r["feasible"] for r in infos), "slices": infos,
            "sqrt_ssvi_start": {"rho": rho, "eta": eta, "thetas": [float(t) for t in thetas]}}
    return params, info


def check_surface(p: SVIArbFreeParams, k=CHECK_GRID) -> dict:
    """Grid check of the conditions in the module docstring."""
    slopes = np.array([s.wing_slopes() for s in p.slices])
    W = np.array([svi_w(k, s) for s in p.slices])
    out = {
        "b_positive_rho_in_range": all(s.b > 0 and -1 < s.rho < 1 and s.sigma > 0 for s in p.slices),
        "min_variance_positive": all(s.min_variance() > 0 for s in p.slices),
        "right_wing_below_lee": bool(np.all(slopes[:, 1] < 2)),
        "wing_slopes_non_decreasing": bool(np.all(np.diff(slopes, axis=0) >= 0)),
        "butterfly_g_non_negative": bool(min(_g(s, k).min() for s in p.slices) >= 0),
        "calendar_no_crossing": bool(np.all(np.diff(W, axis=0) >= 0)),
    }
    out["all_ok"] = all(out.values())
    return out
