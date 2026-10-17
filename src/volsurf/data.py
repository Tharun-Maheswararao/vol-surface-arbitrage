"""Collecting, storing, loading and cleaning raw option chain snapshots.

Raw snapshots are written once to ``data/raw/<snapshot_id>/`` and never
overwritten: the snapshot id is the UTC fetch time, and the directory is
created with ``exist_ok=False``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
YEAR_SECONDS = 365.0 * 86400.0
QUOTE_DELAY_MIN = 15  # Yahoo option quotes are delayed roughly 15 minutes

# Target maturities in calendar days. Short targets may use weeklies; the rest
# prefer standard monthly (3rd Friday) expiries, which carry the deepest strike grid.
DEFAULT_TARGET_DAYS = (14, 30, 60, 90, 120, 150, 240, 330, 420, 600)

RAW_COLUMNS = [
    "contractSymbol", "lastTradeDate", "strike", "lastPrice", "bid", "ask",
    "volume", "openInterest", "impliedVolatility", "inTheMoney",
]


# ----------------------------------------------------------------------------- time


def estimate_quote_time(fetch_utc: datetime) -> datetime:
    """Best estimate of the market time the delayed quotes refer to.

    During regular hours it is the fetch time minus the feed delay; outside
    them it is the most recent 16:00 ET weekday close (exchange holidays are
    not modelled).
    """
    et = fetch_utc.astimezone(ET)
    open_t, close_t = time(9, 30), time(16, 0)
    if et.weekday() < 5 and open_t <= et.time() <= time(16, 15):
        q = et - timedelta(minutes=QUOTE_DELAY_MIN)
        return min(q, datetime.combine(et.date(), close_t, ET)).astimezone(timezone.utc)
    d = et.date()
    if et.weekday() < 5 and et.time() < open_t:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime.combine(d, close_t, ET).astimezone(timezone.utc)


def expiry_datetime(expiry: str | date, root: str) -> datetime:
    """Settlement time: SPX monthlies are AM-settled (open), SPXW are PM-settled."""
    d = pd.Timestamp(expiry).date()
    t = time(9, 30) if root == "SPX" else time(16, 0)
    return datetime.combine(d, t, ET).astimezone(timezone.utc)


def year_fraction(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / YEAR_SECONDS


def is_standard_monthly(d: date, listed: set[date] | None = None) -> bool:
    """Third Friday of the month, or the Thursday before it when that Friday is an
    exchange holiday (i.e. not itself listed)."""
    if d.weekday() == 4:
        return 15 <= d.day <= 21
    if d.weekday() == 3 and 14 <= d.day <= 20:
        return listed is None or (d + timedelta(days=1)) not in listed
    return False


def select_expiries(available: list[str], asof: date, target_days=DEFAULT_TARGET_DAYS,
                    min_days: int = 7) -> list[str]:
    dates = sorted(pd.Timestamp(e).date() for e in available)
    dates = [d for d in dates if (d - asof).days >= min_days]
    listed = set(dates)
    monthly = [d for d in dates if is_standard_monthly(d, listed)]
    chosen: list[date] = []
    for tgt in target_days:
        pool = dates if tgt <= 21 or not monthly else monthly
        pool = [d for d in pool if d not in chosen]
        if not pool:
            continue
        chosen.append(min(pool, key=lambda d: abs((d - asof).days - tgt)))
    return [d.isoformat() for d in sorted(set(chosen))]


# ----------------------------------------------------------------------------- collect


@dataclass
class SnapshotMeta:
    snapshot_id: str
    ticker: str
    source: str
    fetch_time_utc: str
    quote_time_utc: str
    quote_delay_note: str
    spot: float
    spot_time_utc: str
    expiries: list[str]
    available_expiries: list[str]
    yfinance_version: str


def collect_snapshot(ticker: str = "^SPX", out_root: str | Path = "data/raw",
                     target_days=DEFAULT_TARGET_DAYS, expiries: list[str] | None = None) -> Path:
    """Download calls and puts for the selected expiries and save them untouched."""
    import yfinance as yf

    fetch = datetime.now(timezone.utc).replace(microsecond=0)
    sid = fetch.strftime("%Y%m%dT%H%M%SZ")
    if (Path(out_root) / sid).exists():
        raise FileExistsError(f"snapshot {sid} already exists; raw data is never overwritten")

    tk = yf.Ticker(ticker)
    available = list(tk.options)
    qtime = estimate_quote_time(fetch)
    if expiries is None:
        expiries = select_expiries(available, qtime.astimezone(ET).date(), target_days)

    hist = tk.history(period="5d", interval="1d")
    spot = float(hist["Close"].iloc[-1])
    spot_time = hist.index[-1].to_pydatetime().astimezone(timezone.utc)
    try:
        intraday = tk.history(period="1d", interval="1m")
        if len(intraday):
            spot = float(intraday["Close"].iloc[-1])
            spot_time = intraday.index[-1].to_pydatetime().astimezone(timezone.utc)
    except Exception:  # intraday history is best-effort
        pass

    frames = []
    for e in expiries:
        ch = tk.option_chain(e)
        for kind, df in (("call", ch.calls), ("put", ch.puts)):
            df = df[[c for c in RAW_COLUMNS if c in df.columns]].copy()
            df.insert(0, "type", kind)
            df.insert(0, "expiry", e)
            frames.append(df)
    chain = pd.concat(frames, ignore_index=True)
    chain["lastTradeDate"] = pd.to_datetime(chain["lastTradeDate"], utc=True)

    meta = SnapshotMeta(
        snapshot_id=sid, ticker=ticker, source="Yahoo Finance via yfinance",
        fetch_time_utc=fetch.isoformat(), quote_time_utc=qtime.isoformat(),
        quote_delay_note=(f"Yahoo option quotes are delayed about {QUOTE_DELAY_MIN} minutes; "
                          "outside regular hours they are the last quotes of the prior session."),
        spot=spot, spot_time_utc=spot_time.isoformat(), expiries=list(expiries),
        available_expiries=available, yfinance_version=yf.__version__,
    )
    return save_snapshot(chain, asdict(meta), out_root)


def save_snapshot(chain: pd.DataFrame, meta: dict, out_root: str | Path = "data/raw") -> Path:
    """Write a raw snapshot to ``<out_root>/<snapshot_id>/``. Refuses to overwrite."""
    out = Path(out_root) / meta["snapshot_id"]
    out.mkdir(parents=True, exist_ok=False)  # never overwrite raw data
    chain.to_parquet(out / "chain.parquet", index=False)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return out


def list_snapshots(root: str | Path = "data/raw") -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if (p / "chain.parquet").exists())


def load_snapshot(path: str | Path) -> tuple[pd.DataFrame, dict]:
    path = Path(path)
    chain = pd.read_parquet(path / "chain.parquet")
    meta = json.loads((path / "meta.json").read_text())
    return chain, meta


# ----------------------------------------------------------------------------- clean


@dataclass
class CleanConfig:
    max_rel_spread: float = 0.5      # (ask - bid) / mid
    deep_itm_moneyness: float = 0.10  # drop options more than 10% in the money vs spot
    min_bid: float = 0.0             # strictly greater than this


def option_root(symbol: str) -> str:
    m = re.match(r"^([A-Z]+)", symbol)
    return m.group(1) if m else ""


def dedupe_roots(chain: pd.DataFrame) -> pd.DataFrame:
    """Monthly SPX dates list both the AM-settled SPX and PM-settled SPXW series.
    Keep one series per expiry: the one with more quoted strikes (SPX on ties)."""
    chain = chain.copy()
    chain["root"] = chain["contractSymbol"].map(option_root)
    keep = []
    for _, g in chain.groupby("expiry"):
        counts = g[g["bid"] > 0].groupby("root").size()
        if counts.empty:
            counts = g.groupby("root").size()
        best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0] != "SPX"))[0][0]
        keep.append(g[g["root"] == best])
    return pd.concat(keep, ignore_index=True)


def clean_chain(chain: pd.DataFrame, spot: float, cfg: CleanConfig = CleanConfig()):
    """Return (clean chain, drop-reason counts). Each row is dropped for the first
    reason that applies, so the counts add up."""
    df = chain.copy()
    df["mid"] = 0.5 * (df["bid"] + df["ask"])
    reasons = pd.Series("", index=df.index, dtype=object)

    bad_bid = ~(df["bid"] > cfg.min_bid) | df["bid"].isna()
    reasons[bad_bid] = "zero_bid"
    crossed = (reasons == "") & ~(df["ask"] > df["bid"])
    reasons[crossed] = "crossed_or_locked"
    rel = (df["ask"] - df["bid"]) / df["mid"]
    wide = (reasons == "") & (rel > cfg.max_rel_spread)
    reasons[wide] = "wide_spread"
    itm = np.where(df["type"] == "call", spot / df["strike"] - 1.0, df["strike"] / spot - 1.0)
    deep = (reasons == "") & (itm > cfg.deep_itm_moneyness)
    reasons[deep] = "deep_itm"

    counts = {"input_rows": int(len(df))}
    for r in ("zero_bid", "crossed_or_locked", "wide_spread", "deep_itm"):
        counts[r] = int((reasons == r).sum())
    out = df[reasons == ""].reset_index(drop=True)
    counts["kept"] = int(len(out))
    return out, counts
