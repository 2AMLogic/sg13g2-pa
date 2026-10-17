# sg13g2-pa

A SiGe HBT power amplifier on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), IHP's open-source
130 nm SiGe BiCMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened, specification phase.** Nothing is designed yet.

**T1 status.** The tier verdict is graded by `klt signoff`, not read by hand;
the verdict of record is
[`manifests/sg13g2-pa.signoff.json`](manifests/sg13g2-pa.signoff.json), and
[`manifests/README.md`](manifests/README.md) says how it is regenerated and
checked in CI.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
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

## Target specification (DRAFT — engineering to ratify, see issue #1)

All rows are *targets*, not results. The band follows the sibling LNA's
ratified band so the RF canaries share one frequency plan; the spec issue
may change it with a decision record.

| Parameter | Fallback | Target | Stretch |
|---|---|---|---|
| Band | 2400–2483.5 MHz | 2400–2483.5 MHz | — |
| Saturated output power | > +10 dBm | > +15 dBm | > +20 dBm |
| Output P1dB | > +7 dBm | > +12 dBm | > +17 dBm |
| Power gain | > 10 dB | > 15 dB | > 20 dB |
| Peak PAE | > 15% | > 25% | > 35% |
| Input match (S11) | < −8 dB | < −10 dB | < −15 dB |
| Ports | 50 Ω, off-chip output match | 50 Ω, on-chip output match | — |
| Stability | unconditional across the full sweep, every corner | same | — |
| Device stress | no device beyond its documented breakdown over the full swing, every corner | same, inside the model card's validity window | — |
| Signoff | DRC + LVS clean | DRC + LVS clean, post-layout re-verified | — |

Maturity ladder: spec ratified → device and passive characterization →
schematic simulated across PVT → layout DRC/LVS-clean → post-layout
re-verification → shuttle seat → measured silicon.
**Current position: pre-spec.**

## Tool flow

- **Design and simulation**: xschem + ngspice with the SG13G2 VBIC HBT
  models; S-parameter benches for match and stability, transient
  large-signal benches for output power, compression and efficiency.
- **Layout, DRC, LVS**: klayout-tools (`klt`).

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
