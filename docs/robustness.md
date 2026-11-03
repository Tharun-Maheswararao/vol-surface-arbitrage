# Robustness checks on REPORT.md

> **Note (added after this file was written).** The SVI wing bound was later corrected
> from b(1+|ρ|) ≤ 4 to < 2 (Lee's bound in total variance; GJ14 Lemma 2.2). The
> sensitivity grid in section 2 was rerun under the corrected bound on 2026-11-02. SVI
> RMSE is unchanged at two decimals (baseline 0.163 → 0.164), and SVI g < 0 rises from 5
> to 6 slices at max_rel_spread = 0.8, still none inside the quoted range. Raw-quote and
> SSVI numbers are unaffected.

Baseline: snapshot `20261017T212629Z` (Friday 2026-10-16 close, fetched Saturday) with
the default `CleanConfig(max_rel_spread=0.5, deep_itm_moneyness=0.10)`. All sensitivity
runs below were written to a scratch directory, so nothing under `results/` changed. The
baseline reproduces REPORT.md exactly: 620 mid violations, 6 surviving bid/ask, SVI RMSE
0.16, SSVI RMSE 3.00.

## 1. Live intraday snapshots (Tuesday 2026-11-03)

Three live snapshots were collected during the regular session on Tuesday 2026-11-03,
with `volsurf collect` followed by `volsurf run data/raw/<snapshot_id>` (`run` takes the
snapshot *directory*, not the bare id). Yahoo intraday option quotes are delayed about
15 minutes, so the quote times are roughly 15 minutes before the fetch times:

| Snapshot | Fetched (ET) | Quotes as of (ET) | Spot |
|---|---|---|---:|
| `20261103T153057Z` | 10:30 | ≈10:15 | 7,565.48 |
| `20261103T174519Z` | 12:45 | ≈12:30 | 7,579.47 |
| `20261103T202430Z` | 15:24 | ≈15:09 | 7,567.19 |

All three select the same 10 expiries (2026-11-17 SPXW, then SPX monthlies 2026-11-20
through 2028-06-16). That set differs from the baseline's, whose first expiry was the
2026-10-30 SPXW weekly. In both cases the first expiry is about two weeks out.

| | `20261017T212629Z` (baseline) | `20261103T153057Z` | `20261103T174519Z` | `20261103T202430Z` |
|---|---:|---:|---:|---:|
| OTM quotes | 2,308 | 2,070 | 2,092 | 2,093 |
| Mid violations | 620 | 729 | 661 | 674 |
| Survive bid/ask | 6 | 32 | 27 | 34 |
| …with a zero-OI leg | 6 | 22 | 21 | 23 |
| Max surviving profit ($/contract) | 500 | 8,930 | 8,280 | 9,355 |
| Calendar violations (mid) | 0 | 0 | 0 | 0 |
| SVI / SSVI / SSVI-free RMSE | 0.16 / 3.00 / 1.93 | 0.25 / 3.00 / 2.36 | 0.26 / 3.20 / 2.49 | 0.26 / 3.22 / 2.53 |
| SVI slices with g < 0 (inside quoted k) | 5 (0) | 4 (0) | 4 (0) | 4 (0) |
| SVI adjacent pairs crossing (inside quoted k) | 6 (0) | 6 (0) | 4 (1) | 4 (1) |
| First-expiry parity rate | 3.81% (SPXW) | 5.79% (SPXW) | 3.53% (SPXW) | 1.71% (SPXW) |
| Rate range, other expiries | 4.5%–5.2% | 4.5%–5.0% | 4.6%–6.9% | 4.6%–5.0% |

The 6.9% at 12:45 is the 2026-11-20 SPX slice (2.5 weeks). Every other non-first expiry
is in 4.5%–5.0% in all three live runs.

**Live survivors.** These are listed by expiry, check, strikes, profit per contract
and the smallest open interest among the legs.

*10:30 (`20261103T153057Z`), 32 survivors.*

* 2026-11-17 butterflies: 7380/7390/7400 ($35, OI 25), 7570/7575/7580 ($78, OI 13),
  7610/7620/7625 ($10, OI 8), 7645/7650/7655 ($60, OI 6).
* Other positive-OI butterflies: 2027-01-15 7080/7120/7125 ($17, OI 249), 2027-02-19
  7620/7625/7630 ($15, OI 74), 2027-04-16 7575/7600/7625 ($15, OI 975).
* 2028-06-16, positive OI (all on the 6575 put, OI 18): slope bound 6550/6575 ($260),
  butterflies 6525/6550/6575 ($165) and 6575/6600/6625 ($215).
* 2028-06-16, zero OI (22): slope bound 5550/5575 ($580), 6000/6075 ($420), 6725/6775
  ($1,000), 7150/7175 ($1,990), 7250/7275 ($2,170), 8125/8150 ($7,976); vertical
  6775/6800 ($136), 7175/7200 ($856), 7275/7300 ($1,136), 8100/8125 ($7,580);
  butterflies 4300/4400/4500 ($200), 5525/5550/5575 ($330), 5575/5600/5625 ($275),
  5975/6000/6075 ($165), 6075/6100/6125 ($520), 6700/6725/6775 ($453), 6775/6800/6825
  ($850), 7125/7150/7175 ($1,080), 7175/7200/7225 ($1,080), 7225/7250/7275 ($1,185),
  7275/7300/7325 ($1,260), 8100/8125/8150 ($8,930).

*12:45 (`20261103T174519Z`), 27 survivors.*

* 2026-11-17 butterflies: 7520/7525/7530 ($15, OI 41), 7550/7560/7565 ($57, OI 47),
  7575/7580/7585 ($45, OI 37).
* 2028-06-16, positive OI (6575 put, OI 18): slope bound 6550/6575 ($110), butterflies
  6525/6550/6575 ($130) and 6575/6600/6625 ($130).
* 2028-06-16, zero OI (21): the same structures as at 10:30 except the 6775/6800
  vertical, with profits $123–$8,280 (8100/8125/8150 butterfly $8,280, 8125/8150 slope
  bound $7,305, 8100/8125 vertical $6,950).

*15:24 (`20261103T202430Z`), 34 survivors.*

* 2026-11-17 butterflies: 7390/7400/7410 ($15, OI 25), 7430/7440/7450 ($5, OI 118),
  7480/7490/7500 ($40, OI 40), 7625/7630/7635 ($20, OI 11), 7635/7640/7645 ($40, OI 11),
  7655/7660/7665 ($10, OI 6), 7695/7700/7705 ($15, OI 7), 7780/7785/7790 ($5, OI 21).
* 2028-06-16, positive OI (6575 put, OI 18): slope bound 6550/6575 ($270), butterflies
  6525/6550/6575 ($200) and 6575/6600/6625 ($195).
* 2028-06-16, zero OI (23): the 10:30 set plus a 3900/4000/4300 butterfly ($10), with
  profits $10–$9,355 (8100/8125/8150 butterfly $9,355, 8125/8150 slope bound $8,404,
  8100/8125 vertical $8,000).

**What the large survivors are.** The big 2028-06-16 profits all hang on a few
zero-OI strikes whose tight quotes are out of line with their neighbours. At 15:24 the
8125 call is quoted 731.6/739.3 (20.0% vol) between the 8100 call at 647.1/651.6 (17.5%)
and the 8150 call at 620.5/624.5 (17.3%). The 7175 put (OI 0) is off the other way: at
356.3/362.0 it sits below both the 7150 put (381.9/384.9) and the 7200 put (393.6/396.6). The positive-OI 2028 survivors all use the 6575 put (OI 18), which is
quoted 253.0/261.6, below the 6550 put's bid of 264.3. The 2026-11-17 SPXW butterflies
use 5- and 10-point strikes with 0.4–0.6-point spreads, and their profits are $5–$78
per contract (cents to under a point per leg). They change strikes from run to run. With
15-minute-delayed, unsynchronised quotes in a moving market, that is what quote
asynchrony looks like. They should not be read as executable arbitrage.

**Verdict on each weekend finding.**

* **620 mid violations: holds.** Live counts are 661–729, the same order of magnitude,
  on about 10% fewer OTM quotes.
* **6 survivors, all with a zero-OI leg: fails as stated.** Live survivors number
  27–34, and 21–23 of them have a zero-OI leg. The rest are tiny 2-week SPXW butterflies
  (positive OI, $5–$78) and three 2028 structures on one OI-18 put with an inverted
  quote. Only one weekend survivor reappears: the 2028-06-16 7125/7150/7175 butterfly,
  in all three live runs. The qualitative reading holds: the large survivors are bad
  quotes on illiquid strikes, and the remainder are within delayed-quote noise. The
  "$30–$500" profit range does not hold; live maxima are $8,280–$9,355, all on zero-OI
  legs.
* **Raw calendar violations 0: holds.** Zero in every run.
* **SVI RMSE 0.16 and SSVI 3.00: moves, but the gap holds.** SVI rises to 0.25–0.26 and
  SSVI to 3.00–3.22 (SSVI-free 2.36–2.53). SSVI is 12–13× worse than SVI live, against
  19× on the weekend, so the ratio is the figure to soften, not the ≈3 vol-point level.
* **SVI g < 0 on 5 slices, none inside the quoted range: holds.** 4 slices live, none
  inside the range.
* **SVI crossings 6 of 9, none inside the quoted range: moves.** 4–6 of 9 cross. In the
  12:45 and 15:24 runs, one pair (2027-02-19 → 2027-03-19) crosses from k ≈ 0.21–0.22
  onward. The 2027-02-19 calls are quoted up to k = 0.227, so the crossing reaches about
  0.01 into the quoted call wing. "None inside the quoted range" no longer holds strictly.
* **2-week parity rate 3.8% (SPXW), the rest 4.5–5.2%: holds, and the 2-week rate is
  even less stable.** The first-expiry SPXW rate moves from 5.8% to 3.5% to 1.7% over one
  day. Other expiries stay in 4.5%–5.0% apart from one 6.9% on the 2.5-week SPX slice.
  This supports section 4: the short-dated rate is not identified by parity on this feed.

### Weekend snapshots (same Friday quotes)

The two saved weekend snapshots hold the same Friday quotes and differ only in expiry
selection, so comparing them says nothing about robustness:

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
| 0.8 | 0.05 | 2,949 | 2,371 | 638 | 6 | 6 | 763 / 18 | 0.17 | 3.26 | 2.09 | 6 | 7 |
| 0.8 | 0.10 | 3,311 | 2,378 | 639 | 6 | 6 | 927 / 126 | 0.17 | 3.26 | 2.09 | 6 | 7 |
| 0.8 | 0.20 | 3,692 | 2,378 | 640 | 6 | 6 | 1,144 / 290 | 0.18 | 3.26 | 2.09 | 6 | 7 |

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
* **SVI arbitrage counts barely move.** 5 slices have g < 0 (6 at a spread filter of 0.8),
  and 6–7 adjacent pairs cross. None of either is inside the quoted range.

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

**Borrowing D from the SPX curve (option, off by default).** `ForwardConfig` in
`quotes.py` (`volsurf run --fixed-d-max-t T --fixed-d-spxw`) targets expiries with T
below a threshold, SPXW slices, or both. A targeted expiry takes D from the parity
discount factors of the untargeted SPX expiries: log-linear in T between them, and a
flat rate before the first and after the last. Only F is then refitted, by the same
weighted, MAD-trimmed regression with the slope fixed at −D. `forwards.csv` gains a
`D_source` column (`parity`, `spx_interp` or `spx_extrap`). With the defaults every
expiry is `parity`, and the four snapshots below reproduce the committed `forwards.csv`
and `comparison.csv`. The runs were written to a scratch results root.

| Snapshot | 1st-expiry parity rate | SPXW only | T < 0.08 + SPXW | ΔF, 1st expiry | 2026-11-20 SPX rate, ΔF | Max \|Δ vol\| (vol pts) | SVI / SSVI / SSVI-free RMSE |
|---|---:|---:|---:|---:|---:|---:|---|
| `20261017T212629Z` | 3.81% | 4.48% | 4.48% | +0.002 | not targeted (T = 0.095) | 0.004 | 0.16 / 3.00 / 1.93, unchanged |
| `20261103T153057Z` | 5.79% | 4.83% | 4.51% | +0.023 | 4.83% → 4.51%, +0.166 | 0.015 | 0.25 / 3.00 / 2.36, unchanged |
| `20261103T174519Z` | 3.53% | **6.90%** | 4.93% | −0.005 | 6.90% → 4.93%, −0.035 | 0.018 | 0.26 / 3.20 / 2.49, unchanged |
| `20261103T202430Z` | 1.71% | 4.64% | 5.03% | −0.144 | 4.64% → 5.03%, +0.015 | 0.034 | 0.26 / 3.22 / 2.53, unchanged |

ΔF and Δ vol are for T < 0.08 + SPXW against the default. Every rate in the two
borrowed columns is `spx_extrap`, a flat extrapolation of the first untargeted SPX
expiry.

* **SPXW-only is not enough.** It anchors on the 2026-11-20 SPX slice. That slice is
  only 2.5 weeks out on the live days and has the same identification problem, so at
  12:45 it hands its 6.9% to the SPXW slice.
* **T < 0.08 plus SPXW pins the short end.** The first-expiry rate becomes 4.5%–5.0%
  across the live runs (against 1.7%–5.8%), and 4.5% on the baseline. It now moves only
  as much as the anchor's parity rate does: 2027-01-15 live, 2026-11-20 on the baseline.
* **The surface does not notice.** F moves by at most 0.17 index points. Vols move by at
  most 0.034 vol points. Overall RMSEs change by at most 0.0005 vol points, and slice
  RMSEs by at most 0.005. The OTM quote sets, raw violations and survivors, and SVI and
  SSVI arbitrage counts are all identical to the default runs. The one count that moves
  is the full-chain ITM diagnostic at 12:45 under SPXW-only, which goes from 1,024 to
  1,025 mid violations.
* With D fixed, the MAD pass trims 2–4 more pairs on several live short slices, and
  `resid_std` falls. For example, 2026-11-20 at 15:24 falls from 0.68 to 0.38. A free
  slope had been absorbing part of the curvature in C − P.

**Recommendation:** make `ForwardConfig(fixed_d_max_T=0.08, fixed_d_spxw=True)` the
default, in a separate change that regenerates `results/` and rewrites REPORT.md's
forwards paragraph. The fits gain nothing measurable. The gain is a forwards table whose
short-dated rates look like a rate curve and are labelled as borrowed, instead of 1.7%
or 6.9% values that the text then has to explain away. It should not be turned on in
SPXW-only form.

## 5. Which bid/ask survivors are tradable?

`raw_arbitrage` now labels every violation that survives bid/ask (column
`survivor_class` in `raw_violations.csv`, counts in `summary.json` under
`raw_survivor_classes`). The first rule that applies wins:

* `zero_oi`: some leg has open interest 0, so no one holds it;
* `sub_tick`: the executable profit per leg is at or below one quote tick (0.05 below $3,
  0.10 from $3 up, using the coarsest tick among the legs and the quoted option's mid),
  so one tick of slippage per leg erases it;
* `candidate`: everything else.

All five snapshots were rerun with the default `CleanConfig` into a scratch results root.
Every `raw_violations.csv` matches the committed one column for column apart from the
new label. A second scratch run used the new `CleanConfig(min_open_interest=1)` (off by
default; `volsurf run --min-open-interest 1`), which drops zero-OI quotes before the
checks.

| Snapshot | Survive bid/ask | `zero_oi` | `sub_tick` | `candidate` | Survivors with `min_open_interest=1` |
|---|---:|---:|---:|---:|---:|
| `20261017T212354Z` (weekend) | 6 | 6 | 0 | 0 | 0 |
| `20261017T212629Z` (weekend baseline) | 6 | 6 | 0 | 0 | 0 |
| `20261103T153057Z` (10:30 ET) | 32 | 22 | 4 | 6 | 10 |
| `20261103T174519Z` (12:45 ET) | 27 | 21 | 1 | 5 | 6 |
| `20261103T202430Z` (15:24 ET) | 34 | 23 | 6 | 5 | 11 |

With the OI filter on, the survivors are exactly the `sub_tick` and `candidate` rows of
the default run. Removing the zero-OI strikes creates no new survivors among the
neighbouring strikes they leave behind.

**Recurrence across the three live snapshots** (same expiry, check and strikes): the 16
candidates are 10 distinct structures. **3 recur in all three runs and the other 7
appear only once.** None appears in exactly two runs.

* The 3 recurring candidates are the "inverted OI-18 put" structures from section 1, all
  on 2028-06-16: slope bound 6550/6575 and butterflies 6525/6550/6575 and
  6575/6600/6625, worth $110–$270 per contract. They share the 6575 put. Its quote is
  frozen at 253.0 / 261.6 in all three runs while the 6550 and 6600 puts move by 2–3
  points, and it last traded on 2026-07-30. That is a stale quote, not an arbitrage.
* The 7 one-off candidates are 2026-11-17 SPXW butterflies on 5- and 10-point strikes,
  worth $35–$78 per contract (OI 6–47). None repeats, consistent with unsynchronised
  delayed quotes.

So no survivor in any snapshot looks like real, repeatable arbitrage. Limitation: a
calendar's long-dated leg is interpolated, not a listed quote, so the classifier takes
the short-dated leg's open interest and tick for both legs. No calendar survives bid/ask
in any snapshot, so this does not affect the table.

## Proposed changes to REPORT.md

All nine were applied to REPORT.md: items 1–7 on 2026-10-17, and item 5's
qualifier, 8 and 9 on 2026-11-03.

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
8. **Limitations, "One delayed weekend snapshot".** Replace the bullet with:

   > * **Snapshot dependence.** The headline numbers come from one weekend snapshot
   >   (Friday 2026-10-16 close). Three live snapshots on Tuesday 2026-11-03 (10:30,
   >   12:45 and 15:24 ET; quotes delayed about 15 minutes) give 661–729 mid violations,
   >   zero raw calendar violations, SVI RMSE 0.25–0.26 and SSVI RMSE 3.0–3.2, so the
   >   SVI/SSVI gap holds at 12–13× instead of 19×. The survivor count does not hold:
   >   27–34 violations survive bid/ask live, against 6 on the weekend. 21–23 of them
   >   have a zero-open-interest leg and carry the large "profits" (up to $9,355 per
   >   contract) on mis-marked 2028-06-16 strikes. The rest are $5–$78 two-week SPXW
   >   butterflies on 5- and 10-point strikes that change from run to run, consistent
   >   with unsynchronised delayed quotes, plus three structures on one inverted
   >   OI-18 put. The 2-week SPXW parity rate moved from 5.8% to 1.7% within the day.
   >   Fitted SVI calendar crossings reached about 0.01 into the quoted call wing on
   >   one pair (2027-02-19 → 2027-03-19) in two of the three runs. See
   >   docs/robustness.md, section 1.

   Item 5 should then say "outside the quoted range on the weekend snapshot".
9. **Resume bullet.** Replace with:

   > Built an arbitrage-free implied volatility surface for SPX options across 10
   > expiries with ≈3 vol-point RMSE (0.16–0.26 for unconstrained per-slice SVI), by
   > fitting SVI and SSVI under Gatheral–Jacquier constraints, and flagged 620–730 raw
   > quote violations per snapshot. The 6–34 per snapshot that survived bid-ask prices traced to
   > zero-open-interest strikes or delayed, unsynchronised quotes.

   This drops "6 survived … all on zero-open-interest strikes", which the live runs do
   not support (27–34 survivors, about two-thirds with a zero-OI leg).
