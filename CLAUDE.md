# sg13g2-pa — agent instructions

Open-source canary block: a SiGe HBT power amplifier on IHP SG13G2, a
130 nm SiGe BiCMOS open PDK, designed and verified by AI agents.

- **PDK**: IHP SG13G2 (open PDK, IHP-GmbH/IHP-Open-PDK). Open-source flow:
  xschem + ngspice for design/sim, klayout-tools (`klt`) for layout, DRC and
  LVS. Pin the PDK release and build the OSDI models the way `sg13g2-lna`
  documents.
- **Breakdown and the output passives are the point, and the risk.** The
  high-speed HBTs have a BVCEO of about 1.4 V minimum and `npn13g2v` about
  2.2 V minimum (PDK process spec); a PA's collector swing exceeds its
  supply, so every operating point states the peak `V_CE` and `V_CB` on
  every device at every corner, against the documented breakdown and
  against the VBIC model card's validity window. A result outside the
  window is labelled as such, never quoted as a pass. The output match
  depends on inductor models; state where each one comes from, its loss and
  its self-resonance, and never quote output power or PAE through ideal
  passives without saying so.
- **Scope discipline.** No mixer, LO, T/R switch or linearization here. The
  band follows `sg13g2-lna`'s ratified band; cite it at a named commit.
  `sg13g2-vco` has characterized spiral inductors on this PDK and
  `sg13g2-sat-rx` has read the HBT and passive model set in depth; read
  both before characterizing anything yourself. Using `sg13g2-vco`'s
  inductor model in-tree needs a `consumes` edge, which is an operator
  decision — flag it rather than copy numbers across without their
  derivation, and do not build a second inductor model by accident.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and describe
  the gap, not the design.
- **Verification is the product**: no claim without a testbench. PVT corners
  on every recorded result; `sim/` results are append-only evidence. Every
  simulated figure is labelled as simulated, with its corner and testbench.
  Output power and PAE state the load, the drive, the harmonic terminations
  and how efficiency was integrated.
- Spec changes go through `spec/` with a decision record; agents do not relax
  the ratified spec to make results pass.
- **+15 dBm saturated is the target.** +10 dBm is the fallback and +20 dBm a
  stretch. Do not let the stretch drive device stacking before the target
  closes.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.

Work is coordinated through `loom:` labels on issues and pull requests, and the same roles run either under `loom-daemon` or by hand in an attended session — daemon mode is optional. Create the labels once with `.loom/scripts/sync-labels.sh` (an install ships `.github/labels.yml` but does not create the labels on the forge). A pull request ready for review carries `loom:review-requested`; Judge reviews it and applies `loom:pr` (approved) or `loom:changes-requested`; Doctor fixes a `loom:changes-requested` pull request and returns it to `loom:review-requested`. Only a `loom:pr` pull request gets merged, and always via this repo's merge script (`.loom/scripts/merge-pr.sh`) — never a raw forge merge command such as `gh pr merge`. Full state machine: `.loom/docs/label-state-machine.md`.
<!-- END LOOM ORCHESTRATION -->

<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.24.7 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
