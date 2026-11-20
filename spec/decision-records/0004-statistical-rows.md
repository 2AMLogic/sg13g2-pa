# 0004: Statistical specification rows — which ratified rows are statistical, and the evidence they will need (PROPOSED)

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

- The two statistical HBT sections of `cornerHBT.lib` were measured
  **separately** and behave as two distinct mechanisms:
  `hbt_typ_stat` (global `gauss()` multipliers) moves every device together
  across draws — the within-draw spread across the 14 identically biased
  output devices is **exactly zero**; `hbt_typ_mismatch`
  (per-instance `qarea = agauss(1, 0.1, …)`, `mm_ok=1`) makes them differ
  within a single draw and moves the same-draw pair difference `ic1-ic2`
  across draws. So the tool **can** measure device mismatch separately from
  common process/bias movement on this design.
- The per-instance mechanism answers question 1 of the issue: **yes**, the
  campaign samples non-zero variation on `npn13G2` per instance (the 14 array
  devices and the mirror reference draw independently — the reference's
  near-constant current under `hbt_typ_stat` while the array moves shows the
  shared-bias and process paths apart).
- **No deterministic negative control is declarable for this family at the
  pinned client**: `monte_carlo.mismatch_scale` and `monte_carlo.instances`
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
- n=100 puts roughly ±10 % on a sigma estimate — enough to size a campaign,
  not a yield statement.

## Classification: every ratified row

"All ten" means the ten RATIFIED rows of `spec/target-spec.md` (Band, Psat,
Output P1dB, Power gain, Peak PAE, Input match, Output port/match, Stability
small-signal, Device stress, Signoff). A row is **statistical** if the
quantity it bounds is a random variable over the statistical population
(process + mismatch at the PVT corners); **corner-bounded** if the PVT box
already spans the variation the row admits; **deterministic** if no simulated
outcome enters the row's verdict.

| Row (all RATIFIED) | Classification | Rationale |
|---|---|---|
| **Band** | corner-bounded (a test condition) | Defines the frequency plan every figure is evaluated on; it bounds the evaluation, not an outcome. No statistical content even for a yield campaign — "2400–2483.5 MHz" is exact by definition (source (L)/(4)). |
| **Saturated output power (Psat)** | **statistical** | Psat follows the quiescent point and the device strength, both of which the pilot shows move under both sections. The ratified target (> +15 dBm, fallback > +10) is today corner-bounded evidence; a yield form holds the same ladder at a stated yield (proposed row S3). |
| **Output P1dB** | **statistical** | Same mechanism as Psat (compression point tracks bias and gain); proposed as part of S3's campaign, reported per draw. |
| **Power gain** | **statistical** | Small-signal gain moves with the bias point and device globals; the pilot measured min-in-band S21 spread under both sections at the nominal cell. Proposed row S2 holds the ratified ladder (> 15 dB, fallback > 10) at a stated yield. |
| **Peak PAE** | **statistical** | PAE is computed from P_out, P_in and P_DC, each of which carries the same spread; the row's eventual yield form is part of S3. |
| **Input match (S11)** | **statistical** | S11 moves with the same population (the pilot measured its spread at the nominal cell); the ratified limit (< −10 dB) currently has large nominal margin the wrong way (−1.2 dB), which is a design state, not a classification. Held with S2's campaign, reported per draw. |
| **Output port / match** | corner-bounded (a boundary convention) | The row fixes the port convention (single-ended 50 Ω) and the fallback's stated chip boundary; it is a condition on the testbench, not an outcome. The on-chip-match target itself waits on DR 0001 D-1 (inductor source), which is a deferred decision, not a statistical one. |
| **Stability, small-signal** | **statistical** | μ > 1 is a pass metric over S-parameters, which move with the same population; the pilot did not measure μ (different bench), but no mechanism separates it from Power gain's classification. Yield form: μ > 1 in every draw of the campaign (a stability row is not diluted: one unstable draw is a failure, so its "yield" is a worst-case-over-draws report, not a fraction). |
| **Device stress (breakdown / window)** | corner-bounded as written; **worst-case over draws** in any statistical campaign | The row's check is deterministic per cell (peak `V_CE`/`V_CB` against (P) minima, window labelling). A statistical campaign evaluates the same deterministic check in every draw and reports the worst draw; **no yield fraction may dilute a breakdown or window limit** — this row stays worst-case by construction. |
| **Signoff** | deterministic | DRC + LVS clean and post-layout re-verification; no simulated statistical outcome enters the verdict. |

## Proposed statistical rows (for ratification, not in this record's power)

All three are the **existing ratified ladder held over a population**, not new
numbers. Each limit's source is the ratified row it names; each yield target
is an explicit **open operator question** — this record derives no threshold
from the pilot.

| # | Proposed row | Metric | Limit source | Open question |
|---|---|---|---|---|
| **S1** | Quiescent-current spread | Total output-array quiescent Ic at the nominal cell (per-device currents reported alongside; the array current is never divided by 14 — that erases the mismatch being measured) | The stress budget: every draw's per-device quiescent Ic inside the card window (`ic < 0.003·Nx` A) and the load-line study's sizing assumption | The numeric spread limit. Set by the load-line study re-run at the PVT corners (design work with no issue yet) and the operator; a defensible number does not exist in-tree today |
| **S2** | Power gain at yield | Min in-band S21 per draw (ac-gain bench, per PVT cell); S11 reported per draw against the Input-match row | The ratified Power gain ladder (> 15 dB, fallback > 10 dB) and Input match (< −10 dB) | The yield target and confidence (see sample-size below) |
| **S3** | Psat / P1dB / PAE at yield | Psat, output P1dB and peak PAE per draw (psat bench, per PVT cell), same load and extraction as the ratified rows | The ratified Psat/P1dB/PAE ladders | Same as S2, plus whether back-off PAE (a DRAFT row) joins the campaign |

What each will need (the checklist's evidence contract, made concrete):

- **A `klt yield` citation per row.** The checklist text's note that the
  `yield` extra is unpublished is historical — PyPI now lists the native wheel
  the 0.9.1 extra requires — but the citation must carry a **target_yield**:
  a yield citation with no target (`status: "reported"`) contributes no row
  coverage in `klt signoff --manifest`
  ([2AMLogic/klayout-tools#5490](https://github.com/2AMLogic/klayout-tools/issues/5490)).
  Ratifying a row without a yield target would produce evidence item 6 still
  cannot count.
- **A deterministic negative control** (sigma exactly 0 with variation
  elsewhere unchanged). At the pinned client this is refused for sg13g2
  (#5486/#5487 above), so **no yield claim is possible until the client pin
  reaches the sg13g2 `instances`/`mismatch_scale` work** (or the operator
  accepts a deck-level `mm_ok=0` control, which the tool does not declare).
  The pilot's structural zero (the stat section's within-draw spread) is a
  mechanism check, not a declared control.
- **A sample size stated with its rule**, both for sigma estimation and for
  the yield fraction: with zero observed failures, demonstrating yield y at
  confidence c needs n ≥ ln(1−c)/ln(y) draws per population (29 draws for
  90 % @ 95 % confidence; 59 for 95 % @ 95 %); a sigma estimate within ±10 %
  needs ~50 draws (the pilot's n=100 gives ~7 %). The campaign runs the
  statistical sections at each PVT cell of the ratified box, so the per-cell
  draw count is the operator's cost/coverage dial.
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

- If the operator ratifies S1–S3: the campaign needs a klt pin that can
  declare the negative control for sg13g2, a target yield per row, and the
  design to close its rows at the nominal cell first (a yield fraction on a
  design that fails nominally is meaningless).
- If the operator declares the gap instead: item 6 grades `unmet` permanently
  for this block, and `ROADMAP.md` / `manifests/README.md` record that choice.
- Either way the pilot's record stands as the feasibility evidence: the two
  HBT mechanisms are separable and measurable on the fleet at the pinned
  client; the negative control is the one thing the tool will not yet declare.
