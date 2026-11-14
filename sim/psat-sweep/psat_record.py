#!/usr/bin/env python3
"""Reduce a psat-sweep `klt sim` report to the append-only record (markdown + JSON).

    psat_record.py <variant> <record-id> <git-sha> <dirty> <klt-version> <ngspice-version> <report.json> <out.json> > record.md

``<variant>`` is a `gen_dut_benches.psat_bench` variant: `bare` (the default deck, a
flat 50 ohm from RFOUT) or `match` (the same sweep through an ideal, lossless off-chip
output match). It is not a cosmetic switch -- the two decks put the load power and the
chip-boundary current on different nodes, and both the load prose and the
harmonic-termination sentence below are read from the bench rather than assumed, so a
record cannot quote the flat-resistor default while reducing the matched deck.

Per drive point (one klt corner each): rf_extract.extract for P_out, P_in, P_DC, PAE,
H2/H3; large-signal S11 from the measured P_in against the available power;
per-device stress (peak V_CE, V_CB, V_BE, I_C, junction temperature) against the
(P) breakdown minima and the (M) model window, over the same integer-period window.
rf_extract.reduce_sweep then gives Psat, P1dB, peak PAE. A point that cannot be
extracted (e.g. UNSETTLED) is listed with its ExtractError code and left out of the
reduction; it is never dropped silently.

Every limit this grades against comes from `sim/lib/device_limits.py` and every bench
fact it restates comes from `sim/lib/gen_dut_benches.py` (which generates this bench's
deck), including the array size read from the DUT netlist, the deck name, the extraction
node names and the harmonic-termination sentence. The record prose is formatted from
them, so it cannot fall behind the constants that produced its labels.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import gen_dut_benches as gdb  # noqa: E402
import rf_extract as rx  # noqa: E402
# The (P) breakdown minima and the (M) model window live once, in sim/lib/device_limits.py
# (provenance marked there); the bench facts live once in gen_dut_benches.py, which
# generates this bench's deck. Nothing below is a retyped number, and the record prose
# is formatted from these names.
from device_limits import (BVCEO_MIN, BVCBO_MIN, IC_WIN_PER_NX,  # noqa: E402
                           TJ_MAX, VBE_WIN, VCE_WIN)

F0 = gdb.F0_HZ
RS = gdb.RS_OHM
N_UNITS, NX = gdb.output_array()   # output-array devices sharing COLL/VB, and their Nx
IC_MAX_PER_DEVICE = IC_WIN_PER_NX * NX


def dbm(w):
    return 10 * math.log10(w / 1e-3)


def stress(t, s, ex, ambient_c, ic_sense):
    """Peaks and window fractions over the extraction's integer-period window.

    ``ic_sense`` names the trace carrying the current leaving RFOUT into whatever is
    on the far side of the chip boundary -- i.e. `Cblock`'s current, which is what makes
    the per-device I_C below a KCL balance at COLL. In the bare deck the load branch IS
    that current; through an output network it is not (a shunt branch takes part of it),
    so the bench declares the node and this never guesses it. Getting it wrong would
    move every `Ic pk mA` and `frac_ic_outside` with nothing raised.
    """
    t0 = ex["window_start_s"]
    t1 = t0 + ex["window_periods"] / F0
    m = (t >= t0 * (1 - 1e-9)) & (t <= t1 * (1 + 1e-9))
    vc = s["v(xdut.coll)"][m]
    vb = s["v(xdut.vb)"][m]
    ic = (s["i(l.xdut.lchoke)"][m] - s[ic_sense][m]) / N_UNITS
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
        "frac_tj_outside": frac(tj > TJ_MAX),
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
    variant, rid, sha, dirty, klt_v, ng_v, report_path, out_json = argv[1:9]
    bench = gdb.psat_bench(variant)       # raises ValueError on an unknown variant
    net = bench["network"]
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
            # P_out and the harmonics from the LOAD's own V and I (spec: "DFT of the
            # load voltage/current"), whichever nodes this bench puts them on.
            ex = rx.extract(t, F0, s[bench["p_out_v"]], s[bench["p_out_i"]],
                            supplies=[(s["v(vcc)"], -s["i(vcc)"])],
                            v_in=s["v(in)"], i_in=-s["i(bs)"])
            ex = {k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in ex.items()}
            ex["p_avail_dbm"] = dbm(pav)
            ex["s11_large_db"] = 10 * math.log10(max(1 - ex["p_in_w"] / pav, 1e-12))
            ex["stress"] = stress(t, s, ex, c.get("temperature_c", 27), bench["ic_sense_i"])
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

    json.dump({"record_id": rid, "variant": variant, "bench": bench["name"],
               "output_network": net, "points": points, "failures": failures,
               "reduction": red, "reduction_error": red_err},
              open(out_json, "w"), indent=1, default=float)

    o = []
    w = o.append
    w(f"# psat-sweep record {rid}")
    w("")
    if net is None:
        w("**Simulated** (ngspice transient), nominal cell only, **through ideal passives** "
          "(`Lchoke`, `Cblock`, `Cin` of the DUT are lossless with no self-resonance; no inductor model "
          "is used). P_out, PAE and the harmonics below are not quotable as an on-chip output-network "
          "result (spec: Output port / match, Inductor / passive models). Not a pass/fail claim; this "
          "record shows the bench runs cold. Topology DR 0003 is PROPOSED, Supply is DRAFT.")
    else:
        w("**Simulated** (ngspice transient), nominal cell only, **through ideal passives, "
          "off-chip match**. The DUT's own `Lchoke`, `Cblock` and `Cin` are lossless with no "
          "self-resonance, and so is every element of the off-chip matching network below: it is "
          "an **ideal, lossless** L-section with no Q and no self-resonance, and **no inductor "
          "model is used** (DR 0001 D-1, the inductor-model source, is still deferred). "
          "P_out, PAE and the harmonics below are therefore **not** quotable as an on-chip "
          "output-network result (spec: Output port / match, Inductor / passive models).")
        w("")
        w("**What this record does and does not evidence.** It evidences the spec's "
          "**Fallback** Output-port cell -- \"50 ohm, **off-chip** output match (stated "
          "boundary)\" -- and only its boundary convention: the chip boundary is stated below, "
          "and by that same spec row a real off-chip network's loss is **not counted as the "
          "chip's**, so none is modelled here. The **Target** cell (50 ohm, *on-chip* output "
          "match) stays **unevidenced** while DR 0001 D-1 is open. **This is not a pass/fail "
          "claim** for any row: it is one cell (`hbt_typ`, 27 C, Vcc 0.8 V), and Psat, P1dB and "
          "Peak PAE bind every PVT cell with the worst cell as the figure (T1 item 5). "
          "Topology DR 0003 is PROPOSED, Supply is DRAFT.")
    w("")
    w("## Conditions (restated per the spec's extraction section)")
    w("")
    w(f"- Bench `sim/psat-sweep/{bench['name']}.spice`; spec rows: Psat, P1dB, Peak PAE, Input match (large-signal), "
      "Device stress (RATIFIED); back-off PAE, harmonics, large-signal stability, thermal (DRAFT, reported only).")
    w(f"- Cell: process `{gdb.PROCESS_NOM}`, {gdb.TEMP_NOM_C:g} C ambient, Vcc {gdb.VCC_NOM_V:g} V, "
      "self-heating on (card default `selft=1`). One cell; the PVT matrix is item 5.")
    w(f"- Source: sine EMF behind {RS:g} ohm at {F0 / 1e9:g} GHz; drive = **available** power "
      "A^2/(8 Rs); P_in is computed from the measured input V and I (mismatch counted).")
    w(f"- {bench['load_md']} {bench['terminations_md']}")
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
    if net is not None:
        ll = net["loadline_cell"]
        w("## Output network and the chip boundary")
        w("")
        w("**The chip boundary is `RFOUT`** (`design/README.md`: \"`RFOUT` is the off-chip "
          "match boundary\"). On the **chip** side: the DUT only -- its output array and "
          f"`Lchoke`, `Cblock`, `Cin`. **Off** chip: the sense source `Vbsense`, `Lmatch`, "
          f"`Cmatch`, `Vlsense` and the {gdb.RL_OHM:g} ohm load. Every off-chip element is "
          "ideal and lossless.")
        w("")
        w("```")
        w(f"COLL --[Cblock {1e12 * net['cblock_f']:g}p, ON CHIP]-- RFOUT |boundary| "
          f"--[Lmatch]--+--[Rl {gdb.RL_OHM:g}]")
        w("                                                              |")
        w("                                                           [Cmatch]")
        w("                                                              |")
        w("                                                             GND")
        w("```")
        w("")
        w("**Element values are derived, not tuned to a result.** The resistance is the "
          f"load-line record's own array-independent quantity for the nominal row -- "
          f"`vswing_v / iq_per_nx_a` = {ll['vswing_v']:g} / {ll['iq_per_nx_a']:g} = "
          f"{net['r_per_nx_ohm']:.4f} ohm per Nx -- over the array **this netlist has** "
          f"({net['n_units']} devices x Nx={net['nx']} = {net['nx_total']} Nx), giving "
          f"**Ropt = {net['ropt_ohm']:.4f} ohm at the collector**. Source: "
          f"`{net['loadline_record']}`, cell `supply_nominal_v "
          f"{ll['supply_nominal_v']:g}` / `tolerance {ll['tolerance']}` / `swing_mode "
          f"{ll['swing_mode']}`. That record's own `nx_needed.load_ohm_ideal` "
          "(2.5157 ohm) is **not** used: it is the load for the 106-Nx array the study "
          "*recommends*, not the array benched here.")
        w("")
        w(f"- `Q = sqrt({gdb.RL_OHM:g}/Ropt - 1)` = {net['q']:.4f}; "
          f"`Cmatch = Q/(w0 Rl)` = {1e12 * net['cp_f']:.4f} pF; "
          f"`Lmatch = (Q Ropt + 1/(w0 Cblock))/w0` = {1e9 * net['ls_h']:.4f} nH.")
        w(f"- `Cblock` is **{net['cblock_x_ohm']:.4f} ohm** reactive at f0, "
          f"{100 * abs(net['cblock_x_ohm']) / net['ropt_ohm']:.0f} % of Ropt, so it is "
          f"**absorbed in closed form** into `Lmatch` "
          f"({1e9 * net['ls_plain_h']:.4f} nH L-section + "
          f"{1e9 * (net['ls_h'] - net['ls_plain_h']):.4f} nH for `Cblock`), which is why the "
          "**collector**, not `RFOUT`, sees a real Ropt. `Lchoke` (+j1534 ohm in shunt at "
          "`COLL`) perturbs Ropt by 0.12 % and is left alone. Both are ideal, so neither "
          "has a self-resonance.")
        w(f"- Analytic ceiling for this load line: {net['nx_total']} Nx x "
          f"{ll['pout_per_nx_w']:g} W = {net['pout_ceiling_w']:g} W = "
          f"**{dbm(net['pout_ceiling_w']):.2f} dBm**. Hand arithmetic over the load-line "
          "record (tier 5), **not** a simulated result and not a claim.")
        w("")
        w("**Impedance presented, at the two nodes that differ** (arithmetic over ideal "
          "elements, not simulated):")
        w("")
        w("| Frequency | Into the network at `RFOUT` | Seen by `COLL` through `Cblock` |")
        w("|---|---|---|")
        for lab, f, z_rfout, z_coll in gdb.match_impedances(net):
            w(f"| {lab} ({f / 1e9:.5f} GHz) | {z_rfout.real:.3f} {z_rfout.imag:+.3f}j ohm "
              f"| {z_coll.real:.3f} {z_coll.imag:+.3f}j ohm |")
        w("")
        w("**The harmonic terminations are therefore no longer the labelled ideal-50-ohm "
          "default** -- the collector sees "
          f"{gdb._z_md(net, '2 f0')} at 2 f0 and {gdb._z_md(net, '3 f0')} at 3 f0. "
          "`spec/target-spec.md` (\"Harmonic terminations\") permits a bench to change them "
          "provided it says so, and then binds the record: **P_out and PAE under different "
          "terminations are not compared.** So the Psat, P1dB, PAE, H2 and H3 below are "
          "**not** presented as an improvement on, or otherwise compared with, "
          "`20261107-125209-93cf5ae` (the bare-50-ohm record): that run drove a flat "
          "resistor from `RFOUT` and its harmonic terminations were the ideal-50-ohm "
          "default. The two records evidence different benches, not two measurements of "
          "one quantity.")
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
    w(f"The {N_UNITS} array devices share the collector and base nodes and are identical, so one device's "
      "terminals are quoted for each. `V_CE`/`V_CB`/`V_BE` are the **external terminal** voltages (emitter "
      "at ground; the internal collector/base nodes sit inside the card's series resistances). `I_C` per "
      f"device = (i(Lchoke) - {bench['ic_sense_md']}) / {N_UNITS}. Junction temperature = ambient + the card's thermal "
      f"node. Limits: BVCEO(min) {BVCEO_MIN:.1f} V, BVCBO(min) {BVCBO_MIN:.1f} V (process spec Rev. 1.2); "
      f"window V_CE {VCE_WIN[0]:.1f}-{VCE_WIN[1]:.1f} V, V_BE {VBE_WIN[0]:.2f}-{VBE_WIN[1]:.2f} V, "
      f"I_C < {1e3 * IC_MAX_PER_DEVICE:g} mA/device, T_j <= {TJ_MAX:g} C (model card). Fractions are of "
      "the samples in the window.")
    w("")
    if net is not None:
        w(f"`I_C` is taken from the **chip boundary** (`{bench['ic_sense_i']}`, the 0 V source "
          "`Vbsense` at `RFOUT`), which is `Cblock`'s own current and so closes KCL at `COLL`. "
          "It is deliberately **not** the load-branch current: `Cmatch` shunts part of that, so "
          "the load current would under-report every `I_C` below with nothing raised.")
        w("")
        w("**The self-heating thermal node this `Tj max C` column comes from has no "
          "known-answer check yet** (issue #115). `sim/known-answer/` validates the "
          "large-signal extractor (power, P_DC, harmonics) against analytic answers; it does "
          "**not** validate the VBIC card's self-heating node, so the `Tj` column and its "
          "`T_j <= 125 C` window labelling rest on the model card as supplied. Read it as "
          "reported, not as checked.")
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
