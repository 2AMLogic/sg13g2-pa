"""`psat_record.py` reduces the deck it was told to, through that deck's own nodes.

The psat bench has two variants (issue #116): the default `bare` deck, which drives a
flat 50 ohm from `RFOUT`, and `match`, which puts an ideal off-chip L-section between
`RFOUT` and that load. They do not differ only in a filename -- the matched deck moves
BOTH extraction nodes:

* **`P_out`/H2/H3.** In the bare deck `Vlsense` is a 0 V source directly on `out`, so
  `v(out) * i(vlsense)` is the load power. With a network in between, `v(out)` and the
  load current are at different nodes and their product is not a power at all.
* **Per-device `I_C`.** `stress()` takes it as `(i(Lchoke) - <boundary>) / N_UNITS`,
  which is KCL at `COLL` only when `<boundary>` is `Cblock`'s current. In the bare deck
  the load branch *is* that current; through an L-section the shunt capacitor takes part
  of it, so the load current under-reports every `I_C` **silently** -- no KeyError, no
  ExtractError, just a wrong `Ic pk mA` column and a wrong `frac_ic_outside`.

Neither failure raises anything, so the tests below are what catch them: the synthetic
waveform deliberately gives every candidate trace a DIFFERENT amplitude, so a record
reduced through the wrong node produces a different number rather than the same one.
No simulator or PDK is needed.
"""
import importlib.util
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PSAT = _load("_psat_record_e2e", "sim/psat-sweep/psat_record.py")

# A steady sinusoid, long enough and fine enough for rf_extract (>= 100 periods,
# step <= T/200). Amplitudes are deliberately all different -- see the module docstring.
F0 = gdb.F0_HZ
N_PER = 120
PER_STEP = 400
V_OUT_A = 2.0          # v(out), the chip-boundary voltage (bare deck's load node)
V_OUTL_A = 1.2         # v(outl), the 50 ohm resistor's own node (matched deck)
I_LOAD_A = 0.030       # i(vlsense), the load current
I_BOUND_A = 0.080      # i(vbsense), the chip-boundary current -- distinctly larger
I_CHOKE = 0.200        # i(l.xdut.lchoke), the DC feed
VCC = gdb.VCC_NOM_V
I_VCC = -0.210         # ngspice sign: delivered = -i(vcc)


def _waveform(path):
    """A settled steady-state trace carrying every node both variants may ask for."""
    n = N_PER * PER_STEP + 1
    t = np.arange(n) / (F0 * PER_STEP)
    s = np.sin(2 * math.pi * F0 * t)
    traces = {
        "v(out)": V_OUT_A * s,
        "v(outl)": V_OUTL_A * s,
        "v(in)": 0.1 * s,
        "v(vcc)": np.full(n, VCC),
        "v(amp)": np.full(n, 1.0),
        "i(vbsense)": I_BOUND_A * s,
        "i(vlsense)": I_LOAD_A * s,
        "i(vcc)": np.full(n, I_VCC),
        "i(bs)": -0.002 * s,
        "i(l.xdut.lchoke)": np.full(n, I_CHOKE),
        "v(xdut.coll)": VCC + 0.5 * s,
        "v(xdut.vb)": np.full(n, 0.85),
        "v(xdut.xq1.t)": np.full(n, 0.6),
    }
    names = ["time"] + list(traces)
    cols = [t] + list(traces.values())
    doc = {"variables": [{"name": nm} for nm in names],
           "points": np.column_stack(cols).tolist()}
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return traces


def _render(tmp_path, variant, remote="n/a"):
    """Run psat_record.main for one variant; returns (markdown, json)."""
    wav = os.path.join(tmp_path, "waveform.raw.json")
    _waveform(wav)
    report = {
        "environment": {"backend": "test", "remote": remote},
        "corners": [{
            "corner_id": "hbt_typ/vamp=1.000_vcc=0.800V/27C", "status": "pass",
            "supply_v": {"vamp": 1.0, "vcc": VCC}, "temperature_c": 27,
            "artifacts": {"waveform": wav},
        }],
    }
    rep_path = os.path.join(tmp_path, "report.json")
    out_json = os.path.join(tmp_path, f"rec-{variant}.json")
    with open(rep_path, "w") as fh:
        json.dump(report, fh)

    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = PSAT.main(["psat_record.py", variant, f"id-{variant}", "deadbee", "0",
                        "klt 0.9.1", "ngspice-47", rep_path, out_json])
    # One point only, so reduce_sweep cannot find a linear region; the record still
    # renders (with `Reduction refused`) and the per-point and stress tables are what
    # these tests read.
    assert rc == 0
    return buf.getvalue(), json.load(open(out_json))


# --- the node that carries per-device I_C (AC 10) --------------------------


@pytest.mark.parametrize("variant,sense_amp", [("bare", I_LOAD_A), ("match", I_BOUND_A)])
def test_ic_is_taken_from_the_variants_own_boundary_trace(tmp_path, variant, sense_amp):
    """`(i(Lchoke) - <this variant's boundary>) / N_UNITS`, and not the other one's."""
    _md, doc = _render(str(tmp_path), variant)
    st = doc["points"][0]["stress"]
    want = (I_CHOKE + sense_amp) / gdb.output_array()[0]
    assert st["ic_pk_a"] == pytest.approx(want, rel=1e-6)
    # ...and it is NOT what the other variant's node would have given. This is the
    # assertion that fails if the matched deck's I_C silently keeps using the load branch.
    other = (I_CHOKE + (I_BOUND_A if variant == "bare" else I_LOAD_A)) / gdb.output_array()[0]
    assert st["ic_pk_a"] != pytest.approx(other, rel=1e-3)


# --- the node that carries P_out and the harmonics ------------------------


@pytest.mark.parametrize("variant,v_amp", [("bare", V_OUT_A), ("match", V_OUTL_A)])
def test_p_out_is_extracted_from_the_variants_own_load_node(tmp_path, variant, v_amp):
    """P_out = <V, I> at the LOAD. The matched deck's V is the resistor's, not RFOUT's."""
    _md, doc = _render(str(tmp_path), variant)
    # Fundamental power of two co-phase sinusoids: A_v * A_i / 2.
    assert doc["points"][0]["p_out_w"] == pytest.approx(v_amp * I_LOAD_A / 2, rel=1e-6)


def test_an_unknown_variant_is_refused_rather_than_defaulted(tmp_path):
    with pytest.raises(ValueError, match="unknown psat variant"):
        _render(str(tmp_path), "matched")


# --- the prose the record must and must not carry -------------------------


COMMITTED_BARE = os.path.join(
    REPO, "sim/psat-sweep/records/20261107-125209-93cf5ae.md")


def test_the_bare_records_load_and_terminations_line_has_not_moved(tmp_path):
    """Formatting it from the bench must render the committed wording byte-for-byte.

    `20261107-125209-93cf5ae.md` is append-only evidence and is never re-rendered, so
    this compares against its committed line rather than retyping the sentence.
    """
    md, _doc = _render(str(tmp_path), "bare")
    committed = [ln for ln in open(COMMITTED_BARE).read().splitlines()
                 if ln.startswith("- Load:")]
    assert len(committed) == 1
    assert [ln for ln in md.splitlines() if ln.startswith("- Load:")] == committed


def test_the_bare_record_still_names_its_own_deck(tmp_path):
    md, _doc = _render(str(tmp_path), "bare")
    assert "Bench `sim/psat-sweep/psat_sweep.spice`" in md
    assert "psat_sweep_match" not in md
    # ...and does not grow the matched record's sections.
    assert "## Output network and the chip boundary" not in md


def test_the_matched_record_states_the_terminations_and_refuses_the_comparison(tmp_path):
    """AC 8."""
    md, _doc = _render(str(tmp_path), "match")
    net = gdb.match_network()
    assert "Bench `sim/psat-sweep/psat_sweep_match.spice`" in md
    # It must NOT claim the labelled ideal-50-ohm default.
    assert "(the default, labelled; a flat resistor)" not in md
    assert "no longer the labelled ideal-50-ohm" in md
    # Both impedances, at f0 / 2 f0 / 3 f0, at BOTH nodes.
    assert "Into the network at `RFOUT`" in md and "Seen by `COLL` through `Cblock`" in md
    for lab, _f, z_rfout, z_coll in gdb.match_impedances(net):
        assert f"{z_rfout.real:.3f} {z_rfout.imag:+.3f}j ohm" in md
        assert f"{z_coll.real:.3f} {z_coll.imag:+.3f}j ohm" in md
    # And the explicit refusal to compare with the bare record.
    assert "20261107-125209-93cf5ae" in md
    assert "are not compared" in md
    assert "not** presented as an improvement" in md
    assert "different benches, not two measurements of one quantity" in md


def test_the_matched_record_states_the_chip_boundary_and_the_ideality(tmp_path):
    """AC 3 and AC 11."""
    md, _doc = _render(str(tmp_path), "match")
    assert "chip boundary is `RFOUT`" in md
    # which elements are on which side
    assert "`Lchoke`, `Cblock`, `Cin`" in md
    assert "`Vbsense`, `Lmatch`" in md
    assert "ideal and lossless" in md.lower()
    assert "no inductor model is used" in md.lower()
    assert "DR 0001 D-1" in md
    assert "Fallback" in md and "unevidenced" in md
    assert "not counted as the chip's" in md
    assert "not a pass/fail claim" in md.lower()


def test_the_matched_record_derives_ropt_and_cites_the_load_line_row(tmp_path):
    """AC 2: the number and its provenance, not a pasted constant."""
    md, doc = _render(str(tmp_path), "match")
    net = gdb.match_network()
    assert f"Ropt = {net['ropt_ohm']:.4f} ohm at the collector" in md
    assert net["loadline_record"] in md
    assert "swing_mode saturated" in md
    # It says, in the record, that the recommended array's figure was not used.
    assert "2.5157" in md and "106-Nx" in md
    # The derivation is carried in the JSON too, so the record is checkable.
    assert doc["output_network"]["ropt_ohm"] == pytest.approx(net["ropt_ohm"], rel=1e-12)
    assert doc["variant"] == "match"
    assert doc["bench"] == "psat_sweep_match"
    # The choke is described by what the arithmetic covers, not by a reactance
    # copied from the original design point (issue #187).
    assert "series `Cblock` but not the DUT's shunt `Lchoke`" in md
    assert "issue #116" in md
    assert "+j1534" not in md and "0.12 %" not in md


def test_the_matched_record_states_the_tj_check_and_its_scope(tmp_path):
    """AC: the self-heating node is known-answer checked (issue #115), scope stated."""
    md, _doc = _render(str(tmp_path), "match")
    assert "#115" in md
    assert "known-answer checked" in md
    assert "`sim/known-answer-thermal/`" in md
    assert "20261114-205927-00b692a" in md   # the record that licensed the wording
    assert "v(x<inst>.t)" in md              # the node this record actually reads
    assert "Tj max C" in md                  # the column it qualifies is still there
    assert "**not** `cth`" in md             # the verdict's scope
    assert "as checked within that scope" in md


# --- the Conditions bullet must stay readable when the run is sharded ---------


def test_a_single_job_remote_block_is_printed_unchanged():
    """The bare bench does not shard, and its record's wording must not move."""
    one = {"provider": "aws-batch-fleet", "job_id": "klt-sim-abc", "region": "us-east-1"}
    assert PSAT._remote_md(one) is one
    assert PSAT._remote_md("n/a") == "n/a"
    assert PSAT._remote_md({"fleet": []}) == {"fleet": []}


def test_a_sharded_remote_block_is_summarized_not_dumped():
    """`remote.hosts: 10` returns ten full worker captures -- ~15 kB in one bullet."""
    shard = {
        "provider": "aws-batch-fleet", "region": "us-east-1",
        "instance_type": "m7i.4xlarge", "lifecycle": "spot",
        "runner_klt_version": "0.9.0", "elapsed_seconds": 34,
        "worker_environment": {"simulator": {"version_banner": "x" * 2000}},
    }
    fleet = [dict(shard, job_id=f"klt-sim-{k:04x}", elapsed_seconds=30 + k)
             for k in range(10)]
    out = PSAT._remote_md({"fleet": fleet})
    assert isinstance(out, str)
    assert "10 fleet shards" in out
    assert "elapsed 30-39 s" in out
    assert "klt-sim-0000" in out and "klt-sim-0009" in out   # every job id is named
    assert "m7i.4xlarge" in out and "us-east-1" in out
    # the point: the worker capture is NOT inlined
    assert "version_banner" not in out and "x" * 100 not in out
    assert len(out) < 800
    # and it says where the full capture lives
    assert "report.json" in out


def test_the_matched_record_summarizes_its_sharded_backend(tmp_path):
    """The matched bench shards on the batch fleet (`request.remote.hosts`); its
    record's Conditions bullet must carry the one-line summary, not the full
    per-shard environment captures."""
    fleet = [{"provider": "aws-batch-fleet", "job_id": f"klt-sim-{k:04x}",
              "region": "us-east-1", "instance_type": "m7i.4xlarge",
              "lifecycle": "spot", "runner_klt_version": "0.9.0",
              "elapsed_seconds": 30 + k} for k in range(3)]
    md, _doc = _render(str(tmp_path), "match", remote={"fleet": fleet})
    assert "3 fleet shards" in md
    assert "elapsed 30-32 s" in md
    assert "klt-sim-0000" in md and "klt-sim-0002" in md
    # the point: the worker captures are NOT inlined into the markdown, and the
    # summary says where the full capture lives
    assert "{'provider'" not in md and "'job_id'" not in md
    assert "full per-shard environment capture" in md


# --- findings point at the design iteration that tracks them (issue #194) ----


def _sweep_waveform(path, pin_w, pout_w):
    """A settled steady-state trace for one drive point of a matrix cell.

    `v(in)`/`i(bs)` carry ``pin_w`` co-phase, `v(outl)`/`i(vlsense)` carry
    ``pout_w``; the stress traces are constants (no findings test grades them).
    Amplitudes come from the powers, so a cell's rungs are set by the spec's
    own arithmetic on numbers the test chooses, not by retyped voltages.
    """
    n = N_PER * PER_STEP + 1
    t = np.arange(n) / (F0 * PER_STEP)
    s = np.sin(2 * math.pi * F0 * t)
    vin = 2 * pin_w / 0.002          # vin * 0.002 / 2 = pin_w
    voutl = 2 * pout_w / 0.030       # voutl * 0.030 / 2 = pout_w
    traces = {
        "v(out)": 0.5 * s,
        "v(outl)": voutl * s,
        "v(in)": vin * s,
        "v(vcc)": np.full(n, VCC),
        "v(amp)": np.full(n, 1.0),
        "i(vbsense)": 0.080 * s,
        "i(vlsense)": 0.030 * s,
        "i(vcc)": np.full(n, I_VCC),
        "i(bs)": -0.002 * s,
        "i(l.xdut.lchoke)": np.full(n, I_CHOKE),
        "v(xdut.coll)": VCC + 0.5 * s,
        "v(xdut.vb)": np.full(n, 0.85),
        "v(xdut.xq1.t)": np.full(n, 0.6),
    }
    names = ["time"] + list(traces)
    cols = [t] + list(traces.values())
    doc = {"variables": [{"name": nm} for nm in names],
           "points": np.column_stack(cols).tolist()}
    with open(path, "w") as fh:
        json.dump(doc, fh)


def _findings_render(tmp_path, specs, remote="n/a", report_dir=None):
    """Run psat_record.main over a multi-cell report -- the matrix path.

    Each spec: ``proc``/``temp``/``vcc``; ``pins_dbm`` (drive points, P_in at
    the DUT input); ``gains_db`` per drive point (equal on the 3 lowest points
    -> a linear region reduce_sweep accepts); ``s11_ratio`` = P_in/P_avail at
    every point (sets the S11 rung; close to 1 is a good match); ``status``
    makes the whole cell one that did not simulate.
    """
    corners = []
    for si, sp in enumerate(specs):
        for pi, pin_dbm in enumerate(sp["pins_dbm"]):
            cid = f"{sp['proc']}/pt{pi}"
            if sp.get("status", "pass") != "pass":
                corners.append({"corner_id": cid, "process": sp["proc"],
                                "temperature_c": sp["temp"],
                                "supply_v": {"vamp": 1.0, "vcc": sp["vcc"]},
                                "status": sp["status"]})
                continue
            pin_w = 10 ** (pin_dbm / 10) / 1000
            pout_w = pin_w * 10 ** (sp["gains_db"][pi] / 10)
            vamp = math.sqrt(8 * gdb.RS_OHM * pin_w / sp["s11_ratio"])
            wav = os.path.join(str(tmp_path), f"mw{si}-{pi}.json")
            _sweep_waveform(wav, pin_w, pout_w)
            corners.append({"corner_id": cid, "process": sp["proc"],
                            "temperature_c": sp["temp"],
                            "supply_v": {"vamp": vamp, "vcc": sp["vcc"]},
                            "status": "pass",
                            "artifacts": {"waveform": wav}})
    report = {"environment": {"backend": "test", "remote": remote},
              "corners": corners}
    rep_dir = report_dir or str(tmp_path)
    rep_path = os.path.join(rep_dir, "psat_sweep_match.report.json")
    out_json = os.path.join(str(tmp_path), "rec-matrix.json")
    with open(rep_path, "w") as fh:
        json.dump(report, fh)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = PSAT.main(["psat_record.py", "match", "rid-matrix", "deadbee", "0",
                        "klt 0.9.1", "ngspice-47", rep_path, out_json])
    assert rc == 0
    return buf.getvalue(), json.load(open(out_json))


ALL_MET = {"proc": "hbt_typ", "temp": 27.0, "vcc": 0.8,
           "pins_dbm": [-20, -19, -18, -17], "gains_db": [36] * 4,
           "s11_ratio": 0.95}


def test_the_matrix_record_links_each_finding_to_its_tracker(tmp_path):
    """Mixed verdicts: every row below its rung names its tracker, a met row
    acquires no link, and a cell that did not simulate is a recorded finding
    with a tracker, not a silent absence (issue #194)."""
    specs = [
        # all-met cell (Psat +19 dBm, PAE 47 %, S11 -13 dB): no finding may name it
        dict(ALL_MET),
        # compressing cell: P1dB reached and missed, Psat/PAE missed, S11 missed
        {"proc": "hbt_wcs", "temp": 27.0, "vcc": 0.72,
         "pins_dbm": [-20, -19, -18, -17.5, -17],
         "gains_db": [20, 20, 20, 19.4, 18.8], "s11_ratio": 0.5},
        # single drive point: reduction refused, S11 met
        {"proc": "hbt_bcs", "temp": -40.0, "vcc": 0.72,
         "pins_dbm": [-10], "gains_db": [20], "s11_ratio": 0.95},
        # did not simulate at all
        {"proc": "hbt_bcs", "temp": 125.0, "vcc": 0.8,
         "pins_dbm": [-10, -11], "gains_db": [20, 20], "s11_ratio": 0.5,
         "status": "error"},
    ]
    md, _doc = _findings_render(tmp_path, specs)
    sec = md.split("## Findings and their trackers", 1)[1].split("## Per-cell detail", 1)[0]
    assert ("Input match (large-signal S11, worst drive): 1 cell below the Fallback "
            "rung (1 `missed`) -- design iteration #172." in sec)
    for row in ("Psat", "Output P1dB", "Peak PAE"):
        assert (f"{row}: 1 cell below the Fallback rung (1 `missed`) "
                "-- design iteration #192." in sec)
    assert ("2 sweep units did not simulate (`KLT_STATUS_error`) "
            "-- design iteration #188." in sec)
    assert ("1 cell refused a reduction (`SWEEP_TOO_SHORT`) "
            "-- no design-iteration tracker." in sec)
    # the all-met cell is named nowhere in the findings section
    assert "hbt_typ" not in sec
    # ...and the did-not-simulate cell renders a full-width `--` table row (13
    # columns, like every other row), not a shifted short one
    err_row = [ln for ln in md.splitlines() if ln.startswith("| `hbt_bcs` / 125 C / 0.8 V")][0]
    assert err_row.count("|") == 14


def test_an_all_met_matrix_record_links_nothing(tmp_path):
    md, _doc = _findings_render(tmp_path, [dict(ALL_MET),
                                         dict(ALL_MET, proc="hbt_wcs", vcc=0.88)])
    sec = md.split("## Findings and their trackers", 1)[1].split("## Per-cell detail", 1)[0]
    assert "No verdict falls below its rung" in sec
    assert "#172" not in sec and "#188" not in sec and "#192" not in sec


# --- a resumed sharded run describes the whole run, not the last round ------


def _write_round_stderr(path, submitted, mentions=()):
    """A round's submit stderr: `submitting` lines name what the round sent;
    bare status mentions name nothing (a mention is not a launch)."""
    lines = [f"klt: batch job {j} submitting to s3://<bucket>/jobs/{j}" for j in submitted]
    lines += [f"klt: batch job {j} status RUNNING (attempt 2)" for j in mentions]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_receipt(run_dir, bench, job, launched, completed=None):
    """The launch evidence for one shard: a batch receipt."""
    d = os.path.join(run_dir, bench, job)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"batch-receipt-{job}.json"), "w") as fh:
        json.dump({"job_id": job, "launched_at": launched, "completed_at": completed,
                   "state": "done" if completed else None}, fh)


def _run_dir(tmp_path, declared=None):
    run = os.path.join(str(tmp_path), "corners", "rid")
    os.makedirs(run, exist_ok=True)
    req = os.path.join(run, "psat_sweep_match.request.json")
    if declared is not None:
        with open(req, "w") as fh:
            json.dump({"remote": {"hosts": declared}}, fh)
    return run, req


def test_a_resumed_sharded_run_reports_whole_run_provenance(tmp_path):
    """Declared 10 per attempt; initial submits 5 (2 launch), resume1 submits 5
    (3 launch, one never completes); a 2 h gap sits between the rounds. The
    provenance must state per-round counts, the whole-run span and the
    final-round span independently (issue #194)."""
    run, req = _run_dir(tmp_path, declared=10)
    first = [f"klt-sim-{k:04x}" for k in range(5)]
    second = [f"klt-sim-{k:04x}" for k in range(5, 10)]
    _write_round_stderr(os.path.join(run, "psat_sweep_match.stderr"),
                        first, mentions=[first[0], second[0]])    # repeats: no launch
    _write_round_stderr(os.path.join(run, "psat_sweep_match.resume1.stderr"),
                        second, mentions=[second[0]])
    _write_receipt(run, "psat_sweep_match", first[0],
                   "2026-11-21T10:00:00Z", "2026-11-21T10:05:00Z")
    _write_receipt(run, "psat_sweep_match", first[1],
                   "2026-11-21T10:00:30Z", "2026-11-21T10:05:30Z")
    _write_receipt(run, "psat_sweep_match", second[0],
                   "2026-11-21T12:00:00Z", "2026-11-21T12:05:00Z")
    _write_receipt(run, "psat_sweep_match", second[1],
                   "2026-11-21T12:00:05Z", "2026-11-21T12:05:05Z")
    _write_receipt(run, "psat_sweep_match", second[2],
                   "2026-11-21T12:00:10Z", None)                  # never completed
    out = PSAT._sharded_run_md("rid", run, "psat_sweep_match", req,
                               {"fleet": [{"job_id": second[0]}],
                                "unlaunched_shards": 65, "resumable": True})
    assert "declares 10 shards per attempt" in out
    assert "initial: 2 launched of 5 submitted" in out
    assert "resume1: 3 launched of 5 submitted" in out
    assert "5 distinct job ids with launch receipts" in out
    assert "first evidenced launch 2026-11-21T10:00:00Z" in out
    assert "last evidenced completion 2026-11-21T12:05:05Z" in out
    assert "7505 s" in out                      # 10:00:00 -> 12:05:05, gap included
    assert "launch-to-completion" in out        # not submit-to-terminal
    assert "1 receipt records no completion" in out
    assert "round-local" in out and "`unlaunched_shards`" in out and "`resumable`" in out


def test_missing_provenance_evidence_is_named_not_papered_over(tmp_path):
    run, _req = _run_dir(tmp_path)      # no request, no stderr, no receipts
    out = PSAT._sharded_run_md("rid", run, "psat_sweep_match",
                               os.path.join(run, "nope.request.json"),
                               {"fleet": [{"job_id": "klt-sim-0000"}]})
    assert "was not found" in out                     # the request
    assert "no submit stderr found" in out            # the rounds
    assert "no launch receipts found" in out          # the launches


def test_a_sharded_run_without_resumes_says_so(tmp_path):
    run, req = _run_dir(tmp_path, declared=3)
    _write_round_stderr(os.path.join(run, "psat_sweep_match.stderr"),
                        ["klt-sim-0000", "klt-sim-0001"])
    _write_receipt(run, "psat_sweep_match", "klt-sim-0000",
                   "2026-11-21T10:00:00Z", "2026-11-21T10:01:00Z")
    out = PSAT._sharded_run_md("rid", run, "psat_sweep_match", req, {"fleet": []})
    assert "single submit round" in out
    assert "initial: 1 launched of 2 submitted" in out


def test_the_matrix_record_carries_the_sharded_run_provenance(tmp_path):
    run, _req = _run_dir(tmp_path, declared=3)
    _write_round_stderr(os.path.join(run, "psat_sweep_match.stderr"),
                        ["klt-sim-0000", "klt-sim-0001"])
    _write_receipt(run, "psat_sweep_match", "klt-sim-0000",
                   "2026-11-21T10:00:00Z", "2026-11-21T10:01:00Z")
    fleet = [{"provider": "aws-batch-fleet", "job_id": "klt-sim-0000",
              "region": "us-east-1", "instance_type": "m7i.4xlarge",
              "lifecycle": "spot", "runner_klt_version": "0.9.0",
              "elapsed_seconds": 30}]
    md, _doc = _findings_render(tmp_path, [dict(ALL_MET),
                                         dict(ALL_MET, proc="hbt_wcs", s11_ratio=0.5)],
                              remote={"fleet": fleet}, report_dir=run)
    assert "round-local" in md
    assert "Sharded run provenance" in md
    assert "declares 3 shards per attempt" in md
    assert "initial: 1 launched of 2 submitted" in md
    assert "single submit round" in md


def test_the_round_local_wall_clock_uses_launch_stamps_when_submit_stamps_are_absent():
    """A fleet block with no `client_submitted_at` still gets a span -- from its
    launch stamp, labelled as such, never silently narrower (issue #194)."""
    fleet = [{"provider": "aws-batch-fleet", "job_id": "klt-sim-0000",
              "client_submitted_at": None,
              "client_launched_at": "2026-11-21T15:54:31Z",
              "client_status_terminal_at": "2026-11-21T16:00:31Z",
              "elapsed_seconds": 30}]
    out = PSAT._remote_md({"fleet": fleet})
    assert "360 s" in out
    assert "first submit or launch" in out
    assert "round-local" in out


# The #193 run's own committed evidence, re-derived (issue #194 test plan):
# the request, the eight stderr logs, the 747 receipts and the final report
# are all in-tree, so the provenance statements below are checkable forever.
COMMITTED_MATCH_RUN = os.path.join(
    REPO, "sim/psat-sweep/corners/20261121-003533-b2746d0-match")


def test_the_committed_matched_run_provenance_matches_its_artifacts():
    rep = json.load(open(os.path.join(COMMITTED_MATCH_RUN, "psat_sweep_match.report.json")))
    remote = rep["environment"]["remote"]
    out = PSAT._sharded_run_md("20261121-003533-b2746d0-match", COMMITTED_MATCH_RUN,
                               "psat_sweep_match",
                               os.path.join(REPO, "sim/psat-sweep",
                                            "psat_sweep_match.request.json"),
                               remote)
    assert "declares 261 shards per attempt" in out
    assert "8 attempts evidenced" in out
    assert "initial: 61 launched of 293 submitted" in out
    assert "resume1: 99 launched of 261 submitted" in out
    assert "resume7: 38 launched of 38 submitted" in out
    assert "747 distinct job ids with launch receipts" in out
    assert "2026-11-21T00:37:50Z" in out and "2026-11-21T16:02:07Z" in out
    assert "55457 s" in out and "34 receipt records no completion" in out
    assert "launch-to-completion" in out
    loc = PSAT._remote_md(remote)
    assert "39 fleet shards in this report's final round (round-local)" in loc
    assert "478 s" in loc


# --- the two facts this record used to retype (issue #119) -----------------


def test_the_commit_bullet_is_provenance_commit_lines_own_output(tmp_path):
    """The record states its commit the way every other sim/ record does.

    `_render` passes git-sha `deadbee` with dirty `0`, so the bullet is exactly
    what `provenance.commit_line` returns for that pair -- not a second format
    that happens to carry the same sha.
    """
    import provenance
    md, _doc = _render(str(tmp_path), "match")
    assert provenance.commit_line("deadbee", "0") in md.splitlines()
    assert "- Repo `" not in md          # the retyped bullet is gone for good


def test_the_record_shares_the_watts_to_dbm_conversion_with_the_reducer(tmp_path):
    """One conversion per record: the table columns and the headline Psat agree.

    `reduce_sweep` converts through `rf_extract.dbm`; the per-point table used to
    convert through a local copy in psat_record. Asserting the module no longer
    carries its own is what keeps the two from drifting apart by a rounding rule.
    """
    import rf_extract as rx
    assert not hasattr(PSAT, "dbm"), "psat_record must not define its own dbm()"
    md, _doc = _render(str(tmp_path), "match")
    # the one drive point's P_in, as the table prints it, straight from the library
    p_in_w = _doc["points"][0]["p_in_w"]
    assert f"| {rx.dbm(p_in_w):.2f} |" in md


# --- the PVT matrix record (issue #173) ------------------------------------
#
# A multi-cell report renders per cell: one reduction per cell (never one over
# points from different cells), the provisional banner, per-cell verdict rungs
# against the RATIFIED rows, and the 125 C window label. The same synthetic
# waveform serves every corner -- its P_out/P_in are constant, so each cell's
# reduction is a flat sweep (linear region found, P1dB not reached), which is
# enough to exercise the grouping and the grading.


def _matrix_render(tmp_path):
    tmp = str(tmp_path)
    wav = os.path.join(tmp, "waveform.raw.json")
    _waveform(wav)
    corners = []
    for proc, temp, vcc in (("hbt_typ", 27.0, 0.8), ("hbt_wcs", 125.0, 0.72)):
        for k in range(6):
            vamp = 0.01 + 0.001 * k
            corners.append({
                "corner_id": gdb.klt_corner_id(proc, {"vamp": vamp, "vcc": vcc}, temp),
                "process": proc, "temperature_c": temp, "status": "pass",
                "supply_v": {"vamp": vamp, "vcc": vcc},
                "artifacts": {"waveform": wav},
            })
    report = {"environment": {"backend": "test", "remote": "n/a"}, "corners": corners}
    rep_path = os.path.join(tmp, "report.json")
    out_json = os.path.join(tmp, "rec.json")
    with open(rep_path, "w") as fh:
        json.dump(report, fh)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = PSAT.main(["psat_record.py", "match", "rid", "deadbee", "0",
                        "klt 0.9.1", "ngspice-47", rep_path, out_json])
    return rc, buf.getvalue(), json.load(open(out_json))


def test_a_matrix_report_reduces_per_cell_and_labels_it_provisional(tmp_path):
    rc, md, doc = _matrix_render(tmp_path)
    assert rc == 0
    assert doc["pvt_matrix"] is True
    assert len(doc["cells"]) == 2
    for cell in doc["cells"]:
        assert len(cell["points"]) == 6          # the other cell's points are not in it
        assert cell["reduction"] is not None      # one reduction PER CELL
    assert doc["cells"][0]["cell"]["process"] == "hbt_typ"
    assert doc["cells"][1]["cell"] == {"process": "hbt_wcs", "temperature_c": 125.0,
                                       "vcc": 0.72}
    assert "PROVISIONAL: Supply row DRAFT" in md
    assert "2 of 27 declared cells" in md
    # The 27 C cell and the 125 C cell are separate detail blocks.
    assert "`hbt_typ` / 27 C / 0.8 V" in md
    assert "`hbt_wcs` / 125 C / 0.72 V" in md


def test_the_125c_cell_is_labelled_outside_the_window_not_passed(tmp_path):
    _rc, md, doc = _matrix_render(tmp_path)
    hot = doc["cells"][1]
    assert hot["cell"]["temperature_c"] == 125.0
    # Ambient alone sits at the window top, so Tj (125 + the card's rise) is
    # outside by construction -- the label must say so.
    assert hot["worst_stress"]["frac_tj_outside"] > 0
    block = md.split("`hbt_wcs` / 125 C / 0.72 V", 1)[1]
    assert "OUTSIDE MODEL WINDOW" in block
    # The verdict table never passes an outside-window cell: the stress label
    # column carries the label into the same row.
    assert "OUTSIDE MODEL WINDOW" in md.split("## Per-cell figures")[1].split("## Per-cell detail")[0]


def test_a_matrix_report_grades_ratified_rows_per_cell(tmp_path):
    _rc, md, doc = _matrix_render(tmp_path)
    # The synthetic load power is 1.2 V x 30 mA / 2 = 18 mW = 12.55 dBm: above
    # the +10 dBm Fallback and below the +15 dBm Target, so every cell's Psat
    # rung is `fallback` -- grading against sim/lib/spec_rows.py, not a retyped
    # threshold.
    psat = doc["cells"][0]["reduction"]["psat_dbm"]
    assert psat == pytest.approx(10 * math.log10(0.018 * 1e3), abs=0.05)
    assert psat > 10.0 and psat < 15.0
    figures = md.split("## Per-cell figures")[1].split("## Per-cell detail")[0]
    assert figures.count("| fallback |") >= 2      # the Psat column, both cells
    for rung in ("met", "fallback", "missed"):
        pass  # rungs are from _rung(); the fallback count above pins the grading
    assert "worst cell over the matrix" in md.lower()
