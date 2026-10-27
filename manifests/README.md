# Block manifest and tier-verdict record

This directory holds this block's `klt signoff` input and its committed
output, the machine-readable form of the T1 checklist in
[`design-evidence-tiers.md`](design-evidence-tiers.md).

## Files

- **`sg13g2-pa.json`**: the block manifest. `block: sg13g2-pa`,
  `kind: analog` (a SiGe HBT power amplifier, no digital partition) and an
  `evidence` map that is deliberately empty: no design, simulation or spec
  artifact exists yet to cite. Citations are added one T1 item at a time as
  artifacts land, each pinning the `content_hash` of what it cites.
- **`design-evidence-tiers.md`**: the T1-T4 checklist the grader parses.
  Vendored **byte-identical** from
  [`2AMLogic/klayout-tools@44cc42323184`](https://github.com/2AMLogic/klayout-tools/blob/44cc42323184/docs/design-evidence-tiers.md)
  `docs/design-evidence-tiers.md` (git blob `2f7f69825f8c`). Upstream is
  MIT-licensed; this repo's Apache-2.0 `LICENSE` does not relicense the
  vendored copy. When upstream moves, re-vendor the file, update the commit
  above, and regenerate the record in the same PR.
- **`sg13g2-pa.signoff.json`**: **the verdict of record**, the committed
  output of the command below. Never hand-edit it.

## Regenerate

```console
uvx --from "klayout-tools==0.8.0" klt signoff \
    --manifest manifests/sg13g2-pa.json \
    --tiers-doc manifests/design-evidence-tiers.md \
    --format json > manifests/sg13g2-pa.signoff.json
```

`klt signoff --manifest` exits `3` when at least one item is `unmet` (a valid
run: `unmet` with a per-item `reason` is the honest statement of the gap) and
`0` when every T1 item is `met`; the redirect still writes the record on `3`.
Any change that affects the verdict (new evidence, a manifest edit, a
vendored-doc bump, a `klt` pin bump) regenerates and commits the record in the
same PR.

## Freshness is CI-enforced

[`.github/workflows/signoff.yml`](../.github/workflows/signoff.yml) re-runs the
command with the same pinned `klt` on every push and pull request and
byte-compares the output against the committed record, so a manifest change
without a regenerated record fails. Keep the pin in the workflow and in this
file identical.

## Current verdict

`tier: null`, 0 of 11 T1 items met; every item is `unmet` with a `reason` in
the record (`no_evidence` for items 1-11). The record is the source of truth,
not this paragraph.
