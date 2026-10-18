# 0002: Device stress row — Target cell requires the model validity window

- **Status**: ratified on approval of the PR that lands this record and the
  one-row edit to [`spec/target-spec.md`](../target-spec.md).
- **Date**: 2026-10-18
- **Decided by**: builder agent (proposal); the approving reviewer ratifies
- **Issue**: [#10](https://github.com/2AMLogic/sg13g2-pa/issues/10)
- **Amends**: [0001-ratify-target-spec](0001-ratify-target-spec.md), decision 1

## Context

Record 0001 ratified the Device stress row with values "the README draft's
fallback/target/stretch unchanged". The README row reads:

- Fallback: no device beyond its documented breakdown over the full swing,
  every corner.
- Target: same, inside the model card's validity window.

As ratified, the spec row's Target and Fallback cells were identical
(breakdown compliance, peak `V_CE`/`V_CB` stated), and "target adds: inside
the window" appeared only in the Binding-conditions cell. Read cell by cell,
the ratified Target was looser than the README ladder it claims to copy.

## Decision

This is a **correction to match the README draft**, not a change of intent: it
neither relaxes nor adds a requirement beyond what the README ladder already
said.

1. Target cell: breakdown compliance **and** every cell inside the model
   card's validity window.
2. Fallback cell: breakdown compliance only; the window is not required.
3. Binding conditions: the OUTSIDE MODEL WINDOW labelling rule is kept (a cell
   outside the window is labelled, never "pass"); the redundant "target adds:
   inside the window" fragment is removed.
4. No other row, breakdown figure or window definition changes. The README is
   not edited; it is the ratified source.

## Consequences

- A result with a cell outside the model card's validity window can meet the
  Fallback for this row but cannot meet the Target; it is labelled OUTSIDE
  MODEL WINDOW either way.

## Note for the operator

`spec/decision-records/` holds two files numbered `0001-` (`0001-adopt-lna-sim-env.md`
and `0001-ratify-target-spec.md`). This record is numbered `0002` and does not
renumber either; resolving the duplicate is left to the operator.
