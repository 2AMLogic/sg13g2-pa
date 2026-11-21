# mc-pilot — Monte Carlo pilot (issue #174)

This **pilot** measures the variation the pinned PDK's HBT
statistical model sections and the batch runner can actually measure on this
design, at the nominal cell (`hbt_*` statistical sections, 27 C, Vcc 0.8 V),
on a design that **does not yet meet its ratified rows** (`ROADMAP.md`). Its
record is the evidence the PROPOSED decision record
[`spec/decision-records/0005-statistical-rows.md`](../../spec/decision-records/0005-statistical-rows.md)
draws its feasibility findings from; it is never a yield claim and never a
pass/fail claim.

## What runs

| Request | Bench | PDK section | What varies |
|---|---|---|---|
| `mc_op_stat.request.json` | `mc_op.spice` (DC operating point, per-device quiescent Ic) | `hbt_typ_stat` | process-only: `sg13g2_hbt_stat.lib` global `gauss()` multipliers, one draw per die, common to every instance |
| `mc_op_mismatch.request.json` | same | `hbt_typ_mismatch` | per-instance: `qarea = agauss(1, 0.1, mm_ok ? 1 : 0)` in `sg13g2_hbt_mod_mismatch.lib` |
| `mc_ac_stat.request.json` | `mc_ac_gain.spice` (byte-identical to the attested `../ac-gain/ac_gain.spice`) | `hbt_typ_stat` | as above |
| `mc_ac_mismatch.request.json` | same | `hbt_typ_mismatch` | as above |
| `probe_scale.request.json` | DC probe, `--backend local` | `hbt_typ_mismatch` | `monte_carlo.mismatch_scale: 0` — **refused before any draw at the pinned 0.9.0 client**; the refusal is the evidence |
| `probe_instances.request.json` | DC probe, `--backend local` | `hbt_typ_mismatch` | `monte_carlo.instances: {include: [x1.xq1]}` — same refusal |

The two sections are run **separately** (not `both`) so the two mechanisms are
measured apart: the same-draw difference between identically biased output
devices carries only mismatch, the shared movement across draws carries
process and the common mirror bias. One draw's 14 output collector currents
stay separate all the way into the record (`ic1..ic14`, `ic_total`,
`ic_diff_12`, plus the diode-connected reference `ic_ref` tracked on its own);
nothing divides the array current by 14, which would erase the mismatch being
measured. The AC side reads the forward-driven DUT copy (`X1`) for min
in-band S21 and worst in-band S11 per draw, over the committed ac-gain
sweep's 11 points.

## Cold start

```sh
scripts/setup-env.sh && sim/mc-pilot/run_mc_pilot.sh
```

Requires Python 3, NumPy and a configured batch submitter. The
four runs go to the Spot batch fleet (the requests carry
`batch.capacity_wait_s: 600`); a submit that still fails is reported and its
refusal is committed as the record — never rerun locally, never a hand loop.
The record lands in `records/<timestamp>-<sha>.{md,json}` (append-only) with
the klt artifacts under `corners/<id>/`.

## Item 9 cold start

The inventory includes all six requests and invokes `run_mc_pilot.sh` once.
Each baseline request must complete on batch for the cold start to pass.
A refused baseline is recorded and returns a failure. A simulator error in a
corner log stops the runner before it publishes measurement conclusions.
The original feasibility record remains the basis for proposed statistical
rows pending operator ratification. [Item 9 inventory](../../attest/item9.json)

## Known tool limits this pilot records (not works around)

- `monte_carlo.mismatch_scale` / `instances` are curated to sky130/gf180mcu;
  the pinned 0.9.0 client **refuses** them for `ihp-sg13g2` before any draw —
  [2AMLogic/klayout-tools#5486](https://github.com/2AMLogic/klayout-tools/issues/5486).
  The sg13g2 `instances` work (`mm_ok` gating) landed upstream only after the
  0.9.0 pin — [2AMLogic/klayout-tools#5487](https://github.com/2AMLogic/klayout-tools/issues/5487)
  — and the measured two-point scaling check it still wants is
  [2AMLogic/klayout-tools#5503](https://github.com/2AMLogic/klayout-tools/issues/5503).
- `vary: "process"` is **not** a zero-mismatch control for this deck family:
  klt feeds ngspice one combined `.options seed=` per draw, so a deck whose
  mismatch is `agauss()` in `.param` re-rolls under any axis. The honest
  control rows in the record are structural (the stat section's exactly-zero
  within-draw spread), and a declared control waits on the upstream work.
- klt's own `family_mismatch` report says the HBT `bipolar` family is "not
  independently verified" active for sg13g2; the pilot's completed draws are
  that verification.

Everything here is **simulated**, through the DUT's **ideal** output passives
and an ideal bias source (`Iref`, `Rb` contribute no variation; only the 15
HBTs are PDK devices, so the resistor/capacitor statistical sections reach
nothing in this netlist).
