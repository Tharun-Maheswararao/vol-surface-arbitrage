"""End-to-end pipeline: raw snapshot -> clean quotes -> fits -> arbitrage -> saved results.

Everything the notebook and the Streamlit app show is read from the files this
module writes to ``results/<snapshot_id>/``; nothing downstream refits.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import arbitrage as arb
from .data import CleanConfig, clean_chain, dedupe_roots, load_snapshot
from .quotes import build_quotes
from .ssvi import SSVIParams, check_constraints, fit_ssvi, ssvi_d2w, ssvi_dw, ssvi_w, wing_slopes
from .svi import SVIParams, fit_svi, satisfies_constraints, svi_d2w, svi_dw, svi_w

K_GRID = np.linspace(-2.5, 1.0, 3501)
MODELS = ("svi", "ssvi", "ssvi_free")
MODEL_LABELS = {"svi": "SVI", "ssvi": "SSVI", "ssvi_free": "SSVI (unconstrained)"}


def _fit_stats(q: pd.DataFrame, w_model: np.ndarray) -> dict:
    T = q["T"].values
    iv_model = np.sqrt(np.maximum(w_model, 0) / T)
    err = (iv_model - q["iv_mid"].values) * 100  # vol points
    inside = (iv_model >= q["iv_bid"].values) & (iv_model <= q["iv_ask"].values)
    return {"n": int(len(q)), "rmse_volpts": float(np.sqrt(np.mean(err**2))),
            "mae_volpts": float(np.mean(np.abs(err))), "max_abs_volpts": float(np.max(np.abs(err))),
            "pct_inside_bid_ask": float(100 * inside.mean())}


def run_pipeline(snapshot_dir: str | Path, results_root: str | Path = "results",
                 clean_cfg: CleanConfig = CleanConfig()) -> Path:
    snapshot_dir = Path(snapshot_dir)
    chain, meta = load_snapshot(snapshot_dir)
    out = Path(results_root) / meta["snapshot_id"]
    out.mkdir(parents=True, exist_ok=True)

    # 1-2. de-duplicate the SPX/SPXW series on monthly dates, then clean
    chain = dedupe_roots(chain)
    clean, drop_counts = clean_chain(chain, meta["spot"], clean_cfg)

    # 3-5. forwards, OTM selection, implied vols
    quotes, forwards = build_quotes(clean, meta)
    clean = clean[clean["expiry"].isin(forwards["expiry"])]

    # 6. raw quote arbitrage: OTM set (primary) and full clean chain (diagnostic)
    raw = arb.raw_arbitrage(quotes)
    raw_summary = arb.summarize_raw(raw)
    raw_full = arb.raw_arbitrage_full_chain(clean, forwards)
    raw_full_summary = arb.summarize_raw(raw_full)

    expiries = list(forwards.sort_values("T")["expiry"])
    T_of = forwards.set_index("expiry")["T"].to_dict()

    # 7. SVI per expiry, weighted by inverse bid-ask spread in total variance
    svi_rows, svi_params = [], {}
    for e in expiries:
        q = quotes[quotes["expiry"] == e]
        p, info = fit_svi(q["k"].values, q["w_mid"].values, weights=1.0 / q["spread_w"].values)
        svi_params[e] = p
        svi_rows.append({"expiry": e, "T": T_of[e], **p.to_dict(), "objective": info["objective"],
                         "constraints_ok": satisfies_constraints(p), "min_variance": p.min_variance(),
                         "left_wing_slope": p.wing_slopes()[0], "right_wing_slope": p.wing_slopes()[1]})

    # 8. SSVI on the whole surface, with the no-arbitrage constraints and (diagnostic) without
    slices = [{"expiry": e, "T": T_of[e], "k": quotes.loc[quotes.expiry == e, "k"].values,
               "w": quotes.loc[quotes.expiry == e, "w_mid"].values,
               "weights": 1.0 / quotes.loc[quotes.expiry == e, "spread_w"].values} for e in expiries]
    ssvi_p, ssvi_info = fit_ssvi(slices)
    ssvi_cons = check_constraints(ssvi_p)
    free_p, free_info = fit_ssvi(slices, constrained=False)
    free_cons = check_constraints(free_p)

    def slice_fn(model, e):
        """(w, w', w'') callables of k for one model and expiry."""
        if model == "svi":
            p = svi_params[e]
            return (lambda k: svi_w(k, p)), (lambda k: svi_dw(k, p)), (lambda k: svi_d2w(k, p))
        sp = ssvi_p if model == "ssvi" else free_p
        a = (sp.thetas[expiries.index(e)], sp.rho, sp.eta, sp.gamma)
        return (lambda k: ssvi_w(k, *a)), (lambda k: ssvi_dw(k, *a)), (lambda k: ssvi_d2w(k, *a))

    def right_slope(model, e):
        if model == "svi":
            return svi_params[e].wing_slopes()[1]
        sp = ssvi_p if model == "ssvi" else free_p
        return wing_slopes(sp.thetas[expiries.index(e)], sp.rho, sp.eta, sp.gamma)[1]

    # model values at quotes + fit statistics
    stats = []
    for model in MODELS:
        quotes[f"w_{model}"] = np.nan
    for e in expiries:
        m = quotes["expiry"] == e
        q = quotes[m]
        for model in MODELS:
            quotes.loc[m, f"w_{model}"] = slice_fn(model, e)[0](q["k"].values)
            stats.append({"expiry": e, "T": T_of[e], "model": model,
                          **_fit_stats(q, quotes.loc[m, f"w_{model}"].values)})
    for model in MODELS:
        stats.append({"expiry": "ALL", "T": np.nan, "model": model,
                      **_fit_stats(quotes, quotes[f"w_{model}"].values)})
        quotes[f"iv_{model}"] = np.sqrt(quotes[f"w_{model}"] / quotes["T"])
    fit_stats = pd.DataFrame(stats)

    # 9. fitted arbitrage: butterfly via g(k), calendar via slice crossing
    curves = []
    fitted = {m: {"butterfly": {}, "calendar": {}} for m in MODELS}
    kr = {e: (quotes.loc[quotes.expiry == e, "k"].min(), quotes.loc[quotes.expiry == e, "k"].max())
          for e in expiries}
    for e in expiries:
        rec = {"expiry": e, "T": T_of[e], "k": K_GRID}
        for model in MODELS:
            fw, fdw, fd2w = slice_fn(model, e)
            w, dw, d2w = fw(K_GRID), fdw(K_GRID), fd2w(K_GRID)
            g = arb.g_function(K_GRID, w, dw, d2w)
            rec[f"w_{model}"] = w
            rec[f"g_{model}"] = g
            rec[f"density_{model}"] = arb.implied_density(K_GRID, w, dw, d2w)
            fitted[model]["butterfly"][e] = arb.butterfly_report(
                K_GRID, g, k_data=np.array(kr[e]), right_slope=right_slope(model, e))
        curves.append(pd.DataFrame(rec))
    curves = pd.concat(curves, ignore_index=True)

    for e1, e2 in zip(expiries[:-1], expiries[1:]):
        lo, hi = max(kr[e1][0], kr[e2][0]), min(kr[e1][1], kr[e2][1])
        for model in MODELS:
            w1 = curves.loc[curves.expiry == e1, f"w_{model}"].values
            w2 = curves.loc[curves.expiry == e2, f"w_{model}"].values
            fitted[model]["calendar"][f"{e1}->{e2}"] = arb.calendar_report(
                K_GRID, w1, w2, k_data=np.array([lo, hi]))

    comparison = []
    for model in MODELS:
        allrow = fit_stats[(fit_stats.model == model) & (fit_stats.expiry == "ALL")].iloc[0]
        bf = fitted[model]["butterfly"].values()
        cal = fitted[model]["calendar"].values()
        comparison.append({
            "model": MODEL_LABELS[model],
            "rmse_volpts": allrow["rmse_volpts"], "mae_volpts": allrow["mae_volpts"],
            "pct_inside_bid_ask": allrow["pct_inside_bid_ask"],
            "butterfly_slices_negative_g": sum(r["negative"] for r in bf),
            "butterfly_slices_negative_g_in_data": sum(r["negative_in_data_range"] for r in bf),
            "butterfly_slices_wing_over_lee": sum(not r["wing_ok"] for r in bf),
            "butterfly_slices_arbitrage": sum(r["arbitrage"] for r in bf),
            "calendar_pairs_crossing": sum(r["crossing"] for r in cal),
            "calendar_pairs_crossing_in_data": sum(r["crossing_in_data_range"] for r in cal),
            "n_params": 5 * len(expiries) if model == "svi" else 3 + len(expiries),
        })
    comparison = pd.DataFrame(comparison)

    # ---------------------------------------------------------------- save
    quotes.to_parquet(out / "quotes.parquet", index=False)
    clean.to_parquet(out / "clean_chain.parquet", index=False)
    forwards.to_csv(out / "forwards.csv", index=False)
    raw.to_csv(out / "raw_violations.csv", index=False)
    raw_summary.to_csv(out / "raw_summary.csv", index=False)
    raw_full.to_csv(out / "raw_violations_full_chain.csv", index=False)
    raw_full_summary.to_csv(out / "raw_summary_full_chain.csv", index=False)
    pd.DataFrame(svi_rows).to_csv(out / "svi_params.csv", index=False)
    (out / "ssvi_params.json").write_text(json.dumps(
        {**ssvi_p.to_dict(), "fit": ssvi_info, "constraints": ssvi_cons}, indent=2))
    (out / "ssvi_unconstrained_params.json").write_text(json.dumps(
        {**free_p.to_dict(), "fit": free_info, "constraints": free_cons}, indent=2))
    fit_stats.to_csv(out / "fit_stats.csv", index=False)
    curves.to_parquet(out / "curves.parquet", index=False)
    (out / "fitted_arbitrage.json").write_text(json.dumps(fitted, indent=2))
    comparison.to_csv(out / "comparison.csv", index=False)
    summary = {
        "snapshot_id": meta["snapshot_id"], "ticker": meta["ticker"], "source": meta["source"],
        "fetch_time_utc": meta["fetch_time_utc"], "quote_time_utc": meta["quote_time_utc"],
        "quote_delay_note": meta["quote_delay_note"], "spot": meta["spot"],
        "n_expiries": len(expiries), "expiries": expiries, "n_quotes": int(len(quotes)),
        "clean_drop_counts": drop_counts,
        "raw_mid_violations": int(len(raw)),
        "raw_survive_bid_ask": int(raw["survives_bid_ask"].sum()) if len(raw) else 0,
        "raw_full_chain_mid_violations": int(len(raw_full)),
        "raw_full_chain_survive_bid_ask": int(raw_full["survives_bid_ask"].sum()) if len(raw_full) else 0,
        "ssvi_constraints_ok": ssvi_cons["all_ok"],
        "ssvi_unconstrained_constraints_ok": free_cons["all_ok"],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return out


# ----------------------------------------------------------------------------- loading


def load_results(path: str | Path) -> dict:
    """Load everything the pipeline wrote for one snapshot."""
    path = Path(path)
    ssvi = json.loads((path / "ssvi_params.json").read_text())
    svi_df = pd.read_csv(path / "svi_params.csv")
    return {
        "summary": json.loads((path / "summary.json").read_text()),
        "quotes": pd.read_parquet(path / "quotes.parquet"),
        "forwards": pd.read_csv(path / "forwards.csv"),
        "raw_violations": pd.read_csv(path / "raw_violations.csv"),
        "raw_summary": pd.read_csv(path / "raw_summary.csv"),
        "raw_violations_full_chain": pd.read_csv(path / "raw_violations_full_chain.csv"),
        "raw_summary_full_chain": pd.read_csv(path / "raw_summary_full_chain.csv"),
        "svi_params": svi_df,
        "svi": {r.expiry: SVIParams(r.a, r.b, r.rho, r.m, r.sigma) for r in svi_df.itertuples()},
        "ssvi": SSVIParams.from_dict(ssvi),
        "ssvi_meta": ssvi,
        "ssvi_free": SSVIParams.from_dict(json.loads((path / "ssvi_unconstrained_params.json").read_text())),
        "fit_stats": pd.read_csv(path / "fit_stats.csv"),
        "curves": pd.read_parquet(path / "curves.parquet"),
        "fitted_arbitrage": json.loads((path / "fitted_arbitrage.json").read_text()),
        "comparison": pd.read_csv(path / "comparison.csv"),
    }


def list_results(root: str | Path = "results") -> list[Path]:
    root = Path(root)
    return sorted(p for p in root.iterdir() if (p / "summary.json").exists()) if root.exists() else []
