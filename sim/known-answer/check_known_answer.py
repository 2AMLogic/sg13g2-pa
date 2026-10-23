#!/usr/bin/env python3
"""Check the known-answer decks against their analytic values; print the record.

Usage: check_known_answer.py <record-id> <git-sha> <dirty:0|1> <klt-version>
                             <out-dir> <normal|wrong-load>

Reads <out-dir>/<case>.report.json (written by `klt sim --format json`) for
each case, extracts with sim/lib/rf_extract.py and compares with the analytic
values. Prints the Markdown record on stdout. Exit 0 if every check is inside
tolerance, 1 otherwise (also for a failed extraction).

`wrong-load` runs only sine_75 (a 75 ohm load) against the 50 ohm analytic
value of sine_50; it is the negative control and is expected to exit 1.
"""
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import numpy as np  # noqa: E402
import rf_extract as rx  # noqa: E402

F0 = 1e9
# Analytic values (spec: known-answer check).
P_SINE_DBM = 10 * math.log10(0.5 * (1.0 / 2) ** 2 / 50 / 1e-3)  # +3.9794 dBm
V_DC, R_DC = 3.3, 100.0
P_DC_W = V_DC ** 2 / R_DC
H3_DBC = 10 * math.log10((0.1 / 1.0) ** 2)  # -20.000 dBc
TOL_DB = 0.01
TOL_REL = 1e-3
TOL_PAE_ABS = 1e-3

# Per case: load resistance, the node/source naming of the deck.
CASES = {
    "sine_50": dict(rl=50.0, v_load="v(out)", v_in="v(src)", i_in="i(vs)", supply=None),
    "sine_75": dict(rl=75.0, v_load="v(out)", v_in="v(src)", i_in="i(vs)", supply=None),
    "sine_h3": dict(rl=50.0, v_load="v(out)", v_in="v(src)", i_in="i(v3)", supply=None),
    "dc_load": dict(rl=R_DC, v_load="v(c)", v_in=None, i_in=None, supply=("v(c)", "i(vdd)")),
}


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run_case(out_dir, name):
    """Extract one case -> (report-json, extraction dict). Raises on failure."""
    with open(os.path.join(out_dir, f"{name}.report.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    corners = rep.get("corners", [])
    if len(corners) != 1 or corners[0].get("status") != "pass":
        raise rx.ExtractError("KLT_CORNER", f"{name}: klt sim corner did not pass")
    wf = corners[0]["artifacts"].get("waveform")
    if not wf or not os.path.isfile(wf):
        raise rx.ExtractError("NO_WAVEFORM", f"{name}: klt sim returned no waveform artifact")
    t, sig = rx.load_klt_waveform(wf)
    c = CASES[name]
    vl = sig[c["v_load"]]
    il = vl / c["rl"]
    supplies = []
    if c["supply"]:
        supplies.append((sig[c["supply"][0]], -sig[c["supply"][1]]))
    v_in = i_in = None
    if c["v_in"]:
        v_in, i_in = sig[c["v_in"]], -sig[c["i_in"]]
    res = rx.extract(t, F0, vl, il, supplies, v_in=v_in, i_in=i_in)
    res["max_dt_s"] = float(np.max(np.diff(t)))
    return rep, res


def dbm(w):
    return 10 * math.log10(w / 1e-3)


def main(argv):
    rid, git_sha, dirty, klt_ver, out_dir, mode = argv[1:7]
    cases = ["sine_75"] if mode == "wrong-load" else ["sine_50", "dc_load", "sine_h3"]
    rows, ok, engine = [], True, "unknown"
    extracted = {}
    for name in cases:
        try:
            rep, res = run_case(out_dir, name)
        except (rx.ExtractError, OSError, KeyError, ValueError) as exc:
            rows.append((name, "extraction", "-", "-", "-", "-", f"FAIL ({exc})"))
            ok = False
            continue
        engine = rep["environment"]["engine"] + " " + str(rep["environment"]["engine_version"])
        extracted[name] = res

    def row(case, quantity, expected, got, delta, tol, passed):
        nonlocal ok
        ok = ok and passed
        rows.append((case, quantity, expected, got, delta, tol, "PASS" if passed else "FAIL"))

    for name in ("sine_50", "sine_75"):
        if name in extracted:
            got = dbm(extracted[name]["p_out_w"])
            d = got - P_SINE_DBM
            row(name, "P_out (fundamental), dBm", f"{P_SINE_DBM:+.4f}", f"{got:+.4f}",
                f"{d:+.4f} dB", f"abs {TOL_DB} dB", abs(d) <= TOL_DB)
    if "dc_load" in extracted:
        r = extracted["dc_load"]
        rel = r["p_dc_w"] / P_DC_W - 1
        row("dc_load", "P_DC, mW", f"{P_DC_W * 1e3:.4f}", f"{r['p_dc_w'] * 1e3:.4f}",
            f"{rel * 100:+.5f} %", f"rel {TOL_REL * 100:g} %", abs(rel) <= TOL_REL)
        pae = r["pae"]
        row("dc_load", "PAE", "0", "undefined" if pae is None else f"{pae:+.2e}",
            "-", f"abs {TOL_PAE_ABS:g}", pae is not None and abs(pae) < TOL_PAE_ABS)
    if "sine_h3" in extracted:
        h3 = extracted["sine_h3"]["h3_dbc"]
        d = None if h3 is None else h3 - H3_DBC
        row("sine_h3", "P(3 f0)/P(f0), dBc", f"{H3_DBC:.3f}", "none" if h3 is None else f"{h3:.4f}",
            "-" if d is None else f"{d:+.4f} dB", f"abs {TOL_DB} dB", d is not None and abs(d) <= TOL_DB)

    any_res = next(iter(extracted.values()), None)
    label = "NEGATIVE CONTROL (wrong load)" if mode == "wrong-load" else "known-answer check"
    out = [
        f"# Large-signal extraction {label}: record {rid}",
        "",
        "**Simulated** (ngspice via `klt sim`), ideal elements only: ideal sources and ideal",
        "resistors, no PVT axis (temperature 27 C is nominal and has no effect on ideal",
        "resistors). This is the extractor's known-answer check (`spec/target-spec.md`,",
        "\"Large-signal extraction without harmonic balance\"), not a design result.",
        "",
        f"**Result: {'PASS' if ok else 'FAIL'}**"
        + (" (expected: this run compares a 75 ohm load with the 50 ohm analytic value and must fail)"
           if mode == "wrong-load" else ""),
        "",
        "## Results",
        "",
        "| Case | Quantity | Analytic | Extracted | Error | Tolerance | |",
        "|---|---|---|---|---|---|---|",
    ]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out += [
        "",
        "The tolerance type is stated per quantity: the dB checks are absolute, P_DC is",
        "relative, and PAE is an absolute bound because a relative tolerance on an expected",
        "value of 0 is undefined.",
        "",
        "## Extraction settings (spec defaults)",
        "",
        "- Load: 50 ohm resistor (sine_50, sine_h3), 100 ohm (dc_load), 75 ohm (sine_75, the",
        "  negative control); source 50 ohm behind a 1 V sine at f0 = 1 GHz (sine decks).",
        "- Drive: fixed 1 V source amplitude (one point, not a sweep); input power from the",
        "  measured source-port V and I.",
        "- Harmonic terminations: the default, an ideal resistor at 2 f0 and 3 f0 (the same",
        "  resistor at every frequency); labelled as the default, not a bench choice.",
        "- Passives: ideal. Nothing here characterises an inductor or any PDK model.",
        "- Transient: `tran 2.5p 150n` (T/400, 150 RF periods; the spec asks for <= T/200 and",
        "  >= 100 periods); uniform-grid resample at 400 points per period, trapezoid rule.",
        "- Settling: 0.01 dB (P_out) / 0.1 % (supply current), 10 consecutive periods before",
        "  the window and throughout it.",
        "- Window: 20 integer RF periods (the last 20 of the trace); rectangular coherent DFT;",
        "  P_k = 1/2 Re(V_k I_k*); PAE = (P_out - P_in)/P_DC, fundamentals for P_out and P_in.",
    ]
    if any_res:
        out.append(f"- This run: {any_res['periods_simulated']} periods simulated, window starts at "
                   f"period {any_res['window_start_period']}, largest raw time step "
                   f"{any_res['max_dt_s']:.3e} s.")
    out += [
        "",
        "## Provenance",
        "",
        f"- UTC timestamp / record id: `{rid}`",
        f"- Commit: `{git_sha}`" + (" (**working tree dirty** when run)" if dirty == "1" else ""),
        f"- `klt`: `{klt_ver}`; backend `local` (single corner)",
        f"- Engine actually used: `{engine}`",
        "- Corner: `default/novdd/27C` (no process models; the decks include none)",
        "",
        "### Decks and requests (sha256)",
        "",
    ]
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".spice", ".request.json")) and fn.rsplit(".", 2)[0].split(".")[0] in cases:
            out.append(f"- `sim/known-answer/{fn}` `{sha(os.path.join(HERE, fn))}`")
    out.append(f"- `sim/lib/rf_extract.py` `{sha(os.path.join(HERE, '..', 'lib', 'rf_extract.py'))}`")
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
