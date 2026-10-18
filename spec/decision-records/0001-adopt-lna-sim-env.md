# 0001: Adopt sg13g2-lna's simulation environment scripts (adapt, record, no consumes edge)

- **Status**: proposed
- **Date**: 2026-10-17
- **Decided by**: Builder (issue #4); the operator owns the open `consumes` question below
- **Issue**: #4

This record changes no row of the target spec; it records where the simulation
environment scripts came from. No `spec/target-spec.md` exists yet (issue #2).

## Context

`CLAUDE.md` says to pin the PDK release and build the OSDI models "the way
`sg13g2-lna` documents". The same PDK (IHP SG13G2, IHP-Open-PDK `v0.3.0`) is
already in use there, and the resolver (`sim/env.sh`), the OSDI build
(`sim/tools/build-osdi.sh`) and the identity check (`sim/tools/pdk_identity.py`)
exist and work. Re-deriving them would produce a second, subtly different
copy of the same PDK handling.

`reuse.lock.json` (format per `2AMLogic/2am` `REUSE.md`) is the right vehicle
for a fetched/vendored import, but it names an import that the fleet's
`fleet-gitops` `repos.yml` `consumes` edge governs. The `sg13g2-pa` entry has
no `consumes` field today (read 2026-10-17), and `REUSE.md` makes that edge
operator-governed. This builder does not add one and does not write a
`reuse.lock.json` that claims an edge that does not exist.

## Decision

Adapt (copy and edit) the three files below from `2AMLogic/sg13g2-lna` at
commit `02c5ba2dc7ee2ee7dca6557a7c83bcc566a09b2c` (`main` on 2026-10-17), and
record the provenance here instead of in `reuse.lock.json`.

| Source file at that commit | sha256 | Adapted to |
|---|---|---|
| `sim/env.sh` | `877dbadbfc418358c06c841558221cca056df302464afeabc863ae8a9ac38152` | `sim/env.sh` |
| `sim/tools/build-osdi.sh` | `0afd6b491ca988739591a1cf93928e9c9c1a17d23df0dc26c3434c87edb49949` | `sim/tools/build-osdi.sh` |
| `sim/tools/pdk_identity.py` | `27f023fabb81dbd2934d7c3bc37001310d467f43246cbf368cbbdac1ca7f63d7` | `sim/tools/pdk_identity.py` |

Changes made (the diff against the source is the full account):

- Log prefixes and paths renamed `sg13g2-lna` -> `sg13g2-pa`; compiler cache
  default `~/.cache/sg13g2-pa` (was the shared `~/.cache/sg13g2-bandgap`).
- `sim/env.sh`: dropped `sim_jobs` / `sim_pool_*` (a hand-rolled `ngspice -b`
  job pool; grids here go through `klt sim`), `sim_record_paths` and the
  committed-DUT splice (`@@LNA_SUBCKT@@`), and later also `sim_render` (the
  `@@MODELS_LIB@@` / `@@MOS_LIB@@` / `@@OSDI_DIR@@` sed renderer; decks go
  through `klt sim` requests), `SIM_LOG_FAIL_PATTERNS` and the unread
  `SIM_PDK_RELEASE` / `SIM_PDK_ID_ROUTE` (issue #11); every failure now carries a named
  error; added `SG13G2_TOOLS_CACHE/pdk-root` to the resolution order and
  `SIM_LOG_REQUIRE_COMPLETE`; `--osdi` now checks `cornerMOSlv.lib` (core MOS)
  and `r3_cmc.osdi`.
- `sim/tools/build-osdi.sh`: new `NGSPICE_TOO_OLD_FOR_OSDI` check (status 5):
  `openvaf-r v24.0.1mob` emits OSDI 0.4, which ngspice-43 and earlier reject.
  The compiler tag and the per-platform sha256 pins are unchanged.
- `sim/tools/pdk_identity.py`: also accepts the `.fetched-version` marker one
  directory above `ihp-sg13g2/`, which is where klayout-tools'
  `fetch-ihp-sg13g2.sh` (commit `e88f211fa485`) writes it
  (`PDK_ROOT/.fetched-version`, not `PDK_ROOT/ihp-sg13g2/.fetched-version`).
  The provenance schema string is `sg13g2-pa/pdk-provenance/1`.

Not adopted, deliberately: any `sg13g2-lna` or `sg13g2-vco` inductor model or
numbers. That needs a `consumes` edge and belongs to issue #2.

## Consequences

- **Open for the operator**: `sg13g2-pa` has no `consumes` edge to
  `sg13g2-lna` in `fleet-gitops` `repos.yml`. If one is added, replace this
  record's table with a `reuse.lock.json` entry (`mode: vendored`, the same
  three files and hashes).
- These copies can drift from `sg13g2-lna`'s. The table above is the baseline
  for a diff.
- A bump of the PDK release changes `sim/pdk.json`, the pin in
  `scripts/setup-env.sh` and a new record; it is not done in place.
