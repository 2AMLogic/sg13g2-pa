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
