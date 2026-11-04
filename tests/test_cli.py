from pathlib import Path

import volsurf.__main__ as cli
import volsurf.plotting
from volsurf.pipeline import BASELINE_SNAPSHOT, default_results_root, list_results
from volsurf.quotes import ForwardConfig


def test_baseline_is_a_saved_result_but_not_the_newest():
    # Guards the reason the constant exists: later snapshots sort after the baseline.
    names = [p.name for p in list_results(default_results_root())]
    assert BASELINE_SNAPSHOT in names
    assert names[-1] != BASELINE_SNAPSHOT


def test_figures_defaults_to_baseline(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(volsurf.plotting, "save_all_figures", lambda res: seen.append(res) or [])
    cli.main(["figures", "--results-root", str(tmp_path)])
    assert seen == [tmp_path / BASELINE_SNAPSHOT]


def test_run_defaults_to_latest_snapshot(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "list_snapshots", lambda root: [Path("old"), Path("new")])
    monkeypatch.setattr(cli, "run_pipeline", lambda snap, root, *args: seen.append(snap) or snap)
    cli.main(["run", "--results-root", str(tmp_path)])
    assert seen == [Path("new")]


def test_run_passes_forward_config(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "run_pipeline", lambda snap, root, cfg, fcfg: seen.append(fcfg) or snap)
    cli.main(["run", "snap", "--results-root", str(tmp_path)])
    cli.main(["run", "snap", "--results-root", str(tmp_path), "--parity-d"])
    cli.main(["run", "snap", "--results-root", str(tmp_path), "--no-fixed-d-spxw"])
    assert seen == [ForwardConfig(fixed_d_max_T=0.08, fixed_d_spxw=True),
                    ForwardConfig.parity_only(),
                    ForwardConfig(fixed_d_max_T=0.08, fixed_d_spxw=False)]
