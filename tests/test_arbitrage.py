import numpy as np
import pandas as pd
import pytest

from volsurf.arbitrage import (
    calendar_checks,
    calendar_report,
    classify_survivors,
    otm_call_curve,
    quote_tick,
    raw_arbitrage,
    strike_checks,
    summarize_raw,
    survivor_class_counts,
)
from volsurf.pricing import black_price

D = 0.99


def _clean_calls(K, spread=0.10):
    mid = black_price(100.0, K, 0.5, 0.2, D, True)
    return mid - spread / 2, mid + spread / 2


def _checks(rows):
    return sorted({(r["check"], r["survives_bid_ask"]) for r in rows})


def test_clean_set_passes():
    K = np.array([80, 85, 90, 95, 100, 102.5, 105, 110, 120.0])  # uneven spacing
    bid, ask = _clean_calls(K)
    assert strike_checks(K, bid, ask, D, "call") == []


def test_clean_puts_pass():
    K = np.array([80, 85, 90, 95, 100, 105, 110.0])
    mid = black_price(100.0, K, 0.5, 0.2, D, False)
    assert strike_checks(K, mid - 0.05, mid + 0.05, D, "put") == []


def test_vertical_spread_violation():
    K = np.array([90.0, 95.0, 100.0])
    bid = np.array([12.0, 13.0, 4.0])
    ask = np.array([12.2, 13.2, 4.2])  # 95 call bid 13.0 > 90 call ask 12.2
    rows = strike_checks(K, bid, ask, D, "call")
    vert = [r for r in rows if r["check"] == "vertical"]
    assert len(vert) == 1 and vert[0]["strikes"] == "90/95"
    assert vert[0]["survives_bid_ask"] and vert[0]["exec_profit"] == pytest.approx(0.8)


def test_slope_bound_violation():
    K = np.array([90.0, 95.0])
    bid = np.array([12.0, 6.0])
    ask = np.array([12.1, 6.1])  # spread worth up to 4.95, sells for 5.9
    rows = strike_checks(K, bid, ask, D, "call")
    assert len(rows) == 1 and rows[0]["check"] == "slope_bound"
    assert rows[0]["exec_profit"] == pytest.approx(12.0 - 6.1 - D * 5)


def test_uneven_butterfly_violation_uses_strike_weights():
    # Linear in strike -> zero butterfly. Lift the middle strike above the chord.
    K = np.array([90.0, 92.0, 100.0])
    chord = lambda k: 20.0 - 0.8 * (k - 90.0)  # noqa: E731
    mid = np.array([chord(90), chord(92) + 0.5, chord(100)])
    rows = strike_checks(K, mid - 0.05, mid + 0.05, D, "call")
    bf = [r for r in rows if r["check"] == "butterfly"]
    assert len(bf) == 1
    assert bf[0]["mid_violation"] == pytest.approx(0.5)
    assert bf[0]["exec_profit"] == pytest.approx(0.5 - 0.1)
    # naive 1/-2/+1 weights ignore the spacing and would call this set non-convex by 2.9
    assert 0.5 * (mid[0] + mid[2]) - mid[1] == pytest.approx(-2.9)


def test_mid_violation_that_does_not_survive_bid_ask():
    K = np.array([90.0, 95.0, 100.0])
    mid = np.array([10.0, 6.04, 2.0])  # mid butterfly -0.04 (violated), wide quotes
    rows = strike_checks(K, mid - 0.5, mid + 0.5, D, "call")
    assert _checks(rows) == [("butterfly", False)]


def _quotes_for_calendar(w1, w2, spread=1e-4):
    ks = np.linspace(-0.2, 0.2, 21)
    rows = []
    for e, T, w in (("A", 0.25, w1), ("B", 0.5, w2)):
        for k in ks:
            rows.append({"expiry": e, "T": T, "k": k, "strike": 100 * np.exp(k), "type": "call",
                         "w_bid": w - spread, "w_mid": w, "w_ask": w + spread, "F": 100.0, "D": 0.99})
    return pd.DataFrame(rows)


def test_calendar_violation_detected_and_survives():
    rows = calendar_checks(_quotes_for_calendar(0.010, 0.008))
    assert len(rows) > 0 and all(r["survives_bid_ask"] for r in rows)


def test_calendar_mid_only_violation_does_not_survive():
    rows = calendar_checks(_quotes_for_calendar(0.0100, 0.0099, spread=5e-4))
    assert len(rows) > 0 and not any(r["survives_bid_ask"] for r in rows)


def test_calendar_clean_passes():
    assert calendar_checks(_quotes_for_calendar(0.008, 0.012)) == []


def test_otm_call_curve_parity_conversion():
    F, Dq, T = 100.0, 0.98, 0.5
    K = np.array([90.0, 95.0, 105.0, 110.0])
    kind = np.array(["put", "put", "call", "call"])
    px = black_price(F, K, T, 0.2, Dq, kind == "call")
    q = pd.DataFrame({"strike": K, "type": kind, "bid": px, "ask": px, "F": F, "D": Dq})
    c = otm_call_curve(q)
    np.testing.assert_allclose(c["bid"].values, black_price(F, K, T, 0.2, Dq, True), atol=1e-10)


def test_fitted_calendar_report():
    k = np.linspace(-1, 1, 201)
    rep = calendar_report(k, 0.02 + 0.01 * k**2, 0.03 - 0.02 * k, k_data=np.array([-0.5, 0.2]))
    assert rep["crossing"] and not rep["crossing_in_data_range"]
    # w_long - w_short = 0.01 - 0.02k - 0.01k^2 turns negative at k = sqrt(2) - 1
    assert rep["crossing_intervals"][0][0] == pytest.approx(np.sqrt(2) - 1, abs=0.01)


def test_summary_counts():
    K = np.array([90.0, 95.0, 100.0])
    rows = strike_checks(K, np.array([12.0, 13.0, 4.0]), np.array([12.2, 13.2, 4.2]), D, "call")
    s = summarize_raw(pd.DataFrame(rows)).set_index("check")
    assert s.loc["total", "mid_violations"] == len(rows)
    assert s.loc["total", "survive_bid_ask"] == sum(r["survives_bid_ask"] for r in rows)


def test_butterfly_report_flags_wing_beyond_lee_bound():
    from volsurf.arbitrage import butterfly_report

    k = np.linspace(-1, 1, 11)
    g = np.ones_like(k)
    assert butterfly_report(k, g, right_slope=1.5)["arbitrage"] is False
    rep = butterfly_report(k, g, right_slope=2.0)
    assert rep["wing_ok"] is False and rep["arbitrage"] is True


def _viol(check, strikes, profit, expiry="E"):
    return {"expiry": expiry, "check": check, "strikes": strikes, "exec_profit": profit,
            "survives_bid_ask": profit > 0}


def _legs(mids, ois, expiry="E"):
    return pd.DataFrame({"expiry": expiry, "strike": [float(k) for k in mids],
                         "mid": list(mids.values()), "openInterest": ois})


def test_quote_tick_switches_at_three_dollars():
    np.testing.assert_allclose(quote_tick([0.5, 2.99, 3.0, 40.0]), [0.05, 0.05, 0.10, 0.10])


def test_classify_survivors():
    quotes = _legs({90: 1.0, 95: 2.0, 100: 4.0, 105: 2.5}, [10, 0, 50, 20])
    viol = pd.DataFrame([
        _viol("vertical", "90/95", 5.0),             # 95 has no open interest
        _viol("butterfly", "95/100/105", 5.0),       # zero OI wins over size
        _viol("vertical", "90/105", 0.10),           # 0.05 per leg, ticks 0.05: at the tick
        _viol("vertical", "90/105", 0.11),           # 0.055 per leg: above the tick
        _viol("butterfly", "90/100/105", 0.30),      # 0.10 per leg, coarsest tick 0.10
        _viol("butterfly", "90/100/105", 0.31),
        _viol("slope_bound", "90/100", -0.20),       # mid-only violation: not a survivor
        _viol("calendar", "105", 0.10),              # two legs, 0.05 each
    ])
    got = list(classify_survivors(viol, quotes))
    assert got == ["zero_oi", "zero_oi", "sub_tick", "candidate", "sub_tick", "candidate",
                   None, "sub_tick"]
    viol["survivor_class"] = got
    assert survivor_class_counts(viol) == {"zero_oi": 2, "sub_tick": 3, "candidate": 2}


def test_classify_survivors_without_open_interest_or_with_missing_oi():
    quotes = _legs({90: 1.0, 95: 2.0}, [np.nan, 5])
    viol = pd.DataFrame([_viol("vertical", "90/95", 1.0)])
    assert list(classify_survivors(viol, quotes)) == ["candidate"]  # NaN OI is not zero
    assert list(classify_survivors(viol, quotes.drop(columns="openInterest"))) == ["candidate"]


def test_raw_arbitrage_classifies_survivors_on_quoted_prices():
    # Calls 4.0 / 3.3 / 2.2: the 100 call sits 0.2 above the chord, 0.1 at bid/ask.
    # Profit per leg 0.1/3 is below the 0.10 tick of the $3-and-up legs -> sub_tick.
    q = pd.DataFrame({"expiry": "E", "type": "call", "strike": [95.0, 100.0, 105.0],
                      "bid": [3.95, 3.25, 2.15], "ask": [4.05, 3.35, 2.25], "F": 90.0, "D": 1.0,
                      "T": 0.1, "k": np.log(np.array([95.0, 100.0, 105.0]) / 90.0),
                      "openInterest": [100, 100, 100]})
    q["mid"] = 0.5 * (q["bid"] + q["ask"])
    v = raw_arbitrage(q)
    bf = v[v["check"] == "butterfly"].iloc[0]
    assert bf["exec_profit"] == pytest.approx(0.10) and bf["survivor_class"] == "sub_tick"
    q.loc[1, ["bid", "ask"]] = [3.85, 3.95]  # 0.70 at bid/ask: 0.23 per leg
    v = raw_arbitrage(q)
    assert v.loc[v["check"] == "butterfly", "survivor_class"].iloc[0] == "candidate"
    q.loc[2, "openInterest"] = 0
    v = raw_arbitrage(q)
    assert v.loc[v["check"] == "butterfly", "survivor_class"].iloc[0] == "zero_oi"
    assert v.loc[~v["survives_bid_ask"], "survivor_class"].isna().all()
