# volsurf: SPX implied volatility surface and arbitrage detection

![The Streamlit app: rotating the fitted surface and switching between SVI, SSVI, eSSVI, arbitrage-free SVI and all four](docs/app_demo.gif)

*Recorded from the running Streamlit app (`make app`) on the baseline snapshot: the surface
is rotated by dragging, then the Fit control switches between SVI, SSVI, eSSVI,
arbitrage-free SVI and all four together.*

This project builds an implied volatility surface from SPX option quotes and fits it
four ways. SVI fits one expiry at a time and SSVI the whole surface. Extended SSVI
(eSSVI) keeps SSVI's no-arbitrage guarantee but frees the skew per expiry. Arbitrage-free
SVI refits raw SVI slice by slice from an SSVI start, with penalties on calendar crossing
and negative density, following Gatheral and Jacquier (2014) §5.2
([docs/svi_arbfree.md](docs/svi_arbfree.md)). It then checks both the raw quotes and the fitted surfaces for static arbitrage. Every raw
violation is checked twice, on mid prices and on executable bid/ask prices.

**Headline.** The weekend column is the 2026-10-16 close (10 expiries, 2,308 OTM
quotes). The live column is the range over three intraday snapshots on 2026-11-03
(10 expiries, about 2,080 OTM quotes, quotes delayed about 15 minutes).

| | SVI (weekend) | SSVI (weekend) | eSSVI (weekend) | SVI (live) | SSVI (live) | eSSVI (live) |
|---|---:|---:|---:|---:|---:|---:|
| Parameters | 50 | 13 | 30 | 50 | 13 | 30 |
| RMSE (vol points) | 0.16 | 3.00 | 2.20 | 0.25–0.26 | 3.00–3.22 | 2.38–2.57 |
| Fitted vols inside bid-ask | 80% | 9% | 12% | 28–31% | 2–3% | 3% |
| Slices with negative density (g < 0) | 5 of 10 | 0 | 0 | 4 of 10 | 0 | 0 |
| Adjacent expiries crossing | 6 of 9 | 0 | 0 | 4–6 of 9 | 0 | 0 |

Every SVI negative-density slice lies beyond the last quoted call. Every SVI crossing
does too, except one pair in two of the live runs, which reaches about 0.01 in k inside
the quoted call wing. SSVI and eSSVI are arbitrage-free by construction. eSSVI frees the
skew per expiry and closes about a quarter of SSVI's gap to SVI. Most of the rest comes
from the three-parameter SSVI slice shape itself, not from sharing parameters across
maturities ([docs/essvi.md](docs/essvi.md)).

Raw quotes, weekend: **620** violations on mid, **6** survive bid and ask, and every one
of the 6 has a leg with zero open interest. Raw quotes, live: **661–729** on mid and
**27–34** survive bid and ask. Of those, 21–23 have a zero-open-interest leg and are bad
quotes on illiquid 2028 strikes. Most of the rest are $5–$78 two-week butterflies that
change strike from run to run, consistent with unsynchronised, delayed quotes. None of
these looks tradable.

See [REPORT.md](REPORT.md) for the full write-up and
[docs/robustness.md](docs/robustness.md) for the robustness checks.

## Quick start

```bash
make install
```

```bash
make collect
```

```bash
make run
```

```bash
make figures
```

```bash
make app
```

* `make collect` saves a new snapshot to `data/raw/<UTC time>/`. Raw snapshots are never overwritten.
* `make run` fits the latest snapshot (or `make run SNAPSHOT=data/raw/<id>`) and writes
  everything to `results/<snapshot>/`. Expiries under 0.08 years and SPXW slices take
  their discount factor from the SPX parity curve; `python -m volsurf run --parity-d`
  fits every discount factor from its own parity regression instead.
* `make figures` writes the PNG figures to `results/<snapshot>/figures/` for the report's
  baseline snapshot, `BASELINE_SNAPSHOT` in `src/volsurf/pipeline.py`. The notebook and the
  app also open on the baseline; the app can switch to any other snapshot.
* `make all` reruns the baseline end to end: `run`, `figures` and `notebook`.
* `make app` opens the Streamlit viewer. It only reads saved results.

Run the tests with `make test`, and re-execute the notebook with `make notebook`.
Without `make`, use `python -m volsurf collect | run | figures`, and run the app with
`streamlit run app/streamlit_app.py`.

## Pipeline

| Step | Module | What happens |
|---|---|---|
| 1 Collect | `data.collect_snapshot` | Calls and puts for 10 expiries (weeklies for the shortest target, otherwise standard monthlies), all strikes, bid/ask; saved with fetch time and estimated quote time |
| 2 Clean | `data.clean_chain` | Drop zero bids, crossed quotes, spreads > 50% of mid, options > 10% ITM; keep one of SPX (AM) / SPXW (PM) per date |
| 3 Forward and discount | `forwards.fit_forward` | Weighted regression of C − P on K near the money, robust 3-MAD second pass |
| 4 OTM selection | `quotes.build_quotes` | Puts below F, calls at or above F |
| 5 Implied vol | `pricing.implied_vol` | Black on the forward, Brent's method, bid/mid/ask vols |
| 6 Raw arbitrage | `arbitrage.raw_arbitrage` | Vertical, slope bound, strike-weighted butterfly, calendar; mid vs executable |
| 7 SVI | `svi.fit_svi` | Quasi-explicit (Zeliade) fit per expiry, weighted by inverse spread |
| 8 SSVI | `ssvi.fit_ssvi` | Power-law φ, Gatheral and Jacquier constraints enforced through the parameterisation |
| 9 Fitted arbitrage | `arbitrage.g_function`, `calendar_report` | g(k) on a fine grid, slice crossing |
| 10 Report | `pipeline.run_pipeline` | CSV/JSON/parquet results that the notebook and the app read |

## Layout

```
src/volsurf/      package: data, pricing, forwards, quotes, svi, ssvi, arbitrage, plotting, pipeline
tests/            unit and integration tests (offline; synthetic chains)
app/              Streamlit viewer (reads results only)
notebooks/        analysis.ipynb with all visuals, executed
data/raw/         raw snapshots, one folder per fetch, never overwritten
results/          pipeline outputs per snapshot, including figures/
REPORT.md         findings
```

## Tests

`pytest` runs 155 tests in about 30 seconds, with no network access. CI
(`.github/workflows/ci.yml`) follows the quant-signal-pipeline setup: on every push and
pull request to `main` it installs the package and runs `pytest tests/ -v`. It also runs
ruff, on Python 3.11, 3.12 and 3.13.

| Test file | What it proves |
|---|---|
| `test_pricing.py` | Black price → implied vol → price round trip; bounds return NaN; vega and parity identities |
| `test_forwards.py` | Forward and discount recovered exactly from synthetic parity, and robustly with noise and outliers; a fixed D borrowed from the SPX curve recovers F |
| `test_svi.py` | Parameter recovery from noisy SVI data; constraints hold; density integrates to 1 and matches Breeden–Litzenberger; Vogt's arbitrage slice gets g < 0 |
| `test_arbitrage.py` | Handmade price sets with known vertical, slope, uneven butterfly and calendar violations get flagged; clean sets pass; mid-only violations don't survive bid/ask |
| `test_essvi.py` | Fitted eSSVI parameters satisfy the calendar and butterfly conditions; random admissible surfaces and their interpolated slices give g ≥ 0 and no crossing; the weaker calendar conditions alone are shown to allow a crossing |
| `test_svi_arbfree.py` | Arbitrage-free SVI (GJ14 §5.2) recovers a known arbitrage-free, non-SSVI SVI surface; fits to crossing, negative-density slices come back with g ≥ 0 and no crossing on the fitting grid and the report grid; the Lemma 5.1 interpolation is calendar-monotone and convex in strike |
| `test_cli.py` | Command-line defaults: latest snapshot for `run`, the report's baseline for `figures`, and the forward configuration |
| `test_ssvi.py` | Recovery of known SSVI parameters; fitted parameters always satisfy the no-arbitrage conditions, even on data generated outside them; random admissible parameters give g ≥ 0 and no crossing |
| `test_data.py` | Quote-time estimate, AM/PM settlement times, monthly/holiday expiry selection, cleaning counts, raw snapshots cannot be overwritten |
| `test_pipeline.py` | End to end on a synthetic snapshot: forwards recovered, zero executable arbitrage, SSVI truth recovered |

## Data caveats

Yahoo Finance quotes are delayed about 15 minutes and have no quote timestamps or
sizes. Outside market hours they are the prior session's last quotes. "Survives bid
and ask" therefore means "survives the displayed quotes". In-the-money quotes in the
feed are often stale; see the diagnostic in the report.
