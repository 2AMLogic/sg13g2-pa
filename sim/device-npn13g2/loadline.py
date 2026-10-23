#!/usr/bin/env python3
"""Analytic ideal-load-line study for the npn13G2 (stdlib only; run with -I).

Usage:
  python3 -I loadline.py --self-test
  python3 -I loadline.py --out /tmp/loadline.json [--dc-json records/<id>.dc.json]
                         [--supplies 0.5,0.6,...] [--vknee 0.4] [--tol 0.10]

NOT a simulation. Every number here is hand-checkable arithmetic on an ideal
resistive load-line (README "Hand check"); the simulated device data
(`<id>.dc.json`, from summarize.py) only adds the Vbe the quiescent point needs.
The output is a RECOMMENDATION input; nothing here ratifies a spec row.

Model (one npn13G2 array, choke-fed class-A stage, ideal sinusoid):
  vce(t)  = Vcc + Vswing*sin(wt)        Vcc includes the supply tolerance
  Vswing  = Vcc - Vknee                 'saturated' (swing tracks headroom), or
          = Vcc_nominal - Vknee         'fixed-nominal' (swing set at nominal)
  ic      swings 0 .. 2*Iq, Iq = 3 mA*Nx / 2 (peak = the window's ic limit)
  Pout    = 1/2 * Vswing * Iq           fundamental, per unit of Nx
  Vcb_pk  = Vce_pk - Vbe_at_peak        quasi-static; Vbe_at_peak is an input
  Tj      = Tamb + Rth*(Vcc*Iq - Pout)  Rth = 3.26e3*(4/Nx)**0.9 K/W (card)
Limits are the spec's: BVCEO/BVCBO (min) from the PDK process spec; the VBIC
validity window from the card header (spec/target-spec.md, "Model validity
window").
"""
import argparse
import json
import math
import os
import sys

BVCEO_MIN = 1.4          # V, (P) npn13g2 minimum
BVCBO_MIN = 3.8          # V, (P) npn13g2 minimum
VCE_WIN = (0.4, 2.0)     # V, (M) card window
VBE_WIN = (0.65, 0.96)   # V, (M)
IC_WIN_PER_NX = 3e-3     # A per Nx, (M)
TJ_MAX = 125.0           # C, (M) window top
AMBIENTS = (-40.0, 27.0, 125.0)
P_TARGET_DBM = 15.0
EPS = 1e-9

DEFAULT_SUPPLIES = (0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.4)
LIMITS_NOTE = ("BVCEO/BVCBO are DC process-control minima (spec/target-spec.md); a dynamic "
               "excursion above them is judged a violation, per the spec. Window = card "
               "header of sg13g2_hbt_mod.lib v0.3.0 (npn13G2).")


def dbm(p_w):
    return 10.0 * math.log10(p_w / 1e-3)


def rth(nx):
    return 3.26e3 * (4.0 / nx) ** 0.9


def frac_above(mean, amp, level):
    """Fraction of a sinusoid cycle (mean + amp*sin) strictly above `level`."""
    if amp <= 0:
        return 1.0 if mean > level else 0.0
    b = (level - mean) / amp
    if b >= 1.0 - EPS:
        return 0.0
    if b <= -1.0 + EPS:
        return 1.0
    return 0.5 - math.asin(b) / math.pi


def frac_below(mean, amp, level):
    return frac_above(-mean, amp, -level)


def interp_vbe(points, ic_target):
    """Vbe at ic_target by log-linear interpolation of [(vbe, ic)], or None if not bracketed."""
    pts = sorted((v, i) for v, i in points if i > 0)
    for (v0, i0), (v1, i1) in zip(pts, pts[1:]):
        if i0 <= ic_target <= i1:
            f = (math.log(ic_target) - math.log(i0)) / (math.log(i1) - math.log(i0))
            return v0 + f * (v1 - v0)
    return None


def vbe_at_iq(dc, nx_dev, iq_dev, vcc):
    """Range of Vbe that gives iq_dev on an Nx=nx_dev device, over the swept corners, at the
    swept Vce nearest vcc. dc = list of dicts from <id>.dc.json."""
    rows = [c for c in dc if c["nx"] == nx_dev]
    if not rows:
        return None
    vce = min({c["vce"] for c in rows}, key=lambda v: abs(v - vcc))
    vals, total = [], 0
    for key in sorted({(c["process"], c["temperature_c"]) for c in rows}):
        pts = [(c["vbe"], c["ic_a"]) for c in rows
               if (c["process"], c["temperature_c"]) == key and abs(c["vce"] - vce) < 1e-6]
        total += 1
        v = interp_vbe(pts, iq_dev)
        if v is not None:
            vals.append(v)
    out = {"vce_column_v": vce, "corners_bracketed": len(vals), "corners_total": total}
    if vals:
        out["min_v"], out["max_v"] = min(vals), max(vals)
        out["in_window"] = VBE_WIN[0] <= min(vals) and max(vals) <= VBE_WIN[1]
    else:
        out["note"] = "Iq not bracketed by the swept Vbe levels at any corner; Vbe not established"
    return out


def cell(vcc_nom, tol_label, tol, mode, vknee, vbe_at_peak, nx_dev, dc=None):
    vcc = vcc_nom * (1.0 + tol)
    vswing = (vcc if mode == "saturated" else vcc_nom) - vknee
    vswing = max(vswing, 0.0)
    vce_pk, vce_min = vcc + vswing, vcc - vswing
    vcb_pk = vce_pk - vbe_at_peak

    bd = {
        "vceo": {"peak_v": vce_pk, "limit_min_v": BVCEO_MIN, "margin_v": BVCEO_MIN - vce_pk,
                 "violation": vce_pk > BVCEO_MIN + EPS,
                 "fraction_of_cycle_above": frac_above(vcc, vswing, BVCEO_MIN)},
        "vcbo": {"peak_v": vcb_pk, "limit_min_v": BVCBO_MIN, "margin_v": BVCBO_MIN - vcb_pk,
                 "violation": vcb_pk > BVCBO_MIN + EPS, "vbe_at_peak_assumed_v": vbe_at_peak},
    }
    violated = [k for k, v in bd.items() if v["violation"]]
    verdict = ("BREAKDOWN VIOLATION (%s)" % ", ".join(k.upper() for k in violated)
               if violated else "within BVCEO/BVCBO (min)")

    labels = []
    if vce_pk > VCE_WIN[1] + EPS:
        labels.append({"quantity": "vce", "side": "above", "limit_v": VCE_WIN[1], "peak_v": vce_pk,
                       "fraction_of_cycle": frac_above(vcc, vswing, VCE_WIN[1])})
    if vce_min < VCE_WIN[0] - EPS:
        labels.append({"quantity": "vce", "side": "below", "limit_v": VCE_WIN[0], "min_v": vce_min,
                       "fraction_of_cycle": frac_below(vcc, vswing, VCE_WIN[0])})

    iq_nx = IC_WIN_PER_NX / 2.0                      # A per Nx unit
    p_out_nx = 0.5 * vswing * iq_nx                  # W per Nx unit
    p_target = 1e-3 * 10 ** (P_TARGET_DBM / 10.0)
    n_total = math.ceil(p_target / p_out_nx - EPS) if p_out_nx > 0 else None
    pout = {"pout_per_nx_w": p_out_nx, "pout_per_nx_dbm": dbm(p_out_nx) if p_out_nx > 0 else None,
            "iq_per_nx_a": iq_nx, "ic_peak_per_nx_a": 2 * iq_nx}
    need = {"target_dbm": P_TARGET_DBM, "nx_total": n_total}
    if n_total:
        need["devices_at_nx_dev"] = math.ceil(n_total / nx_dev)
        need["nx_dev"] = nx_dev
        need["pout_at_nx_total_w"] = p_out_nx * n_total
        need["pout_at_nx_total_dbm"] = dbm(p_out_nx * n_total)
        need["load_ohm_ideal"] = vswing / (iq_nx * n_total)
        need["ic_peak_total_a"] = 2 * iq_nx * n_total

    p_diss_dev = vcc * iq_nx * nx_dev - p_out_nx * nx_dev
    d_t = rth(nx_dev) * p_diss_dev
    thermal = {"nx_dev": nx_dev, "rth_k_per_w": rth(nx_dev), "p_diss_per_device_w": p_diss_dev,
               "delta_t_k": d_t, "tj_c": {}}
    for ta in AMBIENTS:
        tj = ta + d_t
        thermal["tj_c"]["%+g" % ta] = {"tj_c": tj, "outside_window": tj > TJ_MAX + EPS}
        if tj > TJ_MAX + EPS:
            labels.append({"quantity": "tj", "ambient_c": ta, "limit_c": TJ_MAX, "peak_c": tj,
                           "fraction_of_cycle": None})

    vbe = None
    if dc:
        vbe = vbe_at_iq(dc, nx_dev, iq_nx * nx_dev, vcc)
        if vbe and vbe.get("in_window") is False:
            labels.append({"quantity": "vbe", "limit_v": list(VBE_WIN), "min_v": vbe["min_v"],
                           "max_v": vbe["max_v"], "fraction_of_cycle": None})

    # Thermal labels are reported separately: the 125 C ambient cell is outside by construction.
    non_thermal = [x for x in labels if x["quantity"] != "tj"]
    if violated:
        status = "BREAKDOWN VIOLATION"
    elif non_thermal:
        status = "OUTSIDE MODEL WINDOW"
    else:
        status = "within BV(min) and window (electrical); Tj labelled per ambient"
    return {"supply_nominal_v": vcc_nom, "tolerance": tol_label, "vcc_v": vcc, "swing_mode": mode,
            "vswing_v": vswing, "vce_pk_v": vce_pk, "vce_min_v": vce_min, "vcb_pk_v": vcb_pk,
            "breakdown": bd, "breakdown_verdict": verdict, "window_labels": labels,
            "status": status, "pout": pout, "nx_needed": need, "thermal": thermal,
            "vbe_at_quiescent": vbe}


def study(supplies, tol, vknee, vbe_at_peak, nx_dev, dc=None):
    cells = []
    for mode in ("saturated", "fixed-nominal"):
        for s in supplies:
            for lab, t in (("-%d%%" % round(tol * 100), -tol), ("nominal", 0.0),
                           ("+%d%%" % round(tol * 100), tol)):
                cells.append(cell(s, lab, t, mode, vknee, vbe_at_peak, nx_dev, dc))
    return cells


def recommend(cells, supplies):
    """Largest candidate supply whose three tolerance cells are all clear of breakdown and of the
    electrical window, in saturated mode. Recommendation only."""
    best = None
    for s in sorted(supplies):
        mine = [c for c in cells if c["swing_mode"] == "saturated" and c["supply_nominal_v"] == s]
        if all(c["status"].startswith("within") for c in mine):
            best = s
    if best is None:
        return {"status": "RECOMMENDATION ONLY - not ratified", "supply_nominal_v": None,
                "note": "no candidate clears BVCEO(min) at the +tolerance cell"}
    c = [x for x in cells if x["swing_mode"] == "saturated" and x["supply_nominal_v"] == best
         and x["tolerance"] == "nominal"][0]
    return {"status": "RECOMMENDATION ONLY - not ratified (spec rows stay DRAFT)",
            "supply_nominal_v": best, "nx_total": c["nx_needed"].get("nx_total"),
            "devices_at_nx_dev": c["nx_needed"].get("devices_at_nx_dev"),
            "basis": "largest candidate whose -/nominal/+ tolerance cells all stay within "
                     "BVCEO/BVCBO (min) and the Vce window under a saturated swing, ideal "
                     "resistive load, ideal passives"}


def controls(vknee, vbe_at_peak, nx_dev):
    neg = cell(1.4, "nominal", 0.0, "saturated", vknee, vbe_at_peak, nx_dev)
    pos = cell(0.5, "nominal", 0.0, "saturated", vknee, vbe_at_peak, nx_dev)
    return {"negative": {"what": "Vcc 1.4 V, saturated swing: Vce_pk must exceed BVCEO(min)",
                         "vce_pk_v": neg["vce_pk_v"], "verdict": neg["breakdown_verdict"],
                         "flagged": neg["status"] == "BREAKDOWN VIOLATION"},
            "positive": {"what": "Vcc 0.5 V, saturated swing: must be within BVCEO/BVCBO (min)",
                         "vce_pk_v": pos["vce_pk_v"], "verdict": pos["breakdown_verdict"],
                         "passes": not any(v["violation"] for v in pos["breakdown"].values())}}


def self_test():
    """Known-answer check (hand arithmetic in README "Hand check"). Raises AssertionError."""
    def close(a, b, tol=1e-9):
        assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)

    # Case 1: Vcc 0.9 V, Vknee 0.4 V, saturated: Vswing 0.5, Vce_pk 1.4 (on BVCEO), Vce_min 0.4.
    c = cell(0.9, "nominal", 0.0, "saturated", 0.4, 0.65, 10)
    close(c["vswing_v"], 0.5); close(c["vce_pk_v"], 1.4); close(c["vce_min_v"], 0.4)
    close(c["vcb_pk_v"], 0.75)
    assert not c["breakdown"]["vceo"]["violation"] and c["window_labels"][:1] != [{"x": 0}]
    close(c["pout"]["pout_per_nx_w"], 3.75e-4)
    close(c["pout"]["pout_per_nx_dbm"], 10 * math.log10(0.375))
    assert c["nx_needed"]["nx_total"] == 85 and c["nx_needed"]["devices_at_nx_dev"] == 9
    close(c["nx_needed"]["pout_at_nx_total_w"], 85 * 3.75e-4)
    close(c["nx_needed"]["load_ohm_ideal"], 0.5 / (1.5e-3 * 85))
    # Case 2: +10 % on that supply breaks BVCEO: Vcc 0.99, Vswing 0.59, Vce_pk 1.58.
    c = cell(0.9, "+10%", 0.10, "saturated", 0.4, 0.65, 10)
    close(c["vce_pk_v"], 1.58)
    assert c["status"] == "BREAKDOWN VIOLATION"
    # Case 3: fixed swing 0.2 V on Vcc 0.5 V, floor 0.4: a = 0.5, fraction below 0.4 V = 1/3.
    close(frac_below(0.5, 0.2, 0.4), 1.0 / 3.0)
    close(frac_above(0.5, 0.2, 0.5), 0.5)
    close(frac_above(1.0, 0.5, 1.5), 0.0)
    # Case 4: thermal. Nx=10, Vcc 0.9: P_dc 0.9*15 mA = 13.5 mW, Pout 3.75 mW, P_diss 9.75 mW.
    c = cell(0.9, "nominal", 0.0, "saturated", 0.4, 0.65, 10)
    close(c["thermal"]["p_diss_per_device_w"], 9.75e-3)
    close(c["thermal"]["rth_k_per_w"], 3.26e3 * 0.4 ** 0.9)
    assert c["thermal"]["tj_c"]["+125"]["outside_window"]
    assert not c["thermal"]["tj_c"]["+27"]["outside_window"]
    # Controls.
    ctl = controls(0.4, 0.65, 10)
    assert ctl["negative"]["flagged"] and ctl["positive"]["passes"]
    # Log-linear Vbe interpolation.
    close(interp_vbe([(0.7, 1e-6), (0.8, 1e-4)], 1e-5), 0.75)
    assert interp_vbe([(0.7, 1e-6), (0.8, 1e-4)], 1e-3) is None
    return True


def render(d):
    """Markdown section (record) from a loadline JSON dict."""
    L = ["", "## Analytic load-line (hand-checkable arithmetic, NOT simulated)", "",
         "Ideal resistive load, ideal sinusoid, class-A, **ideal passives, no output network**; "
         "fundamental only; no harmonic terminations modelled; efficiency not computed. "
         "Limits: BVCEO(min) %.1f V, BVCBO(min) %.1f V (process spec); Vce window %.1f-%.1f V, "
         "ic < 3 mA*Nx, Tj <= %g C (model card). Vcb = Vce - Vbe with Vbe at the peak assumed "
         "%.2f V (conservative). Pout is a ceiling per the stated assumptions, not a result." % (
             BVCEO_MIN, BVCBO_MIN, VCE_WIN[0], VCE_WIN[1], TJ_MAX, d["assumptions"]["vbe_at_peak_v"]), "",
         "**Controls.** Negative: %s -> %s (flagged: %s). Positive: %s -> %s (passes: %s)." % (
             d["controls"]["negative"]["what"], d["controls"]["negative"]["verdict"],
             d["controls"]["negative"]["flagged"], d["controls"]["positive"]["what"],
             d["controls"]["positive"]["verdict"], d["controls"]["positive"]["passes"]), ""]
    for mode in ("saturated", "fixed-nominal"):
        L += ["**Swing mode `%s`** (%s)" % (mode, d["assumptions"]["swing_modes"][mode]), "",
              "| Vcc nom | tol | Vcc | Vswing | Vce pk | Vce min | Vcb pk | verdict | window labels | "
              "Pout/Nx (dBm) | Nx for +15 dBm | Nx=10 devices | Tj @125C amb |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in d["cells"]:
            if c["swing_mode"] != mode:
                continue
            lab = "; ".join("%s%s %s (%s)" % (
                x["quantity"], "/" + x["side"] if "side" in x else "",
                "%.3g" % x.get("peak_v", x.get("min_v", x.get("peak_c", 0)) or 0),
                "-" if x["fraction_of_cycle"] is None else "%.0f%% of cycle" % (100 * x["fraction_of_cycle"]))
                for x in c["window_labels"] if x["quantity"] in ("vce", "vbe")) or "-"
            L.append("| %.2f | %s | %.3f | %.3f | %.3f | %.3f | %.3f | %s | %s | %.2f | %s | %s | %.1f C |" % (
                c["supply_nominal_v"], c["tolerance"], c["vcc_v"], c["vswing_v"], c["vce_pk_v"],
                c["vce_min_v"], c["vcb_pk_v"], c["breakdown_verdict"], "OUTSIDE MODEL WINDOW: " + lab
                if lab != "-" else "-", c["pout"]["pout_per_nx_dbm"] if c["pout"]["pout_per_nx_dbm"] is not None else float("nan"),
                c["nx_needed"].get("nx_total"), c["nx_needed"].get("devices_at_nx_dev"),
                c["thermal"]["tj_c"]["+125"]["tj_c"]))
        L.append("")
    r = d["recommendation"]
    L += ["## Recommendation (NOT ratified)", "",
          "%s" % r["status"], "",
          "- Supply nominal: **%s V**; ~%s Nx units total (%s devices of Nx=10) for +15 dBm into the "
          "ideal load-line. Basis: %s." % (r.get("supply_nominal_v"), r.get("nx_total"),
                                           r.get("devices_at_nx_dev"), r.get("basis", r.get("note"))),
          "- Every spec row (Supply, Device flavour, Thermal) remains DRAFT; ratification needs a "
          "decision record and operator approval.", ""]
    return "\n".join(L)


def load_dc(path):
    with open(path) as fh:
        return json.load(fh)["cells"]


def latest_dc(here):
    rec = os.path.join(here, "records")
    names = sorted(n for n in os.listdir(rec) if n.endswith(".dc.json")) if os.path.isdir(rec) else []
    return os.path.join(rec, names[-1]) if names else None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--render", metavar="JSON", help="print the record's Markdown section for a loadline JSON")
    ap.add_argument("--dc-json", help="simulated DC family data (default: newest records/*.dc.json)")
    ap.add_argument("--supplies", default=",".join("%g" % s for s in DEFAULT_SUPPLIES))
    ap.add_argument("--tol", type=float, default=0.10)
    ap.add_argument("--vknee", type=float, default=VCE_WIN[0],
                    help="collector knee (minimum Vce of the swing); default = the window floor")
    ap.add_argument("--vbe-at-peak", type=float, default=VBE_WIN[0],
                    help="Vbe assumed at the Vce peak for Vcb (default: window floor, conservative)")
    ap.add_argument("--nx-dev", type=int, default=10)
    a = ap.parse_args(argv)

    if a.render:
        print(render(json.load(open(a.render))))
        return 0
    self_test()
    if a.self_test:
        print("loadline.py: self-test passed")
        return 0
    if not a.out:
        ap.error("--out is required (or use --self-test)")

    here = os.path.dirname(os.path.abspath(__file__))
    dc_path = a.dc_json or latest_dc(here)
    dc = load_dc(dc_path) if dc_path else None
    supplies = [float(x) for x in a.supplies.split(",")]
    cells = study(supplies, a.tol, a.vknee, a.vbe_at_peak, a.nx_dev, dc)
    out = {
        "kind": "analytic ideal-resistive load-line; NOT a simulation",
        "limits": {"bvceo_min_v": BVCEO_MIN, "bvcbo_min_v": BVCBO_MIN, "vce_window_v": list(VCE_WIN),
                   "vbe_window_v": list(VBE_WIN), "ic_window_a_per_nx": IC_WIN_PER_NX,
                   "tj_max_c": TJ_MAX, "note": LIMITS_NOTE},
        "assumptions": {
            "load": "ideal resistive, optimum for the swing; no output network (D-1 deferred), ideal passives",
            "drive": "ideal sinusoid, class-A, swing limited by headroom (Vcc - Vknee) and by the "
                     "window ic limit (peak ic = 3 mA*Nx)",
            "harmonic_terminations": "none modelled; fundamental only",
            "efficiency": "not computed (no PAE claim)",
            "vknee_v": a.vknee, "vbe_at_peak_v": a.vbe_at_peak, "tolerance": a.tol,
            "swing_modes": {"saturated": "swing tracks headroom at every tolerance cell",
                            "fixed-nominal": "swing set at the nominal supply; low-supply cell may bottom"},
            "target_dbm": P_TARGET_DBM, "nx_dev": a.nx_dev,
        },
        "dc_data": dc_path and os.path.relpath(dc_path, here),
        "controls": controls(a.vknee, a.vbe_at_peak, a.nx_dev),
        "cells": cells,
        "recommendation": recommend(cells, supplies),
    }
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    n_bad = sum(c["status"] == "BREAKDOWN VIOLATION" for c in cells)
    print("loadline.py: %d cells (%d breakdown violations), wrote %s" % (len(cells), n_bad, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
