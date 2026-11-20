#!/usr/bin/env python3
"""Render the append-only record for the Monte Carlo pilot (issue #174).

    mc_pilot_record.py <record-id> <git-sha> <dirty> <klt-version> <ngspice-version> \
        --models-dir <SG13G2_NGSPICE_MODELS> --json-out <path> \
        [--run KEY=report.json[:stderr]]... [--probe KEY=capture.json]...

One record covers the pilot's runs: the DC operating-point bench and the AC
gain bench, each against both statistical HBT sections of ``cornerHBT.lib``
(``hbt_typ_stat``: process-only; ``hbt_typ_mismatch``: per-instance), plus the
two negative-control probes. Every number is **simulated**, at the nominal
cell, through ideal passives and an ideal bias source, on a design that does
not yet meet its ratified rows: the record is a pilot's feasibility evidence
for the PROPOSED decision record ``0004-statistical-rows.md``, never a yield
claim and never a pass/fail claim.

Bench facts (sample count, seed, section names, the 15 device vector names)
come from ``gen_mc_pilot.py`` -- the same module that generates the decks and
requests -- so the record cannot fall behind the decks that produced it (same
rule as ``sim/lib/ac_record.py``). Derived statistics use numpy with the
sample standard deviation (ddof=1); the per-measurement mean/stddev/quantiles
quoted for ``ic_total``/``ic_diff_12``/``ic_ref`` are klt's own Monte Carlo
rollup from the report, not recomputed here.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_mc_pilot as gmp  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import gen_dut_benches as gdb  # noqa: E402
import sparams as sp  # noqa: E402
from provenance import commit_line  # noqa: E402

RUNS = (
    # (key, request filename, section label, what varies)
    ("dc_stat", "mc_op_stat.request.json", "hbt_typ_stat", "process-only section"),
    ("dc_mismatch", "mc_op_mismatch.request.json", "hbt_typ_mismatch",
     "per-instance mismatch section"),
    ("ac_stat", "mc_ac_stat.request.json", "hbt_typ_stat", "process-only section"),
    ("ac_mismatch", "mc_ac_mismatch.request.json", "hbt_typ_mismatch",
     "per-instance mismatch section"),
)

MODEL_FILES = (
    "cornerHBT.lib",
    "sg13g2_hbt_stat.lib",
    "sg13g2_hbt_mod.lib",
    "sg13g2_hbt_mod_mismatch.lib",
)

ISSUE = "#174 (https://github.com/2AMLogic/sg13g2-pa/issues/174)"
DR = "spec/decision-records/0004-statistical-rows.md (PROPOSED)"
UPSTREAM_5486 = "2AMLogic/klayout-tools#5486"
UPSTREAM_5487 = "2AMLogic/klayout-tools#5487"
UPSTREAM_5503 = "2AMLogic/klayout-tools#5503"


def _fmt(x, n=4):
    return f"{x:.{n}g}"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_run(path):
    """A run's report as dict, or {"__failed__": <stderr tail>} when klt did not
    produce a parsable report (the refusal is the evidence then)."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        return {"__failed__": f"{type(exc).__name__}: {exc}"}


def stderr_tail(path, lines=8):
    try:
        with open(path, errors="replace") as fh:
            return "".join(fh.readlines()[-lines:]).rstrip("\n")
    except OSError:
        return "<unreadable>"


def run_summary(report, stderr_path):
    """(one-line status, n_requested, n_completed, remote_desc, report|None)."""
    if "__failed__" in report:
        return (f"**REFUSED/FAILED** (no report; stderr tail below)", None, None, None, None)
    corners = report.get("corners", [])
    n_done = sum(1 for c in corners if c.get("status") == "pass")
    mc = report.get("environment", {}).get("monte_carlo") or {}
    n_req = mc.get("n")
    backend = report.get("environment", {}).get("backend")
    if isinstance(backend, dict):
        backend = backend.get("resolved") or backend.get("requested")
    remote = report.get("environment", {}).get("remote") or {}
    job = remote.get("job_id") or remote.get("job") or ""
    status = report.get("status")
    line = f"`{status}`, {n_done}/{len(corners)} corners pass" if corners else f"`{status}`"
    if n_req is not None:
        line += f" (requested n={n_req})"
    return (line, n_req, n_done, (f"job `{job}`" if job else None), report)


def dc_draws(report):
    """[{name: value}] over the report's corners, measurement values only."""
    draws = []
    for corner in report.get("corners", []):
        if corner.get("status") != "pass":
            continue
        vals = {}
        ok = True
        for m in corner.get("measurements", []):
            if m.get("value") is None:
                ok = False
                break
            vals[m["name"]] = float(m["value"])
        if ok and vals:
            draws.append(vals)
    return draws


def ac_draws(report):
    """[(min_s21_db, worst_s11_db)] per completed draw, from X1's port vectors."""
    out = []
    for corner in report.get("corners", []):
        if corner.get("status") != "pass":
            continue
        art = (corner.get("artifacts") or {}).get("complex_vectors")
        if not art:
            continue
        with open(art) as fh:
            side = json.load(fh)
        d = {k: np.array(v["real"], dtype=float) + 1j * np.array(v["imag"], dtype=float)
             for k, v in side["data"].items()}
        s = sp.s_from_nodes(d)  # the forward-driven copy X1: s21/s11
        out.append((float(np.min(sp.db20(s["s21"]))), float(np.max(sp.db20(s["s11"])))))
    return out


def stats(values):
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return None
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "stddev_sample": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "min": float(a.min()),
        "max": float(a.max()),
    }


def per_draw_device_spread(draws):
    """max-min across the 14 output devices, one value per draw."""
    cols = np.array([[d[f"ic{i}"] for i in range(1, 15)] for d in draws], dtype=float)
    return (cols.max(axis=1) - cols.min(axis=1)).tolist()


def klt_mc_rollup(report, name):
    for entry in report.get("measurements", []):
        if entry.get("name") == name:
            return entry.get("monte_carlo")
    return None


def load_probe(path):
    """A probe capture: the klt error envelope (refusal) or a full report (the
    probe ran; a future pin may accept what 0.9.0 refuses). The capture may
    carry log noise around the JSON object (klt prints its envelope on stderr,
    its report on stdout); the outermost object in the file is the payload."""
    with open(path, errors="replace") as fh:
        text = fh.read()
    try:
        doc = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {"kind": "unreadable", "message": text.strip()[-400:]}
        doc = json.loads(text[start:end + 1])
    if isinstance(doc, dict) and isinstance(doc.get("error"), dict):
        return {"kind": "refusal", "message": doc["error"].get("message", "")}
    return {"kind": "run", "report": doc}


def _sigma_line(key, st, unit):
    if st is None:
        return f"`{key}`: no completed draws"
    return (f"`{key}`: n={st['n']}, mean {_fmt(st['mean'])} {unit}, "
            f"sample sigma {_fmt(st['stddev_sample'])} {unit}, "
            f"min {_fmt(st['min'])} / max {_fmt(st['max'])} {unit}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("rid")
    ap.add_argument("git_sha")
    ap.add_argument("dirty")
    ap.add_argument("klt_version")
    ap.add_argument("ngspice_version")
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--run", action="append", default=[],
                    help="KEY=report.json[:stderr] (KEY in dc_stat/dc_mismatch/ac_stat/ac_mismatch)")
    ap.add_argument("--probe", action="append", default=[],
                    help="KEY=capture.json (KEY in scale/instances)")
    args = ap.parse_args(argv[1:])

    reports, stderrs = {}, {}
    for item in args.run:
        key, _, rest = item.partition("=")
        path, _, stderr = rest.partition(":")
        reports[key] = load_run(path)
        stderrs[key] = stderr or None
    probes = {}
    for item in args.probe:
        key, _, path = item.partition("=")
        probes[key] = load_probe(path)

    out = {}   # the JSON side output
    md = []
    w = md.append

    summaries = {key: run_summary(reports.get(key, {"__failed__": "not run"}),
                                  stderrs.get(key)) for key, *_ in RUNS}
    dc = {k: dc_draws(reports[k]) for k in ("dc_stat", "dc_mismatch") if k in reports}
    ac = {k: ac_draws(reports[k]) for k in ("ac_stat", "ac_mismatch") if k in reports}

    env = (reports.get("dc_mismatch") or reports.get("dc_stat") or {}).get("environment", {})
    if "__failed__" in env:
        env = {}
    backend = env.get("backend")
    if isinstance(backend, dict):
        backend = backend.get("resolved") or backend.get("requested")
    mc_env = env.get("monte_carlo") or {}
    model_hashes = {name: _sha256(os.path.join(args.models_dir, name))
                    for name in MODEL_FILES
                    if os.path.isfile(os.path.join(args.models_dir, name))}

    w(f"# mc-pilot record {args.rid}")
    w("")
    w("**Simulated** (ngspice), a Monte Carlo **pilot** at the nominal cell "
      f"({gdb.PROCESS_NOM} statistical sections, {gdb.TEMP_NOM_C} C, Vcc {gdb.VCC_NOM_V:g} V), "
      "**through ideal passives and an ideal bias source** (the DUT's `Lchoke`/`Cblock`/`Cin` "
      "are lossless; `Iref`/`Rb` contribute no variation). Not a pass/fail claim and **not a "
      "yield claim**: the design does not meet its ratified rows at the nominal cell "
      "(`ROADMAP.md`), so this record only establishes what variation the pinned HBT "
      f"statistical sections and the batch runner can measure, as evidence for {ISSUE} and "
      f"the PROPOSED decision record `{DR}`.")
    w("")
    w("## Conditions")
    w("")
    w("- Bench: `sim/mc-pilot/` (generated by `gen_mc_pilot.py`; the AC deck is byte-identical "
      "to the attested `sim/ac-gain/ac_gain.spice`, the DC deck is the same DUT inlined verbatim)")
    w(f"- Sample count n={gmp.N_SAMPLES} per run, seed {gmp.SEED} (klt derives each draw's "
      "seeds from it; the same requests reproduce the same draws), one corner per section")
    w("- Sections run separately: `hbt_typ_stat` (process-only: `sg13g2_hbt_stat.lib` global "
      "gauss() multipliers, one draw common to every instance) and `hbt_typ_mismatch` "
      "(`sg13g2_hbt_mod_mismatch.lib`: per-instance `qarea=agauss(1, 0.1, mm_ok ? 1 : 0)`, "
      "`mm_ok=1` at default)")
    w(f"- {commit_line(args.git_sha, args.dirty)}")
    w(f"- {args.klt_version}; {args.ngspice_version}; PDK per `sim/pdk.json`; backend "
      f"`{backend or '?'}`"
      + (" (batch fleet)." if backend == "batch" else " (NOT the batch fleet)."))
    w("- Model-file sha256 (submitting host's PDK install; the report's "
      f"`models_lib_sha256_scope` is `{env.get('models_lib_sha256_scope', '?')}`):")
    for name, digest in model_hashes.items():
        w(f"  - `{name}` `{digest[:16]}`")
    w("")
    w("## Runs")
    w("")
    w("| run | request | section | status | remote |")
    w("|---|---|---|---|---|")
    for key, request, section, what in RUNS:
        line, n_req, n_done, job, _ = summaries[key]
        w(f"| {key} | `{request}` | `{section}` ({what}) "
          f"| {line} | {job or '-'} |")
    w("")
    refused = [k for k, s in summaries.items() if s[4] is None]
    if refused:
        w("### Refusals / failures (committed as the record)")
        w("")
        for key in refused:
            w(f"**{key}**: no parsable report. stderr tail:")
            w("")
            w("```")
            w(stderr_tail(stderrs[key]) if stderrs.get(key) else "<none captured>")
            w("```")
            w("")
        w("Per the issue, a refused run is committed as the record and linked below; "
          "no local fallback and no hand loop was used.")
        w("")

    # --- Tool check --------------------------------------------------------
    w("## Tool check (answered from the runs)")
    w("")
    mm = dc.get("dc_mismatch", [])
    stt = dc.get("dc_stat", [])
    spread_mm = stats(per_draw_device_spread(mm)) if mm else None
    spread_st = stats(per_draw_device_spread(stt)) if stt else None
    diff_mm = stats([d["ic_diff_12"] for d in mm]) if mm else None
    diff_st = stats([d["ic_diff_12"] for d in stt]) if stt else None
    w("1. **Does the campaign sample non-zero variation on `npn13G2`, per instance?** "
      + ("Yes, from completed draws: under `hbt_typ_mismatch` the 14 identically biased "
         "output devices differ **within a single draw** (per-draw max-min across the array: "
         f"mean {_fmt(spread_mm['mean'])} A, "
         f"sample sigma {_fmt(spread_mm['stddev_sample'])} A) and the same-draw difference "
         f"`ic1-ic2` moves across draws (sigma {_fmt(diff_mm['stddev_sample'])} A), while "
         "under `hbt_typ_stat` the per-instance spread within a draw is exactly "
         + (f"{_fmt(spread_st['mean'])} A (every device moves together; the process section "
            f"draws one global multiplier set per die) and `ic1-ic2` sigma is "
            f"{_fmt(diff_st['stddev_sample'])} A"
            if spread_st is not None else "(no completed stat draws)")
         + ". The diode-connected reference moves too (see below) -- common movement across "
         "draws can be process or the shared mirror bias; the per-instance spread within a "
         "draw is what only mismatch produces."
         if mm else
         "**No completed mismatch draws** -- the spread is unmeasured (refusal above)."))
    w("")
    scale_p = probes.get("scale", {"kind": "refusal", "message": "<not probed>"})
    inst_p = probes.get("instances", {"kind": "refusal", "message": "<not probed>"})
    w("2. **Can a deterministic negative control be declared for this family "
      "(scaled or gated mismatch)?** No, not through `klt` at the pinned 0.9.0 client:")
    for label, probe_file, probe, link in (
            ("scaled", "probe_scale", scale_p, UPSTREAM_5486),
            ("gated", "probe_instances", inst_p, UPSTREAM_5487)):
        if probe["kind"] == "run":
            rep = probe["report"]
            draws = dc_draws(rep)
            d12 = stats([d["ic_diff_12"] for d in draws]) if draws else None
            verdict = ("a completed control run: sigma(ic1-ic2) = "
                       f"{_fmt(d12['stddev_sample'])} A over {d12['n']} draws"
                       if d12 else "no completed control draws")
            w(f"   - **{label} control**: the probe RAN (this pin accepts it) -- {verdict}.")
        else:
            w(f"   - **{label} control** (`{probe_file}.request.json`): "
              + ("refused before any draw, verbatim: " if probe["kind"] == "refusal"
                 else "capture unreadable, tail: ")
              + f"`{probe['message']}` -- {link}.")
    w("   The card's own gate is the subcircuit parameter `mm_ok` (default 1); the pinned "
      "client cannot reach it (`mismatch_scale`/`instances` shadow a global `.param` switch, "
      f"which sg13g2 does not have). The two-family curation and the `mm_ok` route are "
      f"{UPSTREAM_5486}; the sg13g2 `instances` work landed upstream only after the 0.9.0 "
      f"pin ({UPSTREAM_5487}, completed 2026-11-15), and the measured two-point scaling "
      f"check that acceptance still wants is {UPSTREAM_5503}. The `vary: \"process\"` axis "
      "is NOT a control for this deck family either: klt feeds ngspice one combined "
      "`.options seed=`, so an agauss deck re-rolls under any axis (klt's own "
      "`_expand_monte_carlo` docstring says the control does not extend to such decks).")
    w("")
    def _run_backend(rep):
        if not rep or "__failed__" in rep:
            return None
        b = rep.get("environment", {}).get("backend")
        if isinstance(b, dict):
            b = b.get("resolved") or b.get("requested")
        return b

    ran_batch = all(_run_backend(reports.get(key)) == "batch" for key, *_ in RUNS)
    any_job = any(s[3] for s in summaries.values())
    w("3. **Does the request run on the batch fleet with the pinned client "
      "(`sim/toolchain.json` klt 0.9.0)?** "
      + ("Yes: every run above resolved backend `batch` through the 0.9.0 client"
         + (" (job ids in the table; the runner is the fleet's 0.9.0)."
            if any_job else " (no job id published in the reports).")
         if ran_batch else
         "No: at least one request did not run on the batch backend (a refusal, a "
         "local run, or a failure -- see above); the refusal, where there is one, "
         "is the committed evidence and no local fallback was used."))
    w("")
    fam = json.dumps(mc_env.get("family_mismatch"), indent=2) if mc_env.get("family_mismatch") else None
    if fam:
        w("klt's own per-family disclosure for the mismatch run (the HBT `bipolar` family is "
          "**not independently verified** active -- this pilot's measurements are the "
          "verification, and they show it active):")
        w("")
        w("```json")
        w(fam)
        w("```")
        w("")

    # --- DC distributions --------------------------------------------------
    w("## DC operating point: quiescent collector current (per device and total)")
    w("")
    for key, label in (("dc_stat", "`hbt_typ_stat` (process-only)"),
                       ("dc_mismatch", "`hbt_typ_mismatch` (per-instance)")):
        draws = dc.get(key, [])
        w(f"### {label}")
        w("")
        if not draws:
            w("No completed draws.")
            w("")
            continue
        tot = stats([d["ic_total"] for d in draws])
        ref = stats([d["ic_ref"] for d in draws])
        vcc = stats([-d["icc_vcc"] for d in draws])
        w(f"- Total output-array quiescent Ic (sum of the 14 device currents, never the "
          f"supply current divided by 14): {_sigma_line('ic_total', tot, 'A')}")
        w(f"- Mirror reference device Ic (diode-connected `XQref`, a different operating "
          f"point, tracked separately): {_sigma_line('ic_ref', ref, 'A')}")
        w(f"- Supply current `-i(vcc)` (cross-check; = array + reference + `Iref` path): "
          f"{_sigma_line('icc_vcc', vcc, 'A')}")
        spread = stats(per_draw_device_spread(draws))
        w(f"- Same-draw spread across the 14 identically biased output devices "
          f"(max-min per draw): {_sigma_line('spread', spread, 'A')} -- the mismatch "
          "signature; under the process-only section this is the exactly-zero row")
        w(f"- Same-draw pair difference `ic1-ic2`: "
          f"{_sigma_line('ic_diff_12', stats([d['ic_diff_12'] for d in draws]), 'A')}")
        per_dev = {f"ic{i}": stats([d[f"ic{i}"] for d in draws]) for i in range(1, 15)}
        w("- Per-device across draws (mean / sample sigma, mA): "
          + ", ".join(f"`ic{i}` {per_dev[f'ic{i}']['mean']*1e3:.3f}/{per_dev[f'ic{i}']['stddev_sample']*1e3:.3f}"
                      for i in range(1, 15)))
        roll = {name: klt_mc_rollup(reports[key], name)
                for name in ("ic_total", "ic_diff_12", "ic_ref")}
        w("- klt's own Monte Carlo rollup (tool-computed; p5/p50/p95):")
        for name, r in roll.items():
            if r:
                w(f"  - `{name}`: mean {_fmt(r['mean'])} A, stddev {_fmt(r['stddev'])} A, "
                  f"p5 {_fmt(r['quantiles']['p5'])} A, p50 {_fmt(r['quantiles']['p50'])} A, "
                  f"p95 {_fmt(r['quantiles']['p95'])} A (n={r['n']}, errored {r['errored']})")
        w("")
        out[key] = {
            "draws": draws,
            "ic_total": tot, "ic_ref": ref, "icc_vcc": vcc,
            "per_draw_device_spread": spread,
            "ic_diff_12": stats([d["ic_diff_12"] for d in draws]),
            "per_device": per_dev,
            "klt_rollup": {k: v for k, v in roll.items() if v},
        }

    # --- AC distributions --------------------------------------------------
    w("## AC bench: in-band S21 / S11 per draw (forward-driven copy X1)")
    w("")
    w(f"11 points over the band ({gdb.BAND_LO_HZ:g}-{gdb.BAND_HI_HZ:g} Hz, the committed "
      "ac-gain sweep); per draw the minimum in-band S21 and the worst (highest) in-band S11:")
    w("")
    for key, label in (("ac_stat", "`hbt_typ_stat` (process-only)"),
                       ("ac_mismatch", "`hbt_typ_mismatch` (per-instance)")):
        draws = ac.get(key, [])
        if not draws:
            w(f"- {label}: no completed draws.")
            continue
        s21 = stats([d[0] for d in draws])
        s11 = stats([d[1] for d in draws])
        w(f"- {label}: min-in-band S21 {_sigma_line('', s21, 'dB')}; "
          f"worst-in-band S11 {_sigma_line('', s11, 'dB')}")
        out[key] = {"min_s21_db": s21, "worst_s11_db": s11}
    w("")
    w("The network is not matched at the nominal cell (worst S11 about -1.2 dB, "
      "`sim/ac-gain/records/`); these are distributions of the bench's own numbers, "
      "not claims against the Input-match row.")
    w("")

    # --- Limitations -------------------------------------------------------
    w("## Limits of this record")
    w("")
    w(f"- n={gmp.N_SAMPLES} per run: a sigma estimate carries roughly +/-10 % "
      "(sigma of a sigma estimate ~ sigma/sqrt(2n)); enough to size a campaign, "
      "not a yield statement. No quantile here is a spec limit.")
    w("- The passives and the bias source are ideal: the resistor/capacitor statistical "
      "sections of the PDK reach nothing in this netlist. Only the 15 HBTs are PDK devices.")
    w("- The AC deck carries a second DUT copy (X2, reverse excitation); its devices also "
      "draw mismatch, but S21/S11 above read the forward copy X1 only.")
    w("- Self-heating is on (card default); the operating point is the DUT's own mirror.")
    w("- No negative control completed at this pin: a zero-sigma row here would be "
      "structural (the stat section's within-draw spread), not a declared control "
      f"({UPSTREAM_5486}).")
    w("")

    out["runs"] = {key: {"status": summaries[key][0], "n_requested": summaries[key][1],
                         "n_completed": summaries[key][2], "remote": summaries[key][3]}
                   for key, *_ in RUNS}
    out["monte_carlo_environment"] = mc_env
    out["model_files_sha256"] = model_hashes
    out["probes"] = {k: ({"kind": v["kind"], "message": v["message"]}
                         if v["kind"] in ("refusal", "unreadable") else {"kind": "run"})
                     for k, v in probes.items()}
    with open(args.json_out, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
