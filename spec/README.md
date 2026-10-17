# spec

- [`target-spec.md`](target-spec.md) — the target table, the PDK limits and
  model validity window it is checked against, the PVT corner box, and the
  large-signal extraction method. Rows are RATIFIED or DRAFT.
- [`decision-records/`](decision-records/) — one decision per record, numbered
  `NNNN-<slug>.md`, append-only. [`0001-ratify-target-spec.md`](decision-records/0001-ratify-target-spec.md)
  ratifies the table and records each open question's resolution or deferral.

See the repo README for scope. Agents do not relax a RATIFIED row to make a
result pass; a spec change needs a new decision record.
