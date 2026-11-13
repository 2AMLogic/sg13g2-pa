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
  `evidence/item2.json`), 9 (testbenches shipped, from `evidence/item9.json`)
  and 10 (repo hygiene, from `evidence/item10.json`) are cited today.
- **`../attest/item1.json`**: the item-1 attestation inventory (the xschem
  schematic and `xschemrc`, plus the netlist derived from them with its
  `klt netlist --check` freshness command, `local_only`).
- **`../evidence/item1.json`**: the envelope `klt signoff --attest 1`
  produced from it. Generated, never hand-edited.
- **`../evidence/item2.json`**: the envelope `klt signoff --attest 2`
  produced from `layout/pa/sg13g2_pa.gds`. Generated, never hand-edited. The
  manifest's `content_hash` for item 2 is `sha256sum layout/pa/sg13g2_pa.gds`.
- **`../attest/item9.json`**: the item-9 attestation inventory: every committed
  bench (`sim/smoke`, `sim/known-answer`, `sim/device-npn13g2`, `sim/psat-sweep`,
  `sim/ac-gain`, `sim/ac-stability`), each primary bench with its cold-start argv
  (`local_only`: they need the pinned PDK, ngspice, numpy and, for the grid benches,
  the batch fleet), plus the PDK and tool pins.
- **`../evidence/item9.json`**: the envelope `klt signoff --attest 9` produced from
  it. Generated, never hand-edited. The manifest's `content_hash` for item 9 is
  `sha256sum attest/item9.json`.
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

Item 9 (runs every cold start for real, so it needs `scripts/setup-env.sh`
done, ngspice, a `python3` with numpy on `PATH`, and the batch fleet for the grid
benches; several minutes, and it appends a record under each bench's `records/`):

```console
uvx --from "klayout-tools==0.9.1" klt signoff \
    --attest 9 --inventory attest/item9.json -o evidence/item9.json
```

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

`tier: null`, 4 of 11 T1 items met (item 1, design sources; item 2, layout
stream; item 9, testbenches shipped; item 10, repo hygiene); the other seven are
`unmet` with a `reason` in the record (`no_evidence` for items 3-8 and 11). The record is the source of truth,
not this paragraph.

## T1 item 3 (DRC): the 28 `cont.width.1` violations were a deck artifact

The 28 `cont.width.1` violations previously recorded here were **not real
violations**. They were an artifact of the curated `klt` 0.7.0 `sg13g2` deck
applying the foundry's square-contact rule to the PDK's bar contacts. The
same stream re-run on `klt` 0.9.1 reports **`status: clean`, 0 violations**,
with `cont.width.1` still in `coverage.rules_checked` (the rule ran; it was
not dropped or relaxed). No deck was relaxed and no waiver is claimed.

### Why the 0.7.0 result was wrong

In the pinned PDK (IHP-Open-PDK v0.3.0) the foundry runset splits Cont (6/0)
into squares and bars before any Cont rule runs
(`libs.tech/klayout/tech/drc/ihp-sg13g2.drc`, "cont/contbar general
derivations"):

```ruby
cont_nseal = cont_drw.not(edgeseal_drw)
contbar    = cont_nseal.non_squares
cont_sq    = cont_nseal.not(contbar)
```

`Cnt.a` — the "min. and max. Cont width 0.16 µm" rule the curated deck
transcribes as `cont.width.1` — is measured on `cont_sq` **only**
(`rule_decks/feol/5_14_cont.drc`):

```ruby
cnt_a_l = cont_sq.without_bbox_width(cnt_a_value.um)
```

All 28 flagged polygons are 1.65 × 0.16 µm or 1.52 × 0.16 µm. Those are
non-squares, so the foundry runset routes them to `contbar` and `Cnt.a`
never sees them. Bars are governed by the separate 5.15 ContBar table
(`rule_decks/feol/5_15_contbar.drc`), which contains **no** bar width or
size rule at all — only `CntB.b1` (bar-to-bar space for a common run
> 5 µm) and `CntB.h1` (min. Metal1 enclosure), and `CntB.h1` explicitly
excludes the HBT cell: `contbar.not(npn13g2)`. The foundry deck therefore
treats these PDK-authored bars as legal geometry by construction.

`klt` 0.7.0's `cont.width.1` carried no layer selection, so it measured
every merged Cont polygon, bars included. `klt` 0.8.0 added
`layer_selection="squares"` to `cont.width.1` and `cont.space.1`, mirroring
upstream's `cont_sq`; the deck source cites klayout-tools issues #2943 and
#3139 for it. Both are closed, so no new tool issue was filed for this
cause — see "Residual gap" below for what was filed instead.

### The corrected report

- Report: [`../layout/reports/drc-klt-0.9.1.json`](../layout/reports/drc-klt-0.9.1.json),
  `status: clean`, `violation_count: 0`, schema_version 3.
- Same stream, same hash: `layout/pa/sg13g2_pa.gds`, sha256
  `630bfca67b12d51f1d422ecf3221252f480e128e33a39c825e9201c4408135ee` — the
  hash in `layout/pa/provenance.json`. The GDS was not regenerated or edited.
- Tool: `klt` 0.9.1 (`provenance.klt_reinstall_spec`,
  `klt_git_commit 4d0d29be4fd991f499d59e783a908082d5e24c56`), the same pin
  `layout/pa/generate.sh` and the `signoff` workflow already use. KLayout
  engine 0.30.13 (`klt` warned it differs from the 0.30.12 it was tested
  against; `provenance.klayout_version_mismatch: true` — `klt` states the
  verdict is unaffected, counts such as `rules_skipped` may differ). Deck
  `sg13g2`, content hash
  `sha256:1c95db40596afc5412e216009bcf0b775d1d74895b32738447eccbc76336dd15`.
  PDK IHP-Open-PDK `fetched:0.3.0` (0.9.1 records
  `provenance.pdk.version`; 0.7.0 left it `null`).
- Command (from the repo root, after `scripts/setup-env.sh`, with
  `source sim/env.sh` for `PDK_ROOT`):
  `uvx --from klayout-tools==0.9.1 klt drc --format json --deck sg13g2 --top sg13g2_pa --pdk ihp-sg13g2 --pdk-root "$PDK_ROOT" layout/pa/sg13g2_pa.gds > layout/reports/drc-klt-0.9.1.json`
  (exit 0 = clean). Freshness:
  `uvx --from klayout-tools==0.9.1 klt drc --check layout/reports/drc-klt-0.9.1.json`
  (reports `match`); regenerate whenever the GDS hash changes.
- The superseded 0.7.0 report is kept as append-only evidence at
  [`../layout/reports/drc.json`](../layout/reports/drc.json) (`status:
  violations`, 28). It is the record of the artifact, not a current result.
  `layout/toolchain.json`'s `klt.pin` stays 0.7.0: it is the
  `layout/smoke/` pin and those reports were generated with it. The PA DRC
  pin is recorded separately in that file as `pa_drc.pin`.

### What the `clean` does and does not cover

This is simulated tooling output from a curated deck, not a foundry signoff.
Two limits must travel with it:

- **`cont.width.1` and `cont.space.1` are vacuous on this stream.** All 28
  merged Cont polygons in the GDS are bars; there are **zero** square
  contacts, so `layer_selection="squares"` leaves both rules with nothing to
  measure. They nevertheless appear in `coverage.rules_checked` and
  `coverage.checked`, and 6/0 appears in `coverage.layers_checked`. Their
  `clean` means "no square contacts exist here", not "square contacts were
  measured and passed".
- **The 28 bars get no size or spacing check from this deck.** The curated
  deck does not transcribe the `CntB.*` family (its own `cont.width.1`
  docstring says so). The foundry deck has no bar width rule either, so
  nothing is being hidden on size — but `CntB.b1` bar spacing is a real
  foundry rule that this run did not evaluate, and the coverage block does
  not disclose that, because 6/0 does have rules.

### Residual gap filed

The `cont_sq` fix is upstream and closed. What remains is generic: a rule
narrowed by `layer_selection` grades `checked` even when the selection
empties its input, so a stream can earn `clean` with the rule listed as
checked and zero geometry measured — while rules with no input geometry at
all are correctly graded `inapplicable` / `no_applicable_geometry`. Filed
generically as
[`2AMLogic/klayout-tools#5435`](https://github.com/2AMLogic/klayout-tools/issues/5435)
per the friction protocol.

### Coverage disclosure

Quoted verbatim from `coverage` in `drc-klt-0.9.1.json` (item 3's
disclosure, claimant-enforced; these must accompany any `clean` claim):

- `coverage.deck_scope`: `Act, Cnt, Gat, M1, M2, M3, M4, M5, MIM, NW, TM1, TM2, TV1, TV2, V1, V2, V3, V4, pSD`
- `coverage.layers_in_stream_without_rules` (drawn in the GDS, no rule in the
  deck): `7/21, 8/2, 10/2, 26/0, 33/0, 51/0, 63/0`
- `coverage.rules_skipped` (47 rules): `gatpoly.enclosing.cont.1, gatpoly.separation.activ.1, gatpoly.space.1, gatpoly.width.1, metal2.enclosing.via2.1, metal3.enclosing.via3.1, metal3.space.1, metal3.width.1, metal4.enclosing.via4.1, metal4.space.1, metal4.width.1, metal5.enclosing.mim.1, metal5.enclosing.topvia1.1, metal5.space.1, metal5.width.1, mim.enclosing.topvia1.1, nwell.enclosing.nactiv.1, nwell.enclosing.nactiv.dig.1, nwell.enclosing.nactiv.hv.1, nwell.enclosing.pactiv.1, nwell.enclosing.pactiv.dig.1, nwell.enclosing.pactiv.hv.1, nwell.space.1, nwell.space.nactiv.1, nwell.space.nactiv.dig.1, nwell.space.nactiv.hv.1, nwell.space.pactiv.1, nwell.space.pactiv.dig.1, nwell.space.pactiv.hv.1, nwell.width.1, topmetal1.enclosing.topvia1.1, topmetal1.enclosing.topvia2.1, topmetal1.space.1, topmetal1.width.1, topmetal2.enclosing.topvia2.1, topmetal2.space.1, topmetal2.width.1, topvia1.space.1, topvia1.width.1, topvia2.space.1, topvia2.width.1, via2.space.1, via2.width.1, via3.space.1, via3.width.1, via4.space.1, via4.width.1`
- `coverage.unmodeled_rules` (foundry rules the deck does not model): `LU.a, LU.c, LU.c1, LU.d, LU.d1, Pad.a1, Pad.aR, Pad.bR, Pad.d, Pad.d1R, Pad.dR, Pad.gR, Pad.jR, Pad.kR`

`coverage.skipped` is `[]`, `coverage.nothing_checked` is `false`, and all 47
`rules_skipped` entries also appear in `coverage.inapplicable` with reason
`no_applicable_geometry`. `coverage.layers_checked` is
`1/0, 1/20, 6/0, 8/0, 10/0, 14/0, 19/0` and `coverage.rules_checked` has 15
rules: `activ.enclosing.cont.1, activ.space.1, activ.width.1, cont.space.1,
cont.width.1, metal1.enclosing.via1.1, metal1.space.1, metal1.width.1,
metal2.space.1, metal2.width.1, psd.area.1, psd.space.1, psd.width.1,
via1.space.1, via1.width.1` — two of which (`cont.width.1`, `cont.space.1`)
measured nothing, as above. The layers the HBT cell draws without rules are
not DRC-checked at all, so this `clean` does not cover them.

Relative to the 0.7.0 run, 0.9.1 also added the `pSD` and `NW` scopes and
rules for 1/20 and 14/0, which is why those two layers moved out of
`layers_in_stream_without_rules` and `rules_checked` grew from 12 to 15.

### Item 3's status is not changed here

Whether item 3 renders `met` is decided in #38, which owns the item-3 claim
and its manifest citation. This section records the determination and the
corrected report only; `manifests/sg13g2-pa.json` is untouched and item 3 is
still `unmet` / `no_evidence` in the record.
