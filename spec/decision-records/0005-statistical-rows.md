# 0005 — Statistical specification rows — which ratified rows are statistical, and the evidence they will need (PROPOSED)

- **Status**: **PROPOSED. Not ratified.** No row of
  [`spec/target-spec.md`](../target-spec.md) is edited by this record. Adding
  statistical rows, setting any yield target, or declaring T1 item 6 a gap is
  the operator's; this record proposes the classification and the evidence
  shape so that decision has something to ratify.
- **Date**: 2026-11-20
- **Decided by**: builder agent (proposal); the operator ratifies
- **Issue**: [#174](https://github.com/2AMLogic/sg13g2-pa/issues/174)
- **Relates to**: [0001-ratify-target-spec](0001-ratify-target-spec.md) ("Not
  covered" excludes statistical variation; "Later" asks which ratified rows
  are statistical), T1 item 6 of the pinned checklist

## Why this record exists

The pinned checklist's item 6 (statistical claims carry Monte Carlo evidence)
grades `unmet` / `no_evidence` in `manifests/sg13g2-pa.signoff.json`, and the
checklist text gives an analog block no `not_applicable` form: analog
performance is inherently statistical (bias spread, mismatch, process), so a
spec with no statistical row is a gap in the spec. The item is discharged one
of two ways, and this record is the proposal for the first:

1. **Ratify statistical rows** (operator) and then supply `klt yield` evidence
   for each — the shape this record proposes.
2. **Declare item 6 a gap** — it keeps grading `unmet`.

The Monte Carlo pilot [`sim/mc-pilot/records/20261120-202416-725d438.md`](../../sim/mc-pilot/records/20261120-202416-725d438.md)
(issue #174) establishes the feasibility facts this proposal rests on. **No
limit proposed below is fitted to that pilot's numbers**; the pilot informs
feasibility and sample size only, and says so in its own Limits section.

## Evidence base and its limits (the pilot)

At the nominal cell (`hbt_*` statistical sections, 27 C, Vcc 0.8 V), n=100
draws per section, seed 174, through the batch fleet with the pinned klt 0.9.0
client (all 400 corners passed):

- Under `hbt_typ_stat`, all 14 identically biased outputs moved together.
  The within-draw current range was zero in every draw. Under
  `hbt_typ_mismatch`, the mean within-draw range was 0.230 mA and the
  sample standard deviation of `ic1-ic2` was 0.102 mA. This establishes
  per-instance variation in the simulated output array. The common mirror
  couples its currents. These measurements cannot establish statistical
  independence of all 15 devices, including the differently biased reference.
- In the pinned mismatch card, each `npn13G2` instance draws one Gaussian
  `qarea` multiplier with mean 1 and sigma 0.1 when `mm_ok=1`. That sigma
  stays at 0.1 for an `Nx=10` device. The pilot tests sampling of this
  model. Inferring mismatch in silicon, its scaling with emitter area,
  or a combined process-and-mismatch yield requires independent evidence.
- **Both HBT mismatch-switch probes were refused**. `monte_carlo.mismatch_scale` and `monte_carlo.instances`
  are both refused before any draw (verbatim refusals in the pilot record),
  curated to sky130/gf180mcu —
  [2AMLogic/klayout-tools#5486](https://github.com/2AMLogic/klayout-tools/issues/5486);
  the sg13g2 `instances` work landed only after the 0.9.0 pin
  ([#5487](https://github.com/2AMLogic/klayout-tools/issues/5487), completed
  2026-11-15) and its measured two-point scaling check is still open
  ([#5503](https://github.com/2AMLogic/klayout-tools/issues/5503)). The
  `vary: "process"` axis is not a control for this deck family (one combined
  `.options seed=` reaches ngspice per draw).
- **Everything ran through ideal passives and an ideal bias source**: `Rb`,
  `Iref`, `Lchoke`, `Cin`, `Cblock` contribute no variation, and the PDK's
  resistor/capacitor statistical sections reach nothing in this netlist. Only
  the 15 HBTs are PDK devices. A real passive set changes the population this
  record's proposal must be re-derived over.
- At n=100 the approximate relative standard error of a sample sigma is
  7% under normal sampling. The two sections define separate populations.

## Classification: every ratified row

"All ten" means the ten RATIFIED rows of `spec/target-spec.md` (Band, Psat,
Output P1dB, Power gain, Peak PAE, Input match, Output port/match, Stability
small-signal, Device stress, Signoff). This proposal assigns a statistical row to a
performance quantity for which a population pass fraction would be meaningful.
The circuit or model must supply a plausible source of variation. The table
distinguishes measured variation from hypotheses awaiting a bench. Conditions,
hard limits checked at every corner, and deterministic signoff keep their
ratified forms.

| Row (all RATIFIED) | Classification | Rationale |
|---|---|---|
| **Band** | corner-bounded (a test condition) | Defines the frequency plan every figure is evaluated on; it bounds the evaluation, not an outcome. No statistical content even for a yield campaign — "2400–2483.5 MHz" is exact by definition (source (L)/(4)). |
| **Saturated output power (Psat)** | **statistical (S3)** | Device variation can change the available output current. A voltage-swing limit can also dominate. Only a drive sweep can establish the resulting Psat distribution. |
| **Output P1dB** | **statistical (S3)** | Device variation can shift the drive level at compression. The pilot did not sweep drive into compression. S3 grades the extracted output P1dB per draw. |
| **Power gain** | **statistical** | Small-signal gain moves with the bias point and device globals; the pilot measured min-in-band S21 spread under both sections at the nominal cell. Proposed row S2 holds the ratified ladder (> 15 dB, fallback > 10) at a stated yield. |
| **Peak PAE** | **statistical (S3)** | Delivered RF power and DC supply current enter PAE and can both vary. The pilot contains no driven efficiency measurements. |
| **Input match (S11)** | **statistical (S2)** | The pilot measured a spread in worst in-band S11. Every nominal draw missed the −10 dB target, with worst in-band S11 around −1.2 dB. S2 grades input match alongside gain. |
| **Output port / match** | corner-bounded (a boundary convention) | The row fixes the port convention (single-ended 50 Ω) and the fallback's stated chip boundary; it is a condition on the testbench, not an outcome. The on-chip-match target itself waits on DR 0001 D-1 (inductor source), which is a deferred decision, not a statistical one. |
| **Stability, small-signal** | corner-bounded | The ratified μ > 1 requirement applies through 10 MHz–30 GHz at quiescent bias and the bias extremes of every PVT cell. Keep that deterministic sweep. The pilot did not measure μ, and a sampled minimum would establish only the worst draw seen. A population stability claim would need its own tail criterion and evidence. |
| **Device stress (breakdown / window)** | corner-bounded and checked in each driven draw | Record the smallest headroom to BVCEO(min) and BVCBO(min) over every device, drive point and PVT cell. A sample extremum describes the observed draws only. This proposal makes no extrapolation to the unsampled tail. A guard band for a population claim would need a validated tail model and an operator decision. The per-draw grading rule below applies. |
| **Signoff** | deterministic | DRC + LVS clean and post-layout re-verification; no simulated statistical outcome enters the verdict. |

## Proposed statistical rows (for ratification, not in this record's power)

S2 and S3 use the target column of the ratified ladder. The fallback and
stretch values remain separate dispositions. S1 needs a current range
derived from the corner load lines. All three need an operator-set yield.

| # | Proposed row | Metric per draw and cell | Limit source | Open question |
|---|---|---|---|---|
| **S1** | Quiescent-current spread | Sum the 14 output collector currents. Report the distribution of that sum and measure every device separately, including the reference. Grade the fraction of draws inside the agreed total-current interval with every device in its operating window. | Derive the interval from the load-line and stress budgets across PVT. Check each device against the card, including `ic < 0.003·Nx` A. | The corner load-line study must establish the current interval. The operator sets the required fraction. |
| **S2** | In-band gain and input match at yield | Grade minimum S21 and maximum S11 over the band on the same draw. A draw passes S2 only if both limits hold. Retain each metric and the joint pass count. | Ratified Power gain > 15 dB and Input match < −10 dB. The nominal pilot misses input match. | Yield target. Closing the nominal input-match failure precedes any claim that the design meets S2. |
| **S3** | Psat, output P1dB and peak PAE at yield | At the ratified band points, use the same drive sweep, load, terminations and power extraction as the ratified rows. Grade the three metrics on the same draw with the stress and window check below. | Ratified targets > +15 dBm, > +12 dBm and > 25%, respectively. | Yield target. Back-off PAE remains a separate draft row. |

**Corner coverage.** For S1–S3, identify the HBT corner, supply and
temperature for every population. Cover the three ratified temperatures
(−40, 27 and 125 °C) and nominal supply ±10%, including nominal. The pinned
PDK supplies mismatch sections at typ/bcs/wcs and a process-statistics
section only at typ. Report each supported population separately. If a
combined or additional population is required for ratification, its model
and evidence are open. Pooling these runs cannot supply it.

**Per-draw validity.** For S3, retain per-device `V_CE`, `V_CB`, `V_BE`,
`I_C` and junction temperature throughout the RF cycle and drive sweep.
For `npn13G2`, compare peaks to BVCEO(min) 1.4 V and BVCBO(min) 3.8 V.
A breakdown violation fails the stress requirement regardless of the RF
result. Apply the spec's **OUTSIDE MODEL WINDOW** label to any excursion
(including `V_CE < 0.4 V` or junction temperature above 125 °C). Record
the offending device, quantity, extreme value and fraction of the cycle.
Such a draw contributes no RF pass. Retain it in the campaign denominator
along with missing or unmeasurable results. For S2 and S3, report per-metric
counts over the same draw IDs. For the joint yield, grade a per-draw flag
(1 when all required checks pass, 0 otherwise) against a lower limit of
1, retaining the underlying metrics and failure reasons. Apply the same
rule to the seeded controls. A citation must account for every requested
draw before its confidence interval can support the row.

What each will need (the checklist's evidence contract, made concrete):

- **A `klt yield` citation per row.** The checklist text's note that the
  `yield` extra is unpublished is historical — PyPI now lists the native wheel
  the 0.9.1 extra requires — but the citation must carry a **target_yield**:
  a yield citation with no target (`status: "reported"`) contributes no row
  coverage in `klt signoff --manifest`
  ([2AMLogic/klayout-tools#5490](https://github.com/2AMLogic/klayout-tools/issues/5490)).
  Ratifying a row without a yield target would produce evidence item 6 still
  cannot count.
- **A seeded degradation for each cited metric.** Run a second simulation
  with the same seed, sections, PVT cell, extraction, draw count and limits.
  Record the deliberate change and supply its measured samples under that
  measurement's `negative_control`. For S1, raise the mirror reference
  current to drive per-device current above the ratified operating window,
  or above the eventual upper array-current bound. The final S1 control
  must cross the particular bound the operator ratifies. For S2, reduce the
  mirror bias to push minimum in-band gain below the selected gain floor.
  For the input-match control, detune the input network so worst in-band
  S11 exceeds its ceiling. Run these controls against a passing baseline.
  For S3, introduce a documented dissipative output loss and run the same
  drive sweep through the same load. Expect lower delivered Psat,
  output P1dB and PAE to cross their respective floors. Check detection for
  each cited metric. Record any unmeasurable compression event as such.
  Set the perturbations before the campaign and keep the row limits fixed.
  Require `negative_control.verdict: detected` and
  `sample_size.verdict: sufficient` from the pinned grader. An all-passing
  control with zero spread can still grade `not_detected`. The two refused
  model-switch probes and the process-section structural zero test only how
  the device model generates variation.
- **Size each population against both yield and precision.** Use the
  empirical two-sided 95% Clopper–Pearson interval from `klt 0.9.1 yield`
  with `--confidence 0.95 --target-ci-halfwidth 0.01`. Require the lower
  bound to reach the operator's target and the interval half-width to be at
  most one percentage point. With zero failures the lower bound is
  `0.025^(1/n)`. The target alone needs 36 draws for 90% or 72 for 95%.
  The precision rule needs 183 in either example, so budget at least 183
  per cell and population. Failures can require more draws. Report the
  actual interval and verdict for the predeclared campaign. For planning
  sigma estimation, the approximate relative standard error under normal
  sampling is `1/sqrt(2(n−1))`, about 7% at the pilot's n=100.
- **The population stated** on every figure: section(s) (`_stat`,
  `_mismatch`), PVT cell, seed, n — the pilot's record format is the template.

## What this record does not decide

- It adds no row, no yield target and no limit; it edits no spec row and no
  manifest. Item 6 stays `unmet` / `no_evidence` / `citation: null` until the
  operator ratifies (route 1) or declares the gap (route 2).
- It makes no yield claim and no pass claim: the design does not meet its
  ratified rows at the nominal cell, and every pilot figure is through ideal
  passives and an ideal bias source.
- It does not decide the inductor source (DR 0001 D-1), the supply row or any
  DRAFT row; a real passive set (with the PDK's own resistor/capacitor
  statistical sections) re-opens the population question and this record must
  be re-derived then.
- It does not extend the PVT box (item 5, issue #173); the statistical
  campaign composes with that box, it does not replace it.

## Consequences

- If the operator ratifies S1–S3: record the limits and target yield for each
  row, establish nominal performance, and run the sized populations and
  seeded degradation controls. The proposed circuit-level controls can be
  simulated with ordinary deck changes at the pilot client pin.
- If the operator declares the gap instead: item 6 grades `unmet` permanently
  for this block, and `ROADMAP.md` / `manifests/README.md` record that choice.
- Either way the pilot's record stands as the feasibility evidence: the two
  pinned HBT sections produced distinct current patterns on the fleet. The
  runner refused both HBT mismatch-switch requests. Detection of the proposed
  row-level degradations remains for the ratified campaign.
