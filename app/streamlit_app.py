"""Thin viewer over saved pipeline results. No fitting happens here.

    streamlit run app/streamlit_app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from volsurf.pipeline import BASELINE_SNAPSHOT, list_results, load_results
from volsurf.plotting import LABELS, plotly_g, plotly_smile, plotly_surface

ROOT = Path(__file__).resolve().parents[1] / "results"

st.set_page_config(page_title="SPX vol surface", layout="wide")
st.title("SPX implied volatility surface and arbitrage")

runs = list_results(ROOT)
if not runs:
    st.error("No results found. Run `python -m volsurf collect` then `python -m volsurf run`.")
    st.stop()


@st.cache_data(show_spinner=False)
def _load(path: str):
    return load_results(path)


with st.sidebar:
    names = [p.name for p in runs][::-1]
    snap = st.selectbox("Snapshot", names,
                        index=names.index(BASELINE_SNAPSHOT) if BASELINE_SNAPSHOT in names else 0)
    res = _load(str(ROOT / snap))
    s = res["summary"]
    expiries = list(res["forwards"].sort_values("T")["expiry"])
    expiry = st.selectbox("Expiry", expiries)
    has_essvi = res["essvi"] is not None  # results written before eSSVI was added have none
    fits = ["All", "SVI", "SSVI"] + (["eSSVI"] if has_essvi else [])
    fit = st.radio("Fit", fits, horizontal=True)
    show_free = st.checkbox("Also show unconstrained SSVI", value=False)
    st.caption(f"Quotes as of {s['quote_time_utc']} (fetched {s['fetch_time_utc']}). "
               f"{s['quote_delay_note']}")

models = {"All": ["svi", "ssvi"] + (["essvi"] if has_essvi else []),
          "SVI": ["svi"], "SSVI": ["ssvi"], "eSSVI": ["essvi"]}[fit]
if show_free:
    models = models + ["ssvi_free"]

comp = res["comparison"].set_index("model")
rmse_models = ["SVI", "SSVI"] + (["eSSVI"] if has_essvi else [])
cols = st.columns(len(rmse_models) + 2)
cols[0].metric("Expiries / quotes", f"{s['n_expiries']} / {s['n_quotes']}")
for c, m in zip(cols[1:], rmse_models):
    c.metric(f"{m} RMSE (vol pts)", f"{comp.loc[m, 'rmse_volpts']:.2f}")
cols[-1].metric("Raw violations: mid → bid/ask", f"{s['raw_mid_violations']} → {s['raw_survive_bid_ask']}")

tab_smile, tab_surface, tab_arb, tab_cmp = st.tabs(["Smile", "Surface", "Arbitrage", "Model comparison"])

with tab_smile:
    st.plotly_chart(plotly_smile(res, expiry, models), use_container_width=True)
    fs = res["fit_stats"]
    st.dataframe(fs[(fs.expiry == expiry) & fs.model.isin(models)].assign(
        model=lambda d: d.model.map(LABELS)).drop(columns=["expiry", "T"]), hide_index=True)

with tab_surface:
    st.plotly_chart(plotly_surface(res, models), use_container_width=True)
    st.caption("Drag to rotate. SSVI interpolates theta linearly in T; eSSVI interpolates theta, "
               "psi and rho*psi linearly in T; SVI interpolates total variance linearly in T at "
               "fixed k between fitted expiries.")

with tab_arb:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Raw quotes (OTM set)")
        st.dataframe(res["raw_summary"], hide_index=True)
        only = st.checkbox("Only violations that survive bid/ask", value=True)
        v = res["raw_violations"]
        v = v[v.survives_bid_ask] if only else v
        st.dataframe(v[v.expiry == expiry] if st.checkbox("This expiry only") else v, hide_index=True)
        with st.expander("Diagnostic: full clean chain including ITM strikes"):
            st.dataframe(res["raw_summary_full_chain"], hide_index=True)
    with right:
        st.subheader("Fitted surface")
        st.plotly_chart(plotly_g(res, expiry, models), use_container_width=True)
        rows = []
        for m in models:
            b = res["fitted_arbitrage"][m]["butterfly"][expiry]
            rows.append({"model": LABELS[m], "min g": b["min_g"], "min g in quoted range":
                         b["min_g_in_data_range"], "negative intervals": str(b["negative_intervals"])})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        cal = [{"pair": pair, "model": LABELS[m], "crossing": r["crossing"],
                "in quoted range": r["crossing_in_data_range"], "min w2 - w1": r["min_diff"]}
               for m in models for pair, r in res["fitted_arbitrage"][m]["calendar"].items()]
        st.dataframe(pd.DataFrame(cal), hide_index=True)

with tab_cmp:
    st.dataframe(res["comparison"], hide_index=True)
    st.caption("SSVI no-arbitrage conditions")
    st.json(res["ssvi_meta"]["constraints"])
    if has_essvi:
        st.caption("eSSVI no-arbitrage conditions")
        st.json(res["essvi_meta"]["constraints"])
