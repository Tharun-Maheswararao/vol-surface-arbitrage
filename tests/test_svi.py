import numpy as np
import pytest

from volsurf.arbitrage import g_function, implied_density
from volsurf.pricing import normalized_call
from volsurf.svi import SVIParams, fit_svi, satisfies_constraints, svi_d2w, svi_dw, svi_w

TRUE = SVIParams(a=0.01, b=0.12, rho=-0.6, m=0.02, sigma=0.15)


def test_derivatives_match_finite_differences():
    k, h = np.linspace(-1, 1, 41), 1e-5
    fd1 = (svi_w(k + h, TRUE) - svi_w(k - h, TRUE)) / (2 * h)
    fd2 = (svi_w(k + h, TRUE) - 2 * svi_w(k, TRUE) + svi_w(k - h, TRUE)) / h**2
    np.testing.assert_allclose(svi_dw(k, TRUE), fd1, atol=1e-8)
    np.testing.assert_allclose(svi_d2w(k, TRUE), fd2, atol=1e-4)


def test_exact_recovery():
    k = np.linspace(-0.6, 0.3, 60)
    p, _ = fit_svi(k, svi_w(k, TRUE))
    for name in ("a", "b", "rho", "m", "sigma"):
        assert getattr(p, name) == pytest.approx(getattr(TRUE, name), abs=1e-4)


def test_recovery_with_noise():
    """Known parameters, noisy total variance, weighted fit recovers them."""
    rng = np.random.default_rng(7)
    k = np.linspace(-0.6, 0.3, 120)
    w_true = svi_w(k, TRUE)
    spread = 0.002 * w_true + 1e-4
    w_obs = w_true + rng.normal(0, 0.25 * spread)
    p, _ = fit_svi(k, w_obs, weights=1 / spread)
    assert satisfies_constraints(p)
    assert p.b == pytest.approx(TRUE.b, rel=0.05)
    assert p.rho == pytest.approx(TRUE.rho, abs=0.03)
    assert p.m == pytest.approx(TRUE.m, abs=0.01)
    assert p.sigma == pytest.approx(TRUE.sigma, rel=0.08)
    assert np.max(np.abs(svi_w(k, p) - w_true)) < 3 * spread.max()


def test_fit_respects_constraints_on_awkward_data():
    """Data that wants a negative minimum variance must still give a valid slice."""
    k = np.linspace(-0.5, 0.5, 40)
    w = np.maximum(0.03 * k**2 * 40 - 0.002, 1e-5)
    p, _ = fit_svi(k, w)
    assert satisfies_constraints(p)
    assert np.min(svi_w(np.linspace(-3, 3, 2001), p)) >= -1e-10


def test_density_integrates_to_one_and_matches_breeden_litzenberger():
    k = np.linspace(-3, 3, 6001)
    w, dw, d2w = svi_w(k, TRUE), svi_dw(k, TRUE), svi_d2w(k, TRUE)
    dens = implied_density(k, w, dw, d2w)
    assert np.trapezoid(dens, k) == pytest.approx(1.0, abs=2e-3)
    # Breeden-Litzenberger in strike space: density of K/F is d2c/dx2 at x = e^k
    x = np.exp(k)
    c = normalized_call(k, w)
    d2c = np.gradient(np.gradient(c, x), x)
    inner = slice(200, -200)
    np.testing.assert_allclose((d2c * x)[inner], dens[inner], atol=2e-3)


def test_known_butterfly_arbitrage_slice_has_negative_g():
    # Axel Vogt's example from Gatheral and Jacquier (2014): raw SVI with butterfly arbitrage
    p = SVIParams(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
    k = np.linspace(-1.5, 1.5, 3001)
    g = g_function(k, svi_w(k, p), svi_dw(k, p), svi_d2w(k, p))
    assert g.min() < 0
    g_ok = g_function(k, svi_w(k, TRUE), svi_dw(k, TRUE), svi_d2w(k, TRUE))
    assert g_ok.min() > 0


def test_fit_keeps_wings_inside_lee_bound():
    """Data with a right wing steeper than Lee's bound must not produce a slice whose
    asymptotic slope reaches 2 (GJ14 Lemma 2.2 needs d+ -> -inf)."""
    steep = SVIParams(a=-0.05, b=2.2, rho=0.85, m=0.6, sigma=0.3)  # b(1+rho) = 4.07
    k = np.linspace(-0.9, 0.2, 80)
    p, _ = fit_svi(k, svi_w(k, steep))
    assert satisfies_constraints(p)
    assert p.b * (1 + abs(p.rho)) < 2
    assert not satisfies_constraints(steep)
