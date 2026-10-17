# 0001: Ratify the target spec

- **Status**: ratified on approval of the PR that lands this record and
  [`spec/target-spec.md`](../target-spec.md). Approval of that PR is the
  ratification act. Rows marked DRAFT in the spec are **not** ratified by this
  record; they are listed under "Deferred" below.
- **Date**: 2026-10-17
- **Decided by**: builder agent (proposal); the approving reviewer ratifies
- **Issue**: [#2](https://github.com/2AMLogic/sg13g2-pa/issues/2)

## Context

The README carried a DRAFT target table and `spec/` held only a README. No
design result could be verified against a fixed target, and `CLAUDE.md`
forbids relaxing a ratified spec to make results pass, so what is ratified here
binds all later work. This record ratifies the rows whose values come from the
README ladder unchanged, plus definitions that need no number (band, device
stress, extraction method). It keeps DRAFT every row whose number cannot yet
be backed by evidence, instead of forcing a figure.

## Decision

1. Ratify the rows marked RATIFIED in `spec/target-spec.md`: band, Psat, P1dB,
   power gain, peak PAE, input match, output port/match, small-signal
   stability, device stress, signoff. Values are the README draft's
   fallback/target/stretch **unchanged**. Nothing was relaxed.
2. Keep DRAFT, and defer: PAE at back-off, large-signal stability threshold,
   supply nominal, device flavour/stacking, thermal, electromigration rule,
   harmonics, area, and the inductor-model source (D-1, D-2 below).
3. Add what the README draft lacked as rows: PAE at back-off, harmonics,
   large-signal stability, thermal, EM, area, inductor models. Each is added
   as report-only or DRAFT, never as an invented threshold.
4. Adopt the transient extraction method in the spec ("Large-signal extraction
   without harmonic balance") including its known-answer check.
5. The README target table is synced to the spec and its stale
   "see issue #1" is corrected to point at the spec (the issue is #2).

### Open questions

**Q1. Which HBT flavour, and is stacking required to reach the target with
margin to breakdown? — DEFERRED (D-2), with a recommendation.**
Recommendation: begin with a single `npn13g2`. Hand arithmetic (tier 5, not
evidence): +15 dBm is 31.6 mW; with peak `V_CE` held under BVCEO(min) 1.4 V
the load line needs roughly 8 Ω at the device and ~90 mA peak, which needs an
array of unit cells (the window's `ic` < 0.003·Nx A is per instance). That
looks achievable without a stack on paper, but "with margin" cannot be
decided before a load-line study. A stack or `npn13g2v` is entered only if the
single-device study shows the target cannot close with margin; the +20 dBm
stretch never justifies stacking first. `npn13g2v` trades fT (90–120 GHz,
still far above f₀) and BVCEO (≥ 2.2 V) against ICMAX (0.5 mA on
0.12×1 µm² vs 3.5 mA on 0.07×0.9 µm²) — far less current per device.

**Q2. Where do the inductor models come from? — DEFERRED (D-1), not decided.**
Options:

- **(a) `sg13g2-vco`'s characterized spirals.** Needs a `consumes` edge, an
  operator decision. What was read at `sg13g2-vco` `17e49a8`:
  `sim/inductor-model/README.md` states IHP-Open-PDK v0.3.0 ships **no**
  ngspice-simulatable spiral inductor; it holds an analytic (Mohan 1999)
  model with stated error bars and an openEMS-fitted model at three fixed
  geometries (`p1`, `p13`, `p11`), the EM model authoritative for those three
  only. Its ratified tank Q figures are for the 4.5–5.5 GHz tank
  (e.g. EM Q 9.49 at 2 GHz, 10.28 at 5 GHz for `p11`, SRF 9.42 GHz; ±10 %
  convergence bar, `spec/target-spec.md` row 1 and 5) — a derived-for-the-VCO
  extraction, not a PA output-network figure. No numbers are copied here;
  anything used must come with its derivation.
- **(b) An EM extraction done here.** That is a second inductor model and needs
  a recorded reason; not started.
- **(c) An off-chip output match.** This is the README fallback; it removes the
  need for an on-chip inductor model at the cost of the on-chip-match target.

Recommendation: (a) for the on-chip target, with the fallback (c) always
available; reasons are that (b) would duplicate an existing, derived model, and
that the 2.4 GHz band sits below the evidenced SRFs. Caveat to carry: the
`sg13g2-vco` Q was extracted at its own tank geometry; a PA's power inductors
need much wider traces or a different geometry, so its Q and SRF at the PA's
current levels are an open question for whoever extends it. **Operator
action needed: decide whether to add the `consumes` edge from `sg13g2-pa` to
`sg13g2-vco`.** Until then, any P_out/PAE through ideal passives is labelled
"through ideal passives".

**Q3. How are output power, compression and PAE extracted from transient
benches without harmonic balance? — RESOLVED** in the spec: integer-period
coherent window after a settling criterion tied to the bias loop and thermal
time constant, fixed small time step, DFT for the fundamental and harmonics,
PAE including bias/driver supply, and a known-answer check (resistor-loaded
ideal source = +3.979 dBm for 1 V behind 50 Ω into 50 Ω). The check has not
been run: no bench exists yet. It gates the first DUT record.

**Q4. Does ngspice's VBIC implementation include self-heating as used by the
PDK models, and how is it handled in the benches? — DEFERRED (D-2).**
Read: the `npn13G2` card sets `selft=1`, `rth = 3.26e3·(4/Nx)^0.9` K/W and
`cth = 1.6e-12·(Nx·0.25)^0.95` F and instantiates a 5-node VBIC `Q` with a
thermal node `t` (4-terminal subcircuit hides it, `*_5t` exposes it)
(`sg13g2_hbt_mod.lib` lines 42–48, 118–119). **Not read or tested:**
whether ngspice-46 solves that thermal node as the PDK intends. The spec
therefore plans a known-answer check before relying on it: a constant `P` into
the 5-terminal device and comparison of the node rise against `P·rth`
(settling `rth·cth` ≈ 5 ns for Nx = 4). Until that passes, results with
self-heating are labelled "self-heating unverified".

## Evidence

All quotes are from sources at the revisions named in the spec's "Sources"
table; none is from a testbench, because no bench exists yet.

- **Breakdown and current limits**: SG13G2 Process Specification Rev. 1.2
  (2023-12-20), §3.1 `npn13g2` and §3.2 `npn13g2l` (p. 20), §3.3 `npn13g2v`
  (p. 21): BVCEO min/max 1.4/1.6, 1.4/1.6, 2.2/2.5 V; BVCBO min/max
  3.8/4.8, 3.8/4.8, 7/8.5 V; ICMAX 3.5, 3.0, 0.5 mA; fT 300–350, 280–330,
  90–120 GHz; fmax 400–450, 380–430, 280–330 GHz. Current densities: §2.15
  (p. 16).
- **Validity window**: `sg13g2_hbt_mod.lib` (IHP-Open-PDK v0.3.0 install),
  `npn13G2` lines 33–36: `ic` < 0.003·Nx A, `vbe` 0.65–0.96 V, `vce`
  0.4–2.0 V, −40…+125 °C, Nx = 1–10; `npn13G2l` lines 269–272 (`vce`
  0.4–2.0 V); `npn13G2v` lines 503–506 (`ic` < 0.50·Nx·El A, `vbe`
  0.65–0.84 V, `vce` 0.8–2.3 V). The same window for `npn13G2` is quoted in
  `sg13g2-sat-rx` `spec/target-spec.md` at `b82e458`, which agrees.
- **PDK revision**: the install read carries `.fetched-version` = `0.3.0`,
  the revision `sg13g2-lna` pins in `sim/pdk.json` (`release_tag` v0.3.0). If
  issue #4 lands a `sim/pdk.json` first, that file's revision supersedes this
  naming; no second revision is named here.
- **Band and stability metric**: `sg13g2-lna` `spec/target-spec.md` at
  `50728637d958768ae1b4298d97145b70f18abf94` (identical `spec/` to `02c5ba2`,
  the commit named in the issue): "Band — RATIFIED 2400–2483.5 MHz"; stability
  μ > 1 from 10 MHz to 30 GHz with k, |Δ| and the negative-resistance check
  reported.
- **Corner sections**: `.LIB` names read from `cornerHBT.lib` (`hbt_typ`,
  `hbt_bcs`, `hbt_wcs`, plus `_mismatch`/`_stat`), `cornerMOShv.lib` and
  `cornerMOSlv.lib` (`mos_tt/ss/ff/sf/fs` plus `_mismatch`, `mos_tt_stat`),
  `cornerRES.lib` (`res_typ/bcs/wcs`), `cornerCAP.lib` (`cap_typ/bcs/wcs`).

## Alternatives considered

- **Ratify every row now with numbers.** Rejected: harmonic, thermal, area,
  supply and back-off-PAE numbers would be unbacked, which `CLAUDE.md`
  forbids ("no claim without a testbench").
- **Relax or reshape the ladder to what looks achievable.** Rejected: agents
  do not relax the spec; the README ladder is kept as is.
- **Split spec and record into two PRs.** Rejected: they ratify each other.
- **Characterize devices or the inductor here.** Rejected: later work, out of
  scope for a spec issue.
- **Treat the model's `vce_max = 1.6` as the breakdown budget.** Rejected: the
  process-spec minimum (1.4 V) is more conservative and is the documented
  figure.

## Consequences

- Design work can now verify against fixed rows; results outside the model
  window are labelled, not passed.
- The first bench must be the extraction known-answer check, and the first
  HBT bench must settle Q4 (self-heating).
- The DRAFT rows must be ratified by a follow-up record once evidence exists;
  until then, benches report those quantities with no pass/fail.
- A compressing PA leaves the card's `vce` floor (0.4 V / 0.8 V) in
  saturation, and at 125 °C ambient the junction exceeds the card's +125 °C
  ceiling. Many large-signal cells will therefore be labelled OUTSIDE MODEL
  WINDOW; that is expected, and the rows say how it is reported.
- The on-chip-output-match target is not evaluable through ideal passives, and
  stays unevidenced until D-1 is decided by the operator.
- The README fallback "off-chip output match" is a real ladder rung: the bench
  must define the chip boundary precisely.

## Deferred

- **D-1 — inductor-model source.** Options (a)–(c) above; recommendation (a).
  Needs the operator's `consumes` decision.
- **D-2 — DRAFT rows**: PAE at back-off threshold, large-signal stability
  line limit, supply nominal, device flavour/stacking, thermal limit,
  electromigration rule (DC vs RMS reading of §2.15), harmonic limits, area
  budget, and Q4 (self-heating check). Each to be ratified by a later record
  with evidence.

## klayout-tools gaps

None met while scoping: this issue is documentation and read-only inspection
of the PDK; no `klt` command was run. No issue was filed at
`2AMLogic/klayout-tools`.
