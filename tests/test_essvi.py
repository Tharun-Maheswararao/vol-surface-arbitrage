import numpy as np
import pytest

from volsurf.arbitrage import g_function
from volsurf.essvi import (
    PM_MAX,
    ESSVIParams,
    _pack,
    _unpack,
    check_constraints,
    essvi_d2w,
    essvi_dw,
    essvi_w,
    fit_essvi,
)
from volsurf.ssvi import ssvi_w

K = np.linspace(-6.0, 4.0, 10001)
TS = np.array([0.05, 0.1, 0.25, 0.5, 1.0, 2.0])


def _random_admissible(rng, n=8):
    """Admissible slices drawn straight from the condition set, not through the fit's
    parametrisation. With p = psi*(1+rho) and m = psi*(1-rho), the conditions are:
    theta, p and m non-decreasing, psi/theta non-increasing, max(p, m) < 4 and
    (p + m)*max(p, m) <= 8*theta. Each slice adds random increments to the previous
    (p, m) and halves them until the other bounds hold, which they do at zero
    increment since theta only grows."""
    thetas = np.cumsum(rng.uniform(0.0005, 0.05, n))
    p, m = np.zeros(n), np.zeros(n)
    p_prev = m_prev = 0.0
    for i in range(n):
        dp, dm = rng.uniform(0.001, 1.0, 2) * (2.0 if i == 0 else 0.5)
        cap = np.inf if i == 0 else (p_prev + m_prev) / thetas[i - 1] * thetas[i]
        while True:
            a, b = p_prev + dp, m_prev + dm
            if max(a, b) <= PM_MAX and (a + b) * max(a, b) <= 8 * thetas[i] and a + b <= cap:
                break
            dp, dm = dp / 2, dm / 2
        p[i], m[i] = p_prev, m_prev = a, b
    return thetas, (p - m) / (p + m), 0.5 * (p + m)


def _slices(thetas, rhos, psis, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for T, th, r, ps in zip(TS, thetas, rhos, psis):
        k = np.linspace(-4 * np.sqrt(th), 2 * np.sqrt(th), 40)
        w = essvi_w(k, th, r, ps) * (1 + noise * rng.standard_normal(len(k)))
        out.append({"T": T, "k": k, "w": w, "weights": np.ones_like(k)})
    return out


def test_reduces_to_ssvi():
    k = np.linspace(-1, 1, 21)
    th, rho, eta, gamma = 0.03, -0.6, 1.1, 0.4
    phi = eta / (th**gamma * (1 + th) ** (1 - gamma))
    np.testing.assert_allclose(essvi_w(k, th, rho, th * phi), ssvi_w(k, th, rho, eta, gamma), rtol=1e-12)


def test_derivatives_match_finite_differences():
    th, rho, psi, h = 0.03, -0.6, 0.25, 1e-5
    w = lambda k: essvi_w(k, th, rho, psi)  # noqa: E731
    k = np.linspace(-1, 1, 21)
    np.testing.assert_allclose(essvi_dw(k, th, rho, psi), (w(k + h) - w(k - h)) / (2 * h), atol=1e-8)
    np.testing.assert_allclose(essvi_d2w(k, th, rho, psi), (w(k + h) - 2 * w(k) + w(k - h)) / h**2,
                               atol=1e-4)


@pytest.mark.parametrize("seed", range(30))
def test_admissible_parameters_have_no_static_arbitrage(seed):
    """g >= 0 on every slice and adjacent slices never cross, on a wide k grid,
    for parameters satisfying the Hendriks-Martini / Corbetta et al. conditions."""
    rng = np.random.default_rng(200 + seed)
    thetas, rhos, psis = _random_admissible(rng)
    p = ESSVIParams(thetas, rhos, psis, np.arange(1, len(thetas) + 1) * 0.25)
    assert check_constraints(p)["all_ok"], check_constraints(p)
    prev = None
    for th, r, ps in zip(thetas, rhos, psis):
        w, dw, d2w = (f(K, th, r, ps) for f in (essvi_w, essvi_dw, essvi_d2w))
        assert g_function(K, w, dw, d2w).min() >= -1e-12
        if prev is not None:
            assert np.all(w - prev >= -1e-14)
        prev = w


@pytest.mark.parametrize("seed", range(10))
def test_interpolated_slices_have_no_static_arbitrage(seed):
    """Corbetta et al. section 5: linear interpolation of theta, psi and rho*psi in T
    stays arbitrage-free between and beyond the fitted expiries."""
    rng = np.random.default_rng(300 + seed)
    thetas, rhos, psis = _random_admissible(rng, n=4)
    p = ESSVIParams(thetas, rhos, psis, np.array([0.1, 0.3, 0.7, 1.5]))
    prev = None
    for T in np.linspace(0.01, 2.5, 120):
        th, r, ps = p.slice_at(T)
        w, dw, d2w = (f(K, th, r, ps) for f in (essvi_w, essvi_dw, essvi_d2w))
        assert g_function(K, w, dw, d2w).min() >= -1e-12
        if prev is not None:
            assert np.all(w - prev >= -1e-14)
        prev = w


def test_calendar_conditions_are_tight_enough_to_matter():
    """Breaking |d(rho*psi)| <= d(psi) with theta still increasing makes slices cross."""
    th1, th2 = 0.04, 0.045
    w1 = essvi_w(K, th1, 0.2, 0.3)
    w2 = essvi_w(K, th2, -0.8, 0.31)   # rho*psi falls by 0.31 while psi grows by 0.01
    assert (w2 - w1).min() < 0
    p = ESSVIParams(np.array([th1, th2]), np.array([0.2, -0.8]), np.array([0.3, 0.31]),
                    np.array([0.1, 0.2]))
    cons = check_constraints(p)
    assert cons["theta_monotone"] and cons["psi_monotone"] and not cons["calendar_rho_psi"]
    assert cons["butterfly_part1"] and cons["butterfly_part2"]


def test_necessary_calendar_conditions_alone_allow_crossing():
    """theta and psi increasing with |d(rho*psi)| <= d(psi) is only necessary: this
    pair meets it and both butterfly bounds, but phi = psi/theta rises and the slices
    cross for k in about (-1.49, -0.09). The sufficient condition phi non-increasing
    (Hendriks-Martini Prop. 3.5 as quoted by Mingone 2022) rejects it."""
    p = ESSVIParams(np.array([1.0, 1.01]), np.array([0.0, 0.1]), np.array([1.0, 1.2]),
                    np.array([0.5, 1.0]))
    cons = check_constraints(p)
    assert cons["theta_monotone"] and cons["psi_monotone"] and cons["calendar_rho_psi"]
    assert cons["butterfly_part1"] and cons["butterfly_part2"]
    assert not cons["phi_non_increasing"]
    k = np.linspace(-2, 0.5, 2501)
    diff = essvi_w(k, *p.slice(1)) - essvi_w(k, *p.slice(0))
    assert diff.min() < -0.02
    crossed = k[diff < 0]
    assert crossed.min() == pytest.approx(-1.485, abs=0.01)
    assert crossed.max() == pytest.approx(-0.09, abs=0.01)


def test_parametrisation_is_admissible_and_invertible():
    rng = np.random.default_rng(0)
    n = 8
    for _ in range(200):
        x = np.concatenate([rng.uniform(1e-8, 0.05, n), rng.uniform(1e-6, 1, 2 * n)])
        thetas, rhos, psis = _unpack(x, n)
        assert check_constraints(ESSVIParams(thetas, rhos, psis, np.arange(n) + 1.0))["all_ok"]
        th2, r2, ps2 = _unpack(_pack(thetas, rhos, psis), n)
        np.testing.assert_allclose(ps2, psis, rtol=1e-9)
        np.testing.assert_allclose(r2, rhos, atol=1e-9)


def test_parameter_recovery():
    thetas = 0.04 * TS + 0.002
    rhos = np.array([-0.85, -0.8, -0.75, -0.7, -0.65, -0.6])
    psis = np.array([0.08, 0.1, 0.13, 0.16, 0.2, 0.25])
    p = ESSVIParams(thetas, rhos, psis, TS)
    assert check_constraints(p)["all_ok"]
    fit, _ = fit_essvi(_slices(thetas, rhos, psis))
    np.testing.assert_allclose(fit.thetas, thetas, rtol=1e-4)
    np.testing.assert_allclose(fit.rhos, rhos, atol=2e-3)
    np.testing.assert_allclose(fit.psis, psis, rtol=2e-3)


@pytest.mark.parametrize("seed", range(4))
def test_fit_returns_admissible_parameters(seed):
    """Noisy data from slices that break the calendar and butterfly conditions
    (rho swings, psi falling, psi above its butterfly bound) still fit admissibly."""
    rng = np.random.default_rng(seed)
    thetas = 0.04 * TS + 0.002
    rhos = rng.uniform(-0.95, 0.3, len(TS))
    psis = rng.uniform(0.05, 0.6, len(TS))
    fit, _ = fit_essvi(_slices(thetas, rhos, psis, noise=0.01, seed=seed))
    cons = check_constraints(fit)
    assert cons["all_ok"], cons
    for th, r, ps in zip(fit.thetas, fit.rhos, fit.psis):
        w, dw, d2w = (f(K, th, r, ps) for f in (essvi_w, essvi_dw, essvi_d2w))
        assert g_function(K, w, dw, d2w).min() >= -1e-12
    W = np.array([essvi_w(K, *fit.slice(i)) for i in range(len(TS))])
    assert np.all(np.diff(W, axis=0) >= -1e-14)
