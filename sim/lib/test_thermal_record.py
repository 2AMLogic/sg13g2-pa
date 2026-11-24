"""The thermal-node record's verdict comes from its own tolerance arithmetic.

thermal_record.py recomputes every graded check from the report's measured
values against the analytic answers gen_bench.py derives from
device_limits.rth(); these tests feed it synthetic `klt sim` reports (no
simulator) and assert the verdict, the per-row error and tolerance statements,
and the negative control's contract: a control that fails is the demonstration,
a control that passes is broken. The measured values used are the committed
run's (records/20261114-205927-00b692a.md), so the fixtures are real shapes.
"""
import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BENCH = os.path.join(REPO, "sim", "known-answer-thermal")
sys.path.insert(0, HERE)
from script_loader import load_script  # noqa: E402

RECORD_ID = "20261114-205927-00b692a"


RECORDER = load_script("_thermal_record", "sim/known-answer-thermal/thermal_record.py")
GEN = load_script("_thermal_gen_bench", "sim/known-answer-thermal/gen_bench.py")

# The committed run's measured values (positive case), by measurement name.
MEASURED = {
    "vt5_n1_1m": 11.3518505,
    "vt5_n1_10m": 113.518505,
    "vt5_n4_1m": 3.25998937,
    "vt5_n4_10m": 32.5998937,
    "ic_bias": 0.00235143526,
    "p_bias": 0.00235429179,
    "vt5_bias": 7.67496581,
    "rth_meas": 3259.9892,
    "vt4_bias": 7.67496581,
    "vt4_minus_vt5": 1.0658141e-14,
}
NEG_MEASURED = {
    "vt5_n1_1m": 1.0e6,
    "vt5_n1_10m": 1.0e7,
    "vt5_n4_1m": 1.0e6,
    "vt5_n4_10m": 1.0e7,
}

LOG_TEXT = """
Note: No compatibility mode selected!

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

The temperature limiting function received NaN.
Please check your power dissipation and improve your heat sink Rth!
    This message will be shown only once.

Note: Starting dynamic gmin stepping
Note: Dynamic gmin stepping completed
"""


def _report(values, corner_status="pass", tmp_path=None):
    """A klt sim report shaped like the real one, with its own log artifact."""
    log = tmp_path / "ngspice.log"
    log.write_text(LOG_TEXT)
    return {
        "status": corner_status,
        "environment": {"engine": "ngspice", "engine_version": "47"},
        "corners": [{
            "status": corner_status,
            "process": "hbt_typ",
            "temperature_c": 27,
            "artifacts": {"log": str(log)},
            "measurements": [
                {"name": n, "value": v, "unit": "V",
                 "status": "pass" if corner_status == "pass" else "fail"}
                for n, v in values.items()
            ],
        }],
    }


def _render(tmp_path, report, mode="normal"):
    """Run the recorder over a synthetic report; return (exit, record text)."""
    out = tmp_path / ("out_" + mode)
    out.mkdir(exist_ok=True)
    case = "thermal" if mode == "normal" else "thermal_neg"
    (out / f"{case}.report.json").write_text(json.dumps(report))
    prov = tmp_path / "prov.json"
    prov.write_text(json.dumps({
        "pinned_release_tag": "v0.3.0",
        "installed_release_raw": "0.3.0",
        "identity_route": "tarball-marker",
    }))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RECORDER.main(["thermal_record.py", RECORD_ID, "00b692a", "0",
                            "klt 0.9.0", str(prov), str(out), mode])
    return rc, buf.getvalue()


def test_pass_record_states_verdict_errors_and_tolerances(tmp_path):
    rc, md = _render(tmp_path, _report(MEASURED, tmp_path=tmp_path))
    assert rc == 0
    assert "**Result: PASS**" in md
    # every graded row carries analytic, measured, error, tolerance and verdict
    assert "| vt5_n4_1m |" in md and "3.259989" in md and "-3.26e-06 rel" in md
    assert "rel 0.01 %" in md and "rel 0.1 %" in md and "abs 1e-06 V" in md
    # the 4-terminal transfer statement quotes the graded difference
    assert "measured +1.066e-14 V" in md
    # the systematic and the scope are stated, not implied
    assert "Rt t 0 R = 1e9" in md and "-rth/1e9" in md
    assert "NOT shown: `cth`" in md
    assert "Engine actually used: `ngspice 47`" in md
    # diagnostics are read from the run's own log
    assert "The temperature limiting function received NaN." in md
    assert "--tolerate-recovered-gmin" in md


def test_the_analytic_column_is_rth_not_a_retyped_constant(tmp_path):
    rc, md = _render(tmp_path, _report(MEASURED, tmp_path=tmp_path))
    assert rc == 0
    assert "3.26e3 * (4/Nx)^0.9" in md
    assert "sim/lib/device_limits.py" in md
    # the analytic value of the Nx=1 injection row is rth(1) * 1 mA
    assert "11.351979" in md


def test_out_of_tolerance_case_fails(tmp_path):
    values = dict(MEASURED)
    values["vt5_n4_1m"] = 3.3  # 1.2 % off: far outside the 0.01 % tolerance
    rc, md = _render(tmp_path, _report(values, tmp_path=tmp_path))
    assert rc == 1
    assert "**Result: FAIL**" in md
    row = next(line for line in md.splitlines() if "| vt5_n4_1m |" in line)
    assert "FAIL" in row and "PASS" not in row


def test_negative_control_expected_fail(tmp_path):
    rc, md = _render(tmp_path, _report(NEG_MEASURED, corner_status="fail",
                                       tmp_path=tmp_path), mode="neg")
    # a behaving control exits 0 from the renderer; run.sh still exits 1 in
    # this mode by contract (the klt grading itself failed), and the record
    # is kept as the demonstration
    assert rc == 0
    assert "NEGATIVE CONTROL (selft=0)" in md
    assert "**Result: FAIL**" in md and "expected" in md
    assert "CONTROL DID NOT FAIL" not in md
    # the control's record renders only the rows its own request declares
    assert "| vt5_n4_1m |" in md
    assert "| rth_meas |" not in md and "| vt4_minus_vt5 |" not in md
    # five to six orders of magnitude off
    assert "1000000.000000" in md


def test_negative_control_that_passes_is_broken(tmp_path):
    # selft stayed 1 by accident: every grading passes and the corner passes,
    # so the control must announce itself broken rather than demonstrate
    rc, md = _render(tmp_path, _report(MEASURED, tmp_path=tmp_path), mode="neg")
    assert rc == 1
    assert "CONTROL DID NOT FAIL" in md
    assert "**Result: FAIL** (expected" not in md


def test_missing_report_fails_closed(tmp_path):
    out = tmp_path / "out_empty"
    out.mkdir()
    prov = tmp_path / "prov.json"
    prov.write_text(json.dumps({"pinned_release_tag": "v0.3.0",
                                "installed_release_raw": "0.3.0",
                                "identity_route": "tarball-marker"}))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RECORDER.main(["thermal_record.py", RECORD_ID, "00b692a", "0",
                            "klt 0.9.0", str(prov), str(out), "normal"])
    assert rc == 1
    assert "No usable report" in buf.getvalue()


def test_request_limits_track_the_generator():
    """The committed request's limits center on P * rth with the stated widths."""
    req = json.load(open(os.path.join(BENCH, "thermal.request.json")))
    by_name = {m["name"]: m for m in req["measurements"]}
    for nx in GEN.NX_INJ:
        for i in GEN.I_INJ_A:
            m = by_name[GEN.inj_name(nx, i)]
            center = i * GEN.rth(nx)
            half = GEN.TOL_INJ_REL * center
            assert m["limits"]["min"] == pytest.approx(center - half, rel=1e-12)
            assert m["limits"]["max"] == pytest.approx(center + half, rel=1e-12)
    r = by_name["rth_meas"]["limits"]
    center = GEN.rth(GEN.BIAS_NX)
    assert r["min"] == pytest.approx(center * (1 - GEN.TOL_BIAS_REL), rel=1e-12)
    # the 1 Gohm shunt systematic sits well inside the injection tolerance
    assert GEN.rth(1) / GEN.R_SHUNT_OHM < GEN.TOL_INJ_REL
    assert GEN.rth(4) / GEN.R_SHUNT_OHM < GEN.TOL_INJ_REL


def test_check_passes_on_committed_decks_and_catches_drift(tmp_path):
    """gen_bench --check exits 0 on the committed files, 1 after a one-char edit."""
    assert GEN.main(["--check"]) == 0
    copy = tmp_path / "copy"
    shutil.copytree(BENCH, copy,
                    ignore=shutil.ignore_patterns("records", "corners", "__pycache__"))
    stale = load_script("_thermal_gen_bench_stale", os.path.join(copy, "gen_bench.py"))
    deck = copy / "thermal.spice"
    deck.write_text(deck.read_text().replace("Nx=4", "Nx=5", 1))
    assert stale.main(["--check"]) == 1
