"""Static arbitrage checks on raw quotes and on fitted smiles.

Raw checks are model free. Each one is evaluated twice:

* on mid prices, which flags anything that *looks* like an arbitrage, and
* on executable prices (buy at the ask, sell at the bid). A violation that
  disappears here is quote noise, not money.

An executable violation always implies a mid violation, since bid <= mid <= ask.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .pricing import normalized_call

TOL = 1e-9
CONTRACT_MULTIPLIER = 100


def _row(expiry, check, kind, strikes, mid_value, exec_profit, note=""):
    return {
        "expiry": expiry, "check": check, "type": kind,
        "strikes": "/".join(f"{s:g}" for s in strikes),
        "mid_violation": mid_value,       # size of the violation on mid prices (>0 means violated)
        "exec_profit": exec_profit,       # locked-in profit per unit at bid/ask (>0 means tradable)
        "survives_bid_ask": bool(exec_profit > TOL),
        "profit_usd_per_contract": max(exec_profit, 0.0) * CONTRACT_MULTIPLIER,
        "note": note,
    }


def strike_checks(K, bid, ask, D, kind="call", expiry=""):
    """Vertical spread, slope bound and butterfly checks on one expiry's quotes
    of one option type. Strikes need not be evenly spaced."""
    order = np.argsort(K)
    K, bid, ask = (np.asarray(x, float)[order] for x in (K, bid, ask))
    mid = 0.5 * (bid + ask)
    rows = []

    for i in range(len(K) - 1):
        lo, hi = i, i + 1
        dK = K[hi] - K[lo]
        if kind == "call":
            # Vertical: C(K_lo) >= C(K_hi). Trade: buy K_lo at ask, sell K_hi at bid.
            mid_v = mid[hi] - mid[lo]
            exe = bid[hi] - ask[lo]
            # Slope: C(K_lo) - C(K_hi) <= D dK. Trade: sell K_lo at bid, buy K_hi at ask.
            mid_s = (mid[lo] - mid[hi]) - D * dK
            exe_s = bid[lo] - ask[hi] - D * dK
        else:
            # Vertical: P(K_hi) >= P(K_lo). Trade: buy K_hi at ask, sell K_lo at bid.
            mid_v = mid[lo] - mid[hi]
            exe = bid[lo] - ask[hi]
            # Slope: P(K_hi) - P(K_lo) <= D dK. Trade: sell K_hi at bid, buy K_lo at ask.
            mid_s = (mid[hi] - mid[lo]) - D * dK
            exe_s = bid[hi] - ask[lo] - D * dK
        if mid_v > TOL:
            rows.append(_row(expiry, "vertical", kind, (K[lo], K[hi]), mid_v, exe))
        if mid_s > TOL:
            rows.append(_row(expiry, "slope_bound", kind, (K[lo], K[hi]), mid_s, exe_s))

    for i in range(1, len(K) - 1):
        k1, k2, k3 = K[i - 1], K[i], K[i + 1]
        w1 = (k3 - k2) / (k3 - k1)
        w3 = (k2 - k1) / (k3 - k1)
        # Convexity: w1 C1 + w3 C3 - C2 >= 0. Trade: buy wings at ask, sell middle at bid.
        mid_b = -(w1 * mid[i - 1] + w3 * mid[i + 1] - mid[i])
        exe_b = bid[i] - (w1 * ask[i - 1] + w3 * ask[i + 1])
        if mid_b > TOL:
            rows.append(_row(expiry, "butterfly", kind, (k1, k2, k3), mid_b, exe_b))
    return rows


def calendar_checks(quotes: pd.DataFrame, max_gap: float = 0.05):
    """Total variance must not fall with expiry at fixed log-moneyness k.

    For each pair of adjacent expiries T1 < T2 and each quote of T1 at k, the
    T2 total variances (bid, mid, ask separately) are linearly interpolated at k
    from the two neighbouring T2 quotes, provided they are within ``max_gap`` in k.
    Mid violation: w2_mid < w1_mid. Executable: w2_ask < w1_bid, i.e. the longer
    option bought at its ask is still cheaper in variance than the shorter option
    sold at its bid. At fixed k the normalised price c(k, w) is increasing in w,
    so this is equivalent to comparing normalised prices; the profit is reported
    in normalised-price units times the T1 forward and discount factor.
    """
    rows = []
    exps = quotes.groupby("expiry")["T"].first().sort_values()
    names = list(exps.index)
    for e1, e2 in zip(names[:-1], names[1:]):
        q1 = quotes[quotes["expiry"] == e1]
        q2 = quotes[quotes["expiry"] == e2].sort_values("k")
        k2 = q2["k"].values
        for _, r in q1.iterrows():
            k = r["k"]
            j = np.searchsorted(k2, k)
            if j == 0 or j >= len(k2):
                continue
            if k2[j] - k2[j - 1] > max_gap:
                continue
            t = (k - k2[j - 1]) / (k2[j] - k2[j - 1])
            interp = {s: (1 - t) * q2[f"w_{s}"].values[j - 1] + t * q2[f"w_{s}"].values[j]
                      for s in ("bid", "mid", "ask")}
            mid_v = r["w_mid"] - interp["mid"]
            if mid_v <= TOL:
                continue
            c_sell = normalized_call(k, r["w_bid"])     # sell short-dated at bid
            c_buy = normalized_call(k, interp["ask"])   # buy long-dated at ask
            exe = (c_sell - c_buy) * r["F"] * r["D"]
            rows.append(_row(e1, "calendar", r["type"], (r["strike"],), mid_v, float(exe),
                             note=f"vs {e2} at k={k:.4f}"))
    return rows


VIOLATION_COLUMNS = ["expiry", "check", "type", "strikes", "mid_violation", "exec_profit",
                     "survives_bid_ask", "profit_usd_per_contract", "note"]


def otm_call_curve(q: pd.DataFrame) -> pd.DataFrame:
    """One expiry's OTM quotes expressed as call prices. Puts are converted by
    put-call parity, C = P + D (F - K), applied to bid and ask alike. The shift is
    linear in K, so butterflies are unaffected, call verticals on converted puts
    are exactly put slope-bound checks and vice versa; only the pair and triple
    straddling F depend on the estimated forward."""
    shift = np.where(q["type"] == "put", q["D"] * (q["F"] - q["strike"]), 0.0)
    return pd.DataFrame({"strike": q["strike"].values, "bid": q["bid"].values + shift,
                         "ask": q["ask"].values + shift}).sort_values("strike")


def raw_arbitrage(quotes: pd.DataFrame) -> pd.DataFrame:
    """Raw checks on the OTM quote set used for fitting: strike checks on the OTM
    call curve of each expiry, and calendar checks across expiries."""
    rows = []
    for e, q in quotes.groupby("expiry"):
        c = otm_call_curve(q)
        rows += strike_checks(c["strike"].values, c["bid"].values, c["ask"].values,
                              float(q["D"].iloc[0]), kind="call", expiry=e)
    for r in rows:
        r["type"] = "otm"
    rows += calendar_checks(quotes)
    out = pd.DataFrame(rows, columns=VIOLATION_COLUMNS)
    if "openInterest" in quotes.columns and len(out):
        oi = {(e, s): v for e, s, v in zip(quotes["expiry"], quotes["strike"], quotes["openInterest"])}
        out["min_open_interest"] = [
            min(oi.get((e, float(k)), np.nan) for k in ks.split("/"))
            for e, ks in zip(out["expiry"], out["strikes"])
        ]
    return out


def raw_arbitrage_full_chain(clean_chain: pd.DataFrame, forwards: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic: the same strike checks on every clean quote of each type,
    in-the-money strikes included."""
    D_of = forwards.set_index("expiry")["D"].to_dict()
    rows = []
    for (e, kind), g in clean_chain.groupby(["expiry", "type"]):
        if e in D_of:
            rows += strike_checks(g["strike"].values, g["bid"].values, g["ask"].values,
                                  D_of[e], kind=kind, expiry=e)
    return pd.DataFrame(rows, columns=VIOLATION_COLUMNS)


def summarize_raw(viol: pd.DataFrame) -> pd.DataFrame:
    if viol.empty:
        return pd.DataFrame(columns=["check", "mid_violations", "survive_bid_ask", "max_profit_usd"])
    g = viol.groupby("check")
    out = pd.DataFrame({
        "mid_violations": g.size(),
        "survive_bid_ask": g["survives_bid_ask"].sum().astype(int),
        "max_profit_usd": g["profit_usd_per_contract"].max(),
    }).reset_index()
    total = pd.DataFrame([{"check": "total", "mid_violations": int(out["mid_violations"].sum()),
                           "survive_bid_ask": int(out["survive_bid_ask"].sum()),
                           "max_profit_usd": float(out["max_profit_usd"].max())}])
    return pd.concat([out, total], ignore_index=True)


# ----------------------------------------------------------------------------- fitted checks


def g_function(k, w, dw, d2w):
    """Gatheral's density factor. g < 0 means a negative implied density (butterfly arbitrage)."""
    k, w, dw, d2w = (np.asarray(x, float) for x in (k, w, dw, d2w))
    return (1 - k * dw / (2 * w)) ** 2 - dw**2 / 4 * (1 / w + 0.25) + d2w / 2


def implied_density(k, w, dw, d2w):
    """Risk-neutral density of log(S_T / F) at k implied by a smooth slice:
    p(k) = g(k) / sqrt(2 pi w) * exp(-d2^2 / 2),  d2 = -k/sqrt(w) - sqrt(w)/2."""
    k, w = np.asarray(k, float), np.asarray(w, float)
    g = g_function(k, w, dw, d2w)
    d2 = -k / np.sqrt(w) - np.sqrt(w) / 2
    return g / np.sqrt(2 * np.pi * w) * np.exp(-0.5 * d2**2)


def _intervals(k, mask):
    """Contiguous k-intervals where mask is True."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = k[i]
        if not m and start is not None:
            out.append((float(start), float(k[i - 1])))
            start = None
    if start is not None:
        out.append((float(start), float(k[-1])))
    return out


def butterfly_report(k, g, k_data=None):
    neg = g < -TOL
    rep = {"min_g": float(np.min(g)), "k_at_min_g": float(k[np.argmin(g)]),
           "negative": bool(neg.any()), "negative_intervals": _intervals(k, neg)}
    if k_data is not None:
        inside = (k >= np.min(k_data)) & (k <= np.max(k_data))
        rep["min_g_in_data_range"] = float(np.min(g[inside])) if inside.any() else np.nan
        rep["negative_in_data_range"] = bool((neg & inside).any())
    return rep


def calendar_report(k, w_short, w_long, k_data=None):
    diff = np.asarray(w_long) - np.asarray(w_short)
    neg = diff < -TOL
    rep = {"min_diff": float(np.min(diff)), "k_at_min_diff": float(k[np.argmin(diff)]),
           "crossing": bool(neg.any()), "crossing_intervals": _intervals(k, neg)}
    if k_data is not None:
        inside = (k >= np.min(k_data)) & (k <= np.max(k_data))
        rep["crossing_in_data_range"] = bool((neg & inside).any())
    return rep
