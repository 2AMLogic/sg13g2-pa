# layout

`smoke/` holds the DRC/LVS toolchain smoke test on a PDK reference cell (not a
design result); `toolchain.json` pins `klt` for it (0.7.0). `pa/` holds the PA
layout described below. See the repo README for scope.

## `pa/`: PA core placement (T1 item 2)

`pa/sg13g2_pa.gds` is **reproducibly generated** by `pa/generate.sh` from the
committed netlist `design/netlist/sg13g2-pa.spice`. `pa/provenance.json` records
the netlist's sha256, the generator script's sha256, the `klt` pin, the PDK
release and the GDS sha256. Regenerate with `layout/pa/generate.sh` (needs the
pinned PDK; `source sim/env.sh` is done by the script). Verify with
`layout/pa/generate.sh --check`: it regenerates into a temp dir and fails if the
GDS bytes or the provenance differ, so a netlist, script or pin change turns the
committed layout stale. The two GDS regenerations done while writing this were
byte-identical. The check needs the PDK, so it is local-only and is not a step
in the stock-runner `signoff` workflow.

The generator runs `klt gen bjt_array` (rows 2, columns = devices / 2) under
`uvx --from klayout-tools==0.9.1`. This is the pin the generator needs: the
sg13g2 HBT flavor of `bjt_array` and `klt signoff --attest 2` are not in 0.7.0
or 0.8.0. It is also the `signoff` workflow pin. `toolchain.json` and the
smoke test stay at 0.7.0 and are a separate concern.

### What this layout is, and is not

- **Placement only.** 14 PDK `npn13G2` cells, one per `XQ1`..`XQ14` in the
  netlist, in a 2 x 7 grid (bounding box 58.9 x 16.22 um). Nothing is wired:
  no collector, base or emitter routing, no supply or ground straps, no
  RF in/out routing, no pads.
- **Not drawn:** the bias device `XQref`, `Rb`, `Cin`, `Cblock` and `Lchoke`.
  The choke is an inductor and inductor sourcing is deferred (decision record
  0001, D-1); no inductor model or spiral is built here. Where the choke and
  match live (on-chip or off-chip) is not decided by this layout.
- **Electromigration: nothing to size yet.** No output-path metal is drawn, so
  there are no widths or currents to record against the DRAFT EM row in
  `spec/target-spec.md`. The row is not ratified here and no EM pass is
  claimed. Sizing the routing against the (P) section 2.15 limits belongs with
  the routed layout.
- **Netlist correspondence is unproven.** The netlist devices are `Nx=10`; the
  PDK `npn13G2` cell is a fixed layout and `klt gen` ignores the `Nx` parameter
  (generator note in `provenance.json`). The base cell carries two `EmWind`
  (33/0) shapes. Whether one fixed cell stands for an `Nx=10` device is not
  established; it is settled by extraction and LVS, not by this item. The
  generator states that LVS recognition of `npn13G2` is not claimed.
- **No clean DRC or LVS result is claimed** (items 3 and 4). The pinned DRC run
  is recorded in `reports/drc.json` and is `violations` (28, `cont.width.1`);
  see `manifests/README.md`, "T1 item 3 (DRC)". The item-2 envelope
  (`evidence/item2.json`) only checks that the stream reads, has a non-empty
  top cell and a dbu on grid, and binds the GDS by content hash.
