# layout/smoke -- DRC/LVS toolchain smoke test

**This is a toolchain smoke test on an IHP-Open-PDK reference cell
(`sg13g2_inv_1`). It is not a design result and says nothing about the PA.**

- `klt` **0.9.1** (`layout/toolchain.json`). The reports record KLayout 0.30.14.
- PDK: IHP-Open-PDK **v0.3.0** (`sim/pdk.json`), fetched by `scripts/setup-env.sh`
  into `~/.cache/sg13g2-pa/pdk-root` by default. The DRC report records
  `provenance.pdk.version` as `fetched:0.3.0`.
- Cell: `sg13g2_inv_1`, copied unmodified from
  `ihp-sg13g2/libs.tech/klayout/tech/lvs/testing/testcases/sg13g2_cells/sg13g2_inv_1/`
  (`layout/sg13g2_inv_1.gds` -> `sg13g2_inv_1.gds`, `netlist/sg13g2_inv_1.cdl` -> `sg13g2_inv_1.cdl`).
  The GDS has three top cells; `--top sg13g2_inv_1` selects one.

## Run from the repository root

```
scripts/setup-env.sh            # once
cd layout/smoke
K="uvx --from klayout-tools==0.9.1 klt"
pdk_root="${SG13G2_TOOLS_CACHE:-$HOME/.cache/sg13g2-pa}/pdk-root"
$K drc --format json --deck sg13g2 --top sg13g2_inv_1 --pdk ihp-sg13g2 \
       --pdk-root "$pdk_root" sg13g2_inv_1.gds                           > reports/drc.json
$K lvs --format json lvs-pdk-cdl.request.json                            > reports/lvs-pdk-cdl.json   # exit 3
$K lvs --format json lvs-simform.request.json                            > reports/lvs-simform.json   # exit 0
$K drc --check reports/drc.json
$K lvs --check reports/lvs-pdk-cdl.json
$K lvs --check reports/lvs-simform.json
```

`--check` verifies the recorded input and deck hashes. All three checks report
`match`, including the one for the expected CDL mismatch. To reproduce the
reports, repeat the three generation commands above. The DRC command selects
`sg13g2_inv_1` from the three top cells and records the PDK used.

## Results (simulated tooling output, curated `klt` engine, not a signoff)

| Report | Status |
|---|---|
| `reports/drc.json` (`klt drc`, deck `sg13g2`) | `clean`, 0 violations |
| `reports/lvs-simform.json` (`klt lvs`, reference converted to X-call form) | `match`; nets 4/4, devices 2/2, body verification `verified` |
| `reports/lvs-pdk-cdl.json` (`klt lvs`, PDK CDL as shipped) | **`mismatch`**, 16 entries, 0 devices/nets paired |

### DRC coverage fields (from `reports/drc.json`, `coverage`)

- `deck_scope` lists 19 scopes (`Act, Cnt, Gat, M1, M2, M3, M4, M5, MIM, NW, TM1, TM2, TV1, TV2, V1, V2, V3, V4, pSD`).
- Five layers drawn in the GDS have no rule in the curated deck
  (`layers_in_stream_without_rules` lists `8/2, 8/25, 32/0, 60/0, 189/4`).
- `rules_checked` lists 22 rules for activ, cont, gatpoly, metal1, nwell and psd.
- All 40 entries in `rules_skipped` appear in `coverage.inapplicable` with reason
  `no_applicable_geometry`. They include six nwell rules for nactiv.
  `coverage.skipped` is empty.
- `unchecked_rules` names `NW.b1`, which requires net-aware well spacing.
  `unmodeled_rules` lists 14 latch-up and pad rules.

### LVS: the PDK CDL does not compare as shipped

The shipped CDL uses `M` cards naming `sg13_lv_nmos`/`sg13_lv_pmos`. `klt lvs`
keeps those as device classes `SG13_LV_NMOS`/`SG13_LV_PMOS`, which never pair
with the extracted `nfet`/`pfet`, giving `lvs-pdk-cdl.json`'s mismatch (not a
layout defect). `sg13g2_inv_1.sim.spice` is the same two devices rewritten by hand
as `X` subcircuit calls (device names, nets, `m/w/l/ng` unchanged) and compared
with `reference.form: "subckt-call"`; that is the `match` above. The match
therefore rests on this derived reference, not on the PDK file. The `sim.spice`
rewrite is not a `klt` feature.

The shipped-CDL comparison is tracked in [klayout-tools#3882](https://github.com/2AMLogic/klayout-tools/issues/3882).
