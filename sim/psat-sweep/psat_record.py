#!/usr/bin/env python3
"""Reduce a psat-sweep `klt sim` report to the append-only record (markdown + JSON).

    psat_record.py <record-id> <git-sha> <dirty> <klt-version> <ngspice-version> <report.json> <out.json> > record.md

Per drive point (one klt corner each): rf_extract.extract for P_out, P_in, P_DC, PAE,
H2/H3; large-signal S11 from the measured P_in against the available power;
per-device stress (peak V_CE, V_CB, V_BE, I_C, junction temperature) against the
(P) breakdown minima and the (M) model window, over the same integer-period window.
rf_extract.reduce_sweep then gives Psat, P1dB, peak PAE. A point that cannot be
extracted (e.g. UNSETTLED) is listed with its ExtractError code and left out of the
reduction; it is never dropped silently.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import rf_extract as rx  # noqa: E402

F0 = 2.44175e9
RS = 50.0
N_UNITS = 14                       # array devices sharing COLL/VB (design/netlist/sg13g2-pa.spice)
NX = 10
# (P) SG13G2 Process Specification Rev. 1.2, npn13g2: minima.
BVCEO_MIN, BVCBO_MIN = 1.4, 3.8
# (M) sg13g2_hbt_mod.lib npn13G2 validity window.
VCE_WIN = (0.4, 2.0)
VBE_WIN = (0.65, 0.96)
IC_MAX_PER_DEVICE = 0.003 * NX     # 0.003*Nx A
TJ_MAX_C = 125.0


def dbm(w):
    return 10 * math.log10(w / 1e-3)


def stress(t, s, ex, ambient_c):
    """Peaks and window fractions over the extraction's integer-period window."""
    t0 = ex["window_start_s"]
    t1 = t0 + ex["window_periods"] / F0
    m = (t >= t0 * (1 - 1e-9)) & (t <= t1 * (1 + 1e-9))
    vc = s["v(xdut.coll)"][m]
    vb = s["v(xdut.vb)"][m]
    ic = (s["i(l.xdut.lchoke)"][m] - s["i(vlsense)"][m]) / N_UNITS
    tj_rise = s["v(xdut.xq1.t)"][m]
    vcb = vc - vb
    tj = ambient_c + tj_rise
    frac = lambda mask: float(np.mean(mask))   # noqa: E731  (uniform-ish step; reported as sample fraction)
    out = {
        "vce_pk_v": float(vc.max()), "vce_min_v": float(vc.min()),
        "vcb_pk_v": float(vcb.max()), "vbe_pk_v": float(vb.max()), "vbe_min_v": float(vb.min()),
        "ic_pk_a": float(ic.max()), "tj_max_c": float(tj.max()),
        "frac_vce_outside": frac((vc < VCE_WIN[0]) | (vc > VCE_WIN[1])),
        "frac_vbe_outside": frac((vb < VBE_WIN[0]) | (vb > VBE_WIN[1])),
        "frac_ic_outside": frac(ic > IC_MAX_PER_DEVICE),
        "frac_tj_outside": frac(tj > TJ_MAX_C),
    }
    out["breakdown_violation"] = bool(out["vce_pk_v"] > BVCEO_MIN or out["vcb_pk_v"] > BVCBO_MIN)
    out["outside_window"] = bool(any(out[k] > 0 for k in
                                     ("frac_vce_outside", "frac_vbe_outside", "frac_ic_outside", "frac_tj_outside")))
    return out


def label(st):
    tags = []
    if st["breakdown_violation"]:
        tags.append("BREAKDOWN VIOLATION")
    if st["outside_window"]:
        tags.append("OUTSIDE MODEL WINDOW")
    return "; ".join(tags) if tags else "inside window, within breakdown minima"


def main(argv):
    rid, sha, dirty, klt_v, ng_v, report_path, out_json = argv[1:8]
    rep = json.load(open(report_path))
    points, failures = [], []
    for c in rep["corners"]:
        cid = c.get("corner_id", "?")
        if c.get("status") != "pass":
            failures.append({"corner_id": cid, "code": f"KLT_STATUS_{c.get('status')}"})
            continue
        amp = c["supply_v"]["vamp"]
        pav = amp * amp / (8 * RS)
        try:
            t, s = rx.load_klt_waveform(c["artifacts"]["waveform"])
            ex = rx.extract(t, F0, s["v(out)"], s["i(vlsense)"],
                            supplies=[(s["v(vcc)"], -s["i(vcc)"])],
                            v_in=s["v(in)"], i_in=-s["i(bs)"])
            ex = {k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in ex.items()}
            ex["p_avail_dbm"] = dbm(pav)
            ex["s11_large_db"] = 10 * math.log10(max(1 - ex["p_in_w"] / pav, 1e-12))
            ex["stress"] = stress(t, s, ex, c.get("temperature_c", 27))
            ex["corner_id"] = cid
            points.append(ex)
        except rx.ExtractError as e:
            failures.append({"corner_id": cid, "p_avail_dbm": dbm(pav), "code": e.code, "message": str(e)})
    points.sort(key=lambda p: p["p_in_w"])
    red, red_err = None, None
    try:
        red = rx.reduce_sweep(points)
    except rx.ExtractError as e:
        red_err = {"code": e.code, "message": str(e)}

    json.dump({"record_id": rid, "points": points, "failures": failures, "reduction": red,
               "reduction_error": red_err}, open(out_json, "w"), indent=1, default=float)

    o = []
    w = o.append
    w(f"# psat-sweep record {rid}")
    w("")
    w("**Simulated** (ngspice transient), nominal cell only, **through ideal passives** "
      "(`Lchoke`, `Cblock`, `Cin` of the DUT are lossless with no self-resonance; no inductor model "
      "is used). P_out, PAE and the harmonics below are not quotable as an on-chip output-network "
      "result (spec: Output port / match, Inductor / passive models). Not a pass/fail claim; this "
      "record shows the bench runs cold. Topology DR 0003 is PROPOSED, Supply is DRAFT.")
    w("")
    w("## Conditions (restated per the spec's extraction section)")
    w("")
    w("- Bench `sim/psat-sweep/psat_sweep.spice`; spec rows: Psat, P1dB, Peak PAE, Input match (large-signal), "
      "Device stress (RATIFIED); back-off PAE, harmonics, large-signal stability, thermal (DRAFT, reported only).")
    w("- Cell: process `hbt_typ`, 27 C ambient, Vcc 0.8 V, self-heating on (card default `selft=1`). "
      "One cell; the PVT matrix is item 5.")
    w("- Source: sine EMF behind 50 ohm at 2.44175 GHz; drive = **available** power "
      "A^2/(8 Rs); P_in is computed from the measured input V and I (mismatch counted).")
    w("- Load: 50 ohm resistive. **Harmonic terminations: ideal 50 ohm at 2 f0 and 3 f0 (the default, "
      "labelled; a flat resistor).** Results under other terminations are not comparable.")
    w("- PAE = (P_out,f0 - P_in,f0) / P_DC; P_DC = total supply power drawn from Vcc, including the bias "
      "reference current (the 1 mA reference is an ideal source from Vcc, so it is inside P_DC); no separate "
      "driver. Integrated by `rf_extract.extract` over an integer number of RF periods "
      "(window "
      + (f"{points[0]['window_periods']} periods" if points else "n/a")
      + ") after the settling test, rectangular-window coherent DFT, step T/400.")
    w(f"- Repo `{sha}` (dirty={dirty}); klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`; "
      "known-answer check of the extractor: `sim/known-answer/` (run before DUT records).")
    w(f"- Backend: `{rep.get('environment', {}).get('backend', 'see report')}`; "
      f"remote job: `{rep.get('environment', {}).get('remote', 'n/a')}`.")
    w("")
    w("## Reduction (extracted points only)")
    w("")
    if red:
        w(f"- Linear gain (median of the 3 lowest-drive points): {red['gain_linear_db']:.2f} dB")
        w(f"- **Psat = {red['psat_dbm']:.2f} dBm** (fundamental; sweep end reached: {red['psat_at_sweep_end']}), "
          f"PAE at Psat {100 * (red['pae_at_psat'] or 0):.1f} %")
        if red["p1db_status"] == "reached":
            w(f"- **P1dB (output) = {red['p1db_out_dbm']:.2f} dBm** at P_in = {red['p1db_in_dbm']:.2f} dBm")
        else:
            w("- P1dB: not reached within the sweep (no extrapolation)")
        w(f"- **Peak PAE = {100 * red['peak_pae']:.1f} %**")
    else:
        w(f"- Reduction refused: `{red_err['code']}` -- {red_err['message']}")
    w("")
    w("## Per-point results")
    w("")
    w("| Pavail dBm | Pin dBm | Pout dBm | Gain dB | PAE % | S11 large dB | H2 dBc | H3 dBc |")
    w("|---|---|---|---|---|---|---|---|")
    for p in points:
        g = dbm(p["p_out_w"]) - dbm(p["p_in_w"]) if p["p_out_w"] > 0 and p["p_in_w"] > 0 else float("nan")
        w(f"| {p['p_avail_dbm']:.1f} | {dbm(p['p_in_w']):.2f} | {dbm(p['p_out_w']):.2f} | {g:.2f} | "
          f"{100 * (p['pae'] or 0):.1f} | {p['s11_large_db']:.2f} | "
          f"{p['h2_dbc'] if p['h2_dbc'] is None else round(p['h2_dbc'], 1)} | "
          f"{p['h3_dbc'] if p['h3_dbc'] is None else round(p['h3_dbc'], 1)} |")
    w("")
    w("## Device stress (peaks over the extraction window)")
    w("")
    w("The 14 array devices share the collector and base nodes and are identical, so one device's terminals "
      "are quoted for each. `V_CE`/`V_CB`/`V_BE` are the **external terminal** voltages (emitter at ground; "
      "the internal collector/base nodes sit inside the card's series resistances). `I_C` per device = "
      "(i(Lchoke) - i(load)) / 14. Junction temperature = ambient + the card's thermal node. Limits: "
      "BVCEO(min) 1.4 V, BVCBO(min) 3.8 V (process spec Rev. 1.2); window V_CE 0.4-2.0 V, V_BE 0.65-0.96 V, "
      "I_C < 30 mA/device, T_j <= 125 C (model card). Fractions are of the samples in the window.")
    w("")
    w("| Pavail dBm | Vce pk V | Vce min V | Vcb pk V | Vbe pk V | Ic pk mA | Tj max C | outside window (Vce / Vbe / Ic / Tj) | label |")
    w("|---|---|---|---|---|---|---|---|---|")
    for p in points:
        st = p["stress"]
        w(f"| {p['p_avail_dbm']:.1f} | {st['vce_pk_v']:.3f} | {st['vce_min_v']:.3f} | {st['vcb_pk_v']:.3f} | "
          f"{st['vbe_pk_v']:.3f} | {1e3 * st['ic_pk_a']:.2f} | {st['tj_max_c']:.1f} | "
          f"{100 * st['frac_vce_outside']:.0f} % / {100 * st['frac_vbe_outside']:.0f} % / "
          f"{100 * st['frac_ic_outside']:.0f} % / {100 * st['frac_tj_outside']:.0f} % | {label(st)} |")
    w("")
    if points:
        worst = max(points, key=lambda p: p["stress"]["vce_pk_v"])
        w(f"Worst Vce peak over the sweep: {worst['stress']['vce_pk_v']:.3f} V at "
          f"Pavail {worst['p_avail_dbm']:.1f} dBm ({label(worst['stress'])}).")
        w("")
    if failures:
        w("## Points that could not be extracted (not in the reduction)")
        w("")
        for f in failures:
            w(f"- `{f['corner_id']}`: `{f['code']}`" + (f" ({f['p_avail_dbm']:.1f} dBm)" if "p_avail_dbm" in f else ""))
        w("")
    print("\n".join(o))
    return 0 if points else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
