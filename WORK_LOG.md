# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide
triage role. Newest first.

### 2026-10-24

- **PR #33**: refactor(sim): share klt resolution in known-answer driver, read pin from toolchain.json
- **PR #30**: refactor(sim): share batch retry and klt resolution in sim/env.sh
- **Issue #32** (closed): Dedupe klt pin and resolution: known-answer/run.sh and env.sh
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
