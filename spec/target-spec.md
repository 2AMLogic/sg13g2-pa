# Target specification

**Status: RATIFIED for the rows marked RATIFIED, DRAFT for the rest**, by
decision record
[0001 — ratify the target spec](decision-records/0001-ratify-target-spec.md)
(issue [#2](https://github.com/2AMLogic/sg13g2-pa/issues/2)). Approval of the
PR that lands this file and that record is the ratification act. A row that
cannot yet be justified by evidence stays DRAFT and is listed as deferred in
the record; nothing here is force-ratified, and an agent does not relax a
RATIFIED row to make a result pass (`CLAUDE.md`).

**Nothing in this file is a result.** Every number is a target, a fallback, a
stretch, or a quoted PDK limit. No schematic, simulation, layout or device
characterization exists yet. Hand arithmetic in the notes is labelled as such
and is not evidence.

The ladder is the README's: **+15 dBm saturated is the target**, +10 dBm the
fallback, +20 dBm a stretch. The stretch does not drive device stacking before
the target closes.

## Sources

Every quoted limit is from one of these. Revisions are pinned; re-read on bump.

| Tag | Source | Pinned at |
|---|---|---|
| (P) | `SG13G2_os_process_spec.pdf`, **SG13G2 Process Specification Rev. 1.2 (2023-12-20)**, at `ihp-sg13g2/libs.doc/doc/` | IHP-Open-PDK **v0.3.0** (`.fetched-version` = `0.3.0`; the revision `sg13g2-lna/sim/pdk.json` pins) |
| (M) | `ihp-sg13g2/libs.tech/ngspice/models/sg13g2_hbt_mod.lib`, VBIC Rev. 1.15, TNOM 27 °C | same v0.3.0 install |
| (L) | `2AMLogic/sg13g2-lna` `spec/target-spec.md` | `50728637d958768ae1b4298d97145b70f18abf94` (its `spec/` is byte-identical to `02c5ba2`) |
| (S) | `2AMLogic/sg13g2-sat-rx` `spec/target-spec.md`, `spec/porting-plan.md` | `b82e458d3277e85870880d2c551284108d371311` |
| (V) | `2AMLogic/sg13g2-vco` `sim/inductor-model/README.md`, `spec/target-spec.md` | `17e49a8f9aa4f858cff804ff33c3c484ed826095` |
| (R) | `SG13G2_os_layout_rules.pdf`, Rev. 0.4 (2024-12-19) | v0.3.0 install |

### PDK limits on the three HBT flavours — (P) §3, Rev. 1.2

Minimum-size process-control devices; the comment column gives the emitter
area measured. "Min" is the guaranteed floor and is what every budget below
uses.

| Parameter | `npn13g2` (§3.1, p. 20) | `npn13g2l` (§3.2, p. 20) | `npn13g2v` (§3.3, p. 21) |
|---|---|---|---|
| BVCEO (min / max) | **1.4** / 1.6 V | **1.4** / 1.6 V | **2.2** / 2.5 V |
| BVCBO (min / max) | **3.8** / 4.8 V | **3.8** / 4.8 V | **7** / 8.5 V |
| BVEBO (min / max) | 1.0 / 1.6 V | 1.0 / 1.6 V | 1.0 / 1.8 V |
| ICMAX | 3.5 mA (0.07×0.9 µm²) | 3.0 mA (0.07×1 µm²) | 0.5 mA (0.12×1 µm²) |
| fT (min / max), 4 emitters | 300 / 350 GHz | 280 / 330 GHz | 90 / 120 GHz |
| fmax (min / max), 4 emitters | 400 / 450 GHz | 380 / 430 GHz | 280 / 330 GHz |
| Emitter measured | 0.07×0.9 µm² | 0.07×1 µm² | 0.12×1 µm² |

BVCEO and BVCBO are DC, open-base / open-emitter figures at process-control
bias. They are the documented breakdown the README and `CLAUDE.md` bind the
design to; an RF stage driven with a low-impedance base sustains higher
`V_CE` than BVCEO, but that is a design-phase claim that needs its own
extraction, and it does not move the budget here.

### Model validity window — (M) header, lines 33–36 (`npn13G2`), 269–272 (`npn13G2l`), 503–506 (`npn13G2v`)

| Flavour | `ic` | `vbe` | `vce` | Temperature | Size | Also in card |
|---|---|---|---|---|---|---|
| `npn13G2` | < 0.003·Nx A | 0.65–0.96 V | **0.4–2.0 V** | −40…+125 °C | Nx = 1–10 (0.07×0.90 µm² per Nx) | `vce_max = 1.6` (line 54), `selft=1`, `rth = 3.26e3·(4/Nx)^0.9` K/W, `cth = 1.6e-12·(Nx·0.25)^0.95` F |
| `npn13G2l` | < Nx·El (header text, line 270) | 0.65–0.96 V | **0.4–2.0 V** | −40…+125 °C | Nx = 1–4, El = 1–2.5 | `vce_max = 1.6` (line 290) |
| `npn13G2v` | < 0.50·Nx·El A | 0.65–0.84 V | **0.8–2.3 V** | −40…+125 °C | Nx = 1–4, El = 1–5 | `vce_max = 2.2` (line 525) |

Two consequences the design must carry, and which no one may quote around:

1. **The window has a floor as well as a ceiling.** A PA driven into
   compression pulls `V_CE` toward saturation. For `npn13G2`/`npn13G2l`
   anything below **0.4 V** (below **0.8 V** for `npn13G2v`) is outside the
   card's window. Compression and saturated-power results therefore sit
   outside the window by construction wherever the collector bottoms out;
   they are labelled as such with the fraction of the cycle spent outside
   (see "Window labelling").
2. **The breakdown budget binds well before the window ceiling** for the
   high-speed flavours: BVCEO(min) 1.4 V against a 2.0 V window top, so the
   binding limit is the process spec, not the card. For `npn13g2v` the two
   nearly coincide (2.2 V vs 2.3 V).

The headers' "Maximum collector-to-emitter voltage" (1.6 at lines 27 and 263,
2.5 at line 497) and the `vce_max` parameters (1.6 / 1.6 / 2.2) sit at or above
the process-spec BVCEO *minimum* (1.4 V; 2.2 V for `npn13g2v`). The budget uses
the process-spec minimum, the more conservative figure.

### Corner model files — exact names

All under `ihp-sg13g2/libs.tech/ngspice/models/` (v0.3.0). Section names were
read from the `.LIB` lines of each file.

| Device class | File | Sections (✔ = in the PVT box) |
|---|---|---|
| HBT | `cornerHBT.lib` | `hbt_typ` ✔, `hbt_bcs` ✔, `hbt_wcs` ✔; also present, **not** in the box: `hbt_typ_mismatch`, `hbt_bcs_mismatch`, `hbt_wcs_mismatch`, `hbt_typ_stat` |
| MOS, HV | `cornerMOShv.lib` | `mos_tt` ✔, `mos_ss` ✔, `mos_ff` ✔, `mos_sf` ✔, `mos_fs` ✔ (+ `_mismatch`, `mos_tt_stat` not in the box) |
| MOS, LV | `cornerMOSlv.lib` | same section names; used only if a LV MOS is instantiated (bias circuitry) |
| Resistor | `cornerRES.lib` | `res_typ` ✔, `res_bcs` ✔, `res_wcs` ✔ (+ `_mismatch`, `res_typ_stat`) |
| Capacitor | `cornerCAP.lib` | `cap_typ` ✔, `cap_bcs` ✔, `cap_wcs` ✔ (+ `_mismatch`, `cap_typ_stat`) |

The HBT corner file ships **three** process corners (typ/bcs/wcs), not five
(established in (S) `spec/target-spec.md`). The HV and LV MOS libraries ship
`ss`/`ff`/`sf`/`fs` in addition to `tt`. The PSP103 MOS and `r3_cmc` models
are Verilog-A and load in ngspice only as OSDI binaries built with the
toolchain `sg13g2-lna` pins (`sim/pdk.json` `osdi_toolchain`, OpenVAF-Reloaded
`v24.0.1mob`); the VBIC `npn13G2*` and Gummel-Poon `pnpMPA` cards are native
and need none.

### PVT corner box

| Axis | Values | Notes |
|---|---|---|
| HBT process | `hbt_typ`, `hbt_bcs`, `hbt_wcs` | `cornerHBT.lib` |
| MOS process (if any MOS is used) | `mos_tt`, `mos_ss`, `mos_ff`, `mos_sf`, `mos_fs` | HV flavour where the supply exceeds the LV maximum |
| R / C process | `res_typ/bcs/wcs`, `cap_typ/bcs/wcs` | paired with the HBT corner of the same name |
| Temperature | **−40, 27, 125 °C** ambient | **Self-heating on** (card default `selft=1`); the *device* temperature is ambient + P·rth and is reported, see row "Thermal" |
| Supply | nominal **±10 %** (nominal set by the supply row) | |
| Drive | swept from small-signal through compression to deep saturation | the drive step is stated in each bench |
| Frequency | 2400, 2441.75, 2483.5 MHz (band edges and center) | harmonic content evaluated at 2f₀, 3f₀ of each |

**Window labelling.** For every cell, each device's `V_CE`, `V_CB`, `V_BE`,
`I_C` and **junction temperature** are recorded against both the (P) breakdown
limit and the (M) window. A cell where any device leaves the window at any
instant is labelled **OUTSIDE MODEL WINDOW** with the offending quantity, its
peak value and the fraction of the cycle it is outside; it is never quoted as
a pass. A cell where a device exceeds its (P) BVCEO or BVCBO minimum is a
**breakdown violation** and fails the row regardless of the window. A junction
temperature above +125 °C is outside the window's temperature range.

## Ratified target table

Columns: parameter / **target** / fallback / stretch / binding conditions /
planned testbench / evidence tier / notes. Evidence tiers: **(1)** committed
simulation, **(2)** PDK document or model file, **(3)** sibling-repo
evidence, **(4)** convention / definition, **(5)** hand arithmetic, no
testbench. No row is tier (1) yet, because no bench exists.

| Parameter | Target | Fallback | Stretch | Binding conditions | Planned testbench | Tier | Notes |
|---|---|---|---|---|---|---|---|
| **Band** — RATIFIED | 2400–2483.5 MHz (2.4 GHz ISM) | same | — | Every "in band" figure is evaluated at 2400, 2441.75 and 2483.5 MHz; S-parameter sweeps cover ≥ 11 points across it | all benches | (3) + (4) | Follows `sg13g2-lna` row "Band — RATIFIED 2400–2483.5 MHz" at (L); the PA and LNA then share one frequency plan. A 5–6 GHz variant is out of scope and would need its own record. |
| **Saturated output power (Psat)** — RATIFIED | **> +15 dBm** | > +10 dBm | > +20 dBm | Load: 50 Ω resistive at f₀, source of stated impedance, single tone, drive swept to saturation; harmonic terminations stated in the bench (default: ideal 50 Ω at 2f₀, 3f₀ until the output network says otherwise, and labelled so); defined as the maximum of P_out(P_in) over the drive sweep, as a fundamental-tone power from the extraction below. Every PVT cell; worst cell is the figure | `sim/psat-sweep/` (transient, see "Large-signal extraction") | (2) + (4) + (5) | Ladder from the README draft, unchanged. Hand arithmetic (tier 5, not evidence): +15 dBm is 31.6 mW; into 50 Ω that is 1.78 V peak, and with a collector swing held under BVCEO(min) = 1.4 V a single `npn13g2` needs a load transformation to roughly 8 Ω and ~90 mA peak, i.e. an array whose per-instance `ic` stays under the window's 0.003·Nx A. Whether that closes with margin on one device or needs a stack is **open question 1**, deferred. |
| **Output P1dB** — RATIFIED | **> +12 dBm** | > +7 dBm | > +17 dBm | Same load, drive, terminations and corners as Psat. Reference gain: the small-signal gain from the linear region of the same sweep (drive ≥ 20 dB below the compressing level); P1dB is the output power where large-signal gain is 1.00 dB below it, interpolated between drive points no more than 0.5 dB apart | `sim/psat-sweep/` | (4) + (5) | Ladder from the README draft, unchanged. Target sits 3 dB below Psat, the README draft's spacing. |
| **Power gain** — RATIFIED | **> 15 dB** (small-signal, in band) | > 10 dB | > 20 dB | Transducer gain with 50 Ω source and load, at the bias point of the Psat bench, evaluated at the 3 band points, every PVT cell; stated alongside the large-signal gain at P1dB | `sim/ac-gain/` (S-parameters at the quiescent point) | (4) | Ladder from the README draft, unchanged. |
| **Peak PAE** — RATIFIED | **> 25 %** | > 15 % | > 35 % | PAE = (P_out,f₀ − P_in,f₀) / P_DC with P_DC the full supply power of the stage **including bias and driver circuitry**, integrated over an integer number of RF periods (see extraction); maximum over the drive sweep; every PVT cell | `sim/psat-sweep/` | (4) | Ladder from the README draft, unchanged. If the driver is not on the supply measured, the bench says so; PAE is never quoted for the output stage alone while the driver is excluded unless labelled. |
| **PAE at back-off** — DRAFT | reported at 6 dB below Psat; **no pass/fail threshold yet** | — | — | Same definition as Peak PAE, at P_out = Psat − 6 dB | `sim/psat-sweep/` | (4) | Not in the README draft. A threshold has no evidence behind it before the first bias and load-line study; recorded as deferred (record 0001, D-2). |
| **Input match (S11)** — RATIFIED | **< −10 dB** across the band | < −8 dB | < −15 dB | 50 Ω reference, small-signal at the quiescent point **and** reported at Psat drive (large-signal S11 from the drive-port V/I fundamentals); every PVT cell | `sim/ac-gain/`, `sim/psat-sweep/` | (4) | Ladder from the README draft, unchanged. |
| **Output port / match** — RATIFIED | **50 Ω, on-chip output match** | 50 Ω, **off-chip** output match (stated boundary) | — | Port convention: single-ended 50 Ω. The fallback moves the matching network off chip; the bench then states exactly where the chip boundary is and what the off-chip network is assumed to be, and its loss is **not** counted as the chip's | `sim/psat-sweep/` (load network in the testbench) | (4) | The on-chip target depends on the inductor-model source, which is **deferred** (record 0001, D-1). Until it lands, an on-chip result through ideal passives is labelled "through ideal passives" and is not a result for this row. |
| **Inductor / passive models** — DRAFT | each inductor's model source, loss (Q at f₀) and self-resonance stated at every use | — | — | A figure for P_out or PAE through an inductor with no stated source, Q and SRF is not quotable. Using `sg13g2-vco`'s model in-tree needs a `consumes` edge (operator decision) | bench output-network characterization | (3) | See record 0001, D-1. Source of the inductor model is **deferred, not decided**. |
| **Stability, small-signal** — RATIFIED | **μ > 1** (Edwards–Sinsky), 10 MHz–30 GHz, **k, \|Δ\| and the negative-resistance check (max \|S11\|, max \|S22\| < 1 with the other port at 50 Ω) reported** | same | — | Every PVT cell, at the quiescent point and at the bias extremes the cell produces | `sim/ac-stability/` (≥ 40 pts/decade) | (3) + (4) | Same metric and sweep as `sg13g2-lna` at (L) ("μ > 1 over 10 MHz–30 GHz, k, \|Δ\|, negative-resistance check reported"). μ is the pass metric because k is ill-conditioned on low-S12 topologies (finding documented at (L)); k is reported, not graded. |
| **Stability, large-signal** — DRAFT | no sustained non-harmonic spectral line in the output transient at any drive level of the sweep, evaluated from the same windows as Psat; **line-level threshold not yet set** | — | — | Every drive point of the Psat sweep, every PVT cell, including deep saturation. The window is long enough to resolve a subharmonic at f₀/2 and the bias-loop time constant | `sim/psat-sweep/` (spectrum of the steady window) | (4) | The README draft says "same" (unconditional) without a large-signal definition. This row adds one; the numeric line limit is deferred until a first spectrum exists (record 0001, D-2). Small-signal μ > 1 does **not** imply large-signal stability and is not quoted as such. |
| **Supply** — DRAFT | single rail, **nominal to be set by the first load-line study**; ±10 % is binding | — | — | Nominal is chosen so that, in every PVT cell, peak `V_CE` and `V_CB` on every device stay under (P) BVCEO(min)/BVCBO(min) of that flavour (table above) | `sim/psat-sweep/` (per-device `V_CE`, `V_CB` peaks) | (2) + (5) | Not ratified: choosing a nominal now would be a number without a bench. Ceiling for the choice: ≤ 1.4 V peak `V_CE` on `npn13g2`/`npn13g2l` or ≤ 2.2 V on `npn13g2v` at the worst cell (from (P)); a PA's collector swing exceeds its supply, so the nominal supply is **below** these. Deferred (record 0001, D-2). |
| **Device flavour and stacking** — DRAFT | **`npn13g2` single device is the first design**; a stack or `npn13g2v` is entered only if the load-line study shows the target cannot close with margin to breakdown on one device | — | stack/`npn13g2v` only for the +20 dBm stretch | Peak `V_CE`, `V_CB` per device, per cell, against (P) and (M) above. Stretch never drives stacking before the target closes (`CLAUDE.md`). | `sim/psat-sweep/` | (2) + (5) | Recommendation, not a ratified choice: see open question 1 in record 0001. `npn13g2v` has fT 90–120 GHz (still ≈ 40× f₀) and BVCEO ≥ 2.2 V but ICMAX 0.5 mA per 0.12×1 µm² — much less current per area. |
| **Device stress (breakdown / window)** — RATIFIED | no device beyond its documented (P) breakdown at any instant of the full swing, every cell; every cell states peak `V_CE` and `V_CB` per device; **and every cell inside the model card's validity window** | no device beyond its documented (P) breakdown at any instant of the full swing, every cell; every cell states peak `V_CE` and `V_CB` per device (breakdown only; the window is not required) | — | Cells outside the model card's validity window are labelled OUTSIDE MODEL WINDOW (never "pass") | all large-signal benches | (2) | Ladder from the README draft, with the window labelling made explicit; Target/Fallback cells corrected to match the README draft by record 0002. A BVCEO excursion is judged against the minimum (1.4 V / 2.2 V), not the typical. |
| **Thermal** — DRAFT | junction temperature reported for every output device in every cell; **T_j ≤ +125 °C** is the in-window condition; no numeric reliability limit yet | — | — | T_j = ambient + P_diss·R_th with `rth` from the card (`3.26e3·(4/Nx)^0.9` K/W for `npn13G2`); the 125 °C ambient cell pushes T_j above the card's +125 °C window ceiling by construction and is labelled | `sim/psat-sweep/` with the 5-terminal (`*_5t`) device or the 4-terminal one with self-heating, per open question 4 | (2) + (5) | The PDK documents no junction-temperature reliability limit in (P) that this repo has located; the in-window condition is the card's temperature range. Deferred (record 0001, D-2). |
| **Electromigration** — DRAFT | every output-path wire and via carries ≤ the (P) §2.15 maximum current density for its layer, at the peak RMS/DC current of the worst PVT cell | — | — | (P) §2.15 (p. 16, "11 years @ 105 °C"): Metal1 1 mA/µm (w > 0.36 µm); Metal2–5 2 mA/µm (w > 0.3 µm); TopMetal1 15 mA/µm; TopMetal2 16 mA/µm; Contact 0.3 mA; Via1–4 0.4 mA; TopVia1 1.4 mA; TopVia2 10 mA | layout current-density check after layout; DC/RMS currents from `sim/psat-sweep/` | (2) | The limits are quoted; the current they apply to is a layout-phase quantity. The 105 °C reference differs from the 125 °C corner; no derating is applied or claimed here. Unratified: a pass/fail rule needs the DC-vs-RMS reading of (P) §2.15, deferred (record 0001, D-2). |
| **Harmonics (2nd, 3rd)** — DRAFT | reported at Psat and at Psat − 6 dB; **no pass/fail threshold yet** | — | — | Evaluated by the harmonic extraction below with the harmonic terminations stated | `sim/psat-sweep/` | (4) | The README is silent. "If specified" in the issue: specified as a report, not a limit, until an output network exists to terminate them. Deferred (record 0001, D-2). |
| **Area** — DRAFT | reported (bounding box of the placed cell) | — | — | After layout | `layout/` | (4) | No budget before a floor-plan exists; deferred (record 0001, D-2). |
| **Signoff** — RATIFIED | **DRC + LVS clean, post-layout re-verified** | DRC + LVS clean | — | `klt` DRC and LVS decks; post-layout re-verification means every ratified row above is re-run on extracted parasitics | `layout/` + the benches above | (4) | Ladder from the README draft, unchanged. |

## Large-signal extraction without harmonic balance

ngspice here is run with transient analysis only; no harmonic-balance
analysis is available in the flow. Psat, P1dB, PAE and harmonics are
extracted from transient benches as follows. Each bench restates these
parameters in its record.

- **Load and source.** Output load: 50 Ω resistor at f₀ through the stated
  output network (ideal or modelled — the record says which). Source:
  sinusoidal voltage with stated series resistance (50 Ω), amplitude set per
  point so the **available** power is the stated drive. Input power is
  computed from the measured input-port V and I (not from the available
  power), so mismatch is counted.
- **Harmonic terminations.** Stated per bench; the default is an ideal 50 Ω
  at 2f₀ and 3f₀ and is labelled as the default. A bench that changes them
  says so, and PAE or P_out under different terminations is not compared.
- **Settling.** Run at least 100 RF periods, and until the cycle-to-cycle
  change of both P_out and the supply current (each averaged over one period)
  is below 0.01 dB / 0.1 % for 10 consecutive periods. The bias loop and the
  self-heating thermal node are the slowest elements: for the card's
  `rth·cth` the thermal time constant is of order 5 ns (`3.26e3 Ω·1.6e-12 F`
  for Nx = 4), about 12 RF periods, so the criterion above must hold, not a
  fixed count alone. Bias-network time constants longer than that extend the
  run.
- **Window and integration.** Integrate over an **integer number of RF
  periods** (default 20) after settling, with a fixed maximum time step of
  T/200 or finer; cumulative integration by the trapezoid rule on the
  simulator's own output points interpolated to a uniform grid.
  P_out = (1/NT)·∫ v_load·i_load dt, P_DC = (1/NT)·∫ v_supply·i_supply dt over
  every supply (bias and driver included), P_in likewise at the input port.
  PAE = (P_out − P_in)/P_DC, with each power the **fundamental-only** component
  for P_out and P_in (see next item) and P_DC the total average.
- **Fundamental and harmonics.** DFT of the load voltage/current over the same
  integer-period window with a rectangular window (coherent, so no leakage);
  P at k·f₀ = ½·Re(V_k·I_k*). Harmonic levels are dBc relative to the
  fundamental power. P_out in the table above is the fundamental component.
- **Compression point.** Drive swept in steps ≤ 0.5 dB through the 1 dB
  compression and in steps ≤ 1 dB to saturation; Psat the maximum
  fundamental P_out over the sweep; P1dB interpolated linearly in dB between
  the two bracketing points.
- **Known-answer check, run before any DUT result is recorded.** A
  resistor-loaded ideal source: ideal sine voltage source of amplitude
  V₀ = 1 V behind 50 Ω into a 50 Ω load. Analytic load power
  = (V₀/2)²/(2·50 Ω) = 2.500 mW = **+3.979 dBm**; an ideal DC source V into R
  gives P_DC = V²/R for the PAE integrator (and PAE of a pure resistor = 0);
  an ideal source with a known 3rd-harmonic amplitude checks the DFT bins. The
  extraction must reproduce the analytic values to within 0.01 dB / 0.1 %
  before any record using it is accepted. The check's own record is committed
  alongside the first DUT record.

## Not covered

- Statistical (Monte Carlo, `_stat`, `_mismatch`) variation: the PVT box is
  process corners × temperature × supply; Monte Carlo and mismatch sections
  are not in the box and no row claims statistical coverage.
- Passive tolerance beyond the `res_*`/`cap_*` corner sections.
- Load pull and mismatched-load behaviour (VSWR): the load is 50 Ω.
- Modulated-signal quantities (EVM, ACPR) and linearization — out of scope per
  the README.
- RF coupling to the substrate and to pads, and package/bondwire parasitics,
  until the layout phase.
- Reliability beyond the (P) §2.15 current-density table (HBT hot-carrier /
  HBT degradation under RF stress): no limit has been located in (P) or (R).
- Silicon: nothing here is measured.

## Maturity position

Spec phase. Position on the README ladder: **spec drafted; ratification
pending PR approval**. Next rung: device and passive characterization, which
is where the DRAFT rows above (supply, flavour/stacking, thermal, EM,
harmonics, back-off PAE, large-signal stability threshold, inductor source)
get their evidence.
