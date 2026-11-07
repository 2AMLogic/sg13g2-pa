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

## T1 item 3 (DRC): result is `violations`, not `clean`

**Item 3 is not met and is not cited in the manifest.** The pinned `klt drc`
run on the PA placement GDS (`layout/pa/sg13g2_pa.gds`, sha256
`630bfca67b12d51f1d422ecf3221252f480e128e33a39c825e9201c4408135ee`, the same hash
as `layout/pa/provenance.json`) reports **`status: violations`, 28 violations**,
all `cont.width.1`. This is simulated tooling output from the curated `klt`
deck, not a foundry signoff, and the deck was not relaxed.

- Report: [`../layout/reports/drc.json`](../layout/reports/drc.json).
- Tool: `klt` 0.7.0 (`layout/toolchain.json` pin), KLayout engine 0.30.13
  (`klt` warned it differs from the 0.30.12 it was tested against;
  `provenance.klayout_version_mismatch: true`; the verdict is stated by `klt`
  to be unaffected, counts such as `rules_skipped` may differ). Deck `sg13g2`,
  content hash `sha256:bf483105cb17948270f0cad45d9418787654bfc0a5ffd04a2e2413d8c7d3b6e7`.
  PDK IHP-Open-PDK v0.3.0 (`provenance.pdk.version` is `null` at 0.7.0).
- Command (from the repo root, after `scripts/setup-env.sh`):
  `uvx --from klayout-tools==0.7.0 klt drc --format json --deck sg13g2 --top sg13g2_pa --pdk ihp-sg13g2 --pdk-root ~/.cache/sg13g2-pa/pdk-root layout/pa/sg13g2_pa.gds > layout/reports/drc.json`
  (exit 3 = violations). Freshness: `klt drc --check layout/reports/drc.json`
  (reports `match`); regenerate the report whenever the GDS hash changes.
- What the violations are: every one is on a contact (`Cont.drawing`) inside
  the PDK-authored `npn13G2_base_CDNS_675179387640` sub-cell, 14 of
  1.65 x 0.16 um and 14 of 1.52 x 0.16 um (two per placed HBT, 14 HBTs). The
  rule text is "min/max Cont size (fixed 0.16 x 0.16 um square)". These are
  PDK cell internals, not geometry drawn here. Whether they are real
  violations or an over-strict curated-deck rule on the PDK's bar contacts
  is **not established**; no waiver is claimed. Follow-up filed (see PR).

Coverage fields quoted verbatim from `coverage` in the report (item 3's
disclosure, claimant-enforced; these must accompany any future `clean`):

- `coverage.deck_scope`: `Act, Cnt, Gat, M1, M2, M3, M4, M5, MIM, TM1, TM2, TV1, TV2, V1, V2, V3, V4`
- `coverage.layers_in_stream_without_rules` (drawn in the GDS, no rule in the
  deck): `1/20, 7/21, 8/2, 10/2, 14/0, 26/0, 33/0, 51/0, 63/0`
- `coverage.rules_skipped` (33 rules): `gatpoly.enclosing.cont.1, gatpoly.separation.activ.1, gatpoly.space.1, gatpoly.width.1, metal2.enclosing.via2.1, metal3.enclosing.via3.1, metal3.space.1, metal3.width.1, metal4.enclosing.via4.1, metal4.space.1, metal4.width.1, metal5.enclosing.mim.1, metal5.enclosing.topvia1.1, metal5.space.1, metal5.width.1, mim.enclosing.topvia1.1, topmetal1.enclosing.topvia1.1, topmetal1.enclosing.topvia2.1, topmetal1.space.1, topmetal1.width.1, topmetal2.enclosing.topvia2.1, topmetal2.space.1, topmetal2.width.1, topvia1.space.1, topvia1.width.1, topvia2.space.1, topvia2.width.1, via2.space.1, via2.width.1, via3.space.1, via3.width.1, via4.space.1, via4.width.1`

`coverage.skipped` is `[]` and every `rules_skipped` entry also appears in
`coverage.inapplicable` with reason `no_applicable_geometry`. `layers_checked`
is `1/0, 6/0, 8/0, 10/0, 19/0` and `rules_checked` has 12 rules. The layers the HBT cell draws
without rules (the list above) are not DRC-checked at all, so even a future
`clean` would not cover them.
