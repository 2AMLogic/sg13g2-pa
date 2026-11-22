# sim

Simulation environment and evidence for the SG13G2 PA. Results here are
**simulated** (ngspice), always labelled with their corner and testbench, and
`records/` entries are append-only.

## Cold start

From a fresh clone, with `ngspice`, `python3`, `curl`, `tar` and `dpkg-deb` on
`PATH` and `uvx` for the pinned `klt`:

```sh
scripts/setup-env.sh         # fetch the pinned PDK, build OSDI, verify (~1 min + ~350 MB download)
sim/smoke/run_smoke.sh       # toolchain smoke test; writes sim/smoke/records/<timestamp>-<sha>.md
```

`scripts/setup-env.sh --check` verifies an existing install offline. Everything
lands in `~/.cache/sg13g2-pa` (override: `SG13G2_TOOLS_CACHE`); no host-wide
tool is installed or changed. `source sim/env.sh` resolves `PDK_ROOT` / `PDK`
for an interactive session.

`setup-env.sh` fails closed, with a named error and a non-zero exit:

| Error | Meaning |
|---|---|
| `NGSPICE_NOT_FOUND` | no `ngspice` on `PATH` |
| `FETCH_SCRIPT_CHECKSUM_MISMATCH` | the klayout-tools fetch script does not match its pinned sha256 |
| `PDK_CHECKSUM_MISMATCH` | the IHP-Open-PDK tarball failed its pinned sha256 |
| `PDK_IDENTITY_MISMATCH` / `PDK_IDENTITY_UNVERIFIABLE` | the installed release (`.fetched-version`) is not the one in `sim/pdk.json`, or cannot be told |
| `OSDI_MISSING` | OSDI objects absent; run `sim/tools/build-osdi.sh` |
| `NGSPICE_TOO_OLD_FOR_OSDI` | objects built, but ngspice < 44 cannot load OSDI 0.4 (see below) |

## PDK pin

`sim/pdk.json`: IHP-Open-PDK `v0.3.0`, `ihp-sg13g2`. Every record must trace to
it. A release bump is a change to `sim/pdk.json` and `scripts/setup-env.sh`
together, with a decision record under `spec/decision-records/`.

## klt pin

`sim/toolchain.json` pins `klt` 0.9.0 (was 0.7.0 until 2026-11-07). The batch fleet's
runner runs 0.9.0 and refuses a client of another version, so every grid bench needs the
matching client. Records produced before the bump (smoke, known-answer, device) name
0.7.0 in their own provenance and stay as they are.

## OSDI device models

The core and HV MOS devices are PSP103.6 Verilog-A; ngspice needs compiled OSDI
objects, which the release tarball does not ship. `sim/tools/build-osdi.sh`
compiles the PDK's own sources with a checksum-pinned OpenVAF-Reloaded
(`v24.0.1mob`) into `PDK_ROOT/ihp-sg13g2/libs.tech/ngspice/osdi/` (not
committed). `npn13G2` is a native VBIC card and needs none.

**ngspice floor.** OpenVAF-Reloaded emits OSDI 0.4; ngspice-43 and earlier
accept only 0.3. A MOS deck therefore needs ngspice >= 44 (enforced as
`NGSPICE_OSDI_MIN_MAJOR=44` in `sim/tools/build-osdi.sh`). Every host on this
fleet clears that floor today (batch and dispatch workers both run ngspice-47,
verified 2026-11-15 from the `sim/*/records/` worker banners and this dispatch
worker's `ngspice --version`); the floor is a requirement on the host, not a
version this repo pins. A host below it can still fetch
the PDK, build the objects and run the HBT, but cannot load the MOS devices
locally: `setup-env.sh` then exits `NGSPICE_TOO_OLD_FOR_OSDI`, downgraded to a
warning only when `KLT_SIM_BACKEND=batch`, because `klt sim` runs the MOS decks
on the fleet. No current fleet host takes that path; the sentence describes
what such a host would hit, not the hosts that exist today.

## DUT benches (one per ratified electrical row)

Run against `design/netlist/sg13g2-pa.spice` (topology DR 0003, **PROPOSED**; **ideal
passives** in the output network, so no output-power or PAE figure is an on-chip result).
The three characterization benches (`psat --match`, `ac-gain`, `ac-stability`) cover the
full PVT corner box (issue #173): 3 `cornerHBT.lib` sections (`hbt_typ`, `hbt_bcs`,
`hbt_wcs`) x -40/27/125 C x supply 0.72/0.8/0.88 V (nominal +/-10 %), declared once in
`sim/pvt-matrix.json` (the psat drive-crossed variant in
`sim/psat-sweep/psat_sweep_match.pvt-matrix.json`) and checked against every request and
report with `klt corner-matrix` before any submit. The bare psat variant stays
nominal-only: its 50 ohm harmonic terminations differ from the matched bench the ratified
rows are judged on, so its figures are not comparable across the matrix. Every verdict
from the matrix benches is **provisional** (Supply row DRAFT, DR 0003 PROPOSED). Cold
start, after `scripts/setup-env.sh` and with `python3` + `numpy` available:

| Spec rows | Bench | Cold-start command | Where it runs |
|---|---|---|---|
| Psat, P1dB, peak PAE, large-signal S11, device stress (peak `V_CE`/`V_CB`/`V_BE`/`I_C`/T_j per device, window labelling), harmonics and back-off PAE reported | `psat-sweep/` | `sim/psat-sweep/run_psat_sweep.sh` | one `klt sim` request, nominal cell only, 72 drive points: the batch fleet; a submit refused for capacity is waited out by `klt` (`batch.capacity_wait_s` 600 in the request), never run locally |
| The same rows, **through an ideal off-chip output match** (study variant, see "The off-chip output match" below), over the full 27-cell PVT matrix (106 drive points per cell, 2862 units) | `psat-sweep/` (`--match`) | `sim/psat-sweep/run_psat_sweep.sh --match` | one `klt sim` request, `remote.hosts` 261: the batch fleet, same capacity wait; an interrupted run resumes with `--resume` into the same outdir |
| Power gain, small-signal S11 (S22, S12) over the band, over the full 27-cell PVT matrix | `ac-gain/` | `sim/ac-gain/run_ac_gain.sh` | one `klt sim` request, `remote.hosts` 3: the batch fleet |
| Small-signal stability: mu, mu', k, abs(delta), negative-resistance check, 10 MHz-30 GHz at 50 pts/decade, over the full 27-cell PVT matrix | `ac-stability/` | `sim/ac-stability/run_ac_stability.sh` | one `klt sim` request, `remote.hosts` 3: the batch fleet |

The provisional matrix's findings, and the design iterations that track them (the
committed records are the authority -- `psat-sweep/records/20261121-003533-b2746d0-match.md`,
`ac-gain/records/20261121-010216-b2746d0.md`, `ac-stability/records/20261121-011402-b2746d0.md`;
`sim/lib/finding_trackers.py` is the one place the map lives, and every record the
renderers write from here on states the same links in its own findings section):

- Input match (S11, small-signal and large-signal) and small-signal stability below
  their rungs: #172.
- In three 125 °C cells on both AC benches, ngspice completed the sweeps and
  produced finite vectors. The records withhold grades because klt reported
  `error` with a `singular_matrix` diagnostic. [#188](https://github.com/2AMLogic/sg13g2-pa/issues/188)
  tracks the validity of the recovered operating points.
- The large-signal power rows -- output P1dB, Psat, peak PAE -- below their rungs:
  #192.
- Reduction refusals (e.g. `SWEEP_STEP_TOO_COARSE`) and units that cannot be
  extracted (e.g. `UNSETTLED`) are findings no issue tracks yet; the records say so
  rather than linking to the nearest-sounding issue.

Device stress is extracted from the `psat-sweep/` transients (spec: "all large-signal
benches"), not a separate bench. The decks are generated by `lib/gen_dut_benches.py`, which
inlines the DUT netlist verbatim with its sha256; each run script first runs
`gen_dut_benches.py --check`, so a netlist change that is not regenerated fails with
`STALE_BENCH` instead of silently benching old nodes. That gate (shared with
`device-npn13g2/gen_bench.py` through `lib/bench_gen.py`) acts on `--check` and on
nothing else: any other argument is a usage error, exit 2, and writes nothing, so a
typo'd flag cannot turn the gate into a rewrite of the attested decks. Each run writes an append-only
`records/<timestamp>-<sha>.md` (psat-sweep also `.json`) restating load, drive, harmonic
terminations (ideal 50 ohm at 2 f0 / 3 f0, the labelled default), PAE integration and the
window/breakdown labels. The raw waveforms of the sweep (tens of MB per drive point) are
deleted after the record is written. `lib/sparams.py` and `lib/ac_record.py` do the
S-parameter and stability reduction (tests: `python3 -m pytest sim/lib`).

The item-9 inventory of every bench and its cold start is `../attest/item9.json`
(envelope `../evidence/item9.json`, see `../manifests/README.md`). **The matched psat
deck (`psat_sweep_match.{spice,request.json}`) is a study variant of the psat bench and
is deliberately outside that inventory**, which covers "every committed bench": folding
it in means re-running every bench to re-attest item 9, which would move
`manifests/sg13g2-pa.signoff.json`. It is to be added when item 9 is next re-attested
for its own reasons, not before.

### The off-chip output match (`run_psat_sweep.sh --match`)

The default psat deck drives a **bare 50 ohm** from `RFOUT`, so nothing transforms the
load and the output array is not loaded the way the load-line study
(`device-npn13g2/records/`, DR 0003) sized it. `--match` runs the same sweep through an
**ideal, lossless off-chip L-section** designed for that load-line resistance.
It evidences the spec's **Fallback** Output-port cell -- "50 ohm, **off-chip**
output match (stated boundary)" -- and only its boundary convention; the **Target**
(on-chip match) row stays unevidenced while DR 0001 D-1, the inductor-model source, is
deferred. No inductor model is used or needed.

**The chip boundary is `RFOUT`** (`design/README.md`), and the two sides are:

| Side | Elements |
|---|---|
| **On chip** | the DUT, including the output array, `Lchoke`, `Cblock`, `Cin` and the four stabilisation resistors |
| **Off chip** | `Vbsense` (a 0 V boundary sense), `Lmatch`, `Cmatch`, `Vlsense`, the 50 ohm load -- all **ideal and lossless**: no Q, no self-resonance |

By that same spec row, a real off-chip network's loss is **not counted as the chip's**,
which is why none is modelled. The record says all of this, and makes no pass claim.

Element values are **derived in `lib/gen_dut_benches.py` (`match_network`), never
tuned**: the resistance is the load-line record's own array-independent
`vswing_v / iq_per_nx_a` over the array the DUT netlist actually has (via
`output_array()`), and the L-section is the closed form for it with the DUT's on-chip
`Cblock` -- a third of that resistance in reactance at f0 -- absorbed into the series
branch. This gives the design target at f0. The actual collector load also
includes `Rsho` at `RFOUT` and `Rdchoke` in parallel with `Lchoke` at `COLL`. The study's own
`nx_needed.load_ohm_ideal` is **not** used: it belongs to the larger array the study
*recommends*, not the one benched.

Two things about the matched bench are easy to get wrong silently, so both are declared
in `psat_bench(variant)` and read from there by `psat_record.py` rather than assumed:

- **The harmonic terminations stop being the labelled ideal-50-ohm default** -- the
  network sets them, and the collector sees nothing like 50 ohm at 2 f0 / 3 f0. The
  record states both impedances (at `RFOUT` and at `COLL`) and, per
  `../spec/target-spec.md` ("Harmonic terminations"), does **not** compare its P_out or
  PAE with the bare-50-ohm record's.
- **Both extraction nodes move.** `P_out` and the harmonics come from the 50 ohm
  resistor's own V and I. The `RFOUT` boundary sense measures the current entering
  the off-chip network. Adding the on-chip `Rsho` current gives the current through
  `Cblock`. Subtract that sum from the currents arriving through `Lchoke` and
  `Rdchoke` and divide by the device count to get per-device collector current.

Its record is suffixed `-match` (`sim_begin_record --suffix`, as
`known-answer/run.sh --wrong-load` does), so it cannot be confused with or overwrite a
bare-deck record.

**The drive grid is not the bare grid, shifted or reused.** It starts where the bare
grid starts (-36.0 dBm available), fine-steps earlier, and ends higher (+10.0 dBm). Each
of those three came from a real run that failed the previous guess, and both failed runs
are kept as the evidence for them:

| Run | What it settled |
|---|---|
| `records/20261114-032358-651c0cf-match.*` | **The bottom must not move.** That grid was the bare grid translated up by the ~14.2 dB the load-drop estimate had predicted, the estimate the first grid was built on, so it started at -22.0 dBm -- where this deck already compresses. `reduce_sweep` takes its reference gain from the three lowest-drive points; they disagreed by 0.391 dB against a 0.1 dB limit and the whole reduction was refused `LINEAR_REGION_NOT_FOUND`. The same run also bounded the **top**: above roughly +17 dBm available the deck stops solving (12 points aborted with ngspice's `timestep_too_small`, flagged on the bias-reference device `XQref`; two more came back `UNSETTLED`), and those levels sit at collector peaks near 6 V against a BVCEO(min) of 1.4 V. |
| `records/20261114-033006-28e69b9-match.*` | **The coarse tail must stop early.** With the bare grid's 0.8 dB/0.4 dB boundary (-16.8 dBm) the 1 dB compression point landed inside the coarse region: 0.912 dB of measured P_in across the bracket against a 0.5 dB limit, refused `SWEEP_STEP_TOO_COARSE`. The matched load compresses 1 dB at about -25 dBm available, 10 dB earlier than the bare deck does. |

So the grid is 0.8 dB only up to -28.0 dBm -- the linear reference tail -- and 0.4 dB the
whole way from there to +10.0 dBm, which puts the entire compressing and saturating range
on the fine step with the bracket ~3 dB inside it. Neither bound is fitted to a result:
`reduce_sweep` still judges every run, and a record that reaches its own sweep end, or
brackets P1dB too coarsely, is rerun rather than quoted.

### The P1dB linear-reference probe (`run_p1dbref_probe.sh`, issue #192)

The spec's Output P1dB row requires the reference gain to come from "drive >= 20 dB below
the compressing level". The committed matched grid **cannot** reach that region: klt
names a unit by a corner id whose supply-axis values are formatted to three decimals
(`vamp=0.010`), so below ~10 mV of source amplitude -- about -35.7 dBm available into
50 ohm -- no <= 1 dB spaced drive grid keeps one bucket per point (the
klayout-tools#5870 collision class; `assert_pvt_corner_ids_distinct` refuses it at
generation time), and `reduce_sweep` forbids steps above 1 dB before Psat. The grid
bottom of -36.0 dBm is therefore an **encoding floor**, and the matrix record's
reference points sit only ~8-16 dB below each cell's compression. The encoding gap is
filed with klayout-tools (friction protocol): klayout-tools#7132.

Until it closes, `run_p1dbref_probe.sh` measures what the grid cannot: the SAME
committed matched deck (byte-identical, no bench fact changes) under a sparse low-drive
axis -- `P1DBREF_PROBE_GRID_DBM`, -56..-36 dBm available at 4 dB steps, the finest tested
spacing whose corner ids stay distinct down to the encoding's floor -- over every
declared cell (one fleet submit, 162 units; request committed as
`psat_sweep_match_p1dbref.request.json`). Its append-only record
(`records/<id>-p1dbref.{md,json}`) compares each cell against the committed matrix
record: the extrapolated zero-drive gain `g0` (fit `g(P_in) = g0 - c*P_in`, the
second-order compressor's law) against the matrix record's own reference gain; the
error that reference compression propagates into `P1dB_out` through the crossing
bracket's slope (`epsilon*(1/s - 1)`); the bracket's measured step against the row's
0.5 dB limit; and the quiescent operating point (P_DC, total supply current). The probe
is not a drive sweep -- 4 dB steps bracket no compression, `reduce_sweep` never runs on
it, no Psat/PAE figure appears -- and like the matched deck it is a study bench outside
the item-9 inventory. Like every grid it is never hand-launched: one `klt sim` request,
batch fleet, the request's own capacity wait.

The probe selects the newest matched matrix with the same DUT netlist SHA-256.
An explicit matrix path passes the same check. The reducer verifies the probe
deck against klt's input hash before comparing the cells. For a matrix that
predates DUT metadata, a sibling `<record-id>.dut.json` pins the original record
bytes and the DUT identity verified from its run.

For candidate measurements, `run_psat_sweep.sh --candidate "description"` runs
the matched matrix and identifies the candidate in both record formats. Matched
runs save the generated deck and DUT netlist under `corners/<record-id>/inputs/`.

## Running grids

A multi-corner or Monte Carlo run is a `klt sim` request (`corners` /
`monte_carlo`), never a hand-launched `ngspice -b` loop. With
`KLT_SIM_BACKEND=batch` it goes to the batch fleet; a failed submit is reported,
not rerun locally.

**`klt` owns the wait for fleet capacity, and it is the only mechanism.** A
submit refused for capacity (`batch_no_capacity` / `batch_concurrency_cap`) is
re-launched by `klt` itself with jittered backoff, for up to 600 s. `sim/env.sh`
carries no second copy of that wait and no job pool: `sim_run_one` submits once,
and a refusal that outlasts the 600 s is reported and fails the bench rather
than falling back to a local run. Raising the wait is one number.

The two codes are not a narrower classification than the five stderr strings
`sim_run_one` used to `grep` for: they are the *same* classification, read from
the side that owns it. In the pinned `klt` (0.9.0, `sim/toolchain.json`),
`sim_batch._classify_launch_failure` maps the provisioner's three refusal
messages onto them -- `no capacity in any of the …` and `… exceeds
BATCH_MAX_VCPU=V` (the "`N` vCPU already running" message) to
`batch_no_capacity`, `… exceeds BATCH_MAX_CONCURRENT_INSTANCES=M` to
`batch_concurrency_cap` -- and `_RETRYABLE_LAUNCH_CODES` is exactly those two,
so both are waited out under `capacity_wait_s`. The deleted shell list matched
substrings of those same three messages (plus the two code names), which is why
removing it loses no refusal the fleet is known to emit. The one residual gap is
stated rather than papered over: the shell matched the bare substrings
`vCPU already running` and `BATCH_MAX_CONCURRENT_INSTANCES`, where `klt` requires
the longer `exceeds BATCH_MAX_VCPU` / `exceeds BATCH_MAX_CONCURRENT_INSTANCES`.
Both halves occur in the same single provisioner `fail` line today, so no current
message classifies differently; a *future* provisioner message that said
"vCPU already running" without "exceeds BATCH_MAX_VCPU" would now fail after one
submit instead of being retried. That is a `klt`-side classification bug to file
under the friction protocol, not something to re-fork a shell string list over.
This is read from `klt`'s own source at the pin, not from an induced fleet
refusal -- see "Not exercised live" in PR #102.

The 600 s reaches `klt` two ways, both meaning the same thing:

| Bench | How | Why |
|---|---|---|
| `psat-sweep/`, `device-npn13g2/` (`dc_family`, `ft`) | `batch.capacity_wait_s: 600` in the request | generated by `lib/gen_dut_benches.py` / `device-npn13g2/gen_bench.py`, both of which take the number from `lib/bench_gen.py` (`CAPACITY_WAIT_S`) rather than restating it; the field is inert off the batch backend, so it is safe to commit |
| `smoke/` (`inverter_dc`, `inverter_tran`) | `--wait-for-capacity 600` from `smoke/run_smoke.sh`, passed only when `KLT_SIM_BACKEND=batch` | `evidence/item9.json` content-hashes both request files, and re-attesting item 9 reruns every bench — so the requests stay byte-identical |

The flag is **batch-only**: off the batch backend `klt` exits 1 with
`--wait-for-capacity requires backend 'batch'`, which is why `run_smoke.sh`
guards it on `KLT_SIM_BACKEND` and why the generated requests use the field
instead. Giving the two smoke requests the field as well is the tidier end
state and needs an item-9 re-attestation in the same change.

## Large-signal extraction (`lib/rf_extract.py`)

Psat, P1dB, PAE and harmonics come from transient decks only, extracted the
way `spec/target-spec.md` ("Large-signal extraction without harmonic balance")
fixes it. `lib/rf_extract.py` (stdlib + numpy; tests: `python3 -m pytest sim/lib`)
has a pure layer (arrays in, numbers out) and a thin reader:

| Function | Does |
|---|---|
| `load_klt_waveform(path)` | reads klt's `waveform.raw.json` -> `(time, {name: array})` |
| `extract(t, f0, v_load, i_load, supplies, v_in, i_in, n_periods=20)` | settling test, integer-period window, coherent DFT; returns `p_out_w`, `p_in_w` (fundamental only), `p_dc_w` (total), `pae`, `h2_dbc`, `h3_dbc` |
| `reduce_sweep(points)` | Psat and P1dB (linear dB interpolation between the bracketing points; `p1db_status: not_reached`, never an extrapolation) from a list of `extract` results |

`extract` refuses, with a named `ExtractError.code`: a non-integer window
(`NON_INTEGER_WINDOW`), fewer than 100 periods (`TOO_FEW_PERIODS`), a raw time
step above T/200 (`STEP_TOO_COARSE`) and a trace that fails the settling test
(`UNSETTLED`: 0.01 dB for P_out, 0.1 % for each supply current, over the 10
periods before the window and throughout it). A zero-valued quantity compared
with itself counts as settled (a DC-only deck has no RF power; 0/0 is not a
change). `pae` is `None` when P_DC is zero, and a harmonic is `None` when the
fundamental or that harmonic is zero.

**How a DUT bench calls it.** Write the bench as a `klt sim` request with
`analysis.kind: "tran"`, a `tran` step of at most T/200 (the known-answer decks
use T/400), at least 100 RF periods, and `options.waveforms: true` plus
`options.keep_artifacts: true`; `--backend local` for a single drive point (a
multi-point or multi-corner request goes to the fleet like any grid). Read the
corner's `artifacts.waveform` path from the `--format json` report, then:

```python
import rf_extract as rx
t, s = rx.load_klt_waveform(report["corners"][0]["artifacts"]["waveform"])
r = rx.extract(t, f0, s["v(out)"], s["i(rl)"],            # current INTO the load
               supplies=[(s["v(vcc)"], -s["i(vcc)"])],    # delivered current, every supply
               v_in=s["v(in)"], i_in=-s["i(vsrc)"])       # current into the DUT port
sweep = rx.reduce_sweep(list_of_r)                        # sorted by drive internally
```

ngspice's `i(Vname)` flows into the + terminal, so a source's delivered
current is `-i(Vname)`. P_DC sums every supply passed in, so bias and driver
supplies must all be listed. A bench restates the load, drive, harmonic
terminations (the default is an ideal 50 ohm at 2 f0 and 3 f0, labelled as
such), window length and whether the passives are ideal in its own record;
power or PAE under different terminations are not compared.

A waveform-only request sets `options.capture_only: true`, so `klt sim` grades
a run whose corners all passed `pass` and exits 0 (it refuses the option on a
request that declares measurements); `sim_run_one` treats every non-zero exit
as a failure. Gate on the report's corner status as well, as the record
scripts and `known-answer/run.sh` do.

### Known-answer check (`known-answer/`)

`known-answer/run.sh` is run before any DUT result is recorded. It runs three
ideal decks through `klt sim` (1 V sine behind 50 ohm into 50 ohm, expect
+3.979 dBm within 0.01 dB; 3.3 V DC into 100 ohm, expect P_DC = V^2/R within
0.1 % and |PAE| < 1e-3; 1 V + 0.1 V third-harmonic series sources, expect
-20.00 dBc within 0.01 dB) and writes the append-only record
`known-answer/records/<timestamp>-<sha>.md`; it exits non-zero if any value is
outside tolerance. `run.sh --wrong-load` runs a 75 ohm load against the 50 ohm
answer (0.18 dB low) and must exit 1; its record (`...-wrong-load.md`) is kept
as the demonstration. A 51 ohm load is not a usable control: it moves the
power by only 0.0004 dB, inside the tolerance. Records are evidence: never
edit or delete one, rerun instead.

### Known-answer check (thermal) (`known-answer-thermal/`)

`known-answer-thermal/run.sh` is the thermal-node check DR 0001 Q4 deferred
(D-2): does ngspice solve the `npn13G2` VBIC self-heating node the way the
card intends? Cold start, after `scripts/setup-env.sh`:

```sh
sim/known-answer-thermal/run.sh        # the check; exit 0 = verified
sim/known-answer-thermal/run.sh --neg  # selft=0 control; exit 1 by contract
```

The deck instantiates the 5-terminal `npn13G2_5t`, holds idle devices at known
injected power (2 Nx x 2 powers), runs one biased case whose node is driven by
the device's own dissipation, and one 4-terminal `npn13G2` at the same bias
whose internal node is probed hierarchically as `v(x<inst>.t)` -- the node
`psat-sweep/psat_record.py` reads. Expected values come from
`lib/device_limits.rth()` (the card's expression, never retyped); the request
declares graded `measurements`, so `klt` itself gates every value (0.01 %
relative on the injections, 0.1 % on the biased case, 1 uV on the comparison).
Each subckt ends with `Rt t 0 R = 1e9`, so every reading sits low by
`-rth/1e9` relative; the tolerances absorb that systematic on purpose. The
injection decks' benign NaN temperature-limiter note and recovered gmin
stepping match no `sim_gate_logs` error pattern, so the gate runs with no
flags. One corner (`hbt_typ`, 27 C) is the whole PVT information the check can
carry: the card's `rth` has no process or temperature coefficient. Records
(`records/<timestamp>-<sha>[-neg].md`) are append-only, and the verdict is
scoped to the DC `rth` network and the device-to-node power path -- not `cth`
or a thermal time constant (an `op` solve cannot time-resolve them).

## Layout

- `pdk.json`, `toolchain.json` - pins and tool floors.
- `env.sh` - resolver and shared runner surface, in the order a runner calls it
  (`sim_require_pdk`, `sim_require_numpy`, `sim_resolve_klt`, `sim_begin_record`,
  `sim_run_one`, `sim_gate_logs`), plus `sim_run_ac_bench <gain|stability>` --
  the whole shared body of the two AC runners, which differ only in the bench
  name.
- `tools/` - `build-osdi.sh`, `pdk_identity.py`.
- `lib/` - `units.py` (`dbm`, the one watts-to-dBm conversion every record and
  the sweep reducer share, defined here once -- `rf_extract` re-exports it as
  `rx.dbm`, so both names are the same function; `db10` is defined here once
  too and re-exported the same way, public as `rf_extract.db10`),
  `rf_extract.py` (extraction from transient waveforms and the Psat/P1dB
  sweep reducer), `device_limits.py` (the npn13G2 breakdown
  minima, model window and Rth model, defined once for every bench that grades
  against them), `bench_gen.py` (the pinned PDK name and corner-library path, the
  capacity wait, the `klt sim` request skeleton and the strict write/`--check`
  driver both bench generators use -- so a PDK release that moves the corner
  library is one edit), `provenance.py` (the `- Commit:` bullet and the
  artifact-digest helper every record renderer states its provenance through)
  and their tests.
- `known-answer/` - ideal decks, `run.sh`, `check_known_answer.py`,
  `records/<id>.md`, `corners/<id>/` (klt reports, plus the deck and ngspice log
  per `<case>/<corner>/`, which is what `sim_gate_logs` reads; the raw traces are
  deleted once the record is written).
- `known-answer-thermal/` - the npn13G2 VBIC self-heating node's known-answer
  check (DR 0001 D-2): `gen_bench.py` (decks and graded requests from
  `lib/device_limits.rth()`), `run.sh` (`--neg` is the selft=0 control, expected
  to exit 1), `thermal_record.py`, `records/`, `corners/`.
- `smoke/` - toolchain smoke test (decks, `klt sim` requests, `run_smoke.sh`,
  `corners/<id>/` artifacts, `records/<id>.md`). Not a design result.
- `psat-sweep/`, `ac-gain/`, `ac-stability/` - the DUT benches above (decks and requests
  generated by `lib/gen_dut_benches.py`, `run_*.sh`, `records/`, `corners/<id>/`).
  `psat-sweep/` carries two generated decks: `psat_sweep` (bare 50 ohm, the default) and
  `psat_sweep_match` (through the ideal off-chip match, `--match`), plus the P1dB
  linear-reference probe (`run_p1dbref_probe.sh`, `p1dbref_record.py`, the committed
  `psat_sweep_match_p1dbref.request.json` -- the matched deck under a sparse low-drive
  axis; see "The P1dB linear-reference probe" above).
  `run_ac_gain.sh` and `run_ac_stability.sh` are wrappers over `env.sh`'s
  `sim_run_ac_bench`, so a gate change reaches both at once; `run_psat_sweep.sh`
  keeps its own body (batch backend, `psat_record.py`, waveform cleanup).
- `device-npn13g2/` - `npn13G2` Ic-Vce / fT benches and the analytic load-line study
  (`run_device.sh`, `loadline.py`); simulated device evidence, recommends only.

Provenance of `env.sh`, `tools/build-osdi.sh` and `tools/pdk_identity.py`:
`spec/decision-records/0001-adopt-lna-sim-env.md`.
