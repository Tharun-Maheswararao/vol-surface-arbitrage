import numpy as np
import pandas as pd
import pytest

from volsurf.arbitrage import (
    calendar_checks,
    calendar_report,
    otm_call_curve,
    strike_checks,
    summarize_raw,
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
