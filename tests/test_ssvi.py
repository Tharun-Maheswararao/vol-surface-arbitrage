import numpy as np
import pytest

from volsurf.arbitrage import g_function
from volsurf.ssvi import SSVIParams, check_constraints, fit_ssvi, phi, ssvi_d2w, ssvi_dw, ssvi_w

K = np.linspace(-2.0, 1.5, 3501)


def _slices(rho=-0.7, eta=1.0, gamma=0.4, noise=0.0, seed=0, n=6):
    rng = np.random.default_rng(seed)
    Ts = np.array([0.05, 0.1, 0.25, 0.5, 1.0, 2.0])[:n]
    thetas = 0.04 * Ts + 0.002
    out = []
    for T, th in zip(Ts, thetas):
        k = np.linspace(-4 * np.sqrt(th), 2 * np.sqrt(th), 40)
        w = ssvi_w(k, th, rho, eta, gamma)
        w = w * (1 + noise * rng.standard_normal(len(k)))
        out.append({"T": T, "k": k, "w": w, "weights": np.ones_like(k)})
    return out, thetas


def test_derivatives_match_finite_differences():
    th, rho, eta, gamma, h = 0.03, -0.6, 1.1, 0.4, 1e-5
    w = lambda k: ssvi_w(k, th, rho, eta, gamma)  # noqa: E731
    k = np.linspace(-1, 1, 21)
    np.testing.assert_allclose(ssvi_dw(k, th, rho, eta, gamma), (w(k + h) - w(k - h)) / (2 * h), atol=1e-8)
    np.testing.assert_allclose(ssvi_d2w(k, th, rho, eta, gamma),
                               (w(k + h) - 2 * w(k) + w(k - h)) / h**2, atol=1e-4)


def test_atm_total_variance_is_theta():
    assert ssvi_w(0.0, 0.037, -0.5, 1.2, 0.3) == pytest.approx(0.037)


def test_parameter_recovery():
    slices, thetas = _slices()
    p, _ = fit_ssvi(slices)
    assert p.rho == pytest.approx(-0.7, abs=1e-3)
    assert p.eta == pytest.approx(1.0, abs=5e-3)
    assert p.gamma == pytest.approx(0.4, abs=5e-3)
    np.testing.assert_allclose(p.thetas, thetas, rtol=1e-3)


@pytest.mark.parametrize("seed", range(5))
def test_fitted_parameters_always_satisfy_constraints(seed):
    """Noisy data generated *outside* the admissible region still gives admissible fits."""
    rng = np.random.default_rng(seed)
    rho = rng.uniform(-0.95, -0.2)
    eta, gamma = rng.uniform(1.5, 3.0), rng.uniform(0.5, 0.9)  # violates the bounds
    slices, _ = _slices(rho, eta, gamma, noise=0.01, seed=seed)
    p, _ = fit_ssvi(slices)
    cons = check_constraints(p)
    assert cons["all_ok"], cons
    assert p.eta * (1 + abs(p.rho)) <= 2 + 1e-9 and 0 < p.gamma <= 0.5
    assert np.all(np.diff(p.thetas) >= 0)


@pytest.mark.parametrize("seed", range(20))
def test_admissible_parameters_have_no_static_arbitrage(seed):
    """Numerical confirmation of the Gatheral-Jacquier conditions: g >= 0 on every slice
    and slices never cross when theta increases."""
    rng = np.random.default_rng(100 + seed)
    rho = rng.uniform(-0.99, 0.99)
    eta = rng.uniform(0.01, 2 / (1 + abs(rho)))
    gamma = rng.uniform(0.01, 0.5)
    thetas = np.cumsum(rng.uniform(0.0005, 0.05, 8))
    prev = None
    for th in thetas:
        w, dw, d2w = (f(K, th, rho, eta, gamma) for f in (ssvi_w, ssvi_dw, ssvi_d2w))
        assert g_function(K, w, dw, d2w).min() >= -1e-12
        if prev is not None:
            assert np.all(w - prev >= -1e-14)
        prev = w


def test_bounds_are_tight_enough_to_matter():
    """Outside the admissible region butterfly arbitrage does appear for small theta."""
    rho, eta, gamma, th = -0.9, 4.0, 0.9, 1e-4
    w, dw, d2w = (f(K, th, rho, eta, gamma) for f in (ssvi_w, ssvi_dw, ssvi_d2w))
    assert g_function(K, w, dw, d2w).min() < 0
    p = SSVIParams(rho, eta, gamma, np.array([th]), np.array([0.1]))
    assert not check_constraints(p)["all_ok"]


def test_phi_power_law_limits():
    # theta * phi < eta for all theta, increasing towards eta
    th = np.geomspace(1e-6, 1e4, 200)
    tp = th * phi(th, 1.3, 0.4)
    assert np.all(tp < 1.3) and np.all(np.diff(tp) > 0)


def test_theta_interpolation_monotone():
    p = SSVIParams(-0.5, 1.0, 0.3, np.array([0.01, 0.02, 0.05]), np.array([0.1, 0.5, 1.0]))
    T = np.linspace(0.0, 1.5, 100)
    assert np.all(np.diff(p.theta_at(T)) >= 0)
    assert p.theta_at(0.5) == pytest.approx(0.02)
