import numpy as np
import pytest

from volsurf.pricing import black_price, black_vega, implied_vol, implied_vol_vec, normalized_call


@pytest.mark.parametrize("is_call", [True, False])
def test_black_round_trip(is_call):
    """price -> implied vol -> price returns the original price."""
    F, D = 5000.0, 0.97
    for T in (0.02, 0.25, 1.0, 3.0):
        for K in (3500.0, 4500.0, 5000.0, 5600.0, 7000.0):
            for sigma in (0.05, 0.15, 0.4, 1.2):
                p = black_price(F, K, T, sigma, D, is_call)
                intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
                if p / D - intrinsic < 1e-8 * F:  # time value below double precision resolution
                    continue
                iv = implied_vol(p, F, K, T, D, is_call)
                assert iv == pytest.approx(sigma, rel=1e-6, abs=1e-7)
                assert black_price(F, K, T, iv, D, is_call) == pytest.approx(p, rel=1e-9, abs=1e-9)


def test_out_of_bounds_prices_give_nan():
    F, K, T, D = 100.0, 90.0, 0.5, 0.99
    assert np.isnan(implied_vol(D * 9.0, F, K, T, D, True))       # below intrinsic
    assert np.isnan(implied_vol(D * 100.5, F, K, T, D, True))     # above forward
    assert np.isnan(implied_vol(0.0, F, K, T, D, False))
    assert np.isnan(implied_vol(1.0, F, K, 0.0, D, False))


def test_put_call_parity_of_black():
    F, K, T, s, D = 100.0, np.linspace(60, 150, 19), 0.7, 0.25, 0.96
    c = black_price(F, K, T, s, D, True)
    p = black_price(F, K, T, s, D, False)
    np.testing.assert_allclose(c - p, D * (F - K), atol=1e-10)


def test_vega_matches_finite_difference():
    F, K, T, s, D, h = 100.0, 110.0, 0.5, 0.3, 0.98, 1e-6
    fd = (black_price(F, K, T, s + h, D) - black_price(F, K, T, s - h, D)) / (2 * h)
    assert black_vega(F, K, T, s, D) == pytest.approx(fd, rel=1e-6)


def test_vectorised_matches_scalar():
    F, T, D = 100.0, 0.4, 0.99
    K = np.array([80.0, 100.0, 120.0])
    s = np.array([0.3, 0.2, 0.18])
    p = black_price(F, K, T, s, D, [False, True, True])
    np.testing.assert_allclose(implied_vol_vec(p, F, K, T, D, [False, True, True]), s, rtol=1e-8)


def test_normalized_call_matches_black():
    F, T, s = 100.0, 0.8, 0.22
    K = np.array([70.0, 100.0, 140.0])
    k, w = np.log(K / F), s**2 * T
    np.testing.assert_allclose(normalized_call(k, w) * F, black_price(F, K, T, s), rtol=1e-12)
