from datetime import date, datetime, timezone

import pandas as pd
import pytest

from volsurf.data import (
    clean_chain,
    dedupe_roots,
    estimate_quote_time,
    expiry_datetime,
    is_standard_monthly,
    save_snapshot,
    select_expiries,
)
from volsurf.synthetic import synthetic_snapshot


def test_quote_time_weekend_is_friday_close():
    sat = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)
    assert estimate_quote_time(sat) == datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)


def test_quote_time_intraday_subtracts_delay():
    wed = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)  # 11:00 ET
    assert estimate_quote_time(wed) == datetime(2026, 10, 14, 14, 45, tzinfo=timezone.utc)


def test_settlement_times():
    assert expiry_datetime("2026-12-18", "SPX").hour == 14    # 09:30 ET = 14:30 UTC in December
    assert expiry_datetime("2026-12-18", "SPXW").hour == 21   # 16:00 ET = 21:00 UTC


def test_monthly_detection_and_thursday_holiday_rule():
    assert is_standard_monthly(date(2026, 11, 20))
    listed = {date(2026, 11, 19), date(2026, 11, 20), date(2027, 6, 17)}
    assert not is_standard_monthly(date(2026, 11, 19), listed)   # Friday is listed
    assert is_standard_monthly(date(2027, 6, 17), listed)        # Juneteenth Friday


def test_select_expiries_prefers_monthlies():
    avail = ["2026-10-30", "2026-11-19", "2026-11-20", "2026-11-27", "2026-12-18", "2027-01-15"]
    got = select_expiries(avail, date(2026, 10, 16), target_days=(14, 30, 60, 90))
    assert got == ["2026-10-30", "2026-11-20", "2026-12-18", "2027-01-15"]


def test_clean_chain_reasons_add_up():
    df = pd.DataFrame({
        "type": ["call", "call", "call", "put", "call"],
        "strike": [100.0, 105.0, 110.0, 130.0, 80.0],
        "bid": [0.0, 2.0, 1.0, 30.0, 21.0],
        "ask": [0.1, 1.5, 3.0, 30.5, 21.5],
    })
    out, counts = clean_chain(df, spot=100.0)
    assert counts == {"input_rows": 5, "zero_bid": 1, "crossed_or_locked": 1, "wide_spread": 1,
                      "deep_itm": 2, "kept": 0}
    assert out.empty


def test_dedupe_keeps_one_series_per_expiry():
    df = pd.DataFrame({
        "expiry": ["2026-11-20"] * 3,
        "contractSymbol": ["SPX261120C05000000", "SPX261120C05100000", "SPXW261120C05000000"],
        "bid": [1.0, 1.0, 1.0],
    })
    assert set(dedupe_roots(df)["root"]) == {"SPX"}


def test_snapshots_are_never_overwritten(tmp_path):
    chain, meta = synthetic_snapshot()
    save_snapshot(chain, meta, tmp_path)
    with pytest.raises(FileExistsError):
        save_snapshot(chain, meta, tmp_path)
