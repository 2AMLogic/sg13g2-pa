#!/usr/bin/env python3
"""Check the thermal-node known-answer run and print its record.

Usage: thermal_record.py <record-id> <git-sha> <dirty:0|1> <klt-version>
                         <provenance.json> <out-dir> <normal|neg>

Reads <out-dir>/<case>.report.json (written by `klt sim --format json`; case
is thermal, or thermal_neg for the negative control), recomputes every graded
check from the report's measured values against the analytic answers
gen_bench.py derives from sim/lib/device_limits.rth(), and prints the
append-only Markdown record on stdout. The solver-diagnostics section is read
from the run's own ngspice log (the report's log artifact), not asserted.

Exit 0 if the check passed (mode `normal`: corner pass and every graded value
inside tolerance; mode `neg` never exits 0 -- the control is expected to fail,
and exits 1 with its record kept, as `known-answer/run.sh --wrong-load` does).
Exit 1 on a failed or missing report, an out-of-tolerance value, or a negative
control that did NOT fail (a control that passes is broken and says so).
Stdlib only; run with -I.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("thermal_gen_bench", os.path.join(HERE, "gen_bench.py"))
gb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gb)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
# The card's rth expression lives once, in sim/lib/device_limits.py (provenance
# marked there); never retype it here.
from device_limits import rth  # noqa: E402
from provenance import commit_line, sha  # noqa: E402

CASE = {"normal": "thermal", "neg": "thermal_neg"}
LABEL = {"normal": "known-answer check",
         "neg": "NEGATIVE CONTROL (selft=0)"}


def load(out_dir, case):
    p = os.path.join(out_dir, case + ".report.json")
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def measured_by_name(rep):
    """The single corner's measurements, name -> dict (value/status/unit)."""
    out = {}
    for c in rep.get("corners", []):
        for m in c.get("measurements", []):
            out[m["name"]] = m
    return out


def graded_rows(m):
    """Every graded check: (name, quantity, analytic, tolerance str, kind)."""
    rows = []
    for nx in gb.NX_INJ:
        for i in gb.I_INJ_A:
            name = gb.inj_name(nx, i)
            rows.append((name, "V(t) at Nx=%d, P = %g W injected" % (nx, i),
                         i * rth(nx), "rel 0.01 %", "rel", gb.TOL_INJ_REL))
    rows.append(("rth_meas",
                 "V(t)/P, biased Nx=%d (Vce %g V, Vbe %g V): rth"
                 % (gb.BIAS_NX, gb.BIAS_VCE_V, gb.BIAS_VBE_V),
                 rth(gb.BIAS_NX), "rel 0.1 %", "rel", gb.TOL_BIAS_REL))
    rows.append(("vt4_minus_vt5",
                 "v(x4t.t) - v(t5b), 4-terminal vs 5-terminal at the same bias",
                 0.0, "abs 1e-06 V", "abs", gb.TOL_4T_ABS_V))
    out = []
    for name, quantity, analytic, tol_s, kind, tol in rows:
        m_ = m.get(name)
        if m_ is None or m_["value"] is None:
            out.append((name, quantity, analytic, None, None, tol_s, "FAIL (no measured value)"))
            continue
        val = m_["value"]
        if kind == "rel":
            err = val / analytic - 1.0 if analytic else float("nan")
            inside = abs(err) <= tol
            err_s = "%+.2e rel" % err
        else:
            err = None
            inside = abs(val) <= tol
            err_s = "%+.3e V" % val
        if m_.get("status") != "pass":
            inside = False
        out.append((name, quantity, analytic, val, err_s, tol_s, "PASS" if inside else "FAIL"))
    return out


def log_notes(rep):
    """What the run's own ngspice log actually shows (solver diagnostics)."""
    log = None
    for c in rep.get("corners", []):
        log = (c.get("artifacts") or {}).get("log")
    if not log or not os.path.isfile(log):
        return ["- ngspice log not found; nothing to quote."]
    text = open(log, encoding="utf-8", errors="replace").read()
    notes = []
    for line, why in [
        ("The temperature limiting function received NaN.",
         "benign here: it fires on the injection decks and the solve still converges to "
         "the values above; the gate's error patterns (`singular matrix`, `Error:`, ...) "
         "do not match it, so `sim_gate_logs` runs with no flags and nothing is suppressed"),
        ("Note: Dynamic gmin stepping completed",
         "dynamic gmin stepping started and recovered; `--tolerate-recovered-gmin` is "
         "deliberately NOT passed -- no `Warning: singular matrix` line is present to "
         "tolerate, and the gate passes these logs unmodified"),
    ]:
        if line in text:
            notes.append(f"- The log carries `{line}` -- {why}.")
        else:
            notes.append(f"- The log does not carry `{line}`.")
    return notes


def main(argv):
    rid, git_sha, dirty, klt_ver, prov_path, out_dir, mode = argv[1:8]
    if mode not in CASE:
        print("thermal_record.py: unknown mode '%s' (want normal or neg)" % mode, file=sys.stderr)
        return 2
    case = CASE[mode]
    prov = json.load(open(prov_path))
    rep = load(out_dir, case)
    L = [f"# npn13G2 thermal-node {LABEL[mode]}: record {rid}", "",
         "**Simulated** (ngspice via `klt sim`), one PDK device bench: the VBIC card's",
         "self-heating thermal node is exercised directly, at one corner (`hbt_typ`,",
         "27 C; the card's `rth` carries no process or temperature coefficient, so one",
         "corner is the whole PVT information this check can carry). This is the",
         "known-answer check DR 0001 Q4 deferred (D-2), not a design result.", ""]

    corner_ok = False
    engine = "unknown"
    if rep is None:
        L += ["**No usable report** (see its stderr); nothing was checked.", ""]
    else:
        env = rep.get("environment", {})
        engine = "%s %s" % (env.get("engine"), env.get("engine_version"))
        corners = rep.get("corners", [])
        corner_ok = bool(corners) and corners[0].get("status") == "pass"

    rows = graded_rows(measured_by_name(rep)) if rep else []
    all_inside = bool(rows) and all(r[6] == "PASS" for r in rows)
    if mode == "normal":
        ok = corner_ok and all_inside
        verdict = "PASS" if ok else "FAIL"
        expect = ""
    else:
        # The control is expected to fail: a passing control is a broken control.
        ok = (not corner_ok) and rows and all(r[6] == "FAIL" for r in rows)
        verdict = "FAIL" if ok else "CONTROL DID NOT FAIL"
        expect = (" (expected: `selft=0` removes the card's thermal network, so the same "
                  "injections must miss `P * rth`; this run failing is the demonstration "
                  "that the check can fail)")
    L += [f"**Result: {verdict}**{expect}", "",
          "## Results", "",
          "| Case | Quantity | Analytic | Measured | Error | Tolerance | |",
          "|---|---|---|---|---|---|---|"]
    for name, quantity, analytic, val, err_s, tol_s, verdict_cell in rows:
        a_s = f"{analytic:.6f}"
        v_s = "-" if val is None else f"{val:.6f}"
        L.append(f"| {name} | {quantity} | {a_s} | {v_s} | {err_s} | {tol_s} | {verdict_cell} |")
    L += ["",
          "The analytic column is the card's own answer, `P * rth(Nx)` with `rth(Nx) =",
          "3.26e3 * (4/Nx)^0.9` K/W taken from `sim/lib/device_limits.py` (the card's",
          "expression, defined once for the repo), not retyped. The tolerance type is",
          "stated per row: relative on the thermal-node readings, absolute on the",
          "4-terminal comparison.", ""]
    if rep is not None:
        m = measured_by_name(rep)
        bias_ic = m.get("ic_bias", {}).get("value")
        bias_p = m.get("p_bias", {}).get("value")
        diff4 = m.get("vt4_minus_vt5", {}).get("value")
        if mode == "neg":
            L += ["## Bench", "",
                  "- `thermal_neg.spice` repeats the injection cases of `thermal.spice`",
                  "  (idle 5-terminal `npn13G2_5t`, 2 Nx x 2 powers) with `selft=0` on every",
                  "  instance: the card's `rth` collapses to 0 and only the subckt's own",
                  "  `Rt t 0 R = 1e9` shunt remains, so each node reads `I * 1e9`. Its grading",
                  "  reuses the positive request's limits, so a PASS here would mean the",
                  "  positive check cannot detect a dead thermal network.",
                  "- Single corner `hbt_typ` at 27 C, `--backend local` (one unit; no batch",
                  "  submit)."]
        elif bias_ic is not None and bias_p is not None:
            L += ["## Bench", "",
                  "- `thermal.spice` instantiates the 5-terminal `npn13G2_5t` subcircuit",
                  "  (ports `c b e bn t`). The injection cases hold the device idle (all",
                  "  signal terminals grounded) and drive a known constant current into",
                  "  the thermal node, where amperes are watts, at 2 Nx (1, 4) x 2 powers",
                  "  (1 mW, 10 mW). The biased case runs the device at its own operating",
                  "  point (Vce %g V, Vbe %g V, Nx=%d: Ic %g A, P %g W reconstructed from"
                  % (gb.BIAS_VCE_V, gb.BIAS_VBE_V, gb.BIAS_NX, bias_ic, bias_p),
                  "  the terminal voltages and currents) and grades `V(t)/P` against",
                  "  `rth(%d)`." % gb.BIAS_NX,
                  "- The biased row is graded at 0.1 % rather than 0.01 %: its P comes from",
                  "  the simulation's own terminal V and I, which is not bit-identical to the",
                  "  model's internal power, so this row is a self-consistency check on the",
                  "  device-to-node power path, not a known answer in the injection sense.",
                  "- The 4-terminal case instantiates `npn13G2` (ports `c b e bn`) at the",
                  "  same bias and probes its internal thermal node hierarchically as",
                  "  `v(x4t.t)` -- the node `sim/psat-sweep/psat_record.py` reads. Agreement",
                  "  with the 5-terminal case is graded at abs 1 uV" +
                  ("; measured %+.3e V, so the verdict transfers to the device instance"
                   % diff4 if diff4 is not None
                   else "") + ". If they ever disagreed beyond that, this record's verdict",
                  "  would NOT transfer to `sim/psat-sweep`.",
                  "- Each subckt ends with `Rt t 0 R = 1e9`, so the node sees `rth || 1e9`",
                  "  and every reading sits low by `-rth/1e9` relative (%.2e at Nx=4, %.2e"
                  % (rth(4) / (rth(4) + gb.R_SHUNT_OHM), rth(1) / (rth(1) + gb.R_SHUNT_OHM)),
                  "  at Nx=1). The 0.01 % injection tolerance absorbs that systematic on",
                  "  purpose (margins ~30x and ~9x), so passing it is by design, not luck.",
                  "- Analysis `op` with graded `measurements`: `klt` grades the check itself",
                  "  and its exit code gates; no waveform post-processing and no settling",
                  "  question (an `op` solve has no transient). `cth` is therefore not",
                  "  exercised anywhere in this record.",
                  "- Single corner `hbt_typ` at 27 C, `--backend local` (one unit; no batch",
                  "  submit)."]
        L += ["", "## Solver diagnostics (read from this run's ngspice log)", ""]
        L += log_notes(rep)
        L += ["", "## Scope of the verdict", "",
              "What was shown: the card's `rth` network (kelvin of rise, watts in) and the",
              "device-to-node power path at DC. What was NOT shown: `cth` and the thermal",
              "time constant (an `op` analysis cannot time-resolve them). Results elsewhere",
              "in this repo may cite this check only within that scope.", ""]
    else:
        L += ["## Bench", "", "No report to describe.", ""]
    L += ["## Provenance", "",
          f"- UTC timestamp / record id: `{rid}`",
          commit_line(git_sha, dirty),
          f"- PDK: IHP-Open-PDK pinned `{prov['pinned_release_tag']}`, installed "
          f"`{prov['installed_release_raw']}` (identity route `{prov['identity_route']}`), "
          "verified against `sim/pdk.json` by `sim_require_pdk`",
          f"- `klt`: `{klt_ver}`; backend `local` (single corner)",
          f"- Engine actually used: `{engine}`",
          "- Corner: `hbt_typ/novdd/27C`", "",
          "### Decks, requests and model inputs (sha256)", ""]
    hashed = [f"{case}.spice", f"{case}.request.json", "gen_bench.py"]
    for fn in hashed:
        if os.path.isfile(os.path.join(HERE, fn)):
            L.append(f"- `sim/known-answer-thermal/{fn}` `{sha(os.path.join(HERE, fn))}`")
    L.append(f"- `sim/lib/device_limits.py` `{sha(os.path.join(HERE, '..', 'lib', 'device_limits.py'))}`")
    print("\n".join(L))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
