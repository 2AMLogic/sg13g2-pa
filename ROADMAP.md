# Roadmap

`sg13g2-pa` is a 2.4 GHz SiGe HBT power amplifier on IHP SG13G2, built to
exercise the open PDK and `klt` on a large-signal, breakdown-limited block.

Status as of 2026-11-15, `main` @ `9f429fb`.

[`WORK_PLAN.md`](WORK_PLAN.md) is the generated label snapshot and
[`WORK_LOG.md`](WORK_LOG.md) the merge history. The verdict of record is
[`manifests/sg13g2-pa.signoff.json`](manifests/sg13g2-pa.signoff.json); it
wins over anything written here.

## Where it stands

**Spec.** Core rows are ratified (band, Psat, P1dB, power gain, peak PAE, S11,
output port, small-signal stability, device stress, signoff) by
[DR 0001](spec/decision-records/0001-ratify-target-spec.md). Supply, device
flavour and stacking, thermal, electromigration, harmonics, back-off PAE,
large-signal stability, area and the inductor-model source are still DRAFT.
The first topology, a single-stage array of 14 `npn13G2` (`Nx=10`) at 0.8 V, is
[DR 0003](spec/decision-records/0003-first-topology-single-npn13g2.md):
**PROPOSED, not ratified**.

**T1 checklist: 5 of 11 items met, `tier: null`** (tracker: #5, whose table is
stale; the record is current).

| # | Item | State | Evidence |
|---|---|---|---|
| 1 | Design sources | met | `design/sg13g2-pa.sch`, derived netlist, `evidence/item1.json` (#36) |
| 2 | Layout | met | `layout/pa/sg13g2_pa.gds` from `layout/pa/generate.sh`, `evidence/item2.json` (#37) |
| 3 | DRC clean | met | `layout/reports/drc-klt-0.9.1.json`, coverage disclosed in `manifests/README.md` (#38, #58) |
| 4 | LVS clean | unmet, `no_evidence` | #39, held on a scope decision |
| 5 | Full corner verification | unmet, `no_evidence` | benches exist at the nominal cell only |
| 6 | Monte Carlo evidence | unmet, `no_evidence` | no issue |
| 7 | Post-layout verification | unmet, `no_evidence` | no issue; needs a routed layout |
| 8 | Characterization report | unmet, `no_evidence` | no issue |
| 9 | Testbenches shipped | met | `attest/item9.json`, `evidence/item9.json` (#40) |
| 10 | Repo hygiene | met | `evidence/item10.json`, gate `scripts/check-ci.sh` (#41) |
| 11 | Power delivery | unmet, `no_evidence` | #42, depends on #39 |

**What the met items do not mean:**

- The layout is **placement only**: 14 unwired HBT cells. The bias device,
  `Rb`, `Cin`, `Cblock` and `Lchoke` are not drawn (`layout/README.md`).
- The schematic's passives are ideal placeholders (100 nH, 100 pF, 100 pF),
  not a match (`design/README.md`).
- The three DUT benches ran once, at the nominal cell (`hbt_typ`, 27 C,
  0.8 V), into a bare 50 ohm load, as proof that they run cold. Their records
  (`sim/*/records/20261107-*`) report, without a pass claim: Psat 7.92 dBm and
  output P1dB 6.31 dBm (target > +15 / > +12 dBm, fallback > +10 / > +7 dBm),
  in-band S21 at least 17.53 dB, worst S11 -1.18 dB (target < -10 dB), and
  minimum mu 0.0228 at 0.176 GHz (target mu > 1). The design does not yet
  meet its ratified rows; closing them is design work that has no issue.
- The off-chip matched bench (#116, PR #120) reports Psat 12.98 dBm, output
  P1dB -11.78 dBm and peak PAE 24.0 % at the nominal cell — **through an
  ideal, lossless off-chip L-section**, chip boundary `RFOUT`, evidencing
  only the spec's **Fallback** Output-port cell (its boundary convention),
  not the Target (on-chip) cell, which stays unevidenced while DR 0001 D-1
  is open. Its harmonic terminations are set by the network, not the labelled
  ideal-50-ohm default, so its figures are **not comparable** with the
  bare-50-ohm record above. #121 questions the record's `gain_drop_db`
  labelling and is open.
- DR 0001 Q4 (does ngspice solve the HBT thermal node as the PDK intends) now
  has its known-answer check (#115, PR #130): `sim/known-answer-thermal/`
  grades the thermal-node rise against the card's `P * rth` at rel 0.01 %
  with a negative control, and PASSes; `sim/psat-sweep/psat_record.py` now
  cites it in the `Tj max C` labelling paragraph (`df89f7e`), so
  matched-bench records rendered from here on carry the citation —
  the already-committed records keep their original
  "no known-answer check yet" text, which is append-only.
  The check is single-corner (`hbt_typ`, 27 C —
  the card's `rth` carries no process or temperature coefficient). Recording
  the discharge in the spec (#132) and adding the
  bench to the item-9 inventory (#131) are open.
- The README's stale status lines ("Nothing is designed yet", "ratification
  pending PR approval") were refreshed by #117 (PR #124); the stale
  "Built agent-native" paragraph that remains is filed as #128.

Merged work since 2026-11-07 (PRs #82 to #110, then #113, #118, #120, #124
and #130) simplified `sim/` and the CI gate, landed the three seeded Now
items (#115, #116, #117) and refreshed the generated guide snapshots
(#113); it moved no checklist item.

## Now

All five items the 2026-11-13 list carried are delivered as of `main` @
`9f429fb`: the three seeds — thermal-node known-answer check (#115, PR #130),
bench-side off-chip output match (#116, PR #120) and the README status
refresh (#117, PR #124) — are merged with their done-criteria met, and #96
(PR #103) and #106 (PR #109) are closed. What the pinned tree leaves open:

- **#121** — the matched record's `gain_drop_db` labelling: it reads ~3 dB
  where the label implies 14.2 dB.
- **#128** — the README's "Built agent-native" paragraph still claims every
  claim traces to a PVT-corner result.
- **#131** — add `sim/known-answer-thermal/` to the T1 item-9 testbench
  inventory.
- **#132** — record DR 0001 Q4's discharge in the spec; #130 has merged,
  so nothing holds it.

## Next

- **Small-signal stabilisation and input match.** Done when `ac-stability`
  and `ac-gain` records at the nominal cell show mu > 1 over 10 MHz to 30 GHz
  and S11 < -8 dB (Fallback), with every added element's source stated.
  No issue. Unblocked: the off-chip match bench (PR #120) fixes the load the
  device sees.
- **Provisional PVT matrix on the three DUT benches** (3 HBT corners, -40 /
  27 / 125 C, supply +/-10 %). The matrix benches and their provisional
  records landed with #173 (all three benches, every simulated cell window-
  and breakdown-labelled, Supply row still DRAFT). What remains is design
  work the matrix exposed, not bench work: every cell misses Stability and
  Input match (#172), P1dB is missed in every reduced cell and Psat / peak
  PAE fall under their Fallback rungs in the worst cells (#192), and three
  125 C cells do not simulate on the two AC benches (#188; the psat
  transients simulated all 27 cells, and two cold `hbt_bcs` cells refused
  their reduction on drive-grid granularity -- recorded as findings, not
  passes). Done when a re-run of the three benches after #172/#188/#192
  shows every cell simulated with the ratified rows judged without
  softening.
- **Staged LVS run for item 4** (device census plus `klt lvs` recorded as-is
  on the placement GDS). Done when the report is committed and any
  recognition gap is filed upstream. #39. Unblocked by the scope ruling below.
- **Re-run the PA DRC on a klt release that includes the fix for
  [klayout-tools#5435](https://github.com/2AMLogic/klayout-tools/issues/5435)**
  (closed upstream). Done when the cited report no longer grades
  `cont.width.1` and `cont.space.1` as `checked` on a stream with no square
  contacts. No issue; the release carrying the fix was not identified here.

## Later

- **Routed, complete layout** (array wiring, bias device, `Rb`, `Cin`,
  `Cblock`, the choke), then LVS `match` (item 4), ERC supply evidence (item
  11, #42) and post-layout re-verification (item 7). First question: is the
  choke on chip, and if so where does its model come from (DR 0001 D-1)?
- **Ratify the DRAFT rows** with a decision record. First question: does the
  0.040 V margin to BVCEO(min) at 0.8 V +10 % (DR 0003) survive a real,
  reactive load, or is 0.7 V the nominal?
- **Monte Carlo evidence (item 6) and the characterization report (item 8).**
  First question: which ratified rows are statistical for this block?
- **`npn13g2v` or a stack.** First question: does the large-signal bench show
  the target cannot close on one `npn13g2` with margin? If so, the #21
  load-line study is repeated on that flavour's card first.
- **Shuttle seat and measured silicon**, the README ladder's last rungs.

## Blocked and waiting

- **#39 (item 4)** waits on an operator scope decision: the issue body ranks
  three options and recommends splitting it into the staged run and a new
  routed-layout issue. No open issue covers the routed layout.
- **#42 (item 11)** depends on #39's LVS report for the supply pairing.
- **DR 0003** is PROPOSED; ratifying its rows needs the operator, as does the
  `consumes` edge to `sg13g2-vco`'s inductor model (DR 0001 D-1).
- **#5** needs its tracker marker added and its checklist table refreshed.
- **Simplification proposals #77, #85, #87, #93, #104** are held for operator
  approval. **#100** is no longer blocked on #95 (`loom:hermit`, in the
  backlog); its body is baselined on `74baa8e`.

## Not planned

- Upconversion mixer, LO, T/R switch and any linearization (README scope).
- Stacking or `npn13g2v` to chase the +20 dBm stretch before +15 dBm closes.
- Relaxing a ratified row, waiving a DRC rule or hand-editing a GDS or an
  envelope to obtain a `met`.
- Any claim of foundry signoff: the DRC verdict is a curated open-source
  deck's, with its coverage gaps stated.
