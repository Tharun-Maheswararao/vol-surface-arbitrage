import numpy as np
import pytest

from volsurf.forwards import fit_forward
from volsurf.pricing import black_price


def _synthetic(F, D, K, T=0.5, sigma=0.2):
    return black_price(F, K, T, sigma, D, True), black_price(F, K, T, sigma, D, False)


def test_exact_recovery():
    F, D = 5123.4, 0.9731
    K = np.arange(4500, 5800, 25.0)
    c, p = _synthetic(F, D, K)
    fw = fit_forward(K, c, p)
    assert fw.F == pytest.approx(F, rel=1e-10)
    assert fw.D == pytest.approx(D, rel=1e-10)


def test_recovery_with_noise_and_outliers():
    rng = np.random.default_rng(1)
    F, D = 5123.4, 0.9731
    K = np.arange(4500, 5800, 25.0)
    c, p = _synthetic(F, D, K)
    c = c + rng.normal(0, 0.05, len(K))
    p = p + rng.normal(0, 0.05, len(K))
    c[[3, 17, 40]] += [25.0, -40.0, 15.0]  # bad quotes the robust pass should drop
    fw = fit_forward(K, c, p)
    assert fw.n_used <= len(K) - 3
    assert fw.F == pytest.approx(F, abs=0.5)
    assert fw.D == pytest.approx(D, abs=2e-4)
    assert fw.rate(0.5) == pytest.approx(-np.log(D) / 0.5, abs=1e-3)


def test_too_few_pairs():
    with pytest.raises(ValueError):
        fit_forward([100.0, 105.0], [5.0, 3.0], [4.0, 6.0])
