#!/usr/bin/env python3
"""Reduce the P1dB linear-reference probe's `klt sim` report to the append-only record.

    p1dbref_record.py <record-id> <git-sha> <dirty> <klt-version> <ngspice-version> \
        <probe-report.json> <matrix-record.json> <out.json> > record.md

The probe (issue #192, "check the compression measurement first") measures the
gain-vs-drive curve of every declared PVT cell at drives the committed matched grid
cannot reach. klt names a unit by a corner id whose supply-axis values are formatted to
three decimals, so below ~10 mV of source amplitude no <= 1 dB spaced drive grid keeps
one bucket per point (klayout-tools#5870's collision class; the gap is filed with
klayout-tools under the friction protocol, klayout-tools#7132). The committed grid
therefore stops at
-36.0 dBm available -- roughly 8-16 dB below each cell's compression, against the spec's
"drive >= 20 dB below the compressing level" (Output P1dB row). The probe reuses the
COMMITTED matched deck unchanged (same load, harmonic terminations, extraction nodes)
and swaps only the drive axis for `gen_dut_benches.P1DBREF_PROBE_GRID_DBM`: 4 dB
spacing, the coarsest that stays bucket-distinct down to -56 dBm available, whose
lowest point is 28 dB under the earliest measured compression.

Per cell, against the committed matrix record passed as <matrix-record.json>:

* **Is the committed reference gain compressed?** The probe's gains are fitted with
  ``g(P_in) = g0 - c * P_in`` over the probe points (a second-order compressor's
  deficit is linear in drive power, and the committed sweep's own gain slope
  accelerates with drive -- that law's signature). ``g0`` is the extrapolated
  zero-drive gain; ``epsilon = g0 - g_ref`` is how far the committed
  three-lowest-points reference sits below it.
* **What does that error do to the P1dB figure?** With the compression curve locally
  linear at slope ``s`` (dB of gain per dB of measured P_in across the 1 dB crossing
  pair), a reference compressed by ``epsilon`` reports ``P1dB_out`` high by
  ``epsilon * (1/s - 1)``: the crossing against the low reference sits ``epsilon / s``
  further up the drive axis, and the reference itself adds ``epsilon`` back. The
  record reports the bias, not just epsilon, because the bracket arithmetic is what
  the row's figure inherits.
* **Is the committed bracket legal?** The measured P_in step across the matrix
  record's own crossing pair, against the row's 0.5 dB interpolation limit.
* **The quiescent operating point** (P_DC and total supply current at the lowest probe
  drive) -- the baseline side of issue #192's bias hypothesis comparison.

The probe is NOT a drive sweep: 4 dB steps, no compression bracketed, `reduce_sweep`
never runs on it, and no Psat/PAE figure appears here. Nothing in this record is a
pass claim for any row; the Supply row is DRAFT, so every figure is provisional.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # psat_record
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import gen_dut_benches as gdb  # noqa: E402
import rf_extract as rx  # noqa: E402
from provenance import commit_line  # noqa: E402
from psat_record import F0, RS, _cell_md, _remote_md, label, stress  # noqa: E402

# `reduce_sweep`'s default reference width: the median gain of this many lowest-drive
# points. The renderer reads the reference actually used from the matrix record's own
# reduction; the recomputation below is a cross-check against this default.
LINEAR_POINTS = 3

# The Output P1dB row's interpolation limit (spec; also rf_extract.STEP_P1DB_DB). The
# bracket check reads the matrix record's measured P_in step, so the limit is restated
# here only to label the comparison.
P1DB_BRACKET_LIMIT_DB = rx.STEP_P1DB_DB


def _gain_db(p):
    return rx.dbm(p["p_out_w"]) - rx.dbm(p["p_in_w"])


def fit_zero_drive_gain(points):
    """Least-squares fit of ``g(P_in) = g0 - c * P_in`` over the probe points.

    Returns ``(g0_db, c_per_watt, residual_db)``. The one-parameter physics is a
    second-order compressor whose deficit grows linearly with drive power; fitting a
    line in P (not in dB) is what lets the fit see a 20 dB span with six points.
    """
    p = np.array([q["p_in_w"] for q in points], dtype=float)
    g = np.array([_gain_db(q) for q in points], dtype=float)
    a = np.column_stack([np.ones_like(p), -p])
    (g0, c), *_ = np.linalg.lstsq(a, g, rcond=None)
    resid = float(np.max(np.abs(g - (g0 - c * p))))
    return float(g0), float(c), resid


def _matrix_reference(cell_entry):
    """The committed reference, read from the matrix record and cross-checked.

    ``g_ref`` is the reduction's own ``gain_linear_db`` (the number the committed
    P1dB figures were computed against). The recomputed median-of-3 must agree with
    it, or the cross-check flag says the record and its points disagree -- which
    would make every epsilon below suspect.
    """
    red = cell_entry.get("reduction") or {}
    g_ref = red.get("gain_linear_db")
    pts = sorted(cell_entry["points"], key=lambda q: q["p_in_w"])
    lows = pts[:LINEAR_POINTS]
    recompute = float(np.median([_gain_db(q) for q in lows])) if len(pts) >= LINEAR_POINTS else None
    ok = (g_ref is not None and recompute is not None and abs(g_ref - recompute) < 1e-6)
    return {"g_ref_db": g_ref, "recomputed_db": recompute, "cross_check_ok": ok,
            "ref_points_pin_dbm": [rx.dbm(q["p_in_w"]) for q in lows]}


def _matrix_bracket(cell_entry, g_ref_db):
    """The committed 1 dB crossing: bracketing pair, measured step, local slope.

    Replays `reduce_sweep`'s crossing test on the matrix record's own points:
    compression against the record's reference crosses 1 dB between two consecutive
    points; the pair's measured P_in step is the bracket the row's 0.5 dB limit
    judges, and the pair's compression slope ``s`` (dB/dB) is what turns a reference
    error into a P1dB_out bias.
    """
    if g_ref_db is None:
        return None
    pts = sorted(cell_entry["points"], key=lambda q: q["p_in_w"])
    pin = [rx.dbm(q["p_in_w"]) for q in pts]
    comp = [g_ref_db - _gain_db(q) for q in pts]
    for k in range(1, len(pts)):
        if comp[k] >= 1.0 > comp[k - 1]:
            step = pin[k] - pin[k - 1]
            s = (comp[k] - comp[k - 1]) / step if step > 0 else None
            return {"bracket_low_pin_dbm": pin[k - 1], "bracket_high_pin_dbm": pin[k],
                    "step_db": step, "slope_db_per_db": s,
                    "step_ok": step <= P1DB_BRACKET_LIMIT_DB + 1e-9}
    return None


def fmt(v, spec):
    return "--" if v is None else spec.format(v)


def render(rid, git_sha, dirty, klt_v, ng_v, rep, matrix, out_json):
    bench = gdb.psat_bench("match")
    points, failures = [], []
    for c in rep.get("corners", []):
        cid = c.get("corner_id", "?")
        if c.get("status") != "pass":
            failures.append({"corner_id": cid, "code": f"KLT_STATUS_{c.get('status')}"})
            continue
        amp = c["supply_v"]["vamp"]
        pav = amp * amp / (8 * RS)
        cell = {"process": c.get("process", "?"),
                "temperature_c": float(c.get("temperature_c", 27)),
                "vcc": float(c["supply_v"].get("vcc", gdb.VCC_NOM_V))}
        try:
            t, s = rx.load_klt_waveform(c["artifacts"]["waveform"])
            ex = rx.extract(t, F0, s[bench["p_out_v"]], s[bench["p_out_i"]],
                            supplies=[(s["v(vcc)"], -s["i(vcc)"])],
                            v_in=s["v(in)"], i_in=-s["i(bs)"])
            ex = {k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in ex.items()}
            ex["p_avail_dbm"] = rx.dbm(pav)
            ex["s11_large_db"] = 10 * math.log10(max(1 - ex["p_in_w"] / pav, 1e-12))
            ex["stress"] = stress(t, s, ex, c.get("temperature_c", 27), bench["ic_sense_i"])
            ex["corner_id"] = cid
            ex["cell"] = cell
            points.append(ex)
        except rx.ExtractError as e:
            failures.append({"corner_id": cid, "p_avail_dbm": rx.dbm(pav),
                             "code": e.code, "message": str(e), "cell": cell})

    by_cell = {}
    order = []
    for p in points:
        key = (p["cell"]["process"], p["cell"]["temperature_c"], p["cell"]["vcc"])
        if key not in by_cell:
            by_cell[key] = {"cell": p["cell"], "points": []}
            order.append(key)
        by_cell[key]["points"].append(p)

    mcells = {(c["cell"]["process"], c["cell"]["temperature_c"], c["cell"]["vcc"]): c
              for c in matrix.get("cells", [])}

    rows = []
    for key in order:
        grp = by_cell[key]
        grp["points"].sort(key=lambda q: q["p_in_w"])
        m = mcells.get(key)
        analysis = {"matrix_record_has_cell": m is not None}
        if m is not None:
            ref = _matrix_reference(m)
            br = _matrix_bracket(m, ref["g_ref_db"])
            fit = fit_zero_drive_gain(grp["points"])
            eps = fit[0] - ref["g_ref_db"] if ref["g_ref_db"] is not None else None
            bias = None
            if eps is not None and br is not None and br["slope_db_per_db"]:
                s = br["slope_db_per_db"]
                bias = eps * (1.0 / s - 1.0)
            p1db = (m.get("reduction") or {}).get("p1db_in_dbm")
            below = (p1db - ref["ref_points_pin_dbm"][0]) if (p1db is not None and ref["ref_points_pin_dbm"]) else None
            q = grp["points"][0]
            analysis.update({
                "reference": ref, "bracket": br, "fit": {"g0_db": fit[0], "c_per_watt": fit[1],
                                                         "residual_db": fit[2]},
                "epsilon_db": eps, "p1db_out_bias_db": bias,
                "reference_below_compression_db": below,
                "quiescent": {"p_avail_dbm": q["p_avail_dbm"], "p_dc_w": q["p_dc_w"],
                              "i_total_a": q["p_dc_w"] / q["cell"]["vcc"],
                              "vce_quiescent_v": q["stress"]["vce_pk_v"]},
            })
        grp["analysis"] = analysis
        rows.append(grp)

    json.dump({"record_id": rid, "bench": bench["name"], "probe_grid_dbm": list(gdb.P1DBREF_PROBE_GRID_DBM),
               "matrix_record_id": matrix.get("record_id"), "cells": rows, "failures": failures},
              open(out_json, "w"), indent=1, default=float)

    n_cells = gdb.pvt_cell_count()
    with_eps = [r for r in rows if r["analysis"].get("epsilon_db") is not None]
    with_bias = [r for r in rows if r["analysis"].get("p1db_out_bias_db") is not None]
    max_eps = max((abs(r["analysis"]["epsilon_db"]) for r in with_eps), default=None)
    max_bias = max((abs(r["analysis"]["p1db_out_bias_db"]) for r in with_bias), default=None)
    bad_brackets = [r for r in rows if r["analysis"].get("bracket") and not r["analysis"]["bracket"]["step_ok"]]
    max_step = max((r["analysis"]["bracket"]["step_db"] for r in rows if r["analysis"].get("bracket")), default=None)

    o = []
    w = o.append
    w(f"# psat-sweep record {rid} -- P1dB linear-reference probe, {len(rows)} cells")
    w("")
    w("**PROVISIONAL: Supply row DRAFT.** No verdict here is a pass claim for any "
      "ratified row; this record verifies a measurement (issue #192, acceptance "
      "criterion 1), it does not grade the design.")
    w("")
    w("**What this probe is.** The spec's Output P1dB row takes its reference gain "
      "from the linear region of the sweep, at drive >= 20 dB below the compressing "
      "level. The committed matched grid cannot reach that region: klt's corner-id "
      "encoding rounds supply-axis values to three decimals, so below ~10 mV of "
      "source amplitude no <= 1 dB spaced drive grid keeps one bucket per point "
      "(klayout-tools#5870's collision class), and the grid stops at -36.0 dBm "
      "available -- roughly 8-16 dB below each cell's compression. This probe runs "
      f"the SAME committed matched deck (`{bench['name']}.spice`, byte-identical, "
      f"sha256 in its header) under a sparse low-drive axis "
      f"({gdb.P1DBREF_PROBE_GRID_DBM[0]:g}..{gdb.P1DBREF_PROBE_GRID_DBM[-1]:g} dBm "
      "available, 4 dB steps -- the coarsest spacing whose corner ids stay "
      "distinct), over every declared cell. It is compared against the committed "
      f"matrix record `{matrix.get('record_id')}`.")
    w("")
    w("**Simulated** (ngspice transient), same extractor and extraction nodes as the "
      "matrix bench, through the same ideal lossless off-chip match; every caveat of "
      f"that record's header applies here unchanged ({bench['load_md'].split(':')[0]}: "
      "ideal passives, no inductor model, harmonic terminations set by the network).")
    w("")
    w("## Conditions")
    w("")
    w(f"- Probe request `sim/psat-sweep/{gdb.P1DBREF_PROBE_REQUEST_REL.split('/')[-1]}` "
      f"on deck `sim/psat-sweep/{bench['name']}.spice` (unchanged); {len(points)} of "
      f"{len(points) + len(failures)} units extracted across {len(rows)} of "
      f"{n_cells} declared cells.")
    w(f"- {bench['load_md']} {bench['terminations_md']}")
    w("- Source, P_in accounting and PAE integration: identical to the matrix bench "
      "(sine EMF behind 50 ohm at 2.44175 GHz; drive = available power; P_in from "
      "measured input V and I). The probe reports no PAE and no Psat: 4 dB steps "
      "bracket no compression and `reduce_sweep` is never run on these points.")
    w(f"- Deficit model: g(P_in) = g0 - c*P_in, least squares over each cell's probe "
      "points (a second-order compressor's deficit is linear in drive power).")
    w(commit_line(git_sha, dirty))
    w(f"- klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`.")
    w(f"- Backend: `{rep.get('environment', {}).get('backend', 'see report')}`; "
      f"remote: `{_remote_md(rep.get('environment', {}).get('remote', 'n/a'))}`.")
    w("")
    w("## Per-cell reference verification")
    w("")
    w("g0 = extrapolated zero-drive gain (probe fit); g_ref = the matrix record's own "
      "`gain_linear_db`; epsilon = g0 - g_ref (positive: the committed reference is "
      "compressed); s = compression slope at the matrix record's 1 dB crossing pair "
      "(dB of gain per dB of measured P_in); bias = epsilon*(1/s - 1), the error the "
      "committed P1dB_out figure inherits (a compressed reference biases the figure "
      "HIGH); bracket = measured P_in step across that pair.")
    w("")
    w("| Cell | g0 fit dB | g_ref dB | epsilon dB | s dB/dB | P1dB_out bias dB | bracket dB | ref below comp dB |")
    w("|---|---|---|---|---|---|---|---|")
    for r in rows:
        a = r["analysis"]
        if not a.get("matrix_record_has_cell"):
            w(f"| {_cell_md(r['cell'])} | no matrix cell | | | | | | |")
            continue
        ref, br, fit = a["reference"], a["bracket"], a["fit"]
        eps, bias = a["epsilon_db"], a["p1db_out_bias_db"]
        below = a["reference_below_compression_db"]
        w(f"| {_cell_md(r['cell'])}"
          f"| {fit['g0_db']:.3f} | {fmt(ref['g_ref_db'], '{:.3f}')}"
          f"| {fmt(eps, '{:+.3f}')} | {fmt(br and br['slope_db_per_db'], '{:.3f}')}"
          f"| {fmt(bias, '{:+.3f}')} | {fmt(br and br['step_db'], '{:.3f}')}"
          f"| {fmt(below, '{:.1f}')} |")
    w("")
    if bad_brackets:
        w(f"**Bracket violations**: {', '.join(_cell_md(r['cell']) for r in bad_brackets)} "
          "have a measured crossing step above 0.5 dB.")
    else:
        w(f"**Bracket**: every cell's measured crossing step is within the 0.5 dB "
          f"interpolation limit (max {max_step:.3f} dB)." if max_step is not None else
          "**Bracket**: no reduced cell to check.")
    if max_eps is not None:
        w("")
        w(f"**Reference validity**: the largest reference error over the probed cells "
          f"is {max_eps:.3f} dB"
          + (f", and the largest implied P1dB_out bias is {max_bias:.3f} dB" if max_bias is not None else "")
          + ". Both are the measurement's own uncertainty on a row whose worst-cell "
            "shortfall against the Fallback rung is measured in tens of dB; the "
            "shortfall is the DUT's, not the reference's (issue #192 AC 1).")
    w("")
    w("## Per-cell detail")
    w("")
    for r in rows:
        a = r["analysis"]
        w(f"### {_cell_md(r['cell'])}")
        w("")
        w("| Pavail dBm | P_in dBm | P_out dBm | gain dB | P_DC mW | S11 large dB |")
        w("|---|---|---|---|---|---|")
        for q in r["points"]:
            w(f"| {q['p_avail_dbm']:.1f} | {rx.dbm(q['p_in_w']):.2f} | {rx.dbm(q['p_out_w']):.2f} "
              f"| {_gain_db(q):.3f} | {1e3 * q['p_dc_w']:.3f} | {q['s11_large_db']:.2f} |")
        if a.get("matrix_record_has_cell"):
            fit = a["fit"]
            q = a["quiescent"]
            w("")
            w(f"- Fit: g0 {fit['g0_db']:.3f} dB, c {fit['c_per_watt']:.3e} 1/W, "
              f"max residual {fit['residual_db']:.4f} dB"
              + ("" if a["reference"]["cross_check_ok"] else
                 " **(matrix cross-check FAILED: recomputed reference disagrees with the stored one)**")
              + ".")
            w(f"- Quiescent (lowest probe drive): P_DC {1e3 * q['p_dc_w']:.3f} mW, "
              f"total supply current {1e3 * q['i_total_a']:.2f} mA, Vce {q['vce_quiescent_v']:.3f} V "
              "(peak over the window; the RF swing at these drives is microvolts).")
            st = r["points"][0]["stress"]
            w(f"- Probe-point stress (lowest drive): {label(st).lower()}.")
        w("")
    if failures:
        w("## Points that could not be extracted")
        w("")
        for f in failures:
            w(f"- `{f['corner_id']}`: `{f['code']}`"
              + (f" ({f['p_avail_dbm']:.1f} dBm)" if "p_avail_dbm" in f else ""))
        w("")
    print("\n".join(o))
    return 0 if points else 1



def main(argv):
    if len(argv) != 9:
        print("usage: p1dbref_record.py <record-id> <git-sha> <dirty> <klt-version> "
              "<ngspice-version> <probe-report.json> <matrix-record.json> <out.json>",
              file=sys.stderr)
        return 2
    rid, git_sha, dirty, klt_v, ng_v, rep_path, matrix_path, out_json = argv[1:9]
    rep = json.load(open(rep_path))
    matrix = json.load(open(matrix_path))
    if matrix.get("bench") != "psat_sweep_match":
        print(f"p1dbref_record: matrix record {matrix_path} is not a matched-bench "
              f"record (bench {matrix.get('bench')!r})", file=sys.stderr)
        return 2
    return render(rid, git_sha, dirty, klt_v, ng_v, rep, matrix, out_json)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
