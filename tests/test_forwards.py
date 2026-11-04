import numpy as np
import pytest

from volsurf.data import clean_chain, dedupe_roots, load_snapshot, save_snapshot
from volsurf.forwards import discount_from_curve, fit_forward
from volsurf.pricing import black_price
from volsurf.quotes import ForwardConfig, build_quotes
from volsurf.synthetic import synthetic_snapshot


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


def test_fixed_d_recovers_forward():
    F, D = 5123.4, 0.9731
    K = np.arange(4500, 5800, 25.0)
    c, p = _synthetic(F, D, K)
    fw = fit_forward(K, c, p, D=D)
    assert fw.D == D
    assert fw.F == pytest.approx(F, rel=1e-10)
    assert fw.resid_std == pytest.approx(0.0, abs=1e-8)


def test_fixed_d_wrong_d_shifts_forward_by_lever_arm():
    # With D' fixed instead of the true D, the fitted intercept is the weighted mean of
    # C - P + D'K, so F' = F D/D' + (1 - D/D') * Kbar, where Kbar is the weighted mean strike.
    F, D, D_wrong = 5123.4, 0.9731, 0.9750
    K = np.arange(4500, 5800, 25.0)
    wts = 1.0 + (K - K.min()) / 100.0
    c, p = _synthetic(F, D, K)
    fw = fit_forward(K, c, p, weights=wts, D=D_wrong)
    Kbar = np.sum(wts * K) / np.sum(wts)
    assert fw.D == D_wrong
    assert fw.F == pytest.approx(F * D / D_wrong + (1 - D / D_wrong) * Kbar, rel=1e-10)


def test_fixed_d_robust_pass_drops_outliers():
    rng = np.random.default_rng(2)
    F, D = 5123.4, 0.9731
    K = np.arange(4500, 5800, 25.0)
    c, p = _synthetic(F, D, K)
    c = c + rng.normal(0, 0.05, len(K))
    c[[5, 30]] += [30.0, -20.0]
    fw = fit_forward(K, c, p, D=D)
    assert fw.n_used <= len(K) - 2
    assert fw.F == pytest.approx(F, abs=0.05)


@pytest.mark.parametrize("D", [0.0, -0.5, np.nan])
def test_fixed_d_must_be_positive(D):
    K = np.arange(4500, 5800, 25.0)
    c, p = _synthetic(5123.4, 0.9731, K)
    with pytest.raises(ValueError):
        fit_forward(K, c, p, D=D)


def test_discount_from_curve():
    T_ref, r_ref = np.array([0.5, 0.2, 1.0]), np.array([0.048, 0.045, 0.050])
    D_ref = np.exp(-r_ref * T_ref)
    # exact at the knots, in any order
    for T, D in zip(T_ref, D_ref):
        assert discount_from_curve(T, T_ref, D_ref) == pytest.approx(D, rel=1e-14)
    # flat rate before the first and after the last knot
    assert -np.log(discount_from_curve(0.04, T_ref, D_ref)) / 0.04 == pytest.approx(0.045, rel=1e-12)
    assert -np.log(discount_from_curve(1.6, T_ref, D_ref)) / 1.6 == pytest.approx(0.050, rel=1e-12)
    # log-linear in between
    logD = np.interp(0.35, [0.2, 0.5], np.log([D_ref[1], D_ref[0]]))
    assert discount_from_curve(0.35, T_ref, D_ref) == pytest.approx(np.exp(logD), rel=1e-14)
    with pytest.raises(ValueError):
        discount_from_curve(0.1, [], [])


def _clean_synthetic(tmp_path):
    chain, meta = synthetic_snapshot()
    chain, meta = load_snapshot(save_snapshot(chain, meta, tmp_path))
    clean, _ = clean_chain(dedupe_roots(chain), meta["spot"])
    return clean, meta


def test_forward_config_parity_only_is_parity_everywhere(tmp_path):
    clean, meta = _clean_synthetic(tmp_path)
    _, fwd = build_quotes(clean, meta, ForwardConfig.parity_only())
    assert (fwd["D_source"] == "parity").all()


def test_forward_config_default_targets_short_and_spxw():
    cfg = ForwardConfig()
    assert cfg.targets("SPX", 0.05) and cfg.targets("SPXW", 0.5) and not cfg.targets("SPX", 0.1)


def test_forward_config_fixes_short_expiries_from_spx_curve(tmp_path):
    clean, meta = _clean_synthetic(tmp_path)
    q0, base = build_quotes(clean, meta, ForwardConfig.parity_only())
    q1, fwd = build_quotes(clean, meta, ForwardConfig(fixed_d_max_T=0.08, fixed_d_spxw=False))
    short = fwd["T"] < 0.08
    assert short.sum() == 1
    assert (fwd.loc[short, "D_source"] == "spx_extrap").all()
    assert (fwd.loc[~short, "D_source"] == "parity").all()
    # the synthetic rate curve is flat, so the borrowed D is the true one
    r, T = meta["true_r"], fwd["T"].values
    np.testing.assert_allclose(fwd["D"], np.exp(-r * T), rtol=1e-10)
    np.testing.assert_allclose(fwd["F"], meta["spot"] * np.exp((r - meta["true_q"]) * T), rtol=1e-8)
    # untargeted expiries are untouched
    np.testing.assert_array_equal(fwd.loc[~short, "D"], base.loc[~short, "D"])
    np.testing.assert_allclose(q1["iv_mid"], q0["iv_mid"], atol=1e-8)


def test_forward_config_spxw_flag_targets_only_spxw():
    cfg = ForwardConfig(fixed_d_max_T=None, fixed_d_spxw=True)
    assert cfg.targets("SPXW", 0.5) and not cfg.targets("SPX", 0.01)
    cfg = ForwardConfig(fixed_d_max_T=0.08, fixed_d_spxw=False)
    assert cfg.targets("SPX", 0.05) and not cfg.targets("SPXW", 0.1)
    assert not ForwardConfig.parity_only().targets("SPXW", 0.01)
