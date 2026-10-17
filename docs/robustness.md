# Robustness checks on REPORT.md

> **Note (added after this file was written).** The SVI wing bound was later corrected
> from b(1+|ρ|) ≤ 4 to < 2 (Lee's bound in total variance; GJ14 Lemma 2.2). On the
> baseline snapshot this changes SVI RMSE from 0.163 to 0.164 and leaves the counts of
> negative-g slices (5) and crossings (6) unchanged. The SVI columns in the sensitivity
> table were computed with the old bound and have not been rerun. Raw-quote and SSVI
> numbers are unaffected.

Baseline: snapshot `20261017T212629Z` (Friday 2026-10-16 close, fetched Saturday) with
the default `CleanConfig(max_rel_spread=0.5, deep_itm_moneyness=0.10)`. All sensitivity
runs below were written to a scratch directory, so nothing under `results/` changed. The
baseline reproduces REPORT.md exactly: 620 mid violations, 6 surviving bid/ask, SVI RMSE
0.16, SSVI RMSE 3.00.

## 1. Live intraday snapshots: not yet run

These checks were run on Saturday 2026-10-17. The next US session opens on Monday
2026-10-19 at 09:30 ET, so there are no live quotes to collect yet. The plan for that
session is to collect three times (around 10:30, 12:45 and 15:15 ET) and run the
pipeline on each:

```bash
.venv/bin/python -m volsurf collect
.venv/bin/python -m volsurf run data/raw/<snapshot_id>
```

`run` takes the snapshot *directory*, not the bare id. The two saved snapshots hold the
same Friday quotes, so comparing them says nothing about robustness. They only differ in
expiry selection:

| | `20261017T212354Z` | `20261017T212629Z` (baseline) |
|---|---:|---:|
| OTM quotes | 2,149 | 2,308 |
| Mid violations | 546 | 620 |
| Survive bid/ask | 6 | 6 |
| …with a zero-OI leg | 6 | 6 |
| Calendar violations (mid) | 0 | 0 |
| SVI / SSVI / SSVI-free RMSE | 0.17 / 2.98 / 1.92 | 0.16 / 3.00 / 1.93 |
| SVI slices with g < 0 (inside quoted k) | 5 (0) | 5 (0) |
| SVI adjacent pairs crossing (inside quoted k) | 5 (0) | 6 (0) |

The live columns will be added here once Monday's runs are done.

## 2. Cleaning-threshold sensitivity

This is a 3 × 3 grid over `max_rel_spread` and `deep_itm_moneyness`. Bold marks the
default.

| max_rel_spread | deep_itm | Kept rows | OTM quotes | Mid viol. | Survive b/a | Zero-OI survivors | Full-chain mid / survive | SVI RMSE | SSVI RMSE | SSVI-free RMSE | SVI g<0 | SVI crossings |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.3 | 0.05 | 2,779 | 2,201 | 591 | 6 | 6 | 716 / 18 | 0.16 | 2.62 | 1.70 | 5 | 7 |
| 0.3 | 0.10 | 3,141 | 2,208 | 592 | 6 | 6 | 880 / 126 | 0.16 | 2.62 | 1.70 | 5 | 7 |
| 0.3 | 0.20 | 3,522 | 2,208 | 593 | 6 | 6 | 1,097 / 290 | 0.16 | 2.62 | 1.70 | 5 | 6 |
| 0.5 | 0.05 | 2,879 | 2,301 | 619 | 6 | 6 | 744 / 18 | 0.16 | 3.00 | 1.93 | 5 | 6 |
| **0.5** | **0.10** | **3,241** | **2,308** | **620** | **6** | **6** | **908 / 126** | **0.16** | **3.00** | **1.93** | **5** | **6** |
| 0.5 | 0.20 | 3,622 | 2,308 | 621 | 6 | 6 | 1,125 / 290 | 0.16 | 3.00 | 1.92 | 5 | 6 |
| 0.8 | 0.05 | 2,949 | 2,371 | 638 | 6 | 6 | 763 / 18 | 0.17 | 3.26 | 2.09 | 5 | 7 |
| 0.8 | 0.10 | 3,311 | 2,378 | 639 | 6 | 6 | 927 / 126 | 0.17 | 3.26 | 2.09 | 5 | 7 |
| 0.8 | 0.20 | 3,692 | 2,378 | 640 | 6 | 6 | 1,144 / 290 | 0.18 | 3.26 | 2.09 | 5 | 7 |

In every configuration, none of the SVI g < 0 slices or crossings lies inside the quoted k range.

**What moves and what doesn't.**

* **The 6 survivors do not change.** In all nine configurations they are the same six
  (expiry, check, strikes), with the same profits ($30–$500) and a zero-open-interest leg
  every time. Their spreads are under 30% of mid, so a spread filter cannot remove them.
  Only an open-interest filter would.
* **The mid count tracks the number of OTM quotes.** It runs from 591 to 640, and almost
  all of the change is in butterflies (573–619). Calendar stays at 0 throughout.
* **`deep_itm_moneyness` barely affects the OTM set.** It only removes ITM legs, and those
  only enter through the parity regression, so a change of ±0–7 quotes. It does drive the
  full-chain ITM diagnostic: 18 → 126 → 290 survivors. That supports REPORT.md's point that
  the ITM quotes are bad data, and it shows the "126 survivors" figure depends on the
  threshold.
* **SVI RMSE is stable at 0.16–0.18.**
* **SSVI RMSE depends on the spread filter: 2.62 / 3.00 / 3.26.** A wider filter admits
  more deep-OTM short-dated puts, and that is exactly where SSVI misses. The 3.00 figure
  is a property of the cleaning choice as much as of the model. The SVI/SSVI ratio moves
  between about 16× and 19×.
* **SVI arbitrage counts barely move.** 5 slices have g < 0 in every configuration, and
  6–7 adjacent pairs cross. None of either is inside the quoted range.

## 3. Raw calendar check: the 0 is real

`arbitrage.calendar_checks` was reproduced loop for loop, with the same `searchsorted`,
edge skip and `max_gap = 0.05`. For each adjacent expiry pair, the table counts the
(T1 quote, T2 interpolation) comparisons it makes and the margin w₂/w₁ − 1 on mid.

| Pair (T1 → T2) | T1 quotes | Compared | Outside T2 k-range | Skipped (gap > 0.05) | Min w₂/w₁ − 1 | Median |
|---|---:|---:|---:|---:|---:|---:|
| 2026-10-30 → 2026-11-20 | 380 | 380 | 0 | 0 | +32.0% | +73.9% |
| 2026-11-20 → 2026-12-18 | 212 | 212 | 0 | 0 | +23.0% | +55.1% |
| 2026-12-18 → 2027-01-15 | 245 | 245 | 0 | 0 | +16.0% | +30.2% |
| 2027-01-15 → 2027-02-19 | 258 | 255 | 0 | 3 | +8.0% | +34.2% |
| 2027-02-19 → 2027-03-19 | 249 | 249 | 0 | 0 | +8.0% | +20.2% |
| 2027-03-19 → 2027-06-17 | 202 | 202 | 0 | 0 | +18.1% | +40.6% |
| 2027-06-17 → 2027-09-17 | 226 | 223 | 0 | 3 | +11.5% | +29.0% |
| 2027-09-17 → 2027-12-17 | 203 | 199 | 0 | 4 | +7.5% | +22.2% |
| 2027-12-17 → 2028-06-16 | 142 | 123 | 15 | 4 | +15.6% | +35.4% |
| **Total** | **2,117** | **2,088 (98.6%)** | 15 | 14 | **+7.5%** | |

* The check is not vacuous. It makes 2,088 comparisons, and the closest one still has the
  longer expiry carrying 7.5% more total variance. Raising `max_gap` to 0.10 or 0.20 adds
  only 13 or 18 comparisons.
* The check can fire. Halving the 2027-02-19 total variances in a copy of the quotes
  produces 255 violations against 2027-01-15.
* The 15 out-of-range points are in the last pair. The 2028-06-16 put wing reaches only
  k = −0.97, against −2.08 for 2027-12-17.
* Zero is expected for this expiry set. Adjacent expiries are 3 weeks to 6 months apart,
  so the variance gap is far larger than quote noise. Calendar violations in practice
  show up between expiries a day or a few days apart, such as consecutive weeklies, and
  this pipeline does not select those.

## 4. The 2-week parity-implied rate (3.8%)

REPORT.md says that at T = 0.04, "a parity residual of a few cents moves the implied rate
a lot." That is true, but it is not the whole story.

**The rate depends on the strike band, which random noise would not cause.** For
2026-10-30 SPXW (rate ± regression SE):

| Parity band (log K/S) | Pairs | Rate (1/spread wts) | Rate (equal wts) | F |
|---|---:|---:|---:|---:|
| ±1% | 29 | −7.3% ± 1.1% | −7.4% | 7670.79 |
| ±2% | 61 | −1.3% ± 0.8% | −1.1% | 7670.88 |
| ±3% | 92 | 2.6% ± 0.6% | 2.7% | 7670.95 |
| ±5% | 148 | 3.5% ± 0.3% | 3.4% | 7670.95 |
| ±7% (default) | 167 | 3.8% ± 0.3% | 3.9% | 7670.95 |

The rates differ by many standard errors from band to band. So C − P is not exactly
linear in K at two weeks; it has small systematic curvature. The forward is still pinned
to within ±0.1 index points.

**SPXW gives lower rates than SPX on the same date, every time.** The snapshot holds both
series on monthly dates, so each can be fitted separately (default band):

| Expiry | SPX (AM) | SPXW (PM) |
|---|---:|---:|
| 2026-11-20 | 4.5% | 2.7% |
| 2026-12-18 | 4.5% | 3.9% |
| 2027-01-15 | 4.8% | 4.6% |
| 2027-02-19 | 4.7% | 4.6% |

The earlier snapshot used the 2026-11-19 SPXW weekly, and that gave 2.1%. The 2-week
expiry is the only SPXW slice in the baseline. Settlement style cannot explain a gap this
size, since the two series' discount factors should differ by hours of interest. So the
low 2-week rate is at least partly a property of how SPXW quotes come through this feed,
not of the rate curve. Two other explanations do not hold:

* **Not stale quotes.** Near-the-money 2-week strikes are the freshest in the snapshot:
  median last trade 0.04 h before the close, and 99% traded on the day.
* **Not a fixed bias in the vols.** Forcing D to a 4.6% rate and refitting F with D fixed
  changes F by 0.006 points and the 2-week implied vols by at most 0.005 vol points.

Conclusion: the 2-week rate is not identified by parity on this feed. It is harmless for
the surface, but it should not be read as a market rate.

## Proposed changes to REPORT.md

1. **Forwards section (line 54–58).** Replace "The 2-week expiry gives 3.8%, which is
   expected: … moves the implied rate a lot" with: the 2-week rate is not identified. It
   ranges from −7% to 3.8% depending on the strike band, and SPXW series give lower rates
   than SPX on every shared date (4.5% vs 2.7% at 2026-11-20). F is stable to ±0.1 points
   and the effect on vols is under 0.01 vol points.
2. **Raw quote arbitrage, survivors paragraph.** Add that the same six survivors appear
   under every cleaning threshold tested (spread 0.3–0.8, ITM cut 5–20%). They pass even a
   30% spread filter, so only an open-interest filter removes them.
3. **ITM diagnostic paragraph.** Say that "908 mid / 126 survivors" is for the 10% ITM cut,
   and that it becomes 18 survivors at 5% and 290 at 20%. The growth with depth
   strengthens the "bad data" reading.
4. **Fits / trade-off section.** Give SSVI RMSE as 3.00 at the default filter, with a
   range of 2.6–3.3 across spread filters of 0.3–0.8 (SVI 0.16–0.18). Soften "about 18
   times" to "16–19× depending on the spread filter".
5. **Fitted arbitrage table.** Note that SVI crossings are 6 of 9 at the default and 6–7
   across thresholds (5 on the earlier snapshot), and that every one is outside the quoted
   range.
6. **Limitations, "Calendar check interpolation" bullet.** Replace "It found no
   violations, even on mid" with the audit result: 2,088 comparisons (98.6% of
   short-expiry quotes), minimum variance margin +7.5%, and an injected violation is
   detected. Zero is expected for expiries 3 weeks or more apart.
7. **Limitations, "Rates" bullet.** Cross-reference item 1.
8. **Limitations, "One delayed weekend snapshot".** After the Monday runs, replace this
   with the live comparison, or keep it if that has not been done.
9. **Resume bullet.** Change "3.0 vol-point RMSE" to "≈3 vol-point RMSE". Hold the
   "6 survived … all on zero-open-interest strikes" claim until the live snapshots confirm
   it.
