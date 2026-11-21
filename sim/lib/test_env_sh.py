"""Unit tests for the two shared gates in sim/env.sh: `sim_run_one`, the one
`klt sim` submit path every bench shares, and `sim_gate_logs`, the per-corner
ngspice-log gate every bench runs after it.

No simulator, PDK or network is needed. For `sim_run_one`, `klt` is replaced by
a stub whose exit code and stderr the test chooses, so what is under test is the
runner's own exit handling. For `sim_gate_logs`, the test writes the ngspice
logs itself, so what is under test is which log text fails a point and which
does not.

`sim_run_one` submits once: a fleet capacity refusal is waited out by `klt`
itself -- from the request's `batch.capacity_wait_s`, or a
`--wait-for-capacity` the caller passes through -- so there is no shell-level
resubmit to exercise here.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENV_SH = REPO / "sim" / "env.sh"

STUB = """#!/usr/bin/env bash
# Stands in for `klt`: records its argv, emits the chosen stderr, exits STUB_RC.
printf '%s\\n' "$@" >> "${ARGV_LOG}"
printf '%s' "${STUB_STDERR:-}" >&2
printf '{"status": "stub"}\\n'
exit "${STUB_RC:-0}"
"""

HARNESS = """
set -uo pipefail
source "__ENV_SH__" >/dev/null 2>&1 || true
SCRIPT_DIR="__TMP__/bench"
OUT="__TMP__/out"
SIM_SCRIPT_NAME=test_env_sh
KLT_CMD=("__TMP__/klt-stub")
failed=0
sim_run_one __ARGS__
echo "RESULT failed=${failed}"
"""


def run_one(args, rc=0, stderr_text=""):
    """Run `sim_run_one <args>` against the stub; return (failed, stdout, argv)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bench").mkdir()
        (tmp / "out").mkdir()
        argv_log = tmp / "argv.log"
        argv_log.touch()
        stub = tmp / "klt-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)
        script = (
            HARNESS.replace("__ENV_SH__", str(ENV_SH))
            .replace("__TMP__", str(tmp))
            .replace("__ARGS__", args)
        )
        env = dict(os.environ, STUB_RC=str(rc), STUB_STDERR=stderr_text,
                   ARGV_LOG=str(argv_log))
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, env=env, timeout=120)
        assert "RESULT failed=" in proc.stdout, (proc.stdout, proc.stderr)
        failed = int(proc.stdout.rsplit("RESULT failed=", 1)[1].strip())
        return failed, proc.stdout, argv_log.read_text().splitlines()


def test_clean_run_is_a_success():
    failed, out, _ = run_one("bench", rc=0)
    assert failed == 0
    assert out.count("klt sim bench") == 1


def test_exit_4_is_always_a_failure():
    # Without --allow-errored-corners no bench is waived: a waveform-only
    # request sets `options.capture_only`, so klt exits 0 when every corner
    # simulated; exit 4 means corners errored and the strict default refuses.
    failed, _, _ = run_one("bench", rc=4)
    assert failed == 1


def test_exit_4_is_tolerated_only_when_the_bench_allows_errored_corners():
    # The characterization-matrix waiver (issue #173): a corner that errored is
    # a cell the record must show as "did not simulate", so the matrix benches
    # pass --allow-errored-corners and exit 4 alone does not set failed. The
    # waiver is exit-4 only: every other non-zero exit still fails, waived or
    # not.
    failed, _, _ = run_one("bench --allow-errored-corners", rc=4)
    assert failed == 0
    for rc in (1, 2, 3, 5):
        failed, _, _ = run_one("bench --allow-errored-corners", rc=rc)
        assert failed == 1, f"exit {rc} must still be a failure"


def test_every_non_zero_exit_is_a_failure():
    for rc in (1, 2, 3, 4, 5):
        failed, _, _ = run_one("bench", rc=rc)
        assert failed == 1, f"exit {rc} must be a failure"


def test_extra_args_are_passed_through_to_klt():
    _, _, argv = run_one("bench --backend local", rc=0)
    assert "--backend" in argv and "local" in argv
    assert "bench.request.json" in argv


def test_a_failure_is_submitted_once_whatever_its_cause():
    # klt owns the capacity wait (the request's batch.capacity_wait_s), so the
    # runner submits exactly once and reports: a capacity refusal that outlasts
    # that wait is not re-submitted here, and neither is any other failure.
    for stderr_text in ("error: batch_no_capacity",
                        "error: batch_concurrency_cap",
                        "error: BATCH_MAX_CONCURRENT_INSTANCES reached",
                        "error: BATCH_MAX_VCPU reached",
                        "error: netlist is broken"):
        failed, out, _ = run_one("bench", rc=1, stderr_text=stderr_text)
        assert failed == 1, stderr_text
        assert out.count("klt sim bench") == 1, f"re-submitted: {out}"


# --- sim_gate_logs --------------------------------------------------------
#
# The log gate is pure text matching over ${OUT}/<corner>/<point>/ngspice.log,
# so the test writes the logs directly. These cases pin the contract the
# runners rely on: an error pattern fails the point, a gmin-recovered singular
# matrix is tolerated only when the bench asks for it, and nothing else about
# a log (exit codes, completion markers) is consulted.

GATE_HARNESS = """
set -uo pipefail
source "__ENV_SH__" >/dev/null 2>&1 || true
OUT="__TMP__/out"
SIM_SCRIPT_NAME=test_env_sh
failed=0
sim_gate_logs __ARGS__
echo "RESULT failed=${failed}"
"""

CLEAN_LOG = """Circuit: ** sg13g2 pa bench
Doing analysis at TEMP = 27.000000 and TNOM = 27.000000
No. of Data Rows : 101
"""

GMIN_RECOVERED_LOG = CLEAN_LOG + """Warning: singular matrix:  check nodes net3 and net3
Trying dynamic gmin stepping
Dynamic gmin stepping completed
"""


def gate(logs, args=""):
    """Run `sim_gate_logs <args>` over {point: text}; return (failed, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for point, text in logs.items():
            log = tmp / "out" / point / "ngspice.log"
            log.parent.mkdir(parents=True)
            log.write_text(text)
        script = (
            GATE_HARNESS.replace("__ENV_SH__", str(ENV_SH))
            .replace("__TMP__", str(tmp))
            .replace("__ARGS__", args)
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, timeout=120)
        if "RESULT failed=" not in proc.stdout:
            return proc.returncode, proc.stderr
        failed = int(proc.stdout.rsplit("RESULT failed=", 1)[1].strip())
        return failed, proc.stderr


def test_a_clean_log_passes_the_gate():
    # No BENCH_COMPLETE marker and no exit code are involved: klt-generated
    # logs carry neither, and this log is what a good corner looks like.
    failed, err = gate({"tt/27c": CLEAN_LOG})
    assert failed == 0, err
    assert "FAILED" not in err


def test_an_error_pattern_fails_the_point_and_names_it():
    failed, err = gate({"tt/27c": CLEAN_LOG + "Timestep too small; time = 1e-12\n"})
    assert failed == 1
    assert "FAILED tt/27c" in err
    assert "ngspice.log" in err


def test_every_error_pattern_fails_a_point():
    for needle in ("Unable to find definition of model npn13G2",
                   "osdi file couldn't be loaded",
                   "Unknown model type bogus",
                   "can't open file: no such file or directory",
                   "Warning: singular matrix: check nodes",
                   "Timestep too small",
                   "convergence problem in dcop",
                   "doAnalyses: iteration limit reached, analysis failed",
                   "Error: unknown subckt"):
        failed, err = gate({"tt/27c": CLEAN_LOG + needle + "\n"})
        assert failed == 1, f"{needle!r} did not fail the gate: {err}"


def test_one_bad_log_fails_the_whole_gate():
    failed, err = gate({
        "tt/27c": CLEAN_LOG,
        "ss/m40c": CLEAN_LOG + "convergence problem\n",
        "ff/125c": CLEAN_LOG,
    })
    assert failed == 1
    assert "FAILED ss/m40c" in err
    assert "FAILED tt/27c" not in err


def test_recovered_gmin_fails_the_gate_by_default():
    failed, err = gate({"tt/27c": GMIN_RECOVERED_LOG})
    assert failed == 1, err
    assert "FAILED tt/27c" in err


def test_recovered_gmin_is_tolerated_only_when_the_bench_asks():
    failed, err = gate({"tt/27c": GMIN_RECOVERED_LOG}, "--tolerate-recovered-gmin")
    assert failed == 0, err


def test_tolerating_recovered_gmin_waives_nothing_else():
    # The filter drops only the "Warning: singular matrix" lines; any other
    # error in the same log still fails the point.
    log = GMIN_RECOVERED_LOG + "Unable to find definition of model npn13G2\n"
    failed, err = gate({"tt/27c": log}, "--tolerate-recovered-gmin")
    assert failed == 1, err
    assert "FAILED tt/27c" in err


def test_an_unrecovered_singular_matrix_fails_even_when_tolerating():
    # No "Dynamic gmin stepping completed" line, so the filter does not apply.
    log = CLEAN_LOG + "Warning: singular matrix:  check nodes net3 and net3\n"
    failed, err = gate({"tt/27c": log}, "--tolerate-recovered-gmin")
    assert failed == 1, err


def test_the_failure_message_names_the_real_log_not_a_filtered_copy():
    # Under --tolerate-recovered-gmin the gate greps a filtered temporary copy;
    # the path it reports must still be the recorded log an operator can open.
    log = GMIN_RECOVERED_LOG + "Timestep too small\n"
    failed, err = gate({"tt/27c": log}, "--tolerate-recovered-gmin")
    assert failed == 1
    assert "see " in err and err.strip().endswith("out/tt/27c/ngspice.log")


def test_an_unknown_option_is_a_usage_error():
    rc, err = gate({"tt/27c": CLEAN_LOG}, "--no-such-flag")
    assert rc == 2, err
    assert "unknown option" in err


def test_a_gate_over_no_logs_is_not_a_failure():
    # An empty OUT means the submit path already failed and reported it; the
    # log gate must not invent a second failure from an unmatched glob.
    failed, err = gate({})
    assert failed == 0, err


# --- sim_gate_logs --skip-errored-from --------------------------------------
#
# The characterization-matrix waiver (issue #173): exactly the logs of corners
# the REPORT grades `status: "error"` skip the gate -- their diagnostics are
# the record's "did not simulate" cells. The statuses come from klt's report,
# never from re-parsing the log text, and nothing else is waived.


def gate_with_report(logs, corners, args=""):
    """Run `sim_gate_logs <args> --skip-errored-from <report>` over {point: text}.

    corners is the report's corner list: (corner_id, status, point) with the
    point naming the same directory the log was written to, so the fixture
    report references the very logs the test wrote -- one tree, like a real
    collect.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for point, text in logs.items():
            log = tmp / "out" / point / "ngspice.log"
            log.parent.mkdir(parents=True)
            log.write_text(text)
        report = tmp / "report.json"
        report.write_text(json.dumps({
            "corners": [
                {"corner_id": cid, "status": st,
                 "artifacts": {"log": str(tmp / "out" / point / "ngspice.log")}}
                for cid, st, point in corners
            ],
        }))
        script = (
            GATE_HARNESS.replace("__ENV_SH__", str(ENV_SH))
            .replace("__TMP__", str(tmp))
            .replace("__ARGS__", f"{args} --skip-errored-from {report}".strip())
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, timeout=120)
        if "RESULT failed=" not in proc.stdout:
            return proc.returncode, proc.stderr
        failed = int(proc.stdout.rsplit("RESULT failed=", 1)[1].strip())
        return failed, proc.stderr


BAD_LOG = CLEAN_LOG + "Warning: singular matrix:  check nodes net3 and net3\n"


def test_skip_errored_from_skips_exactly_the_errored_corners_log():
    failed, err = gate_with_report(
        {"hot/125c": BAD_LOG, "tt/27c": CLEAN_LOG},
        [("hbt_wcs/0.800V/125C", "error", "hot/125c"),
         ("hbt_typ/0.800V/27C", "pass", "tt/27c")])
    assert failed == 0, err
    assert "errored corner" in err and "hot/125c" in err


def test_skip_errored_from_waives_nothing_else():
    # A pass-status corner's bad log still fails the gate, and the errored
    # corner's log is not skipped when the report grades it pass.
    failed, err = gate_with_report(
        {"hot/125c": BAD_LOG, "tt/27c": BAD_LOG},
        [("hbt_wcs/0.800V/125C", "pass", "hot/125c"),
         ("hbt_typ/0.800V/27C", "pass", "tt/27c")])
    assert failed == 1, err
    assert "FAILED hot/125c" in err and "FAILED tt/27c" in err


def test_skip_errored_from_with_an_unreadable_report_waives_nothing():
    # A report that cannot be read gates everything: the strict default.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "out" / "hot" / "ngspice.log"
        log.parent.mkdir(parents=True)
        log.write_text(BAD_LOG)
        broken = tmp / "report.json"
        broken.write_text("{not json")
        failed, err = gate({"hot": BAD_LOG},
                           f"--skip-errored-from {broken}")
    assert failed == 1, err


def test_skip_errored_from_needs_a_value():
    rc, err = gate({}, "--skip-errored-from")
    assert rc == 2, err
    assert "needs a value" in err


# --- sim_corner_matrix_check -----------------------------------------------
#
# The `klt corner-matrix` gate: the stub IS klt (its argv is recorded, its
# stdout is the verdict the test chooses), so what is under test is the gate's
# own reading of the verdict -- and, for the errored-cells case, its
# cross-check of the verdict against the report klt graded (issue #173,
# 2AMLogic/klayout-tools#7008).

CM_HARNESS = """
set -uo pipefail
source "__ENV_SH__" >/dev/null 2>&1 || true
OUT="__TMP__/out"
SIM_SCRIPT_NAME=test_env_sh
KLT_CMD=("__TMP__/klt-stub")
failed=0
sim_corner_matrix_check __TMP__/matrix.json __MODE__ __SRC__ bench || failed=1
echo "RESULT failed=${failed}"
"""

CM_KLT_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "${ARGV_LOG}"
cat "${VERDICT_JSON}"
exit "${VERDICT_RC:-0}"
"""


def cm_check(mode, verdict, report=None, verdict_rc=0):
    """Run the gate in <mode> with a chosen verdict; return (failed, stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "out").mkdir()
        (tmp / "matrix.json").write_text("{}\n")
        verdict_json = tmp / "verdict.json"
        verdict_json.write_text(json.dumps(verdict))
        src = tmp / ("report.json" if report is not None else "request.json")
        if report is not None:
            src.write_text(json.dumps(report))
        else:
            src.write_text("{}\n")
        stub = tmp / "klt-stub"
        stub.write_text(CM_KLT_STUB)
        stub.chmod(0o755)
        argv_log = tmp / "argv.log"
        argv_log.touch()
        script = (
            CM_HARNESS.replace("__ENV_SH__", str(ENV_SH))
            .replace("__TMP__", str(tmp))
            .replace("__MODE__", mode)
            .replace("__SRC__", str(src))
        )
        env = dict(os.environ, ARGV_LOG=str(argv_log),
                   VERDICT_JSON=str(verdict_json), VERDICT_RC=str(verdict_rc))
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, env=env, timeout=120)
        assert "RESULT failed=" in proc.stdout, (proc.stdout, proc.stderr)
        return int(proc.stdout.rsplit("RESULT failed=", 1)[1].strip()), proc.stdout


def _report(corners):
    return {"corners": corners}


ERRORED_CELL = {"corner_id": "hbt_wcs/0.800V/125C", "status": "error"}
PASS_CELL = {"corner_id": "hbt_typ/0.800V/27C", "status": "pass"}


def test_a_complete_verdict_passes():
    failed, out = cm_check("report", {"mode": "report", "matrix_size": 2,
                                      "coverage_complete": True, "complete": True,
                                      "missing": [], "extra": [], "duplicate": []},
                           report=_report([PASS_CELL, ERRORED_CELL]))
    assert failed == 0, out
    assert "covers all 2 declared tuples" in out


def test_the_errored_cells_case_passes_and_cites_the_upstream_gap():
    # klt cannot check a matrix whose cells legitimately fail clean
    # (klayout-tools#7008): not_simulated conflates never-ran with
    # ran-and-errored. The gate accepts the errored-cells case -- missing /
    # extra / duplicate empty AND every not_simulated tuple a corner the
    # report itself grades non-pass -- and says so.
    failed, out = cm_check(
        "report",
        {"mode": "report", "matrix_size": 2, "coverage_complete": False,
         "complete": False, "missing": [], "extra": [], "duplicate": [],
         "not_simulated": ["hbt_wcs/0.800V/125C"]},
        report=_report([PASS_CELL, ERRORED_CELL]),
        verdict_rc=3)
    assert failed == 0, out
    assert "2 declared tuples observed once" in out
    assert "1 errored" in out and "klayout-tools#7008" in out


def test_a_not_simulated_tuple_that_never_ran_still_fails():
    # The cross-check is the whole waiver: a not_simulated entry with no
    # matching non-pass corner in the report is a coverage hole, not an
    # errored cell.
    failed, out = cm_check(
        "report",
        {"mode": "report", "matrix_size": 2, "coverage_complete": False,
         "complete": False, "missing": [], "extra": [], "duplicate": [],
         "not_simulated": ["hbt_wcs/0.800V/125C", "hbt_typ/0.720V/-40C"]},
        report=_report([PASS_CELL, ERRORED_CELL]),
        verdict_rc=3)
    assert failed == 1, out
    assert "CORNER_MATRIX_INCOMPLETE" not in out  # the failure is on stderr


def test_a_missing_or_duplicated_tuple_fails_even_with_errored_cells():
    for verdict in (
        {"mode": "report", "matrix_size": 3, "coverage_complete": False,
         "complete": False, "missing": ["hbt_typ/0.720V/-40C"], "extra": [],
         "duplicate": [], "not_simulated": ["hbt_wcs/0.800V/125C"]},
        {"mode": "report", "matrix_size": 2, "coverage_complete": False,
         "complete": False, "missing": [], "extra": [],
         "duplicate": ["hbt_typ/0.800V/27C"], "not_simulated": []},
    ):
        failed, _ = cm_check("report", verdict,
                             report=_report([PASS_CELL, ERRORED_CELL]),
                             verdict_rc=3)
        assert failed == 1, verdict


def test_request_mode_has_no_errored_cells_waiver():
    # A not-complete request verdict fails; the waiver reads the REPORT's own
    # corner statuses and a request has none.
    failed, _ = cm_check(
        "request",
        {"mode": "request", "matrix_size": 2, "coverage_complete": None,
         "complete": False, "missing": [], "extra": [], "duplicate": [],
         "not_simulated": ["hbt_wcs/0.800V/125C"]},
        verdict_rc=3)
    assert failed == 1


# --- sim_run_ac_bench -----------------------------------------------------
#
# The shared body of the two AC bench runners (sim/ac-gain/run_ac_gain.sh and
# sim/ac-stability/run_ac_stability.sh), which differ only in the bench name.
# These cases pin the gate order the benches' append-only evidence depends on:
# a stale deck stops the bench before it submits, a failed submit or a failed
# corner log stops the record, the `kind` reaches ac_record.py, and records and
# corners land under the calling bench's own directory.
#
# No simulator, PDK or network: `klt`, `gen_dut_benches.py` and `ac_record.py`
# are stubs under a temporary `sim/` tree the test points SIM_DIR at, and
# `sim_resolve_klt` is replaced so nothing is fetched through uvx.

AC_KLT_STUB = """#!/usr/bin/env bash
# Stands in for `klt` for the AC driver: records its argv, writes a per-corner
# ngspice.log under its -o directory, answers the three call shapes the driver
# makes (a --dry-run unit expansion, a corner-matrix verdict, a sim report),
# exits STUB_RC.
out=""
prev=""
dry=0
for a in "$@"; do
  [[ "${prev}" == "-o" ]] && out="${a}"
  [[ "${a}" == "--dry-run" ]] && dry=1
  prev="${a}"
done
printf '%s\n' "$@" >> "${ARGV_LOG}"
if [[ -n "${out}" && -n "${STUB_LOG:-}" ]]; then
  mkdir -p "${out}/tt"
  printf '%s' "${STUB_LOG}" > "${out}/tt/ngspice.log"
fi
if [[ "${1:-}" == "corner-matrix" ]]; then
  printf '{"mode": "stub", "matrix_size": 2, "observed_count": 2, "coverage_complete": true, "complete": true, "missing": [], "extra": [], "duplicate": []}\n'
elif (( dry )); then
  printf '{"status": "valid", "units": [{"corner_id": "stub/0.800V/27C"}, {"corner_id": "stub/0.720V/-40C"}]}\n'
else
  printf '{"status": "stub"}\n'
fi
exit "${STUB_RC:-0}"
"""

GEN_DECK_STUB = """import os
import sys

if os.environ.get("STUB_DECK_STALE"):
    sys.stderr.write("gen_dut_benches.py: committed deck is stale\\n")
    sys.exit(1)
sys.exit(0)
"""

AC_RECORD_STUB = """import os
import sys

with open(os.environ["RECORD_ARGV_LOG"], "w") as fh:
    fh.write("\\n".join(sys.argv[1:]))
print("# stub record")
sys.exit(int(os.environ.get("STUB_RECORD_RC", "0")))
"""

# `set -e` is enabled only after sourcing, so a PDK-less host cannot abort the
# source before the functions under test are defined -- the runners themselves
# run the driver under `set -euo pipefail`.
AC_HARNESS = """
set -uo pipefail
source "__ENV_SH__" >/dev/null 2>&1 || true
SIM_DIR="__TMP__/sim"
REPO_ROOT="__TMP__"
SCRIPT_DIR="__TMP__/sim/ac-__DIR__"
SIM_SCRIPT_NAME=test_env_sh
NGSPICE_VERSION="ngspice-stub"
sim_resolve_klt() { KLT_CMD=("__TMP__/klt-stub"); KLT_VERSION="klt-stub"; }
set -e
sim_run_ac_bench __ARGS__
"""


class AcRun:
    """The observable outcome of one `sim_run_ac_bench` invocation.

    Everything is captured eagerly: the sandbox is a TemporaryDirectory that is
    gone by the time a test reads this.
    """

    def __init__(self, proc, argv, record_argv, records, corners):
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        self.argv = argv                # what the klt stub was called with
        self.record_argv = record_argv  # what ac_record.py was called with
        self._records = records         # {kind: [record file names]}
        self._corners = corners         # {kind: [corner dir names]}

    def records(self, kind):
        return self._records[kind]

    def corners(self, kind):
        return self._corners[kind]


def run_ac(args, dir_kind="gain", rc=0, log=None, stale=False, record_rc=0):
    """Run `sim_run_ac_bench <args>` from sim/ac-<dir_kind>/ against the stubs.

    rc is the klt stub's exit status (0, what a clean `capture_only` run exits);
    log is the ngspice log it writes.
    """
    if log is None:
        log = CLEAN_LOG
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lib = tmp / "sim" / "lib"
        lib.mkdir(parents=True)
        (lib / "gen_dut_benches.py").write_text(GEN_DECK_STUB)
        (lib / "ac_record.py").write_text(AC_RECORD_STUB)
        bench_dirs = {}
        for kind in ("gain", "stability"):
            d = tmp / "sim" / f"ac-{kind}"
            d.mkdir()
            bench_dirs[kind] = d
        stub = tmp / "klt-stub"
        stub.write_text(AC_KLT_STUB)
        stub.chmod(0o755)
        argv_log = tmp / "argv.log"
        argv_log.touch()
        record_argv_log = tmp / "record-argv.log"
        script = (
            AC_HARNESS.replace("__ENV_SH__", str(ENV_SH))
            .replace("__TMP__", str(tmp))
            .replace("__DIR__", dir_kind)
            .replace("__ARGS__", args)
        )
        env = dict(os.environ, STUB_RC=str(rc), STUB_LOG=log,
                   ARGV_LOG=str(argv_log), RECORD_ARGV_LOG=str(record_argv_log),
                   STUB_RECORD_RC=str(record_rc))
        env.pop("STUB_DECK_STALE", None)
        if stale:
            env["STUB_DECK_STALE"] = "1"
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, env=env, timeout=120)
        record_argv = (record_argv_log.read_text().splitlines()
                       if record_argv_log.exists() else [])
        # Read the sandbox out before the TemporaryDirectory is removed.
        records = {k: sorted(p.name for p in (d / "records").glob("*.md"))
                   for k, d in bench_dirs.items()}
        corners = {k: sorted(p.name for p in (d / "corners").glob("*")
                             if p.is_dir())
                   for k, d in bench_dirs.items()}
        return AcRun(proc, argv_log.read_text().splitlines(), record_argv,
                     records, corners)


def test_a_clean_ac_run_writes_one_record():
    # A waveform-only request sets `capture_only`, so a good run exits 0; the
    # corner log is what gates, and the record is written.
    r = run_ac("gain")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert len(r.records("gain")) == 1, r.stderr
    assert "record " in r.stdout


def test_the_kind_selects_the_request_the_report_and_the_renderer_argument():
    for kind, other in (("gain", "stability"), ("stability", "gain")):
        r = run_ac(kind, dir_kind=kind)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert f"ac_{kind}.request.json" in r.argv, r.argv
        assert f"ac_{other}.request.json" not in r.argv
        # ac_record.py takes the kind as argv[1] and renders both benches.
        assert r.record_argv[0] == kind, r.record_argv
        assert r.record_argv[-1].endswith(f"ac_{kind}.report.json"), r.record_argv


def test_the_ac_submit_is_one_fleet_run_with_matrix_screens():
    # One real submit (no --backend flag: the host's KLT_SIM_BACKEND decides,
    # batch on the dispatch worker), bracketed by the pre-submit screens (a
    # --dry-run unit expansion and a corner-matrix request check) and the
    # post-run corner-matrix report check.
    r = run_ac("gain")
    assert r.argv.count("--dry-run") == 1, r.argv
    assert r.argv.count("corner-matrix") == 2, r.argv
    assert "--request" in r.argv and "--report" in r.argv
    assert sum(1 for a in r.argv if a.endswith("pvt-matrix.json")) == 2, r.argv
    assert "--backend" not in r.argv
    # Exactly one submit of the request (the dry run expands, it does not run).
    submits = sum(1 for a in r.argv if a == "sim") - 1  # one `sim` is the dry run
    assert submits == 1, f"re-submitted: {r.argv}"


def test_a_failing_corner_log_stops_the_record():
    # The whole point of sharing the body: this gate must hold for both benches.
    for kind in ("gain", "stability"):
        r = run_ac(kind, dir_kind=kind,
                   log=CLEAN_LOG + "Timestep too small; time = 1e-12\n")
        assert r.returncode == 1, (kind, r.stdout, r.stderr)
        assert r.records(kind) == [], f"{kind}: record written past a failed gate"
        assert r.record_argv == [], f"{kind}: renderer ran past a failed gate"
        assert "FAILED" in r.stderr


def test_a_failed_submit_stops_the_record():
    r = run_ac("gain", rc=1)
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert r.records("gain") == []
    assert r.record_argv == []
    assert "klt sim exited 1" in r.stderr


def test_a_stale_deck_stops_the_bench_before_it_submits():
    r = run_ac("gain", stale=True)
    assert r.returncode != 0
    assert r.argv == [], f"klt ran past the staleness gate: {r.argv}"
    assert r.records("gain") == []
    assert "stale" in r.stderr


def test_a_record_render_failure_fails_the_bench():
    r = run_ac("gain", record_rc=1)
    assert r.returncode == 1, (r.stdout, r.stderr)


def test_records_and_corners_land_in_the_calling_bench_directory():
    # sim_begin_record derives OUT and RECORDS_DIR from the caller's
    # SCRIPT_DIR, so each wrapper's evidence stays under its own bench
    # directory even though the body is shared.
    for kind, other in (("gain", "stability"), ("stability", "gain")):
        r = run_ac(kind, dir_kind=kind)
        assert len(r.records(kind)) == 1
        assert len(r.corners(kind)) == 1
        assert r.records(other) == [], f"{kind} wrote into ac-{other}/records"
        assert r.corners(other) == [], f"{kind} wrote into ac-{other}/corners"


def test_an_unknown_kind_is_a_usage_error():
    r = run_ac("psat")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "unknown kind" in r.stderr
    assert r.argv == []


def test_a_missing_kind_is_a_usage_error():
    r = run_ac("")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "is required" in r.stderr
    assert r.argv == []
