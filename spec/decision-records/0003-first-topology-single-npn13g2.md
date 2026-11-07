# 0003: First topology — single-stage `npn13g2` array, 0.8 V nominal (PROPOSED)

- **Status**: **PROPOSED. Not ratified.** No row of
  [`spec/target-spec.md`](../target-spec.md) is edited by this record. The
  Supply, Device-flavour and Thermal rows stay DRAFT; ratifying them needs the
  operator.
- **Date**: 2026-10-27
- **Decided by**: builder agent (proposal); the operator ratifies
- **Issue**: [#36](https://github.com/2AMLogic/sg13g2-pa/issues/36)
- **Answers**: [0001-ratify-target-spec](0001-ratify-target-spec.md), Q1
  (single device versus stack)

## Evidence base and its limits

Every number below is taken from the single-device load-line record
[`sim/device-npn13g2/records/20261023-171155-870a4b7.md`](../../sim/device-npn13g2/records/20261023-171155-870a4b7.md)
(issue #21), section "Analytic load-line", tables "Swing mode `saturated`"
and "Swing mode `fixed-nominal`", row key = (Vcc nom, tol). Read that record
as follows:

- The Pout figures are an **analytic ceiling**: ideal resistive load, ideal
  sinusoid, class A, **through ideal passives**, fundamental only, no
  harmonic terminations, **no PAE**. They are not a simulated PA result.
- The record covers `npn13G2` only. It has no `npn13g2l` or `npn13g2v` data.
- The Tj column is the record's own figure at 125 °C ambient.

## Decision (proposed)

| Choice | Proposal | Trace |
|---|---|---|
| Device flavour | `npn13g2` (model `npn13G2`) | Only flavour with load-line evidence in-tree |
| Stack | None. Single common-emitter stage, no cascode | Q1 answer below |
| Unit-cell array | 14 devices of Nx=10 in parallel (140 Nx units) | Row (0.80, −10 %), `saturated`: Nx for +15 dBm = 132, "Nx=10 devices" = 14 |
| Supply nominal | 0.8 V | Record "Recommendation (NOT ratified)": 0.8 V nominal |
| Output network | Off-chip match boundary or ideal passives | DR 0001 Q2 / D-1 still open |

Sizing note. The record's recommendation line quotes ~106 Nx units (11
devices of Nx=10); that is the nominal-supply row (0.80, nominal). The −10 %
supply cell needs 132 Nx units (14 devices) for the same +15 dBm
ceiling, so the proposal sizes for that cell. The cost of the larger array is
more collector capacitance and more dissipation; neither is quantified here.

## Q1: does one device close the target with margin?

**The record shows a single device (no stack) can reach the +15 dBm ceiling
without exceeding BVCEO(min), but only with thin margin at the high-supply
corner, and none of it is in-window at 125 °C.**

Numbers, `saturated` swing, BVCEO(min) 1.4 V, BVCBO(min) 3.8 V:

| Vcc nom | tol | Vce pk | Margin to BVCEO(min) | Vcb pk | Nx for +15 dBm |
|---|---|---|---|---|---|
| 0.70 | +10 % | 1.140 V | 0.260 V | 0.490 V | 114 |
| 0.80 | −10 % | 1.040 V | 0.360 V | 0.390 V | 132 |
| 0.80 | nominal | 1.200 V | 0.200 V | 0.550 V | 106 |
| 0.80 | +10 % | 1.360 V | **0.040 V (2.9 %)** | 0.710 V | 88 |
| 1.00 | −10 % | 1.400 V | 0.000 V | 0.750 V | 85 |
| 1.00 | nominal | 1.600 V | **−0.200 V** | 0.950 V | 71 |

- Vcb pk is far inside BVCBO(min) at every candidate (at most 0.71 V of 3.8
  V at 0.8 V nominal); the limit that binds is BVCEO, not BVCBO.
- 1.0 V nominal violates BVCEO(min) at nominal and +10 % (record verdict
  "BREAKDOWN VIOLATION (VCEO)"), and its −10 % cell has zero margin. It is
  rejected.
- At 0.8 V nominal the +10 % cell leaves 0.040 V to BVCEO(min). The record's
  own criterion ("within BVCEO/BVCBO (min)") is met, but 2.9 % is not a
  comfortable margin, and BVCEO(min) is a process-spec minimum, not a model
  card figure. 0.7 V nominal buys 0.260 V at +10 % at the price of 141 Nx
  units at nominal (15 devices) and 184 Nx units at −10 % (19 devices).
  Choosing between them is an operator tradeoff; this record proposes 0.8 V
  because that is what the record recommends, and flags 0.7 V as the
  lower-stress alternative.
- Whether this margin survives a real load (reactive, with harmonic content)
  is not shown by the record. Peak `V_CE` in the real circuit can exceed the
  ideal-resistive-load figure. Those peaks must come from the large-signal
  bench (#40), not from this record.

Conclusion: no stack is justified by the evidence in tree. A stack, or
`npn13g2v`, is entered only if the large-signal bench shows peak `V_CE`
exceeding BVCEO(min) on the real network. The +20 dBm stretch never justifies
stacking first (CLAUDE.md scope rule; DR 0001 Q1).

## Thermal: outside the model window at every candidate

The record's Tj at 125 °C ambient is **133.6 °C to 147.3 °C in every row of
both swing tables** (e.g. 137.9 °C at (0.80, nominal) `saturated`; 133.6 °C
at (0.50, −10 %) `fixed-nominal`), above the card's 125 °C ceiling. Therefore:

- No candidate supply is in-window at the 125 °C corner. Any hot-corner
  result for this topology is labelled **OUTSIDE MODEL WINDOW** and is never
  quoted as a pass for the spec's Device stress Target cell (DR 0002); at
  most it meets the Fallback cell, which does not require the window.
- The hot-corner figures would also change if the ambient corner were
  lowered or the device were derated; the Thermal spec row (DRAFT) is where
  that is decided. This record does not decide it. It proposes treating the
  125 °C corner as a labelled out-of-window corner until the operator ratifies
  a thermal row, and reporting −40 °C and +27 °C results in-window as usual.
- Self-heating is on in the record's benches (card default `selft=1`).
  DR 0001 Q4 (whether ngspice solves the thermal node as intended) is not
  resolved by this record.

## What this record does not decide

- It does not ratify supply, flavour or thermal rows; it edits no spec row.
- Inductor-model source (DR 0001 D-1, the `consumes` edge to `sg13g2-vco`) is
  not decided and no inductor numbers are used. The schematic uses ideal
  passives or the off-chip fallback boundary; every Pout/PAE figure derived
  from it is labelled "through ideal passives".
- It makes no claim about PAE, harmonics, gain, stability or input match.
- `npn13g2l` and `npn13g2v` have no load-line evidence in tree. Choosing either
  would first need the same study as #21 run on that flavour's card
  (`npn13G2l`: window `vce` 0.4–2.0 V; `npn13G2v`: window `vce` 0.8–2.3 V,
  `ic` < 0.50·Nx·El A, per DR 0001 Evidence).

## Consequences

- #37, #39 and #40 can proceed against a netlist with one instance family,
  `npn13G2`, Nx=10, 14 in parallel, at 0.8 V nominal.
- If the operator picks 0.7 V or a different flavour, the schematic and this
  record are amended; nothing downstream has been built yet.
