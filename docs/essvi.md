# Extended SSVI (eSSVI)

REPORT.md fits power-law SSVI with one ρ and one φ(θ) for every maturity. It names
eSSVI as the way to close the gap to per-slice SVI without giving up no-arbitrage.
This note adds that fit (`src/volsurf/essvi.py`, model `"essvi"` in the pipeline) and
measures how much of the gap it closes. The short answer is 0.6–0.8 vol points out of
about 2.8–3.0. Almost all of the rest comes from the shape of a three-parameter SSVI
slice, not from the calendar conditions.

## Model and conditions

Each expiry has its own (θᵢ, ρᵢ, ψᵢ), where ψ = θφ:

    w(k) = θ/2 · (1 + ρφk + √((φk + ρ)² + 1 − ρ²)),   φ = ψ/θ

**Sources.** I read two papers:

* Corbetta, Cohort, Laachir and Martini, "Robust calibration and arbitrage-free
  interpolation of SSVI slices", arXiv:1804.04924v2 (4 March 2019), HTML version.
* Mingone, "No arbitrage global parametrization for the eSSVI volatility surface",
  arXiv:2204.00312v1 (1 April 2022), HTML version.

Both take the calendar result from Hendriks and Martini (2019), "The extended SSVI
volatility surface", J. Comput. Finance 22(5). **I could not open Hendriks and Martini
itself.** Everything below about it is as quoted in those two papers.

**Calendar (adjacent slices, T₁ < T₂).** Mingone §2.1, citing Hendriks–Martini
Prop. 3.5:

* necessary: θ₂ > θ₁ and ψ₂ > ψ₁ · max((1 + ρ₁)/(1 + ρ₂), (1 − ρ₁)/(1 − ρ₂));
* sufficient: the necessary conditions, plus either ψ₂/θ₂ ≤ ψ₁/θ₁ (φ non-increasing)
  or a quadratic alternative, (ρ₁ − (ψ₂/ψ₁)ρ₂)² ≤ (θ₂/θ₁ − 1)(ψ₂²θ₁/(ψ₁²θ₂) − 1).

In weak form the necessary part is the condition in the brief and in Corbetta et al.
§2.2: θ and ψ non-decreasing, and |ρ₂ψ₂ − ρ₁ψ₁| ≤ ψ₂ − ψ₁. **Corbetta et al. call this
set necessary and sufficient, but it is not sufficient on its own.** Take
(θ, ρ, ψ) = (1, 0, 1) and then (1.01, 0.1, 1.2). The pair satisfies that set and both
butterfly bounds, yet the slices cross for k in about (−1.49, −0.09)
(`test_necessary_calendar_conditions_alone_allow_crossing`). The fit therefore imposes
Mingone's tractable sufficient set: the necessary conditions plus φ non-increasing. I
have not checked the sufficiency claim against Hendriks–Martini. It is checked
numerically in the tests: 30 random admissible surfaces on k ∈ [−6, 4], plus the
interpolated slices.

**Butterfly (each slice).** Gatheral and Jacquier (2014) Thm 4.2, which Corbetta et
al. quote as eqs. (2)–(3), rewritten with ψ = θφ: ψ(1 + |ρ|) < 4 and
ψ²(1 + |ρ|) ≤ 4θ. These bounds are sufficient, not necessary. The fit caps
ψ(1 + |ρ|) at 3.998 so that the steeper wing slope stays below 1.999, the same margin
SVI keeps against Lee's bound of 2.

**Parametrisation.** Write p = ψ(1 + ρ) and m = ψ(1 − ρ), which are twice the right
and left wing slopes. The necessary calendar condition becomes "θ, p and m
non-decreasing". The other bounds become p + m ≤ 2φᵢ₋₁θᵢ, max(p, m) ≤ 3.998 and
(p + m)·max(p, m) ≤ 8θ, and each one tightens as p or m grows. The fit builds slice i
from slice i − 1 in three steps:

1. θᵢ is a cumulative sum of non-negative increments.
2. pᵢ moves a fraction xᵢ ∈ [0, 1] of the way from pᵢ₋₁ to the largest p the bounds
   allow at m = mᵢ₋₁.
3. mᵢ then moves a fraction yᵢ of the way to the largest m allowed at pᵢ.

This maps the unit box onto the admissible set, so `least_squares` box bounds enforce
every condition exactly, with 3 parameters per expiry. The objective and weights are
the same as for SSVI. The fit starts from the constrained SSVI fit, which is itself
admissible eSSVI, plus four constant-ρ starts.

Between expiries, `ESSVIParams.slice_at` interpolates θ, ψ and ρψ linearly in T, as in
Corbetta et al. §5 and Mingone §5, and that preserves all the conditions.

## Results

All four snapshots were run with the default `CleanConfig` into a scratch results root.
Nothing under `results/` changed. The SVI, SSVI and SSVI-free numbers match
docs/robustness.md. The arbitrage columns count slices or adjacent pairs on
k ∈ [−2.5, 1], with the count inside the quoted k range in brackets.

| Snapshot | Model | Params | RMSE (vol pts) | Inside bid-ask | Slices g < 0 | Pairs crossing |
|---|---|---:|---:|---:|---:|---:|
| `20261017T212629Z` (baseline) | SVI | 50 | 0.16 | 79.6% | 5 (0) | 6 (0) |
| | SSVI | 13 | 3.00 | 8.6% | 0 (0) | 0 (0) |
| | **eSSVI** | 30 | **2.20** | 12.1% | **0 (0)** | **0 (0)** |
| `20261103T153057Z` (10:30 ET) | SVI | 50 | 0.25 | 30.9% | 4 (0) | 6 (0) |
| | SSVI | 13 | 3.00 | 2.8% | 0 (0) | 0 (0) |
| | **eSSVI** | 30 | **2.38** | 3.4% | **0 (0)** | **0 (0)** |
| `20261103T174519Z` (12:45 ET) | SVI | 50 | 0.26 | 28.1% | 4 (0) | 4 (1) |
| | SSVI | 13 | 3.20 | 2.4% | 0 (0) | 0 (0) |
| | **eSSVI** | 30 | **2.54** | 2.7% | **0 (0)** | **0 (0)** |
| `20261103T202430Z` (15:24 ET) | SVI | 50 | 0.26 | 28.1% | 4 (0) | 4 (1) |
| | SSVI | 13 | 3.22 | 2.8% | 0 (0) | 0 (0) |
| | **eSSVI** | 30 | **2.57** | 2.8% | **0 (0)** | **0 (0)** |

Every eSSVI fit passes `check_constraints`. No eSSVI slice breaks Lee's wing bound,
and neither do any SVI or SSVI slices. The unconstrained SSVI diagnostic gives 1.93 /
2.36 / 2.49 / 2.53. Its fitted g stays non-negative, but its parameters break the
sufficient GJ bound.

Fitted ρ ranges from −0.67 to −0.52 (baseline) and from −0.58 to −0.47 (live), with
the steepest skew at the short end on the baseline and at the long end live. φ falls
from about 55 to 5.5 (baseline) and from 48 to 5.2 (live).

## Where the remaining gap is

To split eSSVI's error, the same SSVI slice was fitted to each expiry on its own, with
the same weights. Once with no constraint at all, and once with only the GJ butterfly
bounds. Neither fit has any calendar condition. This was a scratch script and is not
part of the package.

| Snapshot | SVI | Per-slice SSVI, free | Per-slice SSVI, GJ butterfly | eSSVI | SSVI |
|---|---:|---:|---:|---:|---:|
| `20261017T212629Z` | 0.16 | 1.91 | 2.20 | 2.20 | 3.00 |
| `20261103T153057Z` | 0.25 | 2.28 | 2.38 | 2.38 | 3.00 |
| `20261103T174519Z` | 0.26 | 2.42 | 2.53 | 2.54 | 3.20 |
| `20261103T202430Z` | 0.26 | 2.45 | 2.57 | 2.57 | 3.22 |

* **The calendar conditions cost nothing measurable.** eSSVI matches the per-slice
  butterfly-only optimum to within 0.01 vol points on every snapshot. The one
  condition that binds is φ non-increasing between the first two live expiries,
  2026-11-17 and 2026-11-20, three days apart. This also shows the global fit reaches
  the per-slice optimum.
* **Freeing ρ and φ per expiry is worth 0.6–0.8 points** (SSVI → eSSVI).
* **The sufficient GJ butterfly bound costs 0.1–0.3 points** (per-slice free →
  butterfly). Martini and Mingone give a necessary-and-sufficient butterfly condition
  for SSVI slices, quoted in Mingone §2.2. Using it could recover part of this. I have
  not checked it.
* **The SSVI slice shape accounts for 1.75–2.2 points** (SVI → per-slice SSVI, free).
  An SSVI slice has three parameters. Its minimum, curvature and wings are tied
  together through (θ, ρ, ψ), and it cannot match the short-dated SPX smiles that raw
  SVI fits with five.

So the "≈1.9 points structural" in REPORT.md comes mainly from the slice family, not
from sharing one ρ and φ across maturities. eSSVI makes the arbitrage-free surface
better (3.0–3.2 → 2.2–2.6) but cannot get close to SVI's 0.16–0.26. Getting closer
needs a richer arbitrage-free slice. Options are SVI-JW or raw SVI slices with
butterfly and calendar conditions imposed between them, as in Gatheral and Jacquier
§5. A second option is a necessary-and-sufficient butterfly condition in place of the
GJ bound.

## Reproducing

    volsurf run data/raw/<snapshot_id> --results-root <scratch>/results

The results directory gains `essvi_params.json`, which holds θ, ρ, ψ per expiry, the
fit status and `check_constraints`. It also gains `w_essvi`, `g_essvi` and
`density_essvi` columns in `curves.parquet`, `w_essvi` and `iv_essvi` in
`quotes.parquet`, and an `eSSVI` row in `comparison.csv` and `fit_stats.csv`.
`load_results` returns `essvi=None` for result directories written before this change,
such as the committed `results/`.

Runtime: the eSSVI fit takes 30 s to 5 min per snapshot on a laptop. It uses a
finite-difference Jacobian over 30 parameters and five starts.
