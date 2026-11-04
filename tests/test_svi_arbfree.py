import numpy as np
import pytest

from volsurf.arbitrage import g_function
from volsurf.essvi import essvi_w
from volsurf.pipeline import K_GRID
from volsurf.pricing import normalized_call
from volsurf.svi import SVIParams, svi_d2w, svi_dw, svi_w
from volsurf.svi_arbfree import (
    CHECK_GRID,
    SVIArbFreeParams,
    check_surface,
    fit_svi_arbfree,
    implied_total_variance,
    otm_price,
    sqrt_ssvi_slice,
)

TS = np.array([0.1, 0.25, 0.5, 1.0, 2.0])


def _truth():
    """Raw SVI slices that are not SSVI (m and sigma move independently of theta) but are
    free of static arbitrage: g >= 0.24, wing slopes rising, gaps between slices >= 0.004."""
    b = np.array([0.04, 0.06, 0.085, 0.115, 0.15])
    rho = np.array([-0.55, -0.5, -0.45, -0.42, -0.4])
    m = np.array([0.0, 0.01, 0.02, 0.04, 0.06])
    sigma = np.array([0.1, 0.14, 0.2, 0.28, 0.38])
    a = 0.03 * TS + 0.002 - b * sigma * np.sqrt(1 - rho**2)
    return SVIArbFreeParams([SVIParams(*x) for x in zip(a, b, rho, m, sigma)], TS)


def _slices(params, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for T, p in zip(params.Ts, params.slices):
        th = float(svi_w(0.0, p))
        k = np.linspace(-4 * np.sqrt(th), 2 * np.sqrt(th), 40)
        w = svi_w(k, p) * (1 + noise * rng.standard_normal(len(k)))
        out.append({"T": T, "k": k, "w": w, "weights": np.ones_like(k)})
    return out


def _assert_arbitrage_free(p, k):
    W = np.array([svi_w(k, s) for s in p.slices])
    for s in p.slices:
        assert g_function(k, svi_w(k, s), svi_dw(k, s), svi_d2w(k, s)).min() >= 0
        assert s.wing_slopes()[1] < 2
    assert np.all(np.diff(W, axis=0) >= 0)


def test_sqrt_ssvi_slice_is_the_ssvi_slice():
    k = np.linspace(-1, 1, 21)
    th, rho, eta = 0.03, -0.6, 1.1
    np.testing.assert_allclose(svi_w(k, sqrt_ssvi_slice(th, rho, eta)),
                               essvi_w(k, th, rho, eta * np.sqrt(th)), rtol=1e-12)


def test_truth_is_arbitrage_free():
    assert check_surface(_truth())["all_ok"]
    _assert_arbitrage_free(_truth(), np.linspace(-15, 15, 30001))


def test_recovers_known_arbitrage_free_surface():
    truth = _truth()
    fit, info = fit_svi_arbfree(_slices(truth))
    assert info["all_feasible"]
    for s, t in zip(fit.slices, truth.slices):
        for name in ("a", "b", "rho", "m", "sigma"):
            assert getattr(s, name) == pytest.approx(getattr(t, name), abs=1e-6)


def test_recovers_known_surface_from_noisy_quotes():
    truth = _truth()
    data = _slices(truth, noise=0.002, seed=1)
    fit, _ = fit_svi_arbfree(data)
    assert check_surface(fit)["all_ok"]
    for s, t, d in zip(fit.slices, truth.slices, data):
        assert np.max(np.abs(svi_w(d["k"], s) / svi_w(d["k"], t) - 1)) < 0.004


@pytest.mark.parametrize("seed", range(4))
def test_fit_to_arbitrageable_slices_is_arbitrage_free(seed):
    """Independent random SVI slices, which cross and often have g < 0 or right wings near
    Lee's bound, still fit to a surface with g >= 0 and no crossing on the fitted grid and
    on the pipeline's report grid."""
    rng = np.random.default_rng(seed)
    slices = []
    for T in TS:
        p = SVIParams(a=0.0, b=rng.uniform(0.02, 0.6), rho=rng.uniform(-0.9, 0.9),
                      m=rng.uniform(-0.1, 0.3), sigma=rng.uniform(0.02, 0.3))
        p.b = min(p.b, 1.99 / (1 + abs(p.rho)))
        p.a = 0.03 * T + 0.002 - p.b * p.sigma * np.sqrt(1 - p.rho**2)
        slices.append(p)
    raw = SVIArbFreeParams(slices, TS)
    assert not check_surface(raw)["all_ok"]
    fit, info = fit_svi_arbfree(_slices(raw, noise=0.01, seed=seed))
    assert info["all_feasible"]
    assert check_surface(fit)["all_ok"], check_surface(fit)
    _assert_arbitrage_free(fit, CHECK_GRID)
    _assert_arbitrage_free(fit, K_GRID)


def test_otm_price_and_its_inverse():
    k = np.linspace(-1.5, 0.8, 47)
    w = np.linspace(0.02, 0.4, 47)  # w much smaller at k = -1.5 underflows the price
    np.testing.assert_allclose(otm_price(k, w) + np.maximum(1 - np.exp(k), 0), normalized_call(k, w),
                               atol=1e-15)
    np.testing.assert_allclose(implied_total_variance(k, otm_price(k, w), w_hi=0.4), w, rtol=1e-8)


def test_interpolation_is_arbitrage_free():
    """GJ14 Lemma 5.1: w_at hits every slice, rises in T at fixed k, and gives call prices
    convex in strike, from T -> 0 to the last expiry."""
    p = _truth()
    k = np.linspace(-1.2, 0.6, 1801)
    for i, T in enumerate(p.Ts):
        np.testing.assert_allclose(p.w_at(k, T), svi_w(k, p.slice(i)), rtol=1e-12)
    prev = np.zeros_like(k)
    K = np.exp(k)
    for T in np.linspace(0.01, p.Ts[-1], 60):
        w = p.w_at(k, T)
        assert np.all(w - prev >= -1e-10)
        c = normalized_call(k, w)
        slope = np.diff(c) / np.diff(K)
        assert np.all(np.diff(slope) >= -1e-8)
        prev = w
    with pytest.raises(ValueError):
        p.w_at(k, p.Ts[-1] * 1.1)
