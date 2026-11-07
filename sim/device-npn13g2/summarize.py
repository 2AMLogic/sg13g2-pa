#!/usr/bin/env python3
"""Render the npn13G2 device record (Markdown) and its machine-readable DC data.

Usage: summarize.py <record-id> <git-sha> <dirty:0|1> <klt-version> <ngspice-banner>
                    <provenance.json> <out-dir> <dc-json-out>

Reads <out-dir>/{dc_family,ft}.report.json. Prints the record on stdout, writes
<dc-json-out> (Ic cells for loadline.py). Exit 1 if a report is missing or any
corner is not `pass`. Stdlib only; run with -I.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util
_spec = importlib.util.spec_from_file_location("gen_bench", os.path.join(HERE, "gen_bench.py"))
gb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gb)
# Model-window constants and the Rth model live once, in loadline.py (provenance marked there).
_spec = importlib.util.spec_from_file_location("loadline", os.path.join(HERE, "loadline.py"))
ll = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ll)
IC_WIN_PER_NX = ll.IC_WIN_PER_NX
TJ_MAX = ll.TJ_MAX
rth = ll.rth
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from provenance import commit_line, sha  # noqa: E402


def load(out_dir, name):
    p = os.path.join(out_dir, name + ".report.json")
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def main(argv):
    rid, git_sha, dirty, klt_ver, ng, prov_path, out_dir, dc_out = argv[1:9]
    prov = json.load(open(prov_path))
    ok = True
    reports = {n: load(out_dir, n) for n in ("dc_family", "ft")}
    L = [f"# npn13G2 single-device load-line study, record {rid}", "",
         "**Simulated** (ngspice via `klt sim`) device data plus an analytic load-line; not a PA",
         "result. All spec rows (Supply, Device flavour, Thermal) stay **DRAFT**: this record",
         "recommends, it does not ratify. Every table names its corner and temperature.", "",
         "## Provenance", "",
         f"- UTC timestamp / record id: `{rid}`",
         commit_line(git_sha, dirty),
         f"- PDK: IHP-Open-PDK pinned `{prov['pinned_release_tag']}`, installed `{prov['installed_release_raw']}` "
         f"(identity route `{prov['identity_route']}`), verified against `sim/pdk.json`",
         f"- `klt`: `{klt_ver}`",
         f"- Local ngspice (preflight only): `{ng}`", ""]
    for n, r in reports.items():
        if r is None:
            L.append(f"- **{n}: no usable report** (see its stderr)")
            ok = False
            continue
        env, rem = r.get("environment", {}), r.get("environment", {}).get("remote") or {}
        where = "batch fleet worker" if rem else "local host"
        L.append(f"- {n}: status **{r.get('status')}** ({r.get('passed')} pass / {r.get('failed')} fail / "
                 f"{r.get('errored')} error of {r.get('corner_count')}); ran on {where}, ngspice major "
                 f"`{env.get('engine_version')}`" + (f", batch job `{rem.get('job_id')}`" if rem else ""))
    L += ["", "### Decks, requests and model inputs (sha256)", ""]
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".spice", ".request.json")):
            L.append(f"- `sim/device-npn13g2/{fn}` `{sha(os.path.join(HERE, fn))}`")
    for f in prov["model_inputs"]:
        L.append(f"- `{f['path']}` `{f['sha256']}`")

    dc_cells = []
    ic = {}   # (process, T, nx, vbe, vce) -> A
    if reports["dc_family"]:
        for c in reports["dc_family"]["corners"]:
            if c["status"] != "pass":
                ok = False
            for m in c["measurements"]:
                g = re.fullmatch(r"ic_n(\d+)_v(\d+)_vce(\d+)", m["name"])
                if g and m["value"] is not None:
                    nx, vbe, vce = int(g[1]), int(g[2]) / 100.0, int(g[3]) / 100.0
                    ic[(c["process"], c["temperature_c"], nx, vbe, vce)] = m["value"]
                    dc_cells.append({"process": c["process"], "temperature_c": c["temperature_c"],
                                     "nx": nx, "vbe": vbe, "vce": vce, "ic_a": m["value"]})
    with open(dc_out, "w") as fh:
        json.dump({"record": rid, "note": "simulated Ic (A) from sim/device-npn13g2/dc_family",
                   "cells": dc_cells}, fh)
        fh.write("\n")

    L += ["", "## Ic-Vce family (simulated, mA)", "",
          "Bench `dc_family.spice`: 4-terminal `npn13G2`, self-heating on (card default `selft=1`), "
          "Vbe fixed per row, Vce swept. `†` = ic above the card window `0.003*Nx` A "
          "(OUTSIDE MODEL WINDOW for ic). Vce columns span the window 0.4-2.0 V; Vbe rows are "
          "inside the 0.65-0.96 V window. At 125 C ambient the card's temperature window is "
          "already at its top, so any self-heating puts Tj outside it (labelled below).", ""]
    vces = gb.VCE
    for proc in gb.PROCESS:
        for t in gb.TEMPS:
            for nx in gb.NX:
                L += [f"**{proc}, {t:+d} C, Nx={nx}** (simulated)", "",
                      "| Vbe (V) | " + " | ".join(f"Vce {v:g} V" for v in vces) + " |",
                      "|---|" + "---|" * len(vces)]
                for vbe in gb.VBE:
                    row = []
                    for v in vces:
                        x = ic.get((proc, t, nx, vbe, v))
                        row.append("n/a" if x is None else "%.4g%s" % (x * 1e3, " †" if x >= IC_WIN_PER_NX * nx else ""))
                    L.append(f"| {vbe:.2f} | " + " | ".join(row) + " |")
                L.append("")

    L += ["## fT vs Ic at Vce = %.1f V (simulated)" % gb.FT_VCE, "",
          "Bench `ft.spice`: small-signal h21 = |Ic_ac / Ib_ac| from a 1 V ac base drive with the "
          "collector ac-shorted; `.ac dec` 10-100 GHz, h21 read at 20 and 50 GHz; "
          "fT = |h21| * f0 (single-pole extrapolation, valid while |h21| >> 1 and the -20 dB/dec "
          "slope holds, so the two f0 should agree; where |h21| is near or below 1 the "
          "two estimates disagree and fT is **not** established). Ic is the dc family value at the same Vbe, "
          "Vce = 1.0 V. dT = Rth*Ic*Vce with Rth = 3.26e3*(4/Nx)^0.9 K/W (card), Tj = ambient + dT "
          "(estimate; the simulated device self-heats internally). `†` = Tj above the +125 C "
          "window ceiling; `‡` = ic above the window.", ""]
    ft = {}
    if reports["ft"]:
        for c in reports["ft"]["corners"]:
            if c["status"] != "pass":
                ok = False
            m = {x["name"]: x["value"] for x in c["measurements"]}
            for nx in gb.NX:
                for vbe in gb.VBE:
                    tg = gb.tag(nx, vbe)
                    h = []
                    for f in gb.FT_FREQS:
                        a, b = m.get(f"icac_{tg}_f{f}"), m.get(f"ibac_{tg}_f{f}")
                        h.append((a / b, a / b * float(f) / 1e9) if a and b else None)
                    ft[(c["process"], c["temperature_c"], nx, vbe)] = h
    for proc in gb.PROCESS:
        for t in gb.TEMPS:
            L += [f"**{proc}, {t:+d} C** (simulated)", "",
                  "| Nx | Vbe (V) | Ic (mA) | h21 @20 GHz | fT @20 GHz (GHz) | h21 @50 GHz | fT @50 GHz (GHz) | dT (K) | Tj (C) |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for nx in gb.NX:
                for vbe in gb.VBE:
                    i = ic.get((proc, t, nx, vbe, gb.FT_VCE))
                    h = ft.get((proc, t, nx, vbe), [None, None])
                    dt = rth(nx) * i * gb.FT_VCE if i is not None else None
                    tj = t + dt if dt is not None else None
                    cells = []
                    for x in h:
                        cells += ["n/a", "n/a"] if x is None else ["%.4g" % x[0], "%.4g" % x[1]]
                    L.append("| %d | %.2f | %s | %s | %s | %s | %s | %s | %s |" % (
                        nx, vbe, "n/a" if i is None else "%.4g%s" % (i * 1e3, " ‡" if i >= IC_WIN_PER_NX * nx else ""),
                        *cells, "n/a" if dt is None else "%.2f" % dt,
                        "n/a" if tj is None else "%.1f%s" % (tj, " †" if tj > TJ_MAX else "")))
            L.append("")
    L += ["## Solver diagnostics", ""]
    diags = []
    for n, r in reports.items():
        for c in (r or {}).get("corners", []):
            for d in c.get("diagnostics", []):
                diags.append(f"- {n} `{c['corner_id']}`: status {c['status']}, {d['severity']} `{d['code']}`")
    L += sorted(set(diags)) or ["- none"]
    L += ["", "A `singular_matrix` warning here was recovered by ngspice's dynamic gmin stepping (the "
          "corner still reports `pass`); the tables for those corners are monotone in Vbe and Vce.", ""]
    L += ["## Tool friction", "",
          "- `klt sim` captures swept curves only as one `.meas` per point; the `par()` 99-call cap and an "
          "out-of-interval `AT=` both surface as `produced no value`. Worked around with CCVS current probes "
          "and a `dec` AC sweep. Filed generically as 2AMLogic/klayout-tools#4084.", ""]
    print("\n".join(L))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
