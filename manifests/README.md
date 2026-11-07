# Block manifest and tier-verdict record

This directory holds this block's `klt signoff` input and its committed
output, the machine-readable form of the T1 checklist in
[`design-evidence-tiers.md`](design-evidence-tiers.md).

## Files

- **`sg13g2-pa.json`**: the block manifest. `block: sg13g2-pa`,
  `kind: analog` (a SiGe HBT power amplifier, no digital partition) and an
  `evidence` map. Citations are added one T1 item at a time as artifacts
  land, each pinning the `content_hash` of what it cites. Items 1 (design
  sources, from `evidence/item1.json`), 2 (layout stream, from
  `evidence/item2.json`) and 10 (repo hygiene, from `evidence/item10.json`)
  are cited today.
- **`../attest/item1.json`**: the item-1 attestation inventory (the xschem
  schematic and `xschemrc`, plus the netlist derived from them with its
  `klt netlist --check` freshness command, `local_only`).
- **`../evidence/item1.json`**: the envelope `klt signoff --attest 1`
  produced from it. Generated, never hand-edited.
- **`../evidence/item2.json`**: the envelope `klt signoff --attest 2`
  produced from `layout/pa/sg13g2_pa.gds`. Generated, never hand-edited. The
  manifest's `content_hash` for item 2 is `sha256sum layout/pa/sg13g2_pa.gds`.
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

The signoff pin is `klayout-tools==0.9.1`: `--attest` first ships in 0.8.0 and `--attest 2` (layout stream) in 0.9.1.
The `sim/` and `layout/` pins (`sim/toolchain.json`, `layout/toolchain.json`)
stay at 0.7.0 and are a separate concern.

Item 1 (needs xschem and the PDK; `source sim/env.sh` first):

```console
uvx --from "klayout-tools==0.9.1" klt signoff \
    --attest 1 --inventory attest/item1.json -o evidence/item1.json
```

The manifest's `content_hash` for item 1 is `sha256sum attest/item1.json`.

Item 2 (the layout stream; regenerate the GDS first, see
[`../layout/README.md`](../layout/README.md)):

```console
layout/pa/generate.sh --check   # must pass: the committed GDS reproduces
uvx --from "klayout-tools==0.9.1" klt signoff --attest 2 \
    --input layout/pa/sg13g2_pa.gds \
    --generator layout/pa/generate.sh \
    --regenerated-hash "sha256:$(sha256sum layout/pa/sg13g2_pa.gds | cut -d' ' -f1)" \
    -o evidence/item2.json
```

`--regenerated-hash` is only honest after `generate.sh --check` passed, because
`--generator` is echoed and never run by `klt`.

Order matters. The item-10 envelope hashes `README.md`, `LICENSE` and the CI
workflow byte-for-byte, so finish every edit to those first, then attest,
then render the record:

```console
uvx --from "klayout-tools==0.9.1" --with numpy --with pytest klt signoff \
    --attest 10 --inventory attest/item10.json -o evidence/item10.json
```

The inventory's `unit-tests` check runs `python3 -m pytest`, so the throwaway
environment needs `numpy` and `pytest` (`--with`); CI installs them next to
`klt`. The same applies to `--check`.

If `attest/item10.json` changed, update its `content_hash` in
`sg13g2-pa.json` (`sha256sum attest/item10.json`) before the next step.

```console
uvx --from "klayout-tools==0.9.1" klt signoff \
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

`tier: null`, 3 of 11 T1 items met (item 1, design sources; item 2, layout
stream; item 10, repo hygiene); the other eight are `unmet` with a `reason` in
the record (`no_evidence` for items 3-9 and 11). The record is the source of truth,
not this paragraph.
