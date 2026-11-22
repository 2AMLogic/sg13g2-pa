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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import gen_dut_benches as gdb  # noqa: E402
import rf_extract as rx  # noqa: E402
import spec_rows as sr  # noqa: E402
from finding_trackers import POWER_ROWS, STABILITY_AND_MATCH, line_md, plural, units_md  # noqa: E402
from provenance import commit_line  # noqa: E402
# The (P) breakdown minima and the (M) model window live once, in sim/lib/device_limits.py
# (provenance marked there); the bench facts live once in gen_dut_benches.py, which
# generates this bench's deck. Nothing below is a retyped number, and the record prose
# is formatted from these names. The same rule covers the two things this record used to
# retype: the watts-to-dBm conversion is rf_extract.dbm -- the same one reduce_sweep uses,
# so the table columns and the headline Psat/P1dB cannot diverge -- and the commit half of
# the provenance bullet is provenance.commit_line, shared by every sim/ renderer.
from device_limits import (BVCEO_MIN, BVCBO_MIN, IC_WIN_PER_NX,  # noqa: E402
                           TJ_MAX, VBE_WIN, VCE_WIN)

F0 = gdb.F0_HZ
RS = gdb.RS_OHM
N_UNITS, NX = gdb.output_array()   # output-array devices sharing COLL/VB, and their Nx
IC_MAX_PER_DEVICE = IC_WIN_PER_NX * NX


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


def _remote_md(remote):
    """The `remote` block for the record's Conditions bullet.

    A single-job submit is printed whole, as it always has been. A **sharded** one
    (`request.remote.hosts > 1`, which the matched bench sets) comes back as
    `{"fleet": [... one full block per shard ...]}`, and each block carries the worker's
    whole environment capture -- ten of them is some 15 kB of JSON in one bullet, which
    buries the record it is supposed to annotate. Summarize those to the identity a
    record actually needs: how many shards, which jobs, and the instance/region/engine
    they agreed on. The full blocks stay in the committed
    `corners/<id>/psat_sweep_match.report.json`, which is where someone auditing the run
    would look anyway.

    The summary is **round-local**: after a `--resume` run this report's fleet is the
    LAST round's launched set, not the whole run's (issue #194) -- the whole-run
    picture is `_sharded_run_md`'s to state, next to this line.
    """
    if not isinstance(remote, dict):
        return remote
    fleet = remote.get("fleet")
    if not isinstance(fleet, list) or not fleet:
        return remote
    def uniq(key):
        vals = sorted({str(s.get(key)) for s in fleet if s.get(key) is not None})
        return ", ".join(vals) if vals else "n/a"
    ids = ", ".join(str(s.get("job_id", "?")) for s in fleet)
    if len(fleet) > 20:
        ids = ", ".join(str(s.get("job_id", "?")) for s in fleet[:20]) \
            + f", ... (+{len(fleet) - 20} more)"
    elapsed = [s.get("elapsed_seconds") for s in fleet if s.get("elapsed_seconds") is not None]
    elapsed_range = f"{min(elapsed)}-{max(elapsed)} s" if elapsed else "n/a"
    # Round-local wall clock from the fleet blocks' own client timestamps: first
    # submit (launch stamp where a block carries no submit stamp -- that happens
    # on resumed shards) to last terminal state, within THIS round only.
    wall = "n/a"
    starts = [_ts(s.get("client_submitted_at")) or _ts(s.get("client_launched_at"))
              for s in fleet]
    starts = [t for t in starts if t is not None]
    ends = [t for s in fleet if (t := _ts(s.get("client_status_terminal_at"))) is not None]
    if starts and ends:
        wall = f"{(max(ends) - min(starts)).total_seconds():.0f} s"
    return (f"{len(fleet)} fleet shards in this report's final round (round-local); "
            f"provider {uniq('provider')}; "
            f"region {uniq('region')}; instance_type {uniq('instance_type')}; "
            f"lifecycle {uniq('lifecycle')}; runner klt {uniq('runner_klt_version')}; "
            f"elapsed {elapsed_range}; round-local wall clock (first evidenced "
            f"submit or launch to last evidenced terminal) {wall}; "
            f"job ids: {ids}"
            + "  -- full per-shard environment capture in corners/<id>/*.report.json")


def _ts(x):
    """Read an offset-aware artifact timestamp in UTC, if present and usable."""
    if not isinstance(x, str):
        return None
    try:
        timestamp = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else None


# Only these messages establish the action. A status mention, capacity refusal
# or submission in an earlier attempt does not date a job's launch.
_JOB_EVENT = re.compile(
    r"batch job (klt-sim-[0-9a-f]+) "
    r"(submitting\b|launched; re-attach\b|had been submitted but never launched; launched it\b)"
)


def _rounds_md(run, bench):
    """Group distinct submissions and launches by the log that records the event."""
    numbered = {}
    unnumbered = []
    initial = run / f"{bench}.stderr"
    if initial.is_file():
        numbered[0] = [initial]
    for path in sorted(run.glob(f"{bench}.resume*.stderr")):
        match = re.fullmatch(r"resume([1-9][0-9]*)(?:\..+)?\.stderr",
                             path.name[len(bench) + 1:])
        if match:
            numbered.setdefault(int(match[1]), []).append(path)
        else:
            unnumbered.append(path)

    def label(i):
        return f"resume{i}" if i else "initial"

    groups = [(label(i), numbered[i]) for i in sorted(numbered)]
    groups.extend((f"unnumbered resume (`{p.name}`)", [p]) for p in unnumbered)
    if not groups:
        return ["no submit stderr found for the initial or resume rounds"], set()

    lines = []
    all_launched = set()
    for name, paths in groups:
        submitted, launched = set(), set()
        for path in paths:
            with path.open(errors="replace") as fh:
                for line in fh:
                    event = _JOB_EVENT.search(line)
                    if event:
                        ids = submitted if event[2] == "submitting" else launched
                        ids.add(event[1])
        launch_word = "launch" if len(launched) == 1 else "launches"
        lines.append(f"{name}: {len(submitted)} submitted, {len(launched)} {launch_word} logged")
        all_launched.update(launched)

    summary = [f"{plural(len(numbered), 'identified attempt')} evidenced by stderr ({'; '.join(lines)})"]
    missing = []
    if 0 not in numbered:
        missing.append("initial")
    previous = 0
    for i in sorted(numbered):
        if i > previous + 1:
            first, last = label(previous + 1), label(i - 1)
            missing.append(first if first == last else f"{first} through {last}")
        previous = i
    if missing:
        summary.append(f"missing round logs: {', '.join(missing)}")
    if unnumbered:
        summary.append("the unnumbered resume logs do not establish their round numbers")
    elif len(numbered) == 1 and 0 in numbered:
        summary.append("only the initial submit log is available")
    return summary, all_launched


def _artifact(path):
    try:
        with path.open() as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def _sharded_run_md(rid, run_dir, bench, request_path, remote):
    """Describe the run using only the artifacts saved alongside its report."""
    run = Path(run_dir)
    saved_request = run / f"{bench}.request.json"
    if request_path and Path(request_path).resolve().parent == run.resolve():
        saved_request = Path(request_path)
    request_remote = _artifact(saved_request).get("remote")
    declared = request_remote.get("hosts") if isinstance(request_remote, dict) else None
    source = "saved request (`remote.hosts`)"
    if declared is None:
        declared = _artifact(run / f"{bench}.dry-run.json").get("hosts")
        source = "run's dry-run manifest (`hosts`)"
    if declared is None:
        o = ["declared shards per attempt unknown (no host count in the saved request or dry-run manifest)"]
    else:
        o = [f"the {source} declares {declared} shards per attempt"]

    rounds, logged_ids = _rounds_md(run, bench)
    o.extend(rounds)
    receipts, launches, completions = set(), [], {}
    for path in (run / bench).glob("*/batch-receipt-*.json"):
        receipt = _artifact(path)
        job = receipt.get("job_id")
        start, end = _ts(receipt.get("launched_at")), _ts(receipt.get("completed_at"))
        if job and (start or end):
            receipts.add(job)
            if start:
                launches.append(start)
            if end:
                completions[job] = max(end, completions.get(job, end))

    fleet = remote.get("fleet", [])
    fleet_ids = {s["job_id"] for s in fleet if s.get("job_id")}
    distinct = logged_ids | receipts | fleet_ids
    o.append(f"{plural(len(distinct), 'distinct launched job ID')} evidenced across round logs, "
             f"timed receipts and final fleet ({len(logged_ids)} in launch messages, "
             f"{len(receipts)} with timed receipts, {len(fleet_ids)} in final fleet)")
    if receipts - logged_ids:
        o.append(f"no round launch message for {plural(len(receipts - logged_ids), 'receipt-backed job ID')}")
    if not receipts:
        o.append(f"no timestamped launch or completion receipts found under `corners/{rid}/{bench}/`")

    if launches and completions:
        start, end = min(launches), max(completions.values())
        o.append(f"receipt interval, first evidenced launch {start:%Y-%m-%dT%H:%M:%SZ} "
                 f"to last evidenced completion {end:%Y-%m-%dT%H:%M:%SZ} = "
                 f"{(end - start).total_seconds():.0f} s (launch-to-completion, "
                 f"idle gaps included)")
    else:
        o.append("the launch-to-completion span is unknown without both receipt endpoints")
    incomplete = len(receipts - completions.keys())
    if incomplete:
        o.append(f"no completion timestamp for {plural(incomplete, 'receipt-backed job')}")
    submitted = sum(_ts(s.get("client_submitted_at")) is not None for s in fleet)
    o.append(f"{submitted} of {len(fleet)} final-fleet entries carry `client_submitted_at`; "
             "final-round stamps alone cannot date the whole run's first submission")
    # -- the stale tail flags the final report can carry after a resume -------
    if remote.get("resumable") or remote.get("unlaunched_shards"):
        o.append("the final report's fleet line above is round-local -- the LAST "
                 "round's launched set -- and its `unlaunched_shards` / "
                 "`resumable` fields describe that round's tail, not the whole "
                 "run -- whole-run completion is the committed corner-matrix "
                 "report verdict")
    return "Sharded run provenance (whole run): " + "; ".join(o) + "."


def _rung_psat(red):
    if red is None or red.get("psat_dbm") is None:
        return None
    return _rung(red["psat_dbm"] > sr.PSAT_TARGET_DBM, red["psat_dbm"] > sr.PSAT_FALLBACK_DBM)


def _rung_p1db(red):
    if red is None or red.get("p1db_out_dbm") is None:
        return None
    return _rung(red["p1db_out_dbm"] > sr.P1DB_TARGET_DBM, red["p1db_out_dbm"] > sr.P1DB_FALLBACK_DBM)


def _rung_pae(red):
    if red is None or red.get("peak_pae") is None:
        return None
    return _rung(red["peak_pae"] > sr.PAE_TARGET, red["peak_pae"] > sr.PAE_FALLBACK)


def _rung_s11(s11_db):
    if s11_db is None:
        return None
    return _rung(s11_db < sr.S11_TARGET_DB, s11_db < sr.S11_FALLBACK_DB)


def _findings_md(cells):
    """The findings/tracker section: every rung below `met` names the design
    iteration that tracks it, and findings no issue tracks say so (issue #194).

    Rungs are recomputed with the same `_rung_*` the verdict table uses, so a
    count here can never disagree with the table above it. A cell that refused
    its reduction or yielded no extracted points grades nothing -- it is a finding of its
    own class, never folded into a row's shortfall count.
    """
    lines = []
    rows = (
        ("Input match (large-signal S11, worst drive)",
         [_rung_s11(c["s11_large_worst_db"]) for c in cells], STABILITY_AND_MATCH),
        ("Psat", [_rung_psat(c["reduction"]) for c in cells], POWER_ROWS),
        ("Output P1dB", [_rung_p1db(c["reduction"]) for c in cells], POWER_ROWS),
        ("Peak PAE", [_rung_pae(c["reduction"]) for c in cells], POWER_ROWS),
    )
    for name, rungs, tracker in rows:
        ln = line_md(name, rungs, tracker)
        if ln:
            lines.append(ln)
    n_status = sum(1 for c in cells for f in c["failures"]
                   if f["code"].startswith("KLT_STATUS_"))
    if n_status:
        codes = sorted({f["code"] for c in cells for f in c["failures"]
                        if f["code"].startswith("KLT_STATUS_")})
        lines.append(units_md(n_status, "sweep unit",
                              f"excluded by klt status ({', '.join(f'`{c}`' for c in codes)})",
                              None))
    refused = [c for c in cells
               if c["reduction"] is None and c["reduction_error"] and c["points"]]
    if refused:
        codes = sorted({c["reduction_error"]["code"] for c in refused})
        lines.append(units_md(len(refused), "cell",
                              f"refused a reduction ({', '.join(f'`{c}`' for c in codes)})",
                              None))
    unextracted = [f for c in cells for f in c["failures"]
                   if not f["code"].startswith("KLT_STATUS_")]
    if unextracted:
        codes = sorted({f["code"] for f in unextracted})
        lines.append(units_md(len(unextracted), "sweep unit",
                              f"could not be extracted "
                              f"({', '.join(f'`{c}`' for c in codes)}); excluded from "
                              f"their cells' reductions", None))
    if not lines:
        lines.append("- No verdict falls below its rung; every cell reduced and "
                     "every unit simulated.")
    return ["## Findings and their trackers", "",
            "Each finding this run records, with the design iteration that tracks "
            "it (named only where one exists):", ""] + lines


def label(st):
    tags = []
    if st["breakdown_violation"]:
        tags.append("BREAKDOWN VIOLATION")
    if st["outside_window"]:
        tags.append("OUTSIDE MODEL WINDOW")
    return "; ".join(tags) if tags else "inside window, within breakdown minima"


def _cell_md(cell):
    return f"`{cell['process']}` / {cell['temperature_c']:g} C / {cell['vcc']:g} V"


def _rung(ok_target, ok_fallback):
    """A row verdict rung: met (Target), fallback, or missed (below Fallback)."""
    return "met" if ok_target else ("fallback" if ok_fallback else "missed")


def _worst_stress(pts):
    """The worst per-device stress over a cell's whole sweep, and where it sits."""
    worst_pt = max(pts, key=lambda p: p["stress"]["vce_pk_v"])
    out = dict(worst_pt["stress"])
    for k in ("vce_pk_v", "vcb_pk_v", "vbe_pk_v", "ic_pk_a", "tj_max_c"):
        out[k] = max(p["stress"][k] for p in pts)
    for k in ("frac_vce_outside", "frac_vbe_outside", "frac_ic_outside", "frac_tj_outside"):
        out[k] = max(p["stress"][k] for p in pts)
    out["breakdown_violation"] = any(p["stress"]["breakdown_violation"] for p in pts)
    out["outside_window"] = any(p["stress"]["outside_window"] for p in pts)
    out["at_p_avail_dbm"] = worst_pt["p_avail_dbm"]
    return out


def render_matrix(variant, rid, git_sha, dirty, klt_v, ng_v, bench, net, rep,
                  cell_order, by_cell, out_json, run_dir=None, request_path=None):
    """The PVT-matrix record (issue #173): one reduction per cell, per-cell
    ratified-row verdicts, per-cell breakdown/window labels -- all provisional
    while the Supply row is DRAFT. ``run_dir`` (issue #194)
    locates the run's committed artifacts for the whole-run provenance bullet."""
    n_cells_declared = gdb.pvt_cell_count()
    cells = []
    for key in cell_order:
        grp = by_cell[key]
        grp["points"].sort(key=lambda p: p["p_in_w"])
        red, red_err = None, None
        try:
            red = rx.reduce_sweep(grp["points"])
        except rx.ExtractError as e:
            red_err = {"code": e.code, "message": str(e)}
        cells.append({"cell": grp["cell"], "points": grp["points"],
                      "failures": grp["failures"], "reduction": red,
                      "reduction_error": red_err,
                      "s11_large_worst_db": (max(p["s11_large_db"] for p in grp["points"])
                                             if grp["points"] else None),
                      "worst_stress": _worst_stress(grp["points"]) if grp["points"] else None})

    # The row summary the README's failing-row list is drawn from: every row's
    # worst cell (the spec binds the worst cell as the figure).
    def _fig(cell, key):
        return cell["reduction"] and cell["reduction"].get(key)

    def _worst(key, agg):
        vals = [agg(c) for c in cells if agg(c) is not None]
        return min(vals) if vals else None

    row_summary = {}
    if cells:
        row_summary = {
            "psat_worst_dbm": _worst("psat_dbm", lambda c: _fig(c, "psat_dbm")),
            "p1db_worst_dbm": _worst("p1db_out_dbm", lambda c: _fig(c, "p1db_out_dbm")),
            "pae_worst": _worst("peak_pae", lambda c: _fig(c, "peak_pae")),
            "s11_large_worst_db": _worst(None, lambda c: c["s11_large_worst_db"]),
        }

    json.dump({"record_id": rid, "variant": variant, "bench": bench["name"],
               "pvt_matrix": True, "output_network": net, "cells": cells,
               "row_summary": row_summary},
              open(out_json, "w"), indent=1, default=float)

    n_units = len(rep.get("corners", []))
    n_failed = sum(len(c["failures"]) for c in cells)
    o = []
    w = o.append
    w(f"# psat-sweep record {rid} -- PVT matrix, {len(cells)} cells")
    w("")
    w(f"**PROVISIONAL: Supply row DRAFT.** The {gdb.VCC_NOM_V:g} V nominal the "
      f"{gdb.PVT_VCC_V[0]:g}/{gdb.VCC_NOM_V:g}/{gdb.PVT_VCC_V[2]:g} V supply points hang "
      "off is DR 0003, PROPOSED -- the spec's Supply row is not ratified, so **no "
      "verdict below is a pass claim for any ratified row**; each is a per-cell "
      "finding about where the design stands.")
    w("")
    if net is not None:
        w("**Simulated** (ngspice transient) through **ideal passives, off-chip match**: "
          "the DUT's own `Lchoke`, `Cblock`, `Cin` and every element of the off-chip "
          "L-section are lossless with no self-resonance; **no inductor model is used** "
          "(DR 0001 D-1 still deferred), so P_Out/PAE are not quotable as an on-chip "
          "output-network result. The bench evidences the spec's **Fallback** "
          "Output-port cell's boundary convention only; the Target (on-chip match) cell "
          "stays unevidenced. Its harmonic terminations are set by the network, so its "
          "figures are **not compared** with the bare-50-ohm bench's.")
        w("")
    w("## Conditions")
    w("")
    w(f"- Bench `sim/psat-sweep/{bench['name']}.spice`; spec rows: Psat, P1dB, Peak PAE, "
      "Input match (large-signal), Device stress (RATIFIED); back-off PAE, harmonics, "
      "large-signal stability, thermal (DRAFT, reported only).")
    w(f"- **Declared matrix**: `sim/pvt-matrix.json` -- {len(gdb.PVT_PROCESS_SECTIONS)} HBT "
      f"sections ({', '.join(gdb.PVT_PROCESS_SECTIONS)}) x {len(gdb.PVT_TEMP_C)} ambient "
      f"temperatures ({'/'.join(f'{t:g}' for t in gdb.PVT_TEMP_C)} C) x supply "
      f"{gdb.PVT_VCC_V[0]:g}/{gdb.VCC_NOM_V:g}/{gdb.PVT_VCC_V[2]:g} V "
      f"(nominal +/-10 %) = **{n_cells_declared} cells**, each a full drive sweep "
      f"({len(gdb.drive_grid_match_dbm())} points; {n_units} units in this report). "
      "Drive-crossed declaration: `sim/psat-sweep/psat_sweep_match.pvt-matrix.json`. "
      "`klt corner-matrix` checked the request before submit and the report after "
      f"(committed verdicts: `corners/{rid}/{bench['name']}.corner-matrix-{{request,report}}.json`); "
      f"this report covers {len(cells)} of {n_cells_declared} declared cells.")
    w("- **R/C process sections**: the spec pairs `res_*` / `cap_*` sections with the HBT "
      "corner of the same name, but the DUT's `Rb`, `Cin`, `Cblock` and `Lchoke` are "
      "ideal ngspice elements (`design/netlist/sg13g2-pa.spice`), so **no R/C corner "
      "applies to them**; only the HBT section moves. When real passive models land, "
      "the matrix gains the paired sections.")
    w("- **The bare deck stays nominal-only** (`psat_sweep.request.json`, one cell): the "
      "ratified rows are judged on this matched bench, and the bare deck's flat-50-ohm "
      "harmonic terminations make its P_Out/PAE not comparable with it, so a 27-cell "
      "bare run would evidence no judged row.")
    w(f"- Source: sine EMF behind {RS:g} ohm at {F0 / 1e9:g} GHz; drive = **available** "
      "power A^2/(8 Rs); P_in computed from the measured input V and I (mismatch "
      "counted). Self-heating on (card default `selft=1`); the ambient is the cell's.")
    w(f"- {bench['load_md']} {bench['terminations_md']}")
    w("- PAE = (P_out,f0 - P_in,f0) / P_DC; P_DC = total Vcc supply power, bias "
      "reference included; integrated over an integer number of RF periods "
      "(rectangular-window coherent DFT, step T/400), same extractor as the "
      "nominal-cell records (`sim/known-answer/` checked).")
    w(commit_line(git_sha, dirty))
    w(f"- klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`.")
    w(f"- Backend: `{rep.get('environment', {}).get('backend', 'see report')}`; "
      f"remote: `{_remote_md(rep.get('environment', {}).get('remote', 'n/a'))}`.")
    _remote = rep.get("environment", {}).get("remote")
    if (run_dir and isinstance(_remote, dict)
            and isinstance(_remote.get("fleet"), list)):
        w(f"- {_sharded_run_md(rid, run_dir, bench['name'], request_path, _remote)}")
    w("")
    w("## Per-cell figures and ratified-row verdicts")
    w("")
    w("Worst stress over the cell's whole sweep. A cell whose reduction was refused "
      "has no figure and no verdict rung -- `--` -- which is a finding, not a pass; "
      "the refusal code is in the cell's detail block below. A cell with no "
      "extracted units carries `--` throughout: also a finding, never a pass.")
    w("")
    w("| Cell | Psat dBm | P1dB out dBm | Peak PAE % | S11 large worst dB | "
      "Vce pk V | Vcb pk V | Tj max C | Stress label | Psat | P1dB | PAE | S11 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in cells:
        red, st = c["reduction"], c["worst_stress"]

        def fig(key, fmt, _red=red):
            if _red is None or _red.get(key) is None:
                return "--"
            return fmt.format(_red[key])

        pae_pct = "--" if red is None or red.get("peak_pae") is None else f"{100 * red['peak_pae']:.1f}"
        s11 = "--" if c["s11_large_worst_db"] is None else f"{c['s11_large_worst_db']:.2f}"
        stress_md = "-- | -- | -- | --" if st is None else (
            f"{st['vce_pk_v']:.3f} | {st['vcb_pk_v']:.3f} | {st['tj_max_c']:.1f} "
            f"| {label(st)}")
        w(f"| {_cell_md(c['cell'])} "
          f"| {fig('psat_dbm', '{:.2f}')} | {fig('p1db_out_dbm', '{:.2f}')} "
          f"| {pae_pct} | {s11} "
          f"| {stress_md} | {_rung_psat(red) or '--'} | {_rung_p1db(red) or '--'} "
          f"| {_rung_pae(red) or '--'} | {_rung_s11(c['s11_large_worst_db']) or '--'} |")
    w("")
    w(f"Rungs are against the RATIFIED rows (Target / Fallback): Psat > "
      f"{sr.PSAT_TARGET_DBM:g} / > {sr.PSAT_FALLBACK_DBM:g} dBm; output P1dB > "
      f"{sr.P1DB_TARGET_DBM:g} / > {sr.P1DB_FALLBACK_DBM:g} dBm; peak PAE > "
      f"{100 * sr.PAE_TARGET:g} / > {100 * sr.PAE_FALLBACK:g} %; S11 (large-signal, "
      f"worst drive) < {sr.S11_TARGET_DB:g} / < {sr.S11_FALLBACK_DB:g} dB. The spec "
      "binds the **worst cell** as each row's figure, and a cell outside the model "
      "window is labelled, never passed.")
    if row_summary:
        parts = []
        if row_summary.get("psat_worst_dbm") is not None:
            parts.append(f"Psat {row_summary['psat_worst_dbm']:.2f} dBm")
        if row_summary.get("p1db_worst_dbm") is not None:
            parts.append(f"output P1dB {row_summary['p1db_worst_dbm']:.2f} dBm")
        if row_summary.get("pae_worst") is not None:
            parts.append(f"peak PAE {100 * row_summary['pae_worst']:.1f} %")
        if row_summary.get("s11_large_worst_db") is not None:
            parts.append(f"S11 large {row_summary['s11_large_worst_db']:.2f} dB")
        if parts:
            w("")
            w("**Worst cell over the matrix**: " + " | ".join(parts) + ".")
    w("")
    for ln in _findings_md(cells):
        w(ln)
    w("")
    w("## Per-cell detail")
    w("")
    for c in cells:
        red, st, fl = c["reduction"], c["worst_stress"], c["failures"]
        head = _cell_md(c["cell"])
        w(f"### {head}")
        w("")
        if red:
            w(f"- Psat {red['psat_dbm']:.2f} dBm (sweep end reached: "
              f"{red['psat_at_sweep_end']}); PAE at Psat {100 * (red['pae_at_psat'] or 0):.1f} %; "
              + (f"P1dB out {red['p1db_out_dbm']:.2f} dBm at P_in {red['p1db_in_dbm']:.2f} dBm; "
                 if red.get("p1db_out_dbm") is not None else
                 "P1dB not reached within the sweep (no extrapolation); ")
              + f"linear gain {red['gain_linear_db']:.2f} dB.")
        else:
            e = c["reduction_error"]
            w(f"- Reduction refused: `{e['code']}` -- {e['message']}")
        if st:
            w(f"- Worst stress at Pavail {st['at_p_avail_dbm']:.1f} dBm: Vce pk "
              f"{st['vce_pk_v']:.3f} V, Vcb pk {st['vcb_pk_v']:.3f} V, Vbe pk "
              f"{st['vbe_pk_v']:.3f} V, Ic pk {1e3 * st['ic_pk_a']:.2f} mA/device, Tj max "
              f"{st['tj_max_c']:.1f} C -> **{label(st)}** (outside-window fractions "
              f"Vce/Vbe/Ic/Tj {100 * st['frac_vce_outside']:.0f}/"
              f"{100 * st['frac_vbe_outside']:.0f}/{100 * st['frac_ic_outside']:.0f}/"
              f"{100 * st['frac_tj_outside']:.0f} %).")
        w(f"- {len(c['points'])} of {len(c['points']) + len(fl)} units extracted"
          + (f"; {len(fl)} could not be: " + ", ".join(sorted({f_['code'] for f_ in fl})) + "."
             if fl else "."))
        w("")
    w(f"Device stress limits and labels per `sim/lib/device_limits.py`: BVCEO(min) "
      f"{BVCEO_MIN:.1f} V, BVCBO(min) {BVCBO_MIN:.1f} V (process spec); window V_CE "
      f"{VCE_WIN[0]:.1f}-{VCE_WIN[1]:.1f} V, V_BE {VBE_WIN[0]:.2f}-{VBE_WIN[1]:.2f} V, "
      f"I_C < {1e3 * IC_MAX_PER_DEVICE:g} mA/device, Tj <= {TJ_MAX:g} C (model card). "
      "The 125 C cells exceed the card's temperature window by construction "
      "(ambient alone is at the window top, before self-heating) and are labelled "
      "**OUTSIDE MODEL WINDOW**, never passed. Per-point stress lives in this "
      f"record's JSON sidecar (`records/{rid}.json`) and the raw corners under "
      f"`corners/{rid}/`.")
    w("")
    if n_failed:
        w(f"{n_failed} of {n_units} units could not be extracted (listed per cell above); "
          "they are excluded from that cell's reduction and never dropped silently.")
        w("")
    print("\n".join(o))
    return 0 if any(c["points"] for c in cells) else 1


def main(argv):
    variant, rid, git_sha, dirty, klt_v, ng_v, report_path, out_json = argv[1:9]
    bench = gdb.psat_bench(variant)       # raises ValueError on an unknown variant
    net = bench["network"]
    rep = json.load(open(report_path))
    run_dir = os.path.dirname(os.path.abspath(report_path))
    points, failures = [], []
    for c in rep["corners"]:
        cid = c.get("corner_id", "?")
        if c.get("status") != "pass":
            # The cell is carried on the failure (the report names process/
            # temperature/supply even for an errored corner), so a cell none of
            # whose units produced figures still appears below -- as a finding, never
            # as a silent absence.
            failures.append({"corner_id": cid, "code": f"KLT_STATUS_{c.get('status')}",
                             "cell": {"process": c.get("process", "?"),
                                      "temperature_c": float(c.get("temperature_c", 27)),
                                      "vcc": float((c.get("supply_v") or {}).get(
                                          "vcc", gdb.VCC_NOM_V))}})
            continue
        amp = c["supply_v"]["vamp"]
        pav = amp * amp / (8 * RS)
        cell = {"process": c.get("process", "?"),
                "temperature_c": float(c.get("temperature_c", 27)),
                "vcc": float(c["supply_v"].get("vcc", gdb.VCC_NOM_V))}
        try:
            t, s = rx.load_klt_waveform(c["artifacts"]["waveform"])
            # P_out and the harmonics from the LOAD's own V and I (spec: "DFT of the
            # load voltage/current"), whichever nodes this bench puts them on.
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
    # Group by PVT cell. One cell -> the nominal-cell record this bench has
    # always written; several -> the matrix record (issue #173): one reduction
    # per cell, never one reduction over the whole report (points from
    # different cells are not one drive sweep).
    cell_order, by_cell = [], {}
    for p in points:
        key = (p["cell"]["process"], p["cell"]["temperature_c"], p["cell"]["vcc"])
        if key not in by_cell:
            by_cell[key] = {"cell": p["cell"], "points": [], "failures": []}
            cell_order.append(key)
        by_cell[key]["points"].append(p)
    for f in failures:
        key = (f["cell"]["process"], f["cell"]["temperature_c"], f["cell"]["vcc"])
        if key not in by_cell:
            by_cell[key] = {"cell": f["cell"], "points": [], "failures": []}
            cell_order.append(key)
        by_cell[key]["failures"].append(f)

    if len(cell_order) > 1:
        return render_matrix(variant, rid, git_sha, dirty, klt_v, ng_v, bench, net, rep,
                             cell_order, by_cell, out_json,
                             run_dir=run_dir)

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
    w(commit_line(git_sha, dirty))
    w(f"- klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`; "
      "known-answer check of the extractor: `sim/known-answer/` (run before DUT records).")
    w(f"- Backend: `{rep.get('environment', {}).get('backend', 'see report')}`; "
      f"remote job: `{_remote_md(rep.get('environment', {}).get('remote', 'n/a'))}`.")
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
          "**collector**, not `RFOUT`, sees a real Ropt. That impedance includes the "
          "series `Cblock` but not the DUT's shunt `Lchoke` at `COLL`; the numerical "
          "case for leaving `Lchoke` alone, at the original design point, is issue "
          "#116. Both are ideal, so neither has a self-resonance.")
        w(f"- Analytic ceiling for this load line: {net['nx_total']} Nx x "
          f"{ll['pout_per_nx_w']:g} W = {net['pout_ceiling_w']:g} W = "
          f"**{rx.dbm(net['pout_ceiling_w']):.2f} dBm**. Hand arithmetic over the load-line "
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
        g = rx.dbm(p["p_out_w"]) - rx.dbm(p["p_in_w"]) if p["p_out_w"] > 0 and p["p_in_w"] > 0 else float("nan")
        w(f"| {p['p_avail_dbm']:.1f} | {rx.dbm(p['p_in_w']):.2f} | {rx.dbm(p['p_out_w']):.2f} | {g:.2f} | "
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
        w("**The self-heating thermal node this `Tj max C` column comes from is "
          "known-answer checked** in `sim/known-answer-thermal/` (issue #115; record "
          "`20261114-205927-00b692a`): injected and device-driven power read back through "
          "the card's `rth` within 0.01 % / 0.1 %, the 4-terminal node this bench probes "
          "hierarchically (`v(x<inst>.t)`) agrees with the 5-terminal one to 1e-14 V, and "
          "a `selft=0` control fails its grading as designed. The check's verdict is "
          "scoped to the DC `rth` network and the device-to-node power path -- **not** "
          "`cth` or a thermal time constant; `sim/known-answer/` separately validates the "
          "large-signal extractor (power, P_DC, harmonics). Read the `Tj` column as "
          "checked within that scope.")
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
