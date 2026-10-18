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
not rerun locally. `sim/env.sh` deliberately carries no job pool.

## Layout

- `pdk.json`, `toolchain.json` - pins and tool floors.
- `env.sh` - resolver and shared runner surface (`sim_require_pdk`, `sim_check_log`).
- `tools/` - `build-osdi.sh`, `pdk_identity.py`.
- `smoke/` - toolchain smoke test (decks, `klt sim` requests, `run_smoke.sh`,
  `corners/<id>/` artifacts, `records/<id>.md`). Not a design result.

Provenance of `env.sh`, `tools/build-osdi.sh` and `tools/pdk_identity.py`:
`spec/decision-records/0001-adopt-lna-sim-env.md`.
