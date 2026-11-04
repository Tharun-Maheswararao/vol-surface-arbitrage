"""Command line entry point.

    python -m volsurf collect            # save a new raw snapshot
    python -m volsurf run [SNAPSHOT]     # run the pipeline (default: latest snapshot)
    python -m volsurf figures [RESULT]   # write report figures (default: the report's baseline)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .data import CleanConfig, collect_snapshot, list_snapshots
from .pipeline import BASELINE_SNAPSHOT, run_pipeline
from .quotes import ForwardConfig


def main(argv=None):
    ap = argparse.ArgumentParser(prog="volsurf")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="download and save a raw option chain snapshot")
    c.add_argument("--ticker", default="^SPX")
    c.add_argument("--raw-root", default="data/raw")
    r = sub.add_parser("run", help="run the full pipeline on a snapshot")
    r.add_argument("snapshot", nargs="?")
    r.add_argument("--raw-root", default="data/raw")
    r.add_argument("--results-root", default="results")
    r.add_argument("--min-open-interest", type=int, default=None,
                   help="drop quotes with less open interest (default: off)")
    r.add_argument("--fixed-d-max-t", type=float, default=0.08, metavar="T",
                   help="take D from the SPX rate curve for expiries shorter than T years "
                        "and fit only F (default: 0.08)")
    r.add_argument("--fixed-d-spxw", action=argparse.BooleanOptionalAction, default=True,
                   help="take D from the SPX rate curve for SPXW expiries (default: on)")
    r.add_argument("--parity-d", action="store_true",
                   help="take every D from its own parity regression (overrides the above)")
    f = sub.add_parser("figures", help="write static figures for a result")
    f.add_argument("result", nargs="?")
    f.add_argument("--results-root", default="results")
    a = ap.parse_args(argv)

    if a.cmd == "collect":
        print(collect_snapshot(a.ticker, a.raw_root))
    elif a.cmd == "run":
        snap = Path(a.snapshot) if a.snapshot else list_snapshots(a.raw_root)[-1]
        cfg = CleanConfig(min_open_interest=a.min_open_interest)
        fcfg = (ForwardConfig.parity_only() if a.parity_d else
                ForwardConfig(fixed_d_max_T=a.fixed_d_max_t, fixed_d_spxw=a.fixed_d_spxw))
        print(run_pipeline(snap, a.results_root, cfg, fcfg))
    elif a.cmd == "figures":
        os.environ.setdefault("MPLBACKEND", "Agg")
        from .plotting import save_all_figures
        res = Path(a.result) if a.result else Path(a.results_root) / BASELINE_SNAPSHOT
        for p in save_all_figures(res):
            print(p)


if __name__ == "__main__":
    main()
