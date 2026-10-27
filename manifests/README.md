# Block manifest and tier-verdict record

This directory holds this block's `klt signoff` input and its committed
output, the machine-readable form of the T1 checklist in
[`design-evidence-tiers.md`](design-evidence-tiers.md).

## Files

- **`sg13g2-pa.json`**: the block manifest. `block: sg13g2-pa`,
  `kind: analog` (a SiGe HBT power amplifier, no digital partition) and an
  `evidence` map. Citations are added one T1 item at a time as artifacts
  land, each pinning the `content_hash` of what it cites. Today only item 10
  (repo hygiene) is cited, from `evidence/item10.json`.
- **`../attest/item10.json`**: the item-10 attestation inventory (hygiene
  files plus the PDK-free checks run on a stock CI runner).
- **`../evidence/item10.json`**: the envelope `klt signoff --attest 10`
  produced from it. Generated, never hand-edited.
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

The signoff pin is `klayout-tools==0.8.0`: `--attest` first ships in 0.8.0.
The `sim/` and `layout/` pins (`sim/toolchain.json`, `layout/toolchain.json`)
stay at 0.7.0 and are a separate concern.

Order matters. The item-10 envelope hashes `README.md`, `LICENSE` and the CI
workflow byte-for-byte, so finish every edit to those first, then attest,
then render the record:

```console
uvx --from "klayout-tools==0.8.0" --with numpy --with pytest klt signoff \
    --attest 10 --inventory attest/item10.json -o evidence/item10.json
```

The inventory's `unit-tests` check runs `python3 -m pytest`, so the throwaway
environment needs `numpy` and `pytest` (`--with`); CI installs them next to
`klt`. The same applies to `--check`.

If `attest/item10.json` changed, update its `content_hash` in
`sg13g2-pa.json` (`sha256sum attest/item10.json`) before the next step.

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
same PR. **Any later edit to `README.md`, `LICENSE` or the workflow drifts
the envelope and fails CI**; re-run the attest command above and regenerate
the record in the same PR. Check locally with
`klt signoff --attest 10 --inventory attest/item10.json --check evidence/item10.json`
(exit `0` holds, `3` drifted).

## Freshness is CI-enforced

[`.github/workflows/signoff.yml`](../.github/workflows/signoff.yml) re-runs the
command with the same pinned `klt` on every push and pull request and
byte-compares the output against the committed record, so a manifest change
without a regenerated record fails. Keep the pin in the workflow and in this
file identical.

## Current verdict

`tier: null`, 1 of 11 T1 items met (item 10, repo hygiene); the other ten are
`unmet` with a `reason` in the record (`no_evidence` for items 1-9 and 11). The record is the source of truth,
not this paragraph.
