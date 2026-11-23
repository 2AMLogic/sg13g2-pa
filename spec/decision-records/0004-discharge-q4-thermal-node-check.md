# 0004: DR 0001 Q4 discharged — the thermal-node known-answer check passes (PROPOSED)

- **Status**: **PROPOSED. Not ratified.** No row of
  [`spec/target-spec.md`](../target-spec.md) is edited by this record; every
  row citing "record 0001, D-2" keeps its current status. The Thermal row
  stays DRAFT; ratifying it needs the operator (see Recommendation below).
- **Date**: 2026-11-15
- **Decided by**: builder agent (proposal); the operator ratifies
- **Issue**: [#132](https://github.com/2AMLogic/sg13g2-pa/issues/132)
- **Answers**: [0001-ratify-target-spec](0001-ratify-target-spec.md), Q4
  (self-heating known-answer check) — the Q4 item of DR 0001's D-2 deferral
  list only, not the other eight items.

## The question and its answer

DR 0001 Q4 asked whether ngspice's VBIC implementation solves the PDK card's
self-heating thermal node as intended, deferred the known-answer check that
would show it, and ruled: "Until that passes, results with self-heating are
labelled 'self-heating unverified'". The check now exists and passes, so **Q4
is discharged**.

The evidence is
[`sim/known-answer-thermal/records/20261114-205927-00b692a.md`](../../sim/known-answer-thermal/records/20261114-205927-00b692a.md)
(**Result: PASS**, corner `hbt_typ/novdd/27C`, commit `00b692a`, PDK
`v0.3.0`, `klt 0.9.0`, engine **ngspice 47** — the engine the check was
actually shown on, not the ngspice-46 DR 0001 named), backed by the negative
control record `20261114-205928-00b692a-neg`: with `selft=0` the same
injections miss `P·rth` by five to six orders of magnitude (+8.81e+04 to
+3.07e+05 relative), demonstrating that the check can fail.

The record grades six rows, all PASS:

- Four injection cases (Nx ∈ {1, 4} × P ∈ {1, 10} mW): the measured node rise
  sits −1.14e-05 … −3.26e-06 relative to the card's own answer `P·rth(Nx)`,
  graded at 0.01 %.
- One biased `rth` read-back (Nx=4 at Vce 1 V, Vbe 0.85 V, with P
  reconstructed from terminal V and I): −3.31e-06 relative, graded at
  0.1 % — the self-consistency check on the device-to-node power path.
- The 4-terminal-vs-5-terminal comparison: `v(x4t.t) - v(t5b)` =
  +1.066e-14 V against a 1 µV bound.

## Scope of the discharge

The verdict is scoped exactly as the record's own "Scope of the verdict"
section states it. **Shown**: the card's `rth` network (kelvin of rise per
watt in) and the device-to-node power path, **at DC**. **Not shown**: `cth`
and the thermal time constant — the bench is an `op` analysis, which cannot
time-resolve them, so the `rth·cth` ≈ 5 ns settling DR 0001 planned was
observed nowhere and is not part of this discharge.

The single corner is not a PVT gap this record leaves open; it is the whole
of the PVT information this check can carry, for the record's own reason: the
card's `rth` expression (`3.26e3·(4/Nx)^0.9` K/W) carries no process or
temperature coefficient, so no other corner can change the answer this bench
grades.

The 4-terminal agreement row is what transfers the DC-only verdict to the device
instance `sim/psat-sweep/` actually probes: that bench reads the internal
thermal node hierarchically (`v(x<inst>.t)`) on the 4-terminal `npn13G2`
subcircuit, and the row shows that node agrees with the 5-terminal node the
known-answer deck drives to +1.066e-14 V. Without that row the check would
not reach the psat bench.

## What replaces the "self-heating unverified" labelling rule

DR 0001's rule — "Until that passes, results with self-heating are labelled
'self-heating unverified'" — is replaced, within the scope above, by:

> Results that rely on self-heating label **the card's `rth` network and the
> device-to-node power path** as **thermal-node verified (DC)**, on
> ngspice 47, PDK `v0.3.0`, corner `hbt_typ/novdd/27C`
> (`sim/known-answer-thermal/`, record `20261114-205927-00b692a`). The label
> attaches to that DC response only. A **junction-temperature figure extracted
> from a transient waveform** (for example a maximum over RF-cycle samples,
> as `sim/psat-sweep/` reports) is **not** covered: it depends on `cth` through
> `cth·dΔT/dt + ΔT/rth = P(t)`, which an `op` analysis sets to zero, so even a
> wrong `cth` would pass every check in the record. Such a figure stays
> labelled **self-heating unverified (transient peak and settling)** until a
> time-domain known-answer check exists. A claim that depends on `cth`, a
> thermal time constant, ripple or settling-time choices must not cite this
> check.

The `sim/psat-sweep/` `Tj` column is therefore a transient peak that this
record leaves **unverified**. What the record does transfer to that bench is
narrower: the 4-terminal/5-terminal row shows the node the bench reads
hierarchically is the node the check drove, so the DC `rth` gain from power to
node is checked on the instance it probes. The peak value and its settling are
not.

## D-2: only its Q4 item is addressed

DR 0001's D-2 deferral is an umbrella over nine items. This record addresses
exactly one of them, **Q4 (self-heating check)**. The other eight remain
deferred exactly as DR 0001 recorded them: PAE at back-off threshold,
large-signal stability line limit, supply nominal, device flavour/stacking,
**thermal limit**, electromigration rule (DC vs RMS reading of §2.15),
harmonic limits, and area budget. No row of `spec/target-spec.md` changes
status. In particular the **thermal limit** item — a numeric
junction-temperature reliability limit, which the PDK does not document — is
a different D-2 entry that no bench in this repo addresses.

## Recommendation (not performed): ratify the Thermal row

The Thermal row's evidence gap is now the `cth` / thermal time-constant scope
and the missing numeric reliability limit — not the `rth` network, which this
check closes. The operator may ratify the row on that basis. This record only
recommends; it edits nothing. Ratification still waits on:

- the thermal-limit item above — a human-sourced number, if the PDK or a
  reliability document ever provides one; and
- a decision on whether `cth` / the thermal time constant is inside the
  spec's claims (the extraction method's settling criterion references it) or
  explicitly out of scope for them.

## What this record does not decide

- It does not edit any row of `spec/target-spec.md`, and does not edit
  [0001-ratify-target-spec.md](0001-ratify-target-spec.md)
  (`decision-records/` is append-only per [`spec/README.md`](../README.md)).
- It makes no claim that `cth`, a thermal time constant, or a
  junction-temperature reliability limit was checked — none of the three was
  shown.
- It does not address any D-2 item other than Q4, nor DR 0001's other
  deferral (D-1, inductor-model source, stays with the operator).

## Consequences

- The DC `rth` network and power path are labelled "thermal-node verified
  (DC)" (ngspice 47, PDK `v0.3.0`, `hbt_typ/novdd/27C`). Any
  transient-extracted junction-temperature figure stays labelled
  "self-heating unverified (transient peak and settling)".
- `sim/psat-sweep/`'s `Tj` column is a transient maximum and keeps the
  unverified label; this record verifies only the DC gain to the node it
  reads.
- The Thermal row's ratification is a recommendation the operator can act on,
  with its remaining waits named.
