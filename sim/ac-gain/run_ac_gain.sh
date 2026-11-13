#!/usr/bin/env bash
# run_ac_gain.sh -- ac-gain bench: S21 / S11 / S22 over the band (simulated evidence, not a result).
#
#   scripts/setup-env.sh && sim/ac-gain/run_ac_gain.sh
#
# One nominal cell (hbt_typ, 27 C, Vcc 0.8 V), a single unit, so it runs through
# `klt sim --backend local` (no ngspice -b is launched directly). Writes the
# append-only record records/<timestamp>-<sha>.md and the klt artifacts under
# corners/<id>/. Needs python3 + numpy (a venv, or `uvx --with numpy`).
# Exit codes: 0 ok; 1 the run or the record failed; 3 preflight failed; 4 id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_ac_gain.sh
python3 -I -c 'import numpy' 2>/dev/null || { echo "run_ac_gain.sh: PREFLIGHT: python3 numpy missing." >&2; exit 3; }
sim_resolve_klt

# The committed deck must match the DUT netlist (fails loudly on a stale copy).
python3 -I "${SCRIPT_DIR}/../lib/gen_dut_benches.py" --check

sim_begin_record --pathspec sim --pathspec design --pathspec ':!sim/ac-gain/records' --pathspec ':!sim/ac-gain/corners'
failed=0
# A single unit, so --backend local. --allow-not-checked: a waveform-only
# request declares no measurements, so klt exits 4 (not_checked); the corner
# status gates. sim_run_one sets failed=1 rather than exiting, so the gate
# below is what stops the record.
sim_run_one ac_gain --allow-not-checked --backend local
sim_gate_logs
(( failed == 0 )) || exit 1
REC="${RECORDS_DIR}/${RECORD_ID}.md"
python3 -I "${SCRIPT_DIR}/../lib/ac_record.py" gain "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${NGSPICE_VERSION}" "${OUT}/ac_gain.report.json" > "${REC}" || exit 1
echo "run_ac_gain.sh: record ${REC}"
