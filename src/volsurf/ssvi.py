"""Surface SVI (Gatheral and Jacquier, 2014) with the power-law phi.

    w(k, theta) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + 1 - rho^2))
    phi(theta)  = eta / (theta^gamma * (1 + theta)^(1 - gamma))

No-arbitrage conditions used here (checked algebraically in REPORT.md):

Checked against the SSRN version of Gatheral and Jacquier (2014), dated
17 March 2013 (abstract 2033323).

* Calendar (GJ14 Thm 4.1): theta_t non-decreasing in t, and
  0 <= d(theta*phi)/dtheta <= (1 + sqrt(1 - rho^2)) / rho^2 * phi.
  For this phi, d(theta*phi)/dtheta / phi = (1 - gamma) / (1 + theta) < 1, so
  the second part always holds for gamma in (0, 1) and only monotone theta is needed.
* Butterfly (GJ14 Thm 4.2, sufficient): theta*phi*(1 + |rho|) < 4 and
  theta*phi^2*(1 + |rho|) <= 4 for all theta > 0. Lemma 4.2 shows the first is
  necessary and the second tight. With gamma in (0, 1/2] and
  eta*(1 + |rho|) <= 2 both hold for every theta, since theta*phi < eta and
  theta*phi^2 <= eta^2.

The fit enforces these by construction: eta = 2*s/(1+|rho|) with s in (0, 1],
gamma in (0, 1/2], and theta_i = cumulative sum of non-negative increments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

GAMMA_MAX = 0.5


@dataclass
class SSVIParams:
    rho: float
    eta: float
    gamma: float
    thetas: np.ndarray            # ATM total variance per expiry, non-decreasing
    Ts: np.ndarray                # expiries in years
    expiries: list = field(default_factory=list)

    def to_dict(self):
        return {"rho": self.rho, "eta": self.eta, "gamma": self.gamma,
                "thetas": [float(x) for x in self.thetas], "Ts": [float(x) for x in self.Ts],
                "expiries": list(self.expiries)}

    @classmethod
    def from_dict(cls, d):
        return cls(rho=d["rho"], eta=d["eta"], gamma=d["gamma"], thetas=np.array(d["thetas"]),
                   Ts=np.array(d["Ts"]), expiries=d.get("expiries", []))

    def theta_at(self, T):
        """Linear interpolation of theta in T (monotone, so calendar-safe).
        Before the first expiry theta scales linearly from 0."""
        T = np.asarray(T, float)
        Ts = np.concatenate([[0.0], self.Ts])
        th = np.concatenate([[0.0], self.thetas])
        slope_end = (th[-1] - th[-2]) / (Ts[-1] - Ts[-2])
        out = np.interp(T, Ts, th)
        return np.where(T > Ts[-1], th[-1] + slope_end * (T - Ts[-1]), out)


def phi(theta, eta, gamma):
    theta = np.asarray(theta, float)
    return eta / (theta**gamma * (1 + theta) ** (1 - gamma))


def ssvi_w(k, theta, rho, eta, gamma):
    k = np.asarray(k, float)
    p = phi(theta, eta, gamma)
    return 0.5 * theta * (1 + rho * p * k + np.sqrt((p * k + rho) ** 2 + 1 - rho**2))


def ssvi_dw(k, theta, rho, eta, gamma):
    k = np.asarray(k, float)
    p = phi(theta, eta, gamma)
    return 0.5 * theta * p * (rho + (p * k + rho) / np.sqrt((p * k + rho) ** 2 + 1 - rho**2))


def ssvi_d2w(k, theta, rho, eta, gamma):
    k = np.asarray(k, float)
    p = phi(theta, eta, gamma)
    return 0.5 * theta * p**2 * (1 - rho**2) / ((p * k + rho) ** 2 + 1 - rho**2) ** 1.5


def wing_slopes(theta, rho, eta, gamma) -> tuple[float, float]:
    """Asymptotic slopes of w(k, theta) as k -> -inf and k -> +inf (GJ14 Remark 4.3)."""
    tp = theta * phi(theta, eta, gamma)
    return float(0.5 * (1 - rho) * tp), float(0.5 * (1 + rho) * tp)


def check_constraints(p: SSVIParams, tol: float = 1e-9) -> dict:
    """Parameter conditions plus a direct numerical check of GJ14 Thm 4.2 on a theta grid."""
    th = np.geomspace(1e-6, 1e3, 4000)
    ph = phi(th, p.eta, p.gamma)
    r = abs(p.rho)
    out = {
        "rho_in_range": bool(-1 < p.rho < 1),
        "eta_positive": bool(p.eta > 0),
        "gamma_in_range": bool(0 < p.gamma <= GAMMA_MAX + tol),
        "eta_rho_bound": bool(p.eta * (1 + r) <= 2 + tol),
        "theta_monotone": bool(np.all(np.diff(p.thetas) >= -tol)),
        "gj_thm42_part1": bool(np.max(th * ph * (1 + r)) < 4),
        "gj_thm42_part2": bool(np.max(th * ph**2 * (1 + r)) <= 4 + tol),
    }
    out["all_ok"] = all(out.values())
    return out


def _unpack(x, n):
    rho, s, gamma = x[0], x[1], x[2]
    eta = 2.0 * s / (1 + abs(rho))
    thetas = np.cumsum(x[3:3 + n])
    return rho, eta, gamma, thetas


def atm_total_variance(k, w):
    """Market ATM total variance by linear interpolation at k = 0 (nearest point if 0 is outside)."""
    order = np.argsort(k)
    return float(np.interp(0.0, np.asarray(k)[order], np.asarray(w)[order]))


def fit_ssvi(slices, starts=None, constrained: bool = True):
    """Fit SSVI to every expiry at once.

    ``slices`` is a list of dicts with keys T, k, w, weights (and optionally
    expiry), sorted by T. Each slice's residuals are scaled by its market ATM
    total variance and its weights normalised to mean 1, so every expiry counts
    about equally in vol terms; the per-slice SVI fit uses the same objective.

    ``constrained=False`` relaxes gamma to (0, 1) and drops the eta*(1+|rho|) <= 2
    bound. It exists only to measure what the no-arbitrage constraints cost.
    """
    slices = sorted(slices, key=lambda s: s["T"])
    n = len(slices)
    Ts = np.array([s["T"] for s in slices])
    th0 = np.maximum.accumulate([max(atm_total_variance(s["k"], s["w"]), 1e-6) for s in slices])
    inc0 = np.diff(np.concatenate([[0.0], th0]))
    inc0 = np.maximum(inc0, 1e-8)

    ks = [np.asarray(s["k"], float) for s in slices]
    ws = [np.asarray(s["w"], float) for s in slices]
    sw = []
    for s, t0 in zip(slices, th0):
        wt = np.ones(len(s["k"])) if s.get("weights") is None else np.asarray(s["weights"], float)
        sw.append(np.sqrt(wt / wt.mean()) / t0)

    def resid(x):
        rho, eta, gamma, thetas = _unpack(x, n)
        out = []
        for i in range(n):
            out.append(sw[i] * (ssvi_w(ks[i], thetas[i], rho, eta, gamma) - ws[i]))
        return np.concatenate(out)

    lb = np.concatenate([[-0.999, 1e-4, 1e-4], [1e-8], np.zeros(n - 1)])
    s_max, g_max = (1.0, GAMMA_MAX) if constrained else (25.0, 0.999)
    ub = np.concatenate([[0.999, s_max, g_max], np.full(n, 5.0)])
    if starts is None:
        starts = [(r, s, g) for r in (-0.8, -0.5) for s in (0.4, 0.9) for g in (0.2, 0.45)]

    best = None
    for rho0, s0, g0 in starts:
        x0 = np.concatenate([[rho0, s0, g0], inc0])
        x0 = np.clip(x0, lb + 1e-12, ub - 1e-12)
        r = least_squares(resid, x0, bounds=(lb, ub), method="trf", x_scale="jac",
                          ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=5000)
        if best is None or r.cost < best.cost:
            best = r
    rho, eta, gamma, thetas = _unpack(best.x, n)
    params = SSVIParams(rho=float(rho), eta=float(eta), gamma=float(gamma), thetas=thetas, Ts=Ts,
                        expiries=[s.get("expiry", "") for s in slices])
    return params, {"objective": float(2 * best.cost), "nfev": int(best.nfev), "status": int(best.status)}
