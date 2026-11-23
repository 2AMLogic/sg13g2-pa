# sg13g2-pa

A SiGe HBT power amplifier on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), IHP's open-source
130 nm SiGe BiCMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**The core spec is ratified. The first topology has provisional results across a
27-cell process, voltage and temperature (PVT) matrix.**

**No bench row below is a pass claim against the ratified spec.** Every
matched-Psat cell is flagged `BREAKDOWN VIOLATION; OUTSIDE MODEL WINDOW`
(peak `V_CE` 3.781–5.375 V against the ~1.4 V minimum BVCEO documented
below), so those figures are outside the VBIC model card's validity window and
are not quoted as passes.

- **Spec.** The core rows of [`spec/target-spec.md`](spec/target-spec.md) are
  ratified by
  [decision record 0001](spec/decision-records/0001-ratify-target-spec.md),
  amended for the Device-stress row by
  [DR 0002](spec/decision-records/0002-device-stress-target-cell.md). The rows
  marked DRAFT in the table below are **not** ratified, and the
  inductor/passive-model source is deferred on an operator decision
  (DR 0001, D-1).
- **Topology.** A single-stage `npn13g2` array,
  [DR 0003](spec/decision-records/0003-first-topology-single-npn13g2.md) —
  **PROPOSED, not ratified.** A schematic and its derived netlist are
  committed.
- **Layout.** **Placement only**: 14 `npn13G2` cells in a 2 × 7 grid, nothing
  wired, no pads, and `XQref`, `Rb`, `Cin`, `Cblock` and `Lchoke` not drawn
  ([`layout/README.md`](layout/README.md)). DRC is clean on that stream;
  **LVS has not been run.**
- **Simulation.** The AC gain and stability benches each produced results for
  24 of 27 cells; the same three 125 °C cells returned no figures
  (`status: error`; diagnosis open in #188). The matched Psat bench simulated all 27 cells and extracted figures for 25.
  At two cold cells the drive steps were too coarse to extract the figures.
  All three benches use ideal passives, and the Supply row is still DRAFT.
  The matched bench uses an ideal, lossless off-chip L-section at the spec's
  *Fallback* output boundary. The *Target* on-chip match awaits the passive
  model decision in DR 0001 D-1. See [bench conditions and records](sim/README.md).

Per-item state is the signoff record's to report, not this file's — see **T1
status** just below. The near-term plan is [`WORK_PLAN.md`](WORK_PLAN.md).

**T1 status.** The tier verdict is graded by `klt signoff`, not read by hand;
the verdict of record is
[`manifests/sg13g2-pa.signoff.json`](manifests/sg13g2-pa.signoff.json), and
[`manifests/README.md`](manifests/README.md) says how it is regenerated and
checked in CI.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result that states its corner and testbench, and PVT-matrix coverage
is graded by the signoff record (item 5), not asserted here. Where the agents
hit friction with the open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using SG13G2, not just this repo.

## Why this block, on this PDK

The receive side of the SG13G2 RF canaries (`sg13g2-lna`, `sg13g2-mixer`)
is small-signal. A power amplifier is the transmit-side counterpart and the
opposite kind of problem: large-signal, efficiency-driven, and bounded by
breakdown rather than noise.

That makes it a hard, honest test of the open PDK and tools:

- **Breakdown sets the design.** SG13G2's PDK documents three HBT flavours.
  The high-speed `npn13g2` / `npn13g2l` have a collector-emitter breakdown
  (BVCEO) of about 1.4 V minimum; `npn13g2v` trades fT for a higher BVCEO,
  about 2.2 V minimum. A PA's collector swings well beyond its supply, so
  device choice, stacking and the load line are first-order decisions.
- **The model card has a validity window.** The VBIC HBT models are
  characterized over a stated `V_CE` range; a PA's peak swing can leave it.
  Every result has to say where it sits relative to that window.
- **The output network is passive-limited.** The output match and any
  harmonic termination need inductors. Their models, losses and
  self-resonance are where an open-PDK PA is most likely to be wrong.
- **Thermal and electromigration limits** on the output devices and the
  top-metal routing become first-order, which exercises the rule deck in
  places a small-signal block never reaches.

## Scope

- **In scope**: a driver and output stage, their bias, the on-chip output
  match (or a stated off-chip boundary), and the testbench load.
- **Not in scope**: the upconversion mixer, the LO, a transmit/receive
  switch, and any linearization (digital predistortion, envelope tracking).

## Target specification (see [`spec/target-spec.md`](spec/target-spec.md))

Ratified by [decision record 0001](spec/decision-records/0001-ratify-target-spec.md)
on approval of its PR. Rows marked DRAFT are not ratified yet. The spec file
is authoritative; this table is a summary of it and must match it. All rows
are *targets*, not results. The band follows the sibling LNA's ratified band
(`sg13g2-lna` `50728637`) so the RF canaries share one frequency plan.

| Parameter | Fallback | Target | Stretch |
|---|---|---|---|
| Band | 2400–2483.5 MHz | 2400–2483.5 MHz | — |
| Saturated output power | > +10 dBm | > +15 dBm | > +20 dBm |
| Output P1dB | > +7 dBm | > +12 dBm | > +17 dBm |
| Power gain | > 10 dB | > 15 dB | > 20 dB |
| Peak PAE | > 15% | > 25% | > 35% |
| PAE at back-off (Psat − 6 dB) — DRAFT | reported, no threshold | reported, no threshold | — |
| Input match (S11) | < −8 dB | < −10 dB | < −15 dB |
| Ports | 50 Ω, off-chip output match | 50 Ω, on-chip output match | — |
| Inductor / passive models — DRAFT | each inductor's source, Q and self-resonance stated at every use; source deferred (operator `consumes` decision) | same | — |
| Stability, small-signal | μ > 1, 10 MHz–30 GHz, every corner (k, \|Δ\|, negative-resistance check reported) | same | — |
| Stability, large-signal — DRAFT | no sustained non-harmonic line, threshold not set | same | — |
| Supply — DRAFT | single rail, nominal set by the first load-line study, ±10% | same | — |
| Device and stacking — DRAFT | single `npn13g2` first; stack or `npn13g2v` only if the target cannot close with margin | same | stack/`npn13g2v` for +20 dBm only |
| Device stress | no device beyond its documented breakdown over the full swing, every corner | same, inside the model card's validity window | — |
| Thermal, electromigration — DRAFT | junction temperature reported; PDK current-density limits applied after layout | same | — |
| Harmonics (2nd, 3rd) — DRAFT | reported at Psat and Psat − 6 dB, no threshold | same | — |
| Area — DRAFT | reported | reported | — |
| Signoff | DRC + LVS clean | DRC + LVS clean, post-layout re-verified | — |

Maturity ladder: spec ratified → device and passive characterization →
schematic simulated across PVT → layout DRC/LVS-clean → post-layout
re-verification → shuttle seat → measured silicon.
The `npn13g2` load-line study and provisional schematic PVT runs are recorded.
Passive characterization awaits the inductor-source decision (DR 0001 D-1).
The placement-only layout is DRC-clean. LVS is pending.

## Tool flow

- **Design and simulation**: xschem + ngspice with the SG13G2 VBIC HBT
  models; S-parameter benches for match and stability, transient
  large-signal benches for output power, compression and efficiency.
- **Layout, DRC, LVS**: klayout-tools (`klt`).

## Reproduce

Every committed result has one documented command. Run them from the repo
root. `scripts/setup-env.sh` fetches the pinned PDK and builds the OSDI models
into `~/.cache/sg13g2-pa`; it installs nothing host-wide. Simulation grids go
through `klt sim` (the Spot batch fleet on dispatch workers via
`KLT_SIM_BACKEND=batch`) and are never hand-launched as `ngspice -b` loops.

| Result | Command | Output |
|---|---|---|
| Environment (PDK + OSDI) | `scripts/setup-env.sh` (`--check` verifies only, offline) | `~/.cache/sg13g2-pa` |
| Toolchain smoke (inverter corners, one `npn13g2` operating point) | `sim/smoke/run_smoke.sh` | `sim/smoke/records/` |
| Known-answer check of `sim/lib/rf_extract.py` | `sim/known-answer/run.sh` (`--wrong-load` is the negative control and is expected to exit 1) | `sim/known-answer/records/` |
| `npn13g2` device load-line study | `sim/device-npn13g2/run_device.sh` | `sim/device-npn13g2/records/` |
| Psat, P1dB, peak PAE, large-signal S11, device stress and harmonics | `sim/psat-sweep/run_psat_sweep.sh` for the bare 50 Ω nominal cell, or `sim/psat-sweep/run_psat_sweep.sh --match` for the 27-cell off-chip match | `sim/psat-sweep/records/` |
| Power gain and small-signal S11 over the band | `sim/ac-gain/run_ac_gain.sh` | `sim/ac-gain/records/` |
| Small-signal stability (μ, μ', k, \|Δ\|, negative-resistance check, 10 MHz–30 GHz) | `sim/ac-stability/run_ac_stability.sh` | `sim/ac-stability/records/` |
| PA layout reproduces from the committed netlist | `layout/pa/generate.sh --check` | pass/fail on stdout; binds `layout/pa/sg13g2_pa.gds` and `layout/pa/provenance.json` |
| PA DRC report is fresh against the committed stream and deck | `uvx --from "klayout-tools==0.9.1" klt drc --check layout/reports/drc-klt-0.9.1.json` | `status: match` on stdout; the report is `layout/reports/drc-klt-0.9.1.json` |
| Layout smoke DRC/LVS (reference cell, not the PA) | the `klt drc` / `klt lvs` commands in [`layout/smoke/README.md`](layout/smoke/README.md) | `layout/smoke/reports/` |
| Tier verdict of record | the `klt signoff --manifest` command in [`manifests/README.md`](manifests/README.md) | `manifests/sg13g2-pa.signoff.json` |
| Unit tests | `python3 -m pytest sim/lib` (needs only numpy and pytest) | stdout |

The environment, smoke, known-answer, device load-line, layout-smoke, tier
verdict and unit-test rows are toolchain, characterization or hygiene checks,
not PA design results. The five rows for the DUT benches, the layout generator
and the PA DRC report cover the proposed PA, under a PROPOSED topology and
through ideal passives, so none of them is a pass claim against the ratified
spec. Each simulation record states its corner, testbench and findings. The DRC report covers the placement-only
layout. The three bench scripts and `layout/pa/generate.sh --check` need the
PDK (`scripts/setup-env.sh` first); `klt drc --check`, the tier verdict and the
unit tests do not.

## Repo layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
