"""Extended SSVI (eSSVI): the SSVI slice with rho and phi free per expiry.

    w(k) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + 1 - rho^2)),   phi = psi/theta
         = 1/2 * (theta + rho*psi*k + sqrt((psi*k + theta*rho)^2 + theta^2*(1 - rho^2)))

Each expiry i has its own (theta_i, rho_i, psi_i), with psi = theta*phi.

No-arbitrage conditions used here. Sources read: Corbetta, Cohort, Laachir and
Martini, "Robust calibration and arbitrage-free interpolation of SSVI slices",
arXiv:1804.04924v2 (4 March 2019), and Mingone, "No arbitrage global
parametrization for the eSSVI volatility surface", arXiv:2204.00312v1 (1 April
2022). Both take the calendar condition from Hendriks and Martini (2019), "The
extended SSVI volatility surface", Prop. 3.5, which was not itself checked.

* Calendar, necessary (Mingone section 2.1): theta_2 > theta_1 and
  psi_2 > psi_1 * max((1 + rho_1)/(1 + rho_2), (1 - rho_1)/(1 - rho_2)). In weak form
  this is theta and psi non-decreasing with |rho_2*psi_2 - rho_1*psi_1| <= psi_2 - psi_1,
  the set Corbetta et al. (section 2.2) state as necessary and sufficient.
* Calendar, sufficient (Mingone section 2.1): the necessary conditions plus either
  psi_2/theta_2 <= psi_1/theta_1 (phi non-increasing) or a quadratic alternative.
  Like Mingone, this module uses phi non-increasing. The necessary set alone is not
  enough: tests/test_essvi.py has a pair that meets it and crosses.
* Butterfly (Gatheral and Jacquier 2014, Thm 4.2, sufficient; Corbetta et al. eqs
  (2)-(3) with psi = theta*phi): psi*(1 + |rho|) < 4 and psi^2*(1 + |rho|) <= 4*theta.

Fit parametrisation. With p = psi*(1 + rho) and m = psi*(1 - rho), which are twice
the right and left asymptotic wing slopes, the necessary calendar condition is
"theta, p and m non-decreasing". The other conditions read p + m <= 2*phi_{i-1}*theta_i,
max(p, m) < 4 and (p + m)*max(p, m) <= 8*theta, and each tightens as p or m grows.
The fit builds every slice from the previous one: theta_i is a cumulative sum of
non-negative increments, then p_i moves a fraction x_i of the way from p_{i-1} to
the largest p that keeps the bounds at m = m_{i-1}, then m_i a fraction y_i of the
way from m_{i-1} to the largest m that keeps them at p_i. Every (x, y) in the unit
box gives admissible slices, and every admissible sequence comes from one, so the
box bounds of ``least_squares`` enforce the conditions exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from .ssvi import atm_total_variance, fit_ssvi, phi

# Cap on max(p, m) = psi*(1 + |rho|), strictly inside the bound of 4. Half of it is the
# larger wing slope, so this matches svi.WING_MAX = 1.999 against Lee's bound of 2.
PM_MAX = 3.998


@dataclass
class ESSVIParams:
    thetas: np.ndarray            # ATM total variance per expiry, non-decreasing
    rhos: np.ndarray
    psis: np.ndarray              # theta*phi per expiry, non-decreasing
    Ts: np.ndarray                # expiries in years
    expiries: list = field(default_factory=list)

    def to_dict(self):
        return {"thetas": [float(x) for x in self.thetas], "rhos": [float(x) for x in self.rhos],
                "psis": [float(x) for x in self.psis], "Ts": [float(x) for x in self.Ts],
                "expiries": list(self.expiries)}

    @classmethod
    def from_dict(cls, d):
        return cls(thetas=np.array(d["thetas"]), rhos=np.array(d["rhos"]), psis=np.array(d["psis"]),
                   Ts=np.array(d["Ts"]), expiries=d.get("expiries", []))

    def slice(self, i):
        return float(self.thetas[i]), float(self.rhos[i]), float(self.psis[i])

    def slice_at(self, T):
        """(theta, rho, psi) at any T > 0, interpolated as in Corbetta et al. section 5
        and Mingone section 5: theta, psi and rho*psi linear in T between expiries,
        theta and psi scaled by T/T_1 with rho fixed before the first expiry, and
        theta extended at its last slope with rho and psi frozen after the last. All
        three keep the conditions above (tests/test_essvi.py checks it numerically)."""
        T = float(T)
        th, ps, rp = self.thetas, self.psis, self.rhos * self.psis
        if T <= self.Ts[0]:
            lam = T / self.Ts[0]
            return lam * th[0], float(self.rhos[0]), lam * ps[0]
        if T >= self.Ts[-1]:
            slope = (th[-1] - th[-2]) / (self.Ts[-1] - self.Ts[-2]) if len(th) > 1 else th[-1] / self.Ts[-1]
            return th[-1] + slope * (T - self.Ts[-1]), float(self.rhos[-1]), float(ps[-1])
        t, p, r = (float(np.interp(T, self.Ts, a)) for a in (th, ps, rp))
        return t, r / p, p


def essvi_w(k, theta, rho, psi):
    k = np.asarray(k, float)
    return 0.5 * (theta + rho * psi * k + np.sqrt((psi * k + theta * rho) ** 2 + theta**2 * (1 - rho**2)))


def essvi_dw(k, theta, rho, psi):
    k = np.asarray(k, float)
    u = psi * k + theta * rho
    return 0.5 * psi * (rho + u / np.sqrt(u**2 + theta**2 * (1 - rho**2)))


def essvi_d2w(k, theta, rho, psi):
    k = np.asarray(k, float)
    u = psi * k + theta * rho
    v = theta**2 * (1 - rho**2)
    return 0.5 * psi**2 * v / (u**2 + v) ** 1.5


def wing_slopes(theta, rho, psi) -> tuple[float, float]:
    """Asymptotic slopes of w(k) as k -> -inf and k -> +inf."""
    return float(0.5 * psi * (1 - rho)), float(0.5 * psi * (1 + rho))


def check_constraints(p: ESSVIParams, tol: float = 1e-9) -> dict:
    th, r, ps = p.thetas, p.rhos, p.psis
    rp = r * ps
    out = {
        "rho_in_range": bool(np.all(np.abs(r) < 1)),
        "psi_positive": bool(np.all(ps > 0)),
        "theta_monotone": bool(np.all(np.diff(th) >= -tol)),
        "psi_monotone": bool(np.all(np.diff(ps) >= -tol)),
        "calendar_rho_psi": bool(np.all(np.abs(np.diff(rp)) <= np.diff(ps) + tol)),
        "phi_non_increasing": bool(np.all(ps[1:] * th[:-1] <= ps[:-1] * th[1:] * (1 + tol))),
        "butterfly_part1": bool(np.all(ps * (1 + np.abs(r)) < 4)),
        "butterfly_part2": bool(np.all(ps**2 * (1 + np.abs(r)) <= 4 * th + tol)),
    }
    out["all_ok"] = all(out.values())
    return out


def _max_first(other, theta, sum_cap):
    """Largest a with a <= PM_MAX, a + other <= sum_cap and (a + other)*max(a, other) <= 8*theta."""
    if 2 * other**2 <= 8 * theta:
        a = 0.5 * (-other + np.sqrt(other**2 + 32 * theta))
    else:
        a = 8 * theta / other - other
    return min(PM_MAX, a, sum_cap - other)


def _sum_caps(thetas, psis):
    """Cap on p_i + m_i = 2*psi_i from phi non-increasing (none on the first slice)."""
    caps = np.full(len(thetas), np.inf)
    caps[1:] = 2 * psis[:-1] / thetas[:-1] * thetas[1:]
    return caps


def _unpack(x, n):
    thetas = np.cumsum(x[:n])
    xs, ys = x[n:2 * n], x[2 * n:]
    p = np.empty(n)
    m = np.empty(n)
    p_prev = m_prev = 0.0
    cap = np.inf
    for i in range(n):
        p[i] = p_prev + xs[i] * max(_max_first(m_prev, thetas[i], cap) - p_prev, 0.0)
        m[i] = m_prev + ys[i] * max(_max_first(p[i], thetas[i], cap) - m_prev, 0.0)
        p_prev, m_prev = p[i], m[i]
        if i + 1 < n:
            cap = (p[i] + m[i]) / thetas[i] * thetas[i + 1]
    psis = 0.5 * (p + m)
    return thetas, (p - m) / (p + m), psis


def _pack(thetas, rhos, psis):
    """Inverse of ``_unpack`` for admissible slices (used to start from an SSVI fit)."""
    n = len(thetas)
    p, m = psis * (1 + rhos), psis * (1 - rhos)
    caps = _sum_caps(thetas, psis)
    xs, ys = np.empty(n), np.empty(n)
    p_prev = m_prev = 0.0
    for i in range(n):
        room = _max_first(m_prev, thetas[i], caps[i]) - p_prev
        xs[i] = (p[i] - p_prev) / room if room > 1e-14 else 0.5
        room = _max_first(p[i], thetas[i], caps[i]) - m_prev
        ys[i] = (m[i] - m_prev) / room if room > 1e-14 else 0.5
        p_prev, m_prev = p[i], m[i]
    inc = np.diff(np.concatenate([[0.0], thetas]))
    return np.concatenate([inc, xs, ys])


def fit_essvi(slices, ssvi_start=None):
    """Fit eSSVI to every expiry at once, with the same objective as ``fit_ssvi``.

    ``slices`` is a list of dicts with keys T, k, w, weights (and optionally
    expiry). Starts from the constrained SSVI fit (``ssvi_start``, fitted here if
    not given), which is itself admissible eSSVI, plus a few constant-rho starts.
    """
    slices = sorted(slices, key=lambda s: s["T"])
    n = len(slices)
    Ts = np.array([s["T"] for s in slices])
    th0 = np.maximum.accumulate([max(atm_total_variance(s["k"], s["w"]), 1e-6) for s in slices])

    ks = [np.asarray(s["k"], float) for s in slices]
    ws = [np.asarray(s["w"], float) for s in slices]
    sw = []
    for s, t0 in zip(slices, th0):
        wt = np.ones(len(s["k"])) if s.get("weights") is None else np.asarray(s["weights"], float)
        sw.append(np.sqrt(wt / wt.mean()) / t0)

    def resid(x):
        thetas, rhos, psis = _unpack(x, n)
        return np.concatenate([sw[i] * (essvi_w(ks[i], thetas[i], rhos[i], psis[i]) - ws[i])
                               for i in range(n)])

    # theta_1 > 0 and x_1, y_1 > 0 keep the first slice non-degenerate (psi > 0, |rho| < 1)
    lb = np.concatenate([[1e-8], np.zeros(n - 1), [1e-6], np.zeros(n - 1), [1e-6], np.zeros(n - 1)])
    ub = np.concatenate([np.full(n, 5.0), np.ones(2 * n)])

    if ssvi_start is None:
        ssvi_start, _ = fit_ssvi(slices)
    sp = ssvi_start
    psi_ssvi = sp.thetas * phi(sp.thetas, sp.eta, sp.gamma)
    # SSVI is admissible eSSVI: power-law phi with gamma in (0, 1/2] is decreasing in theta
    starts = [_pack(sp.thetas, np.full(n, sp.rho), psi_ssvi)]
    th = np.cumsum(np.maximum(np.diff(np.concatenate([[0.0], th0])), 1e-8))
    for rho0 in (-0.9, -0.6):
        for frac in (0.3, 0.7):
            # constant rho, psi a fixed fraction of its butterfly bound: increasing in theta,
            # and growing like sqrt(theta) or slower, so phi = psi/theta falls
            psi = frac * np.minimum(2 * np.sqrt(th / (1 + abs(rho0))), 4 / (1 + abs(rho0)))
            starts.append(_pack(th, np.full(n, rho0), psi))

    best = None
    for x0 in starts:
        x0 = np.clip(x0, lb, ub)
        r = least_squares(resid, x0, bounds=(lb, ub), method="trf", x_scale="jac",
                          ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=20000)
        if best is None or r.cost < best.cost:
            best = r
    thetas, rhos, psis = _unpack(best.x, n)
    params = ESSVIParams(thetas=thetas, rhos=rhos, psis=psis, Ts=Ts,
                         expiries=[s.get("expiry", "") for s in slices])
    return params, {"objective": float(2 * best.cost), "nfev": int(best.nfev), "status": int(best.status)}
