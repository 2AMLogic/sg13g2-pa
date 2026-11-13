"""Unit tests for `sim_run_one` in sim/env.sh -- the one `klt sim` submit path
every bench shares. No simulator, PDK or network is needed: `klt` is replaced
by a stub whose exit code and stderr the test chooses, so what is under test is
the runner's own exit handling.

`sim_run_one` submits once: a fleet capacity refusal is waited out by `klt`
itself -- from the request's `batch.capacity_wait_s`, or a
`--wait-for-capacity` the caller passes through -- so there is no shell-level
resubmit to exercise here.
"""

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


def test_exit_4_fails_a_bench_that_did_not_opt_in():
    # A request that declares `measurements` must never record an unchecked
    # run silently: without the flag, `not_checked` is a failure.
    failed, _, _ = run_one("bench", rc=4)
    assert failed == 1


def test_exit_4_is_accepted_with_allow_not_checked():
    # The waveform-only benches (psat-sweep, ac-gain, ac-stability) declare no
    # measurements, so a clean run exits 4; the per-corner status gates instead.
    failed, _, _ = run_one("bench --allow-not-checked", rc=4)
    assert failed == 0


def test_allow_not_checked_waives_only_exit_4():
    for rc in (1, 2, 3, 5):
        failed, _, _ = run_one("bench --allow-not-checked", rc=rc)
        assert failed == 1, f"exit {rc} must stay a failure"


def test_allow_not_checked_is_not_passed_through_to_klt():
    _, _, argv = run_one("bench --allow-not-checked --backend local", rc=4)
    assert "--allow-not-checked" not in argv
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
