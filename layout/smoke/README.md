# layout/smoke -- DRC/LVS toolchain smoke test

**This is a toolchain smoke test on an IHP-Open-PDK reference cell
(`sg13g2_inv_1`). It is not a design result and says nothing about the PA.**

- `klt` **0.7.0** (`layout/toolchain.json`), run as `uvx --from klayout-tools==0.7.0 klt`
  (throwaway environment); KLayout 0.30.12 as reported in the envelopes.
- PDK: IHP-Open-PDK **v0.3.0** (`sim/pdk.json`), fetched by `scripts/setup-env.sh`
  into `~/.cache/sg13g2-pa/pdk-root`.
- Cell: `sg13g2_inv_1`, copied unmodified from
  `ihp-sg13g2/libs.tech/klayout/tech/lvs/testing/testcases/sg13g2_cells/sg13g2_inv_1/`
  (`layout/sg13g2_inv_1.gds` -> `sg13g2_inv_1.gds`, `netlist/sg13g2_inv_1.cdl` -> `sg13g2_inv_1.cdl`).
  The GDS has three top cells; `--top sg13g2_inv_1` selects one.

## Run (from this directory)

```
scripts/setup-env.sh            # once, from the repo root
cd layout/smoke
K="uvx --from klayout-tools==0.7.0 klt"
$K drc --format json --deck sg13g2 --top sg13g2_inv_1 --pdk ihp-sg13g2 \
       --pdk-root ~/.cache/sg13g2-pa/pdk-root sg13g2_inv_1.gds           > reports/drc.json
$K lvs --format json lvs-pdk-cdl.request.json                            > reports/lvs-pdk-cdl.json   # exit 3
$K lvs --format json lvs-simform.request.json                            > reports/lvs-simform.json   # exit 0
$K drc --check reports/drc.json; $K lvs --check reports/lvs-simform.json # inputs unchanged
```

`--check` verifies the recorded input and deck hashes; add `--rerun` for a full
re-run. Envelopes carry no absolute paths.

## Results (simulated tooling output, curated `klt` engine, not a signoff)

| Report | Status |
|---|---|
| `reports/drc.json` (`klt drc`, deck `sg13g2`) | `clean`, 0 violations |
| `reports/lvs-simform.json` (`klt lvs`, reference converted to X-call form) | `match`; nets 4/4, devices 2/2, body verification `verified` |
| `reports/lvs-pdk-cdl.json` (`klt lvs`, PDK CDL as shipped) | **`mismatch`**, 16 entries, 0 devices/nets paired |

### DRC coverage fields (from `reports/drc.json`, `coverage`)

A clean DRC here covers only part of the PDK rules; read it with these.

- `deck_scope`: `Act, Cnt, Gat, M1, M2, M3, M4, M5, MIM, TM1, TM2, TV1, TV2, V1, V2, V3, V4`
- `layers_in_stream_without_rules` (drawn in the GDS, no rule in the curated deck):
  `8/2, 8/25, 14/0, 31/0, 32/0, 60/0, 189/4`
- `rules_skipped`: 34 rules, all via/metal2-and-above/MIM/TopMetal width, space and
  enclosure rules. `coverage.skipped` is `[]` and the same 34 appear in
  `coverage.inapplicable` with reason `no_applicable_geometry`: the cell has no
  geometry on those layers, so they did not apply, they were not unsupported.
  Checked: 11 rules (activ, cont, gatpoly, metal1).

### LVS: the PDK CDL does not compare as shipped

The shipped CDL uses `M` cards naming `sg13_lv_nmos`/`sg13_lv_pmos`. `klt lvs`
keeps those as device classes `SG13_LV_NMOS`/`SG13_LV_PMOS`, which never pair
with the extracted `nfet`/`pfet`, giving `lvs-pdk-cdl.json`'s mismatch (not a
layout defect). `sg13g2_inv_1.sim.spice` is the same two devices rewritten by hand
as `X` subcircuit calls (device names, nets, `m/w/l/ng` unchanged) and compared
with `reference.form: "subckt-call"`; that is the `match` above. The match
therefore rests on this derived reference, not on the PDK file. The `sim.spice`
rewrite is not a `klt` feature.

Upstream gap: 2AMLogic/klayout-tools#3882. No other `klt` gap was found. The
DRC envelope's `provenance.pdk.version` is `null` at 0.7.0 (already tracked and
closed upstream as klayout-tools#3070, so not refiled).
