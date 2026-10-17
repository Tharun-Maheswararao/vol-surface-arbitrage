"""Synthetic option chains with a known, arbitrage-free surface. Used by the
tests and handy for checking the pipeline without network access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .data import ET, expiry_datetime, year_fraction
from .pricing import black_price
from .ssvi import ssvi_w

TRUE_SSVI = {"rho": -0.7, "eta": 1.0, "gamma": 0.4}


def synthetic_snapshot(spot=5000.0, r=0.045, q=0.013, n_expiries=6, seed=0,
                       snapshot_id="20250101T210000Z", rel_spread=0.04, noise=0.0):
    """Return (chain, meta) shaped like a saved yfinance snapshot.

    The true surface is SSVI with ``TRUE_SSVI`` and theta(T) = 0.04*T + 0.002,
    which satisfies the Gatheral-Jacquier conditions, so a correct pipeline finds
    no executable arbitrage.
    """
    rng = np.random.default_rng(seed)
    quote_time = datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc)
    days = [14, 35, 63, 91, 182, 365, 540, 730][:n_expiries]
    rows = []
    for dd in days:
        exp = (quote_time.astimezone(ET).date() + timedelta(days=dd)).isoformat()
        T = year_fraction(quote_time, expiry_datetime(exp, "SPX"))
        F, D = spot * np.exp((r - q) * T), np.exp(-r * T)
        theta = 0.04 * T + 0.002
        width = 4 * np.sqrt(theta)
        strikes = np.unique(np.round(F * np.exp(np.linspace(-width, 0.6 * width, 61)) / 5) * 5)
        k = np.log(strikes / F)
        w = ssvi_w(k, theta, **TRUE_SSVI)
        vol = np.sqrt(w / T) * (1 + noise * rng.standard_normal(len(k)))
        for kind in ("call", "put"):
            px = black_price(F, strikes, T, vol, D, kind == "call")
            half = np.maximum(0.5 * rel_spread * px, 0.05)
            bid, ask = np.maximum(px - half, 0.0), px + half
            for K, b, a, p in zip(strikes, bid, ask, px):
                rows.append({
                    "expiry": exp, "type": kind,
                    "contractSymbol": f"SPX{exp.replace('-', '')[2:]}{kind[0].upper()}{int(K * 1000):08d}",
                    "lastTradeDate": pd.Timestamp(quote_time), "strike": float(K),
                    "lastPrice": float(p), "bid": float(b), "ask": float(a), "volume": 10.0,
                    "openInterest": 100.0, "impliedVolatility": np.nan, "inTheMoney": False,
                })
    chain = pd.DataFrame(rows)
    meta = {
        "snapshot_id": snapshot_id, "ticker": "SYNTH", "source": "synthetic",
        "fetch_time_utc": quote_time.isoformat(), "quote_time_utc": quote_time.isoformat(),
        "quote_delay_note": "synthetic", "spot": spot, "spot_time_utc": quote_time.isoformat(),
        "expiries": sorted(chain["expiry"].unique().tolist()), "available_expiries": [],
        "yfinance_version": "", "true_r": r, "true_q": q,
    }
    return chain, meta
