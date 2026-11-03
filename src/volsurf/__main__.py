"""Command line entry point.

    python -m volsurf collect            # save a new raw snapshot
    python -m volsurf run [SNAPSHOT]     # run the pipeline (default: latest snapshot)
    python -m volsurf figures [RESULT]   # write report figures (default: latest result)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .data import CleanConfig, collect_snapshot, list_snapshots
from .pipeline import list_results, run_pipeline


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
    f = sub.add_parser("figures", help="write static figures for a result")
    f.add_argument("result", nargs="?")
    f.add_argument("--results-root", default="results")
    a = ap.parse_args(argv)

    if a.cmd == "collect":
        print(collect_snapshot(a.ticker, a.raw_root))
    elif a.cmd == "run":
        snap = Path(a.snapshot) if a.snapshot else list_snapshots(a.raw_root)[-1]
        cfg = CleanConfig(min_open_interest=a.min_open_interest)
        print(run_pipeline(snap, a.results_root, cfg))
    elif a.cmd == "figures":
        os.environ.setdefault("MPLBACKEND", "Agg")
        from .plotting import save_all_figures
        res = Path(a.result) if a.result else list_results(a.results_root)[-1]
        for p in save_all_figures(res):
            print(p)


if __name__ == "__main__":
    main()
