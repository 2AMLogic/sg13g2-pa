# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide
triage role. Newest first.

### 2026-11-13

- **PR #105**: fix(sim): refuse to build the AC decks when RS_OHM != RL_OHM
- **PR #98**: refactor(sim): format the AC record's bench facts from the deck generator
- **PR #97**: refactor(sim): fold sim_check_log into sim_gate_logs and test the gate
- **Issue #99** (closed): AC record and deck header label unequal Rs/Rl S-parameters that sparams.s_from_nodes does not compute
- **Issue #92** (closed): Single-source the AC bench facts: ac_record.py retypes the nominal cell, port impedance and band that gen_dut_benches.py declares
- **Issue #90** (closed): Simplify sim/env.sh log gate: fold sim_check_log into sim_gate_logs, drop the unreachable BENCH_COMPLETE and exit-code checks
- **PR #91**: fix(ci): point check:all at the gate script and drop the no-op lint script
- **PR #88**: refactor(sim): format the npn13G2 window limits into both summarizers' record prose
- **PR #84**: refactor(sim): share one klt sim submit path across the waveform-only benches
- **PR #83**: refactor(sim): define the npn13G2 breakdown/window limits once in sim/lib
- **PR #82**: refactor(ci): run one gate script from both the workflow and check:ci
- **Issue #89** (closed): Wire or remove the placeholder check:all and lint npm scripts: both exit 0 without checking anything
- **Issue #86** (closed): summarize.py record prose still retypes the npn13G2 window limits as literals
- **Issue #80** (closed): Single-source the CI gate: package.json check:ci and signoff.yml are two hand-kept copies that have drifted
- **Issue #71** (closed): Single-source the npn13G2 breakdown/window limits: psat_record.py duplicates loadline.py
- **Issue #68** (closed): Simplify sim runners: let sim_run_one accept klt exit 4 and drop three open-coded copies
- **PR #78**: fix(signoff): regenerate the item-1 envelope at klt 0.9.1 and gate it in CI
- **PR #75**: docs(manifests): cite the clean 0.9.1 PA DRC report as T1 item 3
- **PR #74**: docs(layout): drop the stale klt.matches pin equality from layout/toolchain.json
- **Issue #76** (closed): T1 item 1 attest envelope no longer reproduces: provenance.input.paths null in the committed evidence
- **Issue #38** (closed): T1 item 3 (DRC clean): klt drc on the PA GDS with coverage disclosed
- **Issue #72** (closed): layout/toolchain.json: klt.matches still claims the signoff workflow installs klayout-tools 0.7.0
- **PR #70**: docs(layout): record PA DRC cont.width.1 result as a 0.7.0 deck artifact, add clean 0.9.1 report
- **Issue #58** (closed): DRC: 28 cont.width.1 violations inside PDK npn13G2 base cell on PA placement GDS

### 2026-11-12

- **PR #65**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-07

- **PR #62**: feat(sim): add psat-sweep, ac-gain and ac-stability benches and attest T1 item 9
- **Issue #40** (closed): T1 item 9 (Testbenches shipped): benches for every ratified row (Psat sweep, gain/S11, stability, device stress)
- **PR #60**: chore: remove stale digital-flow rules from .gitignore
- **PR #59**: docs: record pinned klt drc run on PA GDS (28 cont.width.1 violations)
- **PR #57**: feat(layout): reproducible PA core placement GDS with provenance and item 2 envelope
- **PR #56**: feat: add xschem PA schematic, derived netlist and T1 item 1 attestation
- **PR #53**: Bump Repo Skills 0.25.1 -> 0.25.10
- **PR #45**: docs: propose single-stage npn13g2 topology (DR 0003, proposed)
- **Issue #55** (closed): Remove stale .gitignore entries for flow/cocotb/harness paths this repo lacks
- **Issue #37** (closed): T1 item 2 (Layout): reproducible PA layout generator and committed GDS
- **Issue #36** (closed): T1 item 1 (Design sources): topology decision from the load-line study, then PA schematics and derived netlist

### 2026-11-01

- **PR #50**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-27

- **PR #46**: refactor(sim): share record prelude, log gate and provenance helpers across bench drivers
- **PR #43**: ci: attest T1 item 10 repo hygiene with klt 0.8.0 and document reproduction
- **Issue #44** (closed): Hoist duplicated record-id prelude from three sim drivers into sim/env.sh
- **Issue #41** (closed): T1 item 10 (Repo hygiene): README reproduction section and klt signoff --attest 10

### 2026-10-24

- **PR #33**: refactor(sim): share klt resolution in known-answer driver, read pin from toolchain.json
- **Issue #32** (closed): Dedupe klt pin and resolution: known-answer/run.sh and env.sh
- **PR #30**: refactor(sim): share batch retry and klt resolution in sim/env.sh
- **Issue #29** (closed): Dedupe run_one batch-capacity retry loop across sim drivers into env.sh

### 2026-10-23

- **PR #27**: refactor(sim): share npn13G2 window constants and rth between summarize and loadline
- **PR #25**: chore(sim): remove duplicate tracked loadline.json
- **PR #23**: feat(sim): transient large-signal extraction library with known-answer check
- **PR #22**: sim: npn13G2 single-device load-line study with analytic breakdown/window verdicts
- **Issue #26** (closed): Dedupe npn13G2 window constants and rth in device sim scripts
- **Issue #24** (closed): Remove duplicate tracked sim/device-npn13g2/loadline.json (identical to its append-only record)
- **Issue #21** (closed): sim: npn13G2 single-device load-line study (DC I-V, fT vs Ic, ideal-load swing vs BVCEO) as evidence for the DRAFT supply / flavour rows
- **Issue #20** (closed): sim: large-signal transient extraction library (Pout, PDC, PAE, harmonics, P1dB) with the spec's known-answer check

### 2026-10-21

- **PR #17**: Bump Repo Skills 0.24.3 -> 0.24.7

### 2026-10-20

- **PR #6**: ci: add T1 block manifest, vendored checklist and signoff record check
- **Issue #3** (closed): Add the T1 signoff scaffolding: block manifest, vendored checklist and CI (item 10)

### 2026-10-18

- **PR #14**: feat(layout): pin klt 0.7.0 and add DRC/LVS smoke on sg13g2_inv_1
- **PR #13**: docs(spec): require model validity window in Device stress Target cell
- **PR #12**: refactor(sim): drop unused sim_render and dead env.sh variables
- **Issue #11** (closed): Remove unused sim/env.sh helpers: sim_render, SIM_LOG_FAIL_PATTERNS, SIM_PDK_RELEASE, SIM_PDK_ID_ROUTE
- **Issue #10** (closed): spec: Device stress row puts 'inside the model window' in notes, not the Target cell
- **Issue #7** (closed): Pin klt and commit a DRC/LVS smoke on an SG13G2 reference cell (T1 items 3, 4 bring-up)

### 2026-10-17

- **PR #9**: docs(spec): draft target spec and ratification record
- **PR #8**: feat(sim): pin SG13G2 PDK, add cold-start setup and toolchain smoke test
- **PR #1**: chore(loom): Install Loom 0.19.1181
- **Issue #4** (closed): Pin the PDK and commit a smoke simulation (T1 item 9 bring-up)
- **Issue #2** (closed): Draft and ratify the target spec
