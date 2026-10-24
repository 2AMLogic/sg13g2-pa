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

## OSDI device models

The core and HV MOS devices are PSP103.6 Verilog-A; ngspice needs compiled OSDI
objects, which the release tarball does not ship. `sim/tools/build-osdi.sh`
compiles the PDK's own sources with a checksum-pinned OpenVAF-Reloaded
(`v24.0.1mob`) into `PDK_ROOT/ihp-sg13g2/libs.tech/ngspice/osdi/` (not
committed). `npn13G2` is a native VBIC card and needs none.

**ngspice floor.** OpenVAF-Reloaded emits OSDI 0.4; ngspice-43 and earlier
accept only 0.3. A MOS deck therefore needs ngspice >= 44 (the fleet workers
run 46). A host with an older ngspice (the dispatch workers have 42) can fetch
the PDK, build the objects and run the HBT, but cannot load the MOS devices
locally: `setup-env.sh` then exits `NGSPICE_TOO_OLD_FOR_OSDI`, downgraded to a
warning only when `KLT_SIM_BACKEND=batch`, because `klt sim` runs the MOS decks
on the fleet.

## Running grids

A multi-corner or Monte Carlo run is a `klt sim` request (`corners` /
`monte_carlo`), never a hand-launched `ngspice -b` loop. With
`KLT_SIM_BACKEND=batch` it goes to the batch fleet; a failed submit is reported,
not rerun locally. `sim/env.sh` deliberately carries no job pool: `sim_run_one`'s bounded
retry is a resubmit of one request to batch when the fleet is at capacity, not
a pool of concurrent jobs, and it never falls back to a local run.

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

A waveform-only request declares no measurements, so `klt sim` exits 4
(`not_checked`) with every corner `pass`; gate on the report's corner status,
as `known-answer/run.sh` does.

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

## Layout

- `pdk.json`, `toolchain.json` - pins and tool floors.
- `env.sh` - resolver and shared runner surface (`sim_require_pdk`, `sim_resolve_klt`, `sim_run_one`, `sim_check_log`).
- `tools/` - `build-osdi.sh`, `pdk_identity.py`.
- `lib/` - `rf_extract.py` and its tests.
- `known-answer/` - ideal decks, `run.sh`, `check_known_answer.py`,
  `records/<id>.md`, `corners/<id>/` (klt reports and ngspice logs).
- `smoke/` - toolchain smoke test (decks, `klt sim` requests, `run_smoke.sh`,
  `corners/<id>/` artifacts, `records/<id>.md`). Not a design result.
- `device-npn13g2/` - `npn13G2` Ic-Vce / fT benches and the analytic load-line study
  (`run_device.sh`, `loadline.py`); simulated device evidence, recommends only.

Provenance of `env.sh`, `tools/build-osdi.sh` and `tools/pdk_identity.py`:
`spec/decision-records/0001-adopt-lna-sim-env.md`.
