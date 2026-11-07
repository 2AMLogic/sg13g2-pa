# design

Design sources for the PA: one xschem schematic, a project-local `xschemrc`,
and the SPICE netlist derived from them. T1 item 1 (design sources) attests
this set; see [`attest/item1.json`](../attest/item1.json).

## Contents

| File | Role |
|---|---|
| `sg13g2-pa.sch` | Source. Single flat schematic with three labelled groups: PA core, bias, matching / bias feed |
| `xschemrc` | Source. Symbol search path: xschem's stock `devices/` plus the PDK's `libs.tech/xschem` (`sg13g2_pr/npn13G2.sym`). Reads `$PDK_ROOT` and `$PDK` |
| `netlist/sg13g2-pa.spice` | Derived by `klt netlist --block`; an includable `.subckt sg13g2-pa RFIN RFOUT VCC GND`. Never hand-edited |

The schematic is a single flat sheet rather than three sub-schematics: with
one stage there is no hierarchy to justify symbols for each part. The three
groups are labelled on the sheet.

## Topology and what it is (and is not)

Taken as-is from [`spec/decision-records/0003-first-topology-single-npn13g2.md`](../spec/decision-records/0003-first-topology-single-npn13g2.md),
which is **PROPOSED, not ratified**:

- Device `npn13G2`; 14 instances of `Nx=10` in parallel (140 Nx units); a
  single common-emitter stage, no stack.
- Supply nominal 0.8 V. The supply is a testbench matter (`VCC` is a port);
  the netlist carries no source. Supply, flavour and thermal spec rows stay
  DRAFT.
- **Matching is ideal passives only.** `Lchoke` (VCC to collector), `Cblock`
  (collector to `RFOUT`) and `Cin` (`RFIN` to the base bus) are lossless,
  with no self-resonance. Their values (100 nH, 100 pF, 100 pF) are
  non-tuned placeholders for bias feed and DC blocking, not a match, and are
  not derived from any band. `RFOUT` is the off-chip match boundary. The
  band follows `sg13g2-lna`'s ratified band and has not been cited here yet.
  Any Pout or PAE figure derived from this netlist is **through ideal
  passives**.
- **Bias** is an ideal 1 mA reference current into a diode-connected
  `npn13G2` (`Nx=10`), mirrored 1:14 to the array through `Rb` (1 kΩ). The
  1 mA, the 1 kΩ and the resulting quiescent current are placeholders: the
  bias point is set against the load-line record by the large-signal bench,
  not by this issue. No temperature or beta compensation is modelled.
- No inductor model is used and no `sg13g2-vco` inductor number appears. The
  `consumes` question (DR 0001 D-1) stays open and flagged.
- No breakdown, `V_CE`/`V_CB` peak, Pout or PAE claim is made by this
  netlist; it has not been simulated.

## Regenerate the netlist

`klt netlist` owns the xschem invocation (headless flags, hang kill); never
run `xschem` directly. It needs xschem and the pinned SG13G2 PDK
(`sim/pdk.json`: `v0.3.0`); `source sim/env.sh` sets `PDK` and `PDK_ROOT`.

```console
source sim/env.sh
uvx --from "klayout-tools==0.8.0" klt netlist design/sg13g2-pa.sch \
    -o design/netlist/sg13g2-pa.spice --rcfile design/xschemrc --block
```

## Check for drift (non-mutating)

```console
uvx --from "klayout-tools==0.8.0" klt netlist design/sg13g2-pa.sch \
    -o design/netlist/sg13g2-pa.spice --rcfile design/xschemrc --block --check
```

Exit `0` (`status: match`) when the committed netlist is what the schematic
produces, `3` (`status: drifted`) when it is not. Nothing is written. Shown
at creation: changing `100n` to `101n` in the committed netlist makes this
exit `3`; restoring it exits `0`. A stock CI runner has neither xschem nor
the PDK, so the inventory marks this check `local_only`: `klt signoff
--attest 1 --check` re-hashes the files there and skips this command,
reporting its committed outcome.

After any change to the schematic, `xschemrc` or the netlist, re-attest and
regenerate the verdict record, in that order (see
[`manifests/README.md`](../manifests/README.md)).
