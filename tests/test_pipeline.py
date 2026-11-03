import numpy as np
import pytest

from volsurf.data import save_snapshot
from volsurf.pipeline import load_results, run_pipeline
from volsurf.synthetic import TRUE_SSVI, synthetic_snapshot


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    root = tmp_path_factory.mktemp("run")
    chain, meta = synthetic_snapshot()
    snap = save_snapshot(chain, meta, root / "raw")
    return load_results(run_pipeline(snap, root / "results")), meta


def test_forwards_recovered(results):
    res, meta = results
    fw = res["forwards"]
    T = fw["T"].values
    np.testing.assert_allclose(fw["D"], np.exp(-meta["true_r"] * T), rtol=1e-8)
    np.testing.assert_allclose(fw["F"], meta["spot"] * np.exp((meta["true_r"] - meta["true_q"]) * T),
                               rtol=1e-8)


def test_no_tradable_arbitrage_on_clean_surface(results):
    res, _ = results
    assert res["summary"]["raw_survive_bid_ask"] == 0
    comp = res["comparison"].set_index("model")
    assert comp.loc["SSVI", "butterfly_slices_negative_g"] == 0
    assert comp.loc["SSVI", "calendar_pairs_crossing"] == 0


def test_ssvi_recovers_truth_and_fits(results):
    res, _ = results
    p = res["ssvi"]
    assert p.rho == pytest.approx(TRUE_SSVI["rho"], abs=0.01)
    assert p.gamma == pytest.approx(TRUE_SSVI["gamma"], abs=0.02)
    assert res["ssvi_meta"]["constraints"]["all_ok"]
    stats = res["fit_stats"].set_index(["expiry", "model"])
    assert stats.loc[("ALL", "ssvi"), "rmse_volpts"] < 0.05
    assert stats.loc[("ALL", "svi"), "rmse_volpts"] < 0.05


def test_essvi_is_admissible_and_at_least_as_good_as_ssvi(results):
    res, _ = results
    assert res["essvi_meta"]["constraints"]["all_ok"]
    assert res["summary"]["essvi_constraints_ok"]
    comp = res["comparison"].set_index("model")
    assert comp.loc["eSSVI", "butterfly_slices_arbitrage"] == 0
    assert comp.loc["eSSVI", "calendar_pairs_crossing"] == 0
    assert comp.loc["eSSVI", "rmse_volpts"] <= comp.loc["SSVI", "rmse_volpts"] + 1e-6


def test_default_results_root_from_subfolder(tmp_path, monkeypatch):
    from volsurf.pipeline import default_results_root

    (tmp_path / "results").mkdir()
    (tmp_path / "pyproject.toml").write_text("")
    sub = tmp_path / "notebooks"
    sub.mkdir()
    monkeypatch.chdir(sub)
    assert default_results_root() == tmp_path / "results"
