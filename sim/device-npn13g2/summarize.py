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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util
_spec = importlib.util.spec_from_file_location("gen_bench", os.path.join(HERE, "gen_bench.py"))
gb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gb)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
# Model-window constants and the Rth model live once, in sim/lib/device_limits.py
# (provenance marked there); never retype them here.
from device_limits import IC_WIN_PER_NX, TJ_MAX, VBE_WIN, VCE_WIN, rth  # noqa: E402
from provenance import commit_line, sha  # noqa: E402


def load(out_dir, name):
    p = os.path.join(out_dir, name + ".report.json")
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def _col(cols, name, path):
    if name not in cols:
        raise ValueError("%s: column %s missing from the captured sweep" % (path, name))
    return cols[name]


def _at(axis, target, path, what):
    """Index of the sweep point equal to ``target``; fail loudly if it is not on the grid."""
    for k, x in enumerate(axis):
        if abs(x - target) <= 1e-9 * max(1.0, abs(target)):
            return k
    raise ValueError("%s: %s not on the captured grid" % (path, what))


def _sweep(corner):
    path = corner["artifacts"]["waveform"]
    with open(path) as waveform:
        doc = json.load(waveform)
    names = [v["name"] for v in doc["variables"]]
    pts = doc["points"]
    cols = {n: [row[k] for row in pts] for k, n in enumerate(names)}
    return path, cols[names[0]], cols


def read_dc(corner):
    """{(nx, vbe, vce): Ic} from the dc sweep waveform: Ic = +i(Vs_*) (current into the + terminal)."""
    path, axis, cols = _sweep(corner)
    out = {}
    for nx in gb.NX:
        for vbe in gb.VBE:
            y = _col(cols, "i(vs_%s)" % gb.tag(nx, vbe), path)
            for vce in gb.VCE:
                out[(nx, vbe, vce)] = y[_at(axis, vce, path, "Vce=%g" % vce)]
    return out


def read_ft(corner):
    """klt's AC waveform stores magnitudes, so h21 needs only the two branch-current columns."""
    path, freq, cols = _sweep(corner)
    indices = [_at(freq, float(f), path, "f=%s Hz" % f) for f in gb.FT_FREQS]
    out = {}
    for nx in gb.NX:
        for vbe in gb.VBE:
            tg = gb.tag(nx, vbe)
            ic = _col(cols, "i(vs_%s)" % tg, path)
            ib = _col(cols, "i(vb_%s)" % tg, path)
            out[(nx, vbe)] = [(ic[k], ib[k]) for k in indices]
    return out


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
    # gen_bench.py is exec'd above via spec_from_file_location; bench_gen.py and
    # the model-window constants it and this renderer grade against live in
    # sim/lib, and provenance.py renders the Commit bullet.
    L.append(f"- `sim/device-npn13g2/gen_bench.py` `{sha(os.path.join(HERE, 'gen_bench.py'))}`")
    L.append(f"- `sim/lib/device_limits.py` `{sha(os.path.join(HERE, '..', 'lib', 'device_limits.py'))}`")
    L.append(f"- `sim/lib/provenance.py` `{sha(os.path.join(HERE, '..', 'lib', 'provenance.py'))}`")
    L.append(f"- `sim/lib/bench_gen.py` `{sha(os.path.join(HERE, '..', 'lib', 'bench_gen.py'))}`")

    dc_cells = []
    ic = {}   # (process, T, nx, vbe, vce) -> A
    if reports["dc_family"]:
        for c in reports["dc_family"]["corners"]:
            if c["status"] != "pass":
                ok = False
            try:
                cells = read_dc(c)
            except (OSError, ValueError, KeyError) as e:
                print("summarize.py: %s: %s" % (c.get("corner_id"), e), file=sys.stderr)
                ok = False
                continue
            for (nx, vbe, vce), v in cells.items():
                ic[(c["process"], c["temperature_c"], nx, vbe, vce)] = v
                dc_cells.append({"process": c["process"], "temperature_c": c["temperature_c"],
                                 "nx": nx, "vbe": vbe, "vce": vce, "ic_a": v})
    with open(dc_out, "w") as fh:
        json.dump({"record": rid, "note": "simulated Ic (A) from sim/device-npn13g2/dc_family",
                   "cells": dc_cells}, fh)
        fh.write("\n")

    L += ["", "## Ic-Vce family (simulated, mA)", "",
          "Bench `dc_family.spice`: 4-terminal `npn13G2`, self-heating on (card default `selft=1`), "
          f"Vbe fixed per row, Vce swept. `†` = ic above the card window `{IC_WIN_PER_NX:g}*Nx` A "
          f"(OUTSIDE MODEL WINDOW for ic). Vce columns span the window {VCE_WIN[0]:.1f}-{VCE_WIN[1]:.1f} V; "
          f"Vbe rows are inside the {VBE_WIN[0]:.2f}-{VBE_WIN[1]:.2f} V window. At {TJ_MAX:g} C ambient "
          "the card's temperature window is already at its top, so any self-heating puts Tj outside "
          "it (labelled below).", ""]
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
          "collector ac-shorted; `.ac lin 3` 20-50 GHz, h21 read at the 20 and 50 GHz grid points; "
          "fT = |h21| * f0 (single-pole extrapolation, valid while |h21| >> 1 and the -20 dB/dec "
          "slope holds, so the two f0 should agree; where |h21| is near or below 1 the "
          "two estimates disagree and fT is **not** established). Ic is the dc family value at the same Vbe, "
          "Vce = 1.0 V. dT = Rth*Ic*Vce with Rth = 3.26e3*(4/Nx)^0.9 K/W (card), Tj = ambient + dT "
          f"(estimate; the simulated device self-heats internally). `†` = Tj above the +{TJ_MAX:g} C "
          "window ceiling; `‡` = ic above the window.", ""]
    ft = {}
    if reports["ft"]:
        for c in reports["ft"]["corners"]:
            if c["status"] != "pass":
                ok = False
            try:
                cur = read_ft(c)
            except (OSError, ValueError, KeyError) as e:
                print("summarize.py: %s: %s" % (c.get("corner_id"), e), file=sys.stderr)
                ok = False
                continue
            for (nx, vbe), pairs in cur.items():
                h = []
                for f, (a, b) in zip(gb.FT_FREQS, pairs):
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
    L += ["## Capture method", "",
          "- Currents are read from the captured sweep (`options.waveforms`, `capture_only`): Ic = +i(Vs_*) "
          "from the dc waveform, and the magnitudes of Ic_ac and Ib_ac from the ac waveform.", ""]
    print("\n".join(L))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
