# sim/device-npn13g2

Single-device `npn13G2` load-line study: simulated DC Ic-Vce family, simulated
fT vs Ic, and an analytic ideal-load-line that turns them into a breakdown /
model-window verdict per candidate supply. It is the first device evidence behind
the DRAFT **Supply**, **Device flavour** and **Thermal** rows of
`spec/target-spec.md` (tracker #5, T1 item 1; issue #21). It **recommends**; it
ratifies nothing and edits no spec row.

## Run

```sh
scripts/setup-env.sh                      # once
sim/device-npn13g2/run_device.sh          # ~2 min on the batch fleet
python3 -I sim/device-npn13g2/loadline.py --self-test
python3 -I sim/device-npn13g2/loadline.py --out sim/device-npn13g2/loadline.json
```

`run_device.sh` first runs the `loadline.py` known-answer self-test and checks the
decks against `gen_bench.py`, then submits two `klt sim` corner requests
(`dc_family`, `ft`: 3 HBT corners x -40/27/125 C each; grids, so the batch fleet
via `KLT_SIM_BACKEND=batch`; a failed submit is reported, never rerun locally),
and writes, append-only, `records/<timestamp>-<sha>.md` plus `.dc.json`,
`.loadline.json`, `.pdk-provenance.json` and `corners/<id>/` artifacts. It
refuses to reuse a record id (exit 4). `loadline.py --out` alone needs no
simulation (it uses the newest `records/*.dc.json` if present, for the Vbe at the
quiescent point only).

## Files

- `gen_bench.py` generates `dc_family.*` and `ft.*` (`--check` verifies the committed copies).
- `dc_family.spice`: Nx 1/4/10 x Vbe 0.70-0.90 V, Vce swept 0-2 V, 4-terminal device, self-heating on (`selft=1`, card default). Ic is read back through a 1 ohm CCVS (ngspice caps `par()` at 99 calls per file).
- `ft.spice`: same instances at Vce = 1.0 V, 1 V ac base drive, collector ac-shorted; h21 = |Ic_ac/Ib_ac| at 20 and 50 GHz; fT = |h21| f0. Valid only where |h21| >> 1 and the two f0 agree.
- `summarize.py` renders the record; `loadline.py` is the analytic study.

## loadline.py definitions

Ideal resistive load, ideal sinusoid, class-A, choke-fed, **ideal passives, no
output network** (decision D-1 defers the real one). Fundamental only; harmonic
terminations are not modelled and efficiency (PAE) is not computed.

- `vce = Vcc + Vswing sin(wt)`; `Vswing = Vcc - Vknee` (`saturated`: tracks the supply at each tolerance cell) or `Vcc_nominal - Vknee` (`fixed-nominal`). `Vknee` = 0.4 V, the window floor.
- Peak `Vce = Vcc + Vswing`; `Vcb_pk = Vce_pk - Vbe_at_peak` (quasi-static, Vbe at peak assumed 0.65 V, the window floor, which is conservative).
- Verdict: peak `Vce` > BVCEO(min) 1.4 V or `Vcb` > BVCBO(min) 3.8 V is a **BREAKDOWN VIOLATION**. Window labels (OUTSIDE MODEL WINDOW) carry the quantity, peak and fraction of the cycle outside (analytic, for a sinusoid): `Vce` outside 0.4-2.0 V, Vbe outside 0.65-0.96 V, Tj > 125 C per ambient (the 125 C ambient is outside by construction).
- `Iq = 1.5 mA x Nx` so the peak `ic` (2 Iq) equals the window limit 3 mA x Nx. `Pout = 1/2 Vswing Iq` per unit of Nx; the Nx needed for +15 dBm (31.62 mW) is `ceil(31.62 mW / Pout_per_Nx)`; the ideal load is `Vswing / (Iq Nx_total)`.
- `Tj = Tamb + Rth (Vcc Iq - Pout)`, `Rth = 3.26e3 (4/Nx)^0.9` K/W (card), for an Nx = 10 device.
- Controls: Vcc 1.4 V saturated must be flagged (negative); Vcc 0.5 V must pass (positive). Both are in the JSON.
- Candidate supplies 0.5-1.4 V include sub-1 V values on purpose: with a swing to `2 Vcc - Vknee`, every supply near BVCEO(min) violates it (hand arithmetic, not a simulation).

## Hand check (asserted by `--self-test`)

Vcc = 0.9 V, Vknee = 0.4 V, saturated: Vswing 0.5 V, Vce_pk 1.4 V (on the BVCEO(min) line, not above), Vce_min 0.4 V, Vcb_pk 1.4 - 0.65 = 0.75 V. Pout per Nx = 0.5 x 0.5 V x 1.5 mA = 0.375 mW = -4.26 dBm. Nx for +15 dBm = ceil(31.62 / 0.375) = 85 (Ipk 127.5 mA, 31.9 mW = +15.03 dBm; ideal load 0.5 / 0.1275 = 3.92 ohm; 9 devices of Nx = 10). The +10 % cell (Vcc 0.99, Vswing 0.59) peaks at 1.58 V: violation. Fixed swing 0.2 V on 0.5 V: `a = (0.5-0.4)/0.2 = 0.5`, fraction of the cycle below 0.4 V = 0.5 - asin(0.5)/pi = 1/3.
