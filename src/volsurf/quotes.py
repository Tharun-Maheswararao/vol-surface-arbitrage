"""Turn a cleaned chain into per-expiry forwards and an out-of-the-money
implied volatility table with bid, mid and ask vols."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .data import expiry_datetime, year_fraction
from .forwards import discount_from_curve, fit_forward
from .pricing import implied_vol_vec


@dataclass(frozen=True)
class ForwardConfig:
    """Which expiries take D from the SPX rate curve instead of their own parity slope.

    A targeted expiry (T below ``fixed_d_max_T``, or any SPXW slice if
    ``fixed_d_spxw``) gets D log-linearly interpolated from the parity discount
    factors of the untargeted SPX expiries, with a flat rate outside them, and only
    F is fitted. The default targets expiries under 0.08 y and every SPXW slice, because
    parity does not identify the short-dated rate on this feed (docs/robustness.md,
    section 4). ``ForwardConfig.parity_only()`` takes every D from its own regression.
    """
    fixed_d_max_T: float | None = 0.08
    fixed_d_spxw: bool = True

    @classmethod
    def parity_only(cls) -> "ForwardConfig":
        return cls(fixed_d_max_T=None, fixed_d_spxw=False)

    def targets(self, root: str, T: float) -> bool:
        return ((self.fixed_d_max_T is not None and T < self.fixed_d_max_T)
                or (self.fixed_d_spxw and root == "SPXW"))


def parity_pairs(g: pd.DataFrame, spot: float, T: float) -> pd.DataFrame:
    """Strikes quoted on both sides, restricted to a band around spot where both
    legs are reasonably liquid. The band widens with maturity."""
    c = g[g["type"] == "call"].set_index("strike")
    p = g[g["type"] == "put"].set_index("strike")
    both = c.index.intersection(p.index)
    pairs = pd.DataFrame({
        "strike": both,
        "call_mid": c.loc[both, "mid"].values, "put_mid": p.loc[both, "mid"].values,
        "call_spread": (c.loc[both, "ask"] - c.loc[both, "bid"]).values,
        "put_spread": (p.loc[both, "ask"] - p.loc[both, "bid"]).values,
    })
    band = 0.05 + 0.10 * np.sqrt(T)
    near = np.abs(np.log(pairs["strike"] / spot)) <= band
    if near.sum() >= 5:
        pairs = pairs[near]
    return pairs.reset_index(drop=True)


def build_quotes(chain: pd.DataFrame, meta: dict,
                 fwd_cfg: ForwardConfig = ForwardConfig()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (quotes, forwards). ``chain`` must already be cleaned and de-duplicated."""
    asof = datetime.fromisoformat(meta["quote_time_utc"])
    spot = float(meta["spot"])
    slices = []
    for e, g in chain.groupby("expiry", sort=True):
        root = g["root"].iloc[0]
        T = year_fraction(asof, expiry_datetime(e, root))
        if T <= 0:
            continue
        pairs = parity_pairs(g, spot, T)
        if len(pairs) < 3:
            continue
        wts = 1.0 / (pairs["call_spread"] + pairs["put_spread"])
        slices.append((e, g, root, T, pairs, wts))

    def fit(pairs, wts, D=None):
        return fit_forward(pairs["strike"], pairs["call_mid"], pairs["put_mid"], weights=wts, D=D)

    # parity fits for the untargeted expiries; their SPX slices form the rate curve
    fits = {e: fit(pairs, wts) for e, _, root, T, pairs, wts in slices
            if not fwd_cfg.targets(root, T)}
    source = dict.fromkeys(fits, "parity")
    ref = [(T, fits[e].D) for e, _, root, T, _, _ in slices if e in fits and root == "SPX"]
    for e, _, _, T, pairs, wts in slices:
        if e in fits:
            continue
        if not ref:  # no SPX curve to borrow from
            fits[e], source[e] = fit(pairs, wts), "parity"
            continue
        T_ref, D_ref = zip(*ref)
        fits[e] = fit(pairs, wts, D=discount_from_curve(T, T_ref, D_ref))
        source[e] = "spx_interp" if min(T_ref) <= T <= max(T_ref) else "spx_extrap"

    q_frames, f_rows = [], []
    for e, g, root, T, _, _ in slices:
        fw = fits[e]
        F, D = fw.F, fw.D
        f_rows.append({
            "expiry": e, "root": root, "T": T, "F": F, "D": D, "rate": fw.rate(T),
            "carry": np.log(F / spot) / T, "n_pairs": fw.n_pairs, "n_used": fw.n_used,
            "resid_std": fw.resid_std, "spot": spot, "D_source": source[e],
        })

        otm = g[((g["type"] == "put") & (g["strike"] < F)) |
                ((g["type"] == "call") & (g["strike"] >= F))].copy()
        otm = otm.sort_values("strike").reset_index(drop=True)
        is_call = (otm["type"] == "call").values
        K = otm["strike"].values
        for side in ("bid", "mid", "ask"):
            otm[f"iv_{side}"] = implied_vol_vec(otm[side].values, F, K, T, D, is_call)
        otm["expiry"], otm["root"], otm["T"], otm["F"], otm["D"] = e, root, T, F, D
        otm["k"] = np.log(K / F)
        for side in ("bid", "mid", "ask"):
            otm[f"w_{side}"] = otm[f"iv_{side}"] ** 2 * T
        otm["spread_w"] = otm["w_ask"] - otm["w_bid"]
        q_frames.append(otm)

    quotes = pd.concat(q_frames, ignore_index=True)
    quotes = quotes.dropna(subset=["iv_bid", "iv_mid", "iv_ask"]).reset_index(drop=True)
    quotes = quotes[quotes["spread_w"] > 0].reset_index(drop=True)
    cols = ["expiry", "root", "T", "type", "strike", "bid", "ask", "mid", "F", "D", "k",
            "iv_bid", "iv_mid", "iv_ask", "w_bid", "w_mid", "w_ask", "spread_w",
            "volume", "openInterest", "contractSymbol"]
    return quotes[[c for c in cols if c in quotes.columns]], pd.DataFrame(f_rows)
