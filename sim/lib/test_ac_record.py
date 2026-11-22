"""`ac_record.py` renders a PVT-matrix report per cell (issue #173).

A multi-corner report must not read `corners[0]` and call it the bench's
result: every declared cell is a row, graded against the RATIFIED rows
(`spec_rows.py`), labelled provisional while the Supply row is DRAFT. The
synthetic sidecars below are two flat networks -- S-parameters constant over
frequency -- so the per-cell numbers are closed-form and the assertions pin
the grading, not the numerics of `sparams.py`. No simulator or PDK.
"""
import contextlib
import importlib.util
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402


def _load_ac_record():
    spec = importlib.util.spec_from_file_location(
        "_ac_record", os.path.join(HERE, "ac_record.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


AC = _load_ac_record()


def _sidecar(path, s21_lin, s11_lin):
    """A flat network's complex_vectors sidecar: S21/S11 constant over 11 points.

    ``v(s1) = 1`` (the AC EMF), ``v(in1) = (1 + s11)/2``,
    ``v(out1) = s21/2`` -- the voltage-ratio forms s_from_nodes reads. Port 2
    is the mirror image.
    """
    n = 11
    freq = [2.4e9 + i * 4.835e7 for i in range(n)]
    data = {}
    for name, re, im in (("v(s1)", 1.0, 0.0), ("v(s2)", 1.0, 0.0),
                         ("v(in1)", (1 + s11_lin) / 2, 0.0),
                         ("v(out1)", s21_lin / 2, 0.0),
                         ("v(in2)", s21_lin / 2, 0.0),
                         ("v(out2)", (1 + s11_lin) / 2, 0.0)):
        data[name] = {"real": [re] * n, "imag": [im] * n}
    with open(path, "w") as fh:
        json.dump({"frequency_hz": freq, "data": data}, fh)


def _render(tmp_path, kind, corners):
    report = {"environment": {"backend": "test", "remote": "n/a"}, "corners": corners}
    rep_path = os.path.join(str(tmp_path), "report.json")
    out_json = os.path.join(str(tmp_path), "rec.json")
    with open(rep_path, "w") as fh:
        json.dump(report, fh)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = AC.main(["ac_record.py", kind, "rid", "deadbee", "0",
                      "klt 0.9.1", "ngspice-47", rep_path])
    return rc, buf.getvalue()


def _corners(tmp_path, cells):
    """corners for [(process, temp, vcc, s21_lin, s11_lin), ...]"""
    corners = []
    for i, (proc, temp, vcc, s21, s11) in enumerate(cells):
        side = os.path.join(str(tmp_path), f"cv{i}.json")
        _sidecar(side, s21, s11)
        corners.append({"corner_id": gdb.klt_corner_id(proc, {"vcc": vcc}, temp),
                        "process": proc, "temperature_c": temp, "status": "pass",
                        "supply_v": {"vcc": vcc},
                        "artifacts": {"complex_vectors": side}})
    return corners


def test_a_matrix_gain_report_grades_each_cell(tmp_path):
    # S21 0.5 (-6 dB): below Fallback (missed); S11 0.3 (-10.5 dB): met.
    # Second cell S21 1.0 (0 dB) missed too, S11 0.7 (-3.1 dB): missed.
    cells = [("hbt_typ", 27.0, 0.8, 0.5, 0.3), ("hbt_wcs", -40.0, 0.72, 1.0, 0.7)]
    rc, md = _render(tmp_path, "gain", _corners(tmp_path, cells))
    assert rc == 0
    assert "PROVISIONAL: Supply row DRAFT" in md
    assert "2 of 27 declared cells" in md
    assert "`hbt_typ` / 27 C / 0.8 V" in md and "`hbt_wcs` / -40 C / 0.72 V" in md
    table = md.split("## Per-cell band results", 1)[1]
    # gain column: both below 10 dB -> missed; S11: -10.5 dB met, -3.1 dB missed
    assert "| missed | missed |" in table
    assert "| missed | met |" in table
    assert "-6.02" in table and "-10.46" in table and "-3.10" in table


def test_a_matrix_stability_report_grades_each_cell(tmp_path):
    # mu needs |S11| < 1 and small S12*S21; the flat network gives closed-form
    # values -- just pin that the mu column exists, grades against 1, and the
    # worst-cell line is the minimum.
    cells = [("hbt_typ", 27.0, 0.8, 0.5, 0.3), ("hbt_bcs", 125.0, 0.88, 0.5, 0.3)]
    rc, md = _render(tmp_path, "stability", _corners(tmp_path, cells))
    assert rc == 0
    assert "| mu > 1 |" in md
    assert "**Worst cell over the matrix**" in md and "min mu " in md
    assert "`hbt_bcs` / 125 C / 0.88 V" in md


def test_a_matrix_report_states_the_dc_solve_option(tmp_path):
    """The gmin convergence aid is a bench condition, restated from the
    generator's constant so the record cannot fall behind the deck (issue #188)."""
    rc, md = _render(tmp_path, "gain", _corners(tmp_path, [("hbt_typ", 27.0, 0.8, 0.5, 0.3)]))
    assert rc == 0
    assert f"`.options gmin={gdb.AC_GMIN:g}`" in md


def test_a_matrix_report_lists_cells_with_grades_withheld(tmp_path):
    corners = _corners(tmp_path, [("hbt_typ", 27.0, 0.8, 0.5, 0.3)])
    corners.append({"corner_id": "hbt_wcs/0.720V/125C", "process": "hbt_wcs",
                    "temperature_c": 125.0, "status": "error",
                    "supply_v": {"vcc": 0.72}})
    rc, md = _render(tmp_path, "gain", corners)
    assert rc == 0
    assert "Cells with figures withheld" in md
    assert "`hbt_wcs` / 125 C / 0.72 V" in md
    assert "klt status `error`, grade withheld" in md


# --- findings point at the design iteration that tracks them (issue #194) ----


def test_a_matrix_gain_report_links_each_finding_to_its_tracker(tmp_path):
    # S21 0.5 (-6 dB): gain missed, no tracker for it; S11 0.7 (-3.1 dB): #172.
    # Second cell: gain met, S11 met -- a passing row acquires no link.
    cells = [("hbt_typ", 27.0, 0.8, 0.5, 0.7), ("hbt_wcs", -40.0, 0.72, 6.32, 0.0032)]
    rc, md = _render(tmp_path, "gain", _corners(tmp_path, cells))
    assert rc == 0
    sec = md.split("## Findings and their trackers", 1)[1]
    assert ("Input match (S11): 1 cell below the Fallback rung (`missed`) "
            "-- design iteration #172." in sec)
    gain_line = [ln for ln in sec.splitlines() if ln.startswith("- Power gain:")][0]
    assert "1 cell below the Fallback rung (`missed`)" in gain_line
    assert "#1" not in gain_line          # a row with no tracker is linked to nothing


def test_a_matrix_stability_report_links_mu_to_its_tracker(tmp_path):
    # s21 0.8, s11 0.3: min mu 0.82 < 1 (the flat network's closed-form mu);
    # second cell same. Both missed -> the stability finding names #172.
    cells = [("hbt_typ", 27.0, 0.8, 0.8, 0.3), ("hbt_bcs", 125.0, 0.88, 0.8, 0.3)]
    rc, md = _render(tmp_path, "stability", _corners(tmp_path, cells))
    assert rc == 0
    sec = md.split("## Findings and their trackers", 1)[1]
    assert ("Stability (mu > 1): 2 cells below the rung (`missed`) "
            "-- design iteration #172." in sec)


def test_a_matrix_report_links_only_the_ac_error_tracked_by_188(tmp_path):
    # Both flagged cells have vectors from a completed analysis. Only the AC
    # singular-matrix case investigated in #188 should acquire its tracker.
    cells = [("hbt_typ", 27.0, 0.8, 6.32, 0.0032),
             ("hbt_wcs", 125.0, 0.72, 0.5, 0.7),
             ("hbt_bcs", 125.0, 0.80, 0.5, 0.7)]
    corners = _corners(tmp_path, cells)
    corners[1].update(status="error", diagnostics=[{"code": "singular_matrix"}])
    corners[2].update(status="error", diagnostics=[{"code": "vector_error"}])
    rc, md = _render(tmp_path, "gain", corners)
    assert rc == 0
    assert "3 cells" in md and "grades 1 of 27" in md
    assert "did not simulate" not in md
    sec = md.split("## Findings and their trackers", 1)[1]
    assert "1 cell with grade withheld (klt status `error`) -- design iteration #188." in sec
    assert "1 cell with grade withheld (klt status `error`) -- no design-iteration tracker." in sec


def test_fallback_only_is_counted_at_the_fallback_rung(tmp_path):
    cells = [("hbt_typ", 27.0, 0.8, 4.0, 0.35), ("hbt_wcs", -40.0, 0.72, 4.0, 0.35)]
    rc, md = _render(tmp_path, "gain", _corners(tmp_path, cells))
    assert rc == 0
    sec = md.split("## Findings and their trackers", 1)[1]
    assert "Power gain: 2 cells at the Fallback rung (`fallback`)" in sec
    assert "Input match (S11): 2 cells at the Fallback rung (`fallback`)" in sec
    assert "below the Fallback rung" not in sec and "`missed`" not in sec


def test_an_all_met_matrix_report_links_nothing(tmp_path):
    # S21 6.32 (16 dB) met; S11 0.0032 (-49.9 dB) met; nothing errored.
    cells = [("hbt_typ", 27.0, 0.8, 6.32, 0.0032),
             ("hbt_wcs", -40.0, 0.72, 6.32, 0.0032)]
    rc, md = _render(tmp_path, "gain", _corners(tmp_path, cells))
    assert rc == 0
    sec = md.split("## Findings and their trackers", 1)[1]
    assert "No verdict falls below its rung" in sec
    assert "#172" not in sec and "#188" not in sec
