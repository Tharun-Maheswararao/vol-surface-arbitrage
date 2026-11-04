# Arbitrage-free SVI (Gatheral and Jacquier 2014, §5.2)

REPORT.md finds that most of SSVI's and eSSVI's gap to per-slice SVI comes from the
three-parameter SSVI slice, not from the no-arbitrage conditions. So the way to get
closer to SVI is a richer slice that is still arbitrage-free. This note adds GJ14's
recipe for one (`src/volsurf/svi_arbfree.py`, model `"svi_arbfree"` in the pipeline,
labelled "SVI (arb-free)") and measures how much of the gap it recovers.

## Source and recipe

Gatheral and Jacquier, "Arbitrage-free SVI volatility surfaces", arXiv:1204.0646v4
(21 March 2013), §5.2–5.3. The recipe in §5.2 is:

1. Fit a square-root SVI surface (SSVI with φ(θ) = η/√θ) as the initial guess.
2. Starting from that guess, refit raw SVI slice by slice. Each fit minimises the fit
   error plus a "big penalty" for crossing the previous or the next slice.

Crossing is measured by *crossedness* (Definition 5.1). Find the points kᵢ where two
slices cross and place test points between them (and one unit beyond the outermost
ones). The crossedness is the largest shortfall max(0, w₁ − w₂) at those test points.
§5.2 contains no butterfly step. §5.3 asserts that the resulting smiles are
butterfly-free. The paper gives no penalty weight, no optimiser and no error metrics
for its SPX example.

## What this implementation does

* **Start.** Square-root SSVI, fitted to every expiry at once with the objective SSVI and
  eSSVI use. η = 2s/(1+|ρ|) with s ∈ (0, 1] and θ non-decreasing. For θ < 4 that
  satisfies GJ14 Thms 4.1 and 4.2: ∂θ(θφ) = φ/2, θφ²(1+|ρ|) = 2sη ≤ 4 and
  θφ(1+|ρ|) = 2s√θ < 4. Each SSVI slice converts exactly to raw SVI (GJ14 Lemma 3.3).
* **Refit order.** From the shortest expiry to the longest. GJ14 say the direction
  "seems to make little difference". Each slice is penalised against the slice
  refitted just before it, not the next one. Penalising against the next slice would
  mean penalising against the square-root SSVI guess, which is about to be replaced.
* **Objective.** The pipeline's weighted total-variance error: inverse bid-ask spread
  weights, normalised to mean 1, and residuals scaled by the slice's ATM variance.
  GJ14 use squared price differences.
* **Calendar penalty.** The mean squared shortfall of w_i below w_{i−1} + 10⁻⁶θ_i over a
  fixed k grid, not crossedness at test points between the roots. The grid has spacing
  0.001 on [−4, 2], so it contains the pipeline's `K_GRID`, plus coarse points out to
  ±15. A shortfall anywhere on the grid is penalised, so this is at least as strict as
  crossedness.
* **Butterfly penalty.** The same on g(k) < 10⁻⁵. This is not in GJ14 §5.2. Without it
  the refitted slices keep SVI's negative call-wing densities.
* **Imposed exactly.** The two asymptotic wing slopes L = b(1 − ρ) and R = b(1 + ρ) may
  not fall from one expiry to the next, which no crossing at k → ±∞ requires. Both stay
  at or below 1.999, against Lee's bound of 2. In the coordinates
  (v, L, R, m, σ), with v = a + bσ√(1 − ρ²) the minimum variance, these are box bounds:
  L ∈ [L_{i−1}, 1.999], R ∈ [R_{i−1}, 1.999], v > 0.
* **Penalty weight.** 10⁴ against the fit residuals. If a slice is still infeasible on
  the grid, it is refitted from that point with a weight 100 times heavier, up to six
  times. Starts for each slice: the square-root SSVI slice, the unconstrained per-slice
  SVI fit, and the slice refitted just before it. The fit keeps the best feasible
  result.
* **Interpolation in T** (GJ14 Lemma 5.1, used for the surface plots). At fixed k,
  out-of-the-money prices are mixed with α = (√θ₂ − √θ_t)/(√θ₂ − √θ₁), with θ_t linear
  in T. From T = 0 to the first expiry the mix starts from zero time value. Mixing
  out-of-the-money prices instead of calls gives the same mix, because the two differ
  by the same intrinsic value on both slices, and it keeps precision deep in the money.

**What is proved and what is checked.** Each of the following is checked on the grid
after the fit: g ≥ 0 on every slice, no adjacent pair crossing, wing slopes
non-decreasing and the right wing below 2 (`check_surface`, saved as `constraints` in
`svi_arbfree_params.json`). The pipeline then runs its own g and crossing checks on
`K_GRID`, as for every other model. None of this is a proof between grid points or
beyond ±15. The wing-slope order and the margins make a violation there unlikely, but
unlike SSVI and eSSVI the guarantee comes from checking, not from the parameterisation.

## Results

RMSE in vol points over all OTM quotes, default cleaning and fixed-D forwards. All five
snapshots in `results/` are included: the two weekend fetches of the 2026-10-16 close
(the second, `20261017T212629Z`, is the report's baseline) and the three live
2026-11-03 runs.

| Snapshot | SVI | SVI arb-free | eSSVI | SSVI | Gap recovered |
|---|---:|---:|---:|---:|---:|
| 20261017T212354Z | 0.17 | 0.24 | 2.19 | 2.98 | 96% |
| 20261017T212629Z (baseline) | 0.16 | 0.24 | 2.20 | 3.00 | 96% |
| 20261103T153057Z | 0.25 | 0.33 | 2.38 | 3.00 | 96% |
| 20261103T174519Z | 0.26 | 0.36 | 2.53 | 3.20 | 96% |
| 20261103T202430Z | 0.26 | 0.36 | 2.57 | 3.22 | 96% |

"Gap recovered" is (eSSVI − arb-free)/(eSSVI − SVI). Fitted vols inside bid-ask: 61–62%
on the weekend snapshots and 17–20% live, against 78–80% and 28–31% for SVI and
12% and 3% for eSSVI.

On every snapshot every slice is feasible on the grid, and the pipeline's own checks on
`K_GRID` find no slice with g < 0, no wing slope at or above 2 and no crossing pair. On
the baseline the margins are thin, with the smallest g at 1.4 × 10⁻⁶ and the smallest
gap at 5 × 10⁻⁹. Nine of the ten slices needed the penalty raised to 10⁸–10¹⁰ before
they were feasible. The result does not depend on the starting weight: 10², 10⁴ and 10⁶ give the
same fit to four decimals, while 10⁸ is ill-conditioned and lands at 0.27. Sixty random
starts per slice on four slices found no better butterfly-feasible optimum than the
default starts.

**Decomposition** (refits of the same quotes with one penalty switched off):

| Snapshot | SVI | g ≥ 0 only | calendar only | both (the model) |
|---|---:|---:|---:|---:|
| 20261017T212354Z | 0.167 | 0.242 | 0.555 | 0.241 |
| 20261017T212629Z | 0.164 | 0.240 | 0.729 | 0.239 |
| 20261103T153057Z | 0.248 | 0.329 | 0.486 | 0.327 |
| 20261103T174519Z | 0.260 | 0.357 | 0.511 | 0.356 |
| 20261103T202430Z | 0.258 | 0.361 | 0.517 | 0.360 |

The butterfly condition costs all of the 0.07–0.10 points. The calendar penalty costs
nothing: once each call wing is butterfly-free, the slices no longer cross. Calendar-only
is worse than both because, without g ≥ 0, the shortest slices put their call wings at
Lee's bound, and the wing-slope order then forces every later slice there too. That is
a property of the greedy order, not of calendar arbitrage.

Where the cost lands: g(k) ≥ 0 is active just beyond the last quoted call on most slices
(`figures/g_function_svi_arbfree.png`). The fitted density there is close to zero, and
SVI's five parameters trade about 0.1 vol point inside the quotes for it. The 2-week
slice is unchanged from raw SVI (0.17), since raw SVI is already butterfly-free there
and the first slice has nothing to cross.

Reproduce the decomposition by calling `fit_svi_arbfree` with `butterfly=False` and/or
`calendar=False` on the slices the pipeline builds.

## Tests

`tests/test_svi_arbfree.py`:

* The square-root SSVI slice in raw SVI form equals the SSVI formula.
* A known arbitrage-free raw SVI surface, whose m and σ move independently of θ so it is
  not SSVI, is recovered to 10⁻⁶ in every parameter from exact quotes and to 0.4% in
  total variance from noisy ones.
* Fits to independent random SVI slices, which cross and have negative densities, come
  back with g ≥ 0 and no crossing, both on the fitting grid and on the pipeline's
  `K_GRID`.
* The Lemma 5.1 interpolation hits every slice exactly, rises in T at fixed k, and
  gives call prices convex in strike from T → 0 to the last expiry.
