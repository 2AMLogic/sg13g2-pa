"""`p1dbref_record.py` turns the low-drive probe into the reference verification.

Issue #192's first acceptance criterion: before attributing the P1dB shortfall to
the DUT, verify the measurement -- the committed sweep's reference points sit only
~8-16 dB below compression (the spec wants 20 dB), so the reference gain itself may
be compressed, and a compressed reference biases the OUTPUT-referred P1dB figure
through the bracket arithmetic, not just by its own epsilon. The tests below pin
that arithmetic on synthetic inputs; no simulator or PDK is needed.
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402
from script_loader import load_script  # noqa: E402
from test_psat_record import MATCH_DECK_HASH, _sweep_waveform  # noqa: E402

PR = load_script("_p1dbref_record", "sim/psat-sweep/p1dbref_record.py")

# A synthetic second-order compressor: g(P_in) = G0 - C * P_in. The probe points
# sit on this curve; the matrix record's reference sits 0.6 dB below G0.
G0_DB = 20.6
C_PER_W = 1.0e6
G_REF_DB = 20.0
PROBE_PIN_W = [5.0e-11, 3.16e-10, 2.0e-9, 1.26e-8, 7.9e-8, 5.0e-7]  # ~4 dB apart


def _probe_waveform(path, p_in_w, gain_db):
    """A settled trace whose extracted P_in/P_out hit exact targets."""
    _sweep_waveform(path, p_in_w, p_in_w * 10 ** (gain_db / 10.0))


def _probe_report(tmp_path):
    corners = []
    for pav, pin in zip(gdb.P1DBREF_PROBE_GRID_DBM, PROBE_PIN_W):
        wav = os.path.join(tmp_path, f"wav-{pav:g}.json")
        _probe_waveform(wav, pin, G0_DB - C_PER_W * pin)
        corners.append({
            "corner_id": f"hbt_typ/vamp={gdb.amp_v(pav):.3f}_vcc=0.800V/27C",
            "status": "pass", "process": "hbt_typ",
            "supply_v": {"vamp": gdb.amp_v(pav), "vcc": gdb.VCC_NOM_V},
            "temperature_c": 27, "artifacts": {"waveform": wav},
        })
    return {"environment": {"backend": "test", "remote": "n/a"}, "corners": corners,
            "provenance": {"input": {"content_hash": MATCH_DECK_HASH}}}


def _matrix_record(g_ref=G_REF_DB, refused=False, pin_dbm=None, gains=None, stored=None):
    """A one-cell committed matrix record: three flat reference points, then a
    1 dB crossing pair with a 0.4 dB measured step and slope 0.5 dB/dB.
    ``stored`` overrides the reduction's ``gain_linear_db`` independently of the
    points, to test the cross-check that catches a disagreeing record."""
    pin = pin_dbm or [-43.0, -42.9, -42.8, -32.2, -31.8, -31.4, -30.0]
    gs = gains or [g_ref, g_ref, g_ref, 19.3, 19.1, 18.9, 18.5]
    def pt(p, g):
        return {"p_in_w": 1e-3 * 10 ** (p / 10.0),
                "p_out_w": 1e-3 * 10 ** ((p + g) / 10.0),
                "p_avail_dbm": p + 10.0, "p_dc_w": 0.0082}
    red = None if refused else {"gain_linear_db": stored if stored is not None else g_ref,
                                "p1db_in_dbm": -31.6,
                                "p1db_out_dbm": -12.6, "psat_dbm": 12.98}
    return {"record_id": "synthetic-matrix", "bench": "psat_sweep_match", "pvt_matrix": True,
            "dut": {"netlist_sha256": gdb.netlist_sha256()},
            "cells": [{"cell": {"process": "hbt_typ", "temperature_c": 27.0,
                                "vcc": gdb.VCC_NOM_V},
                       "points": [pt(p, g) for p, g in zip(pin, gs)],
                       "failures": [], "reduction": red,
                       "reduction_error": None if not refused else
                       {"code": "SWEEP_STEP_TOO_COARSE", "message": "synthetic"}}]}


def _render(tmp_path, matrix):
    rep_path = os.path.join(tmp_path, "probe-report.json")
    with open(rep_path, "w") as fh:
        json.dump(_probe_report(str(tmp_path)), fh)
    matrix_path = os.path.join(tmp_path, "matrix.json")
    with open(matrix_path, "w") as fh:
        json.dump(matrix, fh)
    out_json = os.path.join(tmp_path, "probe.json")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = PR.main(["p1dbref_record.py", "synthetic-probe", "deadbee", "0",
                      "klt 0.9.1", "ngspice-47", rep_path, matrix_path, out_json])
    return rc, buf.getvalue(), json.load(open(out_json))


# --- the fit -----------------------------------------------------------------


def test_the_fit_recovers_the_zero_drive_gain():
    points = [{"p_in_w": p, "p_out_w": p * 10 ** ((G0_DB - C_PER_W * p) / 10.0)}
              for p in PROBE_PIN_W]
    g0, c, resid = PR.fit_zero_drive_gain(points)
    assert g0 == pytest.approx(G0_DB, abs=1e-9)
    assert c == pytest.approx(C_PER_W, rel=1e-6)
    assert resid < 1e-9


def test_the_fit_ignores_a_constant_offset_in_the_right_place():
    """An offset in P (gain curve shifted horizontally) must land in g0, not c:
    epsilon is read off g0, so a horizontal shift misread as vertical would
    corrupt every conclusion below."""
    shift = 0.3
    points = [{"p_in_w": p, "p_out_w": p * 10 ** ((G0_DB - shift - C_PER_W * p) / 10.0)}
              for p in PROBE_PIN_W]
    g0, _c, _r = PR.fit_zero_drive_gain(points)
    assert g0 == pytest.approx(G0_DB - shift, abs=1e-9)


# --- the verification arithmetic ---------------------------------------------


def test_epsilon_slope_and_bias_come_out_of_the_record(tmp_path):
    rc, md, doc = _render(str(tmp_path), _matrix_record())
    assert rc == 0
    a = doc["cells"][0]["analysis"]
    assert a["reference"]["cross_check_ok"] is True
    # epsilon = g0 - g_ref = 20.6 - 20.0
    assert a["epsilon_db"] == pytest.approx(0.6, abs=1e-6)
    # the crossing pair is (-31.8 -> -31.4), comp 0.9 -> 1.1: slope 0.5 dB/dB,
    # step 0.4 dB (within the row's 0.5 dB limit)
    assert a["bracket"]["slope_db_per_db"] == pytest.approx(0.5, abs=1e-6)
    assert a["bracket"]["step_db"] == pytest.approx(0.4, abs=1e-6)
    assert a["bracket"]["step_ok"] is True
    # bias = epsilon * (1/s - 1) = 0.6 * 1.0
    assert a["p1db_out_bias_db"] == pytest.approx(0.6, abs=1e-6)
    # the committed reference sits 11.4 dB below the stored compression drive
    assert a["reference_below_compression_db"] == pytest.approx(11.4, abs=1e-6)
    assert "0.600" in md and "0.500" in md


def test_a_non_pass_probe_corner_carries_its_cell_on_the_failure():
    """`run_p1dbref_probe.sh` allows errored corners; their cell must not be dropped."""
    rep = {"corners": [{"corner_id": "c0", "status": "error", "process": "hbt_wcs",
                        "temperature_c": 125, "supply_v": {"vamp": 0.01, "vcc": 0.72}}]}
    points, failures = PR.extract_corners(rep, gdb.psat_bench("match"))
    assert points == []
    assert failures == [{"corner_id": "c0", "code": "KLT_STATUS_error",
                         "cell": {"process": "hbt_wcs", "temperature_c": 125.0,
                                  "vcc": 0.72}}]


def test_a_refused_matrix_cell_still_reports_probe_numbers(tmp_path):
    rc, md, doc = _render(str(tmp_path), _matrix_record(refused=True))
    assert rc == 0
    a = doc["cells"][0]["analysis"]
    assert a["epsilon_db"] is None          # no committed reference to compare with
    assert a["p1db_out_bias_db"] is None
    assert a["fit"]["g0_db"] == pytest.approx(G0_DB, abs=1e-9)
    assert "| -- |" in md or "|  -- |" in md


def test_a_disagreeing_stored_reference_flags_the_cross_check(tmp_path):
    """g_ref must be the median of the three lowest points of the SAME record; a
    stored value that disagrees makes every epsilon suspect and must say so."""
    rc, md, doc = _render(str(tmp_path), _matrix_record(stored=19.5))
    a = doc["cells"][0]["analysis"]
    assert a["reference"]["cross_check_ok"] is False
    assert "cross-check FAILED" in md


def test_a_coarse_bracket_step_is_flagged(tmp_path):
    """Step above the row's 0.5 dB interpolation limit must not print as legal."""
    pin = [-43.0, -42.9, -42.8, -32.2, -31.8, -31.0, -30.0]
    gains = [G_REF_DB, G_REF_DB, G_REF_DB, 19.3, 19.1, 18.9, 18.5]
    rc, md, doc = _render(str(tmp_path), _matrix_record(pin_dbm=pin, gains=gains))
    a = doc["cells"][0]["analysis"]
    assert a["bracket"]["step_ok"] is False
    assert "Bracket violations" in md


def test_the_quiescent_operating_point_is_reported(tmp_path):
    """The baseline side of issue #192's hypothesis comparison: P_DC and total
    supply current at the lowest probe drive, from the probe's own extraction."""
    rc, _md, doc = _render(str(tmp_path), _matrix_record())
    q = doc["cells"][0]["analysis"]["quiescent"]
    assert q["p_avail_dbm"] == pytest.approx(gdb.P1DBREF_PROBE_GRID_DBM[0])
    # the synthetic waveform's supply: -i(vcc) = 0.210 A at Vcc 0.8 V
    assert q["i_total_a"] == pytest.approx(0.210 / gdb.VCC_NOM_V * gdb.VCC_NOM_V, rel=1e-9)
    assert q["p_dc_w"] == pytest.approx(gdb.VCC_NOM_V * 0.210, rel=1e-6)


@pytest.mark.parametrize("change", ["bare", "nominal", "other DUT", "unknown DUT", "wrong probe deck"])
def test_incompatible_matrix_or_probe_is_refused_before_reduction(tmp_path, change):
    matrix = _matrix_record()
    report = {"provenance": {"input": {"content_hash": MATCH_DECK_HASH}}}
    if change == "bare":
        matrix["bench"] = "psat_sweep"
    elif change == "nominal":
        matrix["pvt_matrix"] = False
    elif change == "other DUT":
        matrix["dut"]["netlist_sha256"] = "0" * 64
    elif change == "unknown DUT":
        del matrix["dut"]
    else:
        report["provenance"]["input"]["content_hash"] = "sha256:" + "0" * 64
    matrix_path, rep_path, out = (tmp_path / name for name in ("matrix.json", "rep.json", "out.json"))
    matrix_path.write_text(json.dumps(matrix))
    rep_path.write_text(json.dumps(report))
    rc = PR.main(["p1dbref_record.py", "probe", "deadbee", "0", "klt", "ngspice",
                  str(rep_path), str(matrix_path), str(out)])
    assert rc == 2
    assert not out.exists()


def test_default_reference_skips_the_newer_refuted_candidate(tmp_path, capsys, monkeypatch):
    # Replay the two records and the DUT of the reviewed run, even after later
    # records arrive or the design advances.
    records = Path(REPO) / "sim/psat-sweep/records"
    baseline = tmp_path / "20261121-003533-b2746d0-match.json"
    candidate = tmp_path / "20261122-020117-8062a122-match.json"
    companion = baseline.with_suffix(".dut.json")
    for path in (baseline, candidate, companion):
        path.symlink_to(records / path.name)
    baseline_hash = json.loads(companion.read_text())["netlist_sha256"]
    monkeypatch.setattr(gdb, "netlist_sha256", lambda: baseline_hash)

    assert PR.main(["p1dbref_record.py", "--select-matrix", str(tmp_path)]) == 0
    assert Path(capsys.readouterr().out.strip()) == baseline
    assert PR.main(["p1dbref_record.py", "--select-matrix", str(tmp_path), str(candidate)]) == 2
    # A companion for a different legacy record cannot supply the missing identity.
    baseline.unlink()
    baseline.write_text(json.dumps({"bench": "psat_sweep_match", "pvt_matrix": True}))
    assert PR.main(["p1dbref_record.py", "--select-matrix", str(tmp_path)]) == 2


# --- the cell label is the shared one (issue #221) ---------------------------


def test_the_cell_label_is_the_shared_one(tmp_path):
    """Not `psat_record._cell_md`: the probe record used to reach into another
    module for a private name, which only existed because both reducers carried
    a copy of the same formatter."""
    import pvt_cells
    assert PR.cell_md is pvt_cells.cell_md
    rc, md, _doc = _render(str(tmp_path), _matrix_record())
    assert rc == 0
    cell = _matrix_record()["cells"][0]["cell"]
    assert f"### {pvt_cells.cell_md(cell)}" in md
