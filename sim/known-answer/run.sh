#!/usr/bin/env bash
# run.sh -- known-answer check for sim/lib/rf_extract.py (NOT a design result).
#
#   sim/known-answer/run.sh               # the three analytic checks
#   sim/known-answer/run.sh --wrong-load  # negative control: 75 ohm vs the 50 ohm answer
#
# Runs each deck through `klt sim` (single corner, so `--backend local`; no
# `ngspice -b` is ever launched directly), extracts with sim/lib/rf_extract.py
# and compares with the analytic values (+3.979 dBm into 50 ohm; P_DC = V^2/R
# with PAE = 0; -20.00 dBc third harmonic). Writes the append-only record
# sim/known-answer/records/<timestamp>-<sha>[-wrong-load].md and the klt
# artifacts under sim/known-answer/corners/<same id>/: the per-case report and
# stderr, plus the deck and ngspice log under <case>/<corner>/. The raw traces
# are large and regenerable and are deleted once the record is written.
#
# `klt` is the release pinned in sim/toolchain.json, through uvx (sim_resolve_klt
# in sim/env.sh); override with KLT="path/to/klt" (word-split).
# Exit codes: 0 every value inside tolerance; 1 a value outside tolerance or a
# run/extraction failed (--wrong-load is EXPECTED to exit 1); 3 preflight
# failed; 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mode=normal
cases=(sine_50 dc_load sine_h3)
suffix=""
case "${1:-}" in
  "") ;;
  --wrong-load) mode=wrong-load; cases=(sine_75); suffix="-wrong-load" ;;
  *) echo "run.sh: unknown argument '$1'" >&2; exit 2 ;;
esac

for tool in ngspice python3; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "run.sh: PREFLIGHT: ${tool} not on PATH." >&2; exit 3; }
done
python3 -I -c 'import numpy' 2>/dev/null || { echo "run.sh: PREFLIGHT: python3 numpy missing." >&2; exit 3; }

# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_resolve_klt

# shellcheck disable=SC2034  # read by sim_begin_record
SIM_SCRIPT_NAME=run.sh
# Earlier records/corners of this directory are evidence, not inputs: ignore them.
sim_begin_record --suffix "${suffix}" --pathspec sim \
  --pathspec ':!sim/known-answer/records' --pathspec ':!sim/known-answer/corners'
failed=0
# --allow-not-checked: a waveform-only request declares no measurements, so klt
# grades the run `not_checked` and exits 4 even with every corner `pass`; the
# per-corner status in the report is what gates (sim_gate_logs below, and
# check_known_answer.py). sim_run_one submits once, never reruns locally, and
# sets failed=1 rather than exiting, so the test at the end is what stops the
# run. --backend local: one corner per deck, so no grid goes to the fleet.
for name in "${cases[@]}"; do
  sim_run_one "${name}" --allow-not-checked --backend local
done
sim_gate_logs

REC="${RECORDS_DIR}/${RECORD_ID}.md"
check=0
python3 -I "${SCRIPT_DIR}/check_known_answer.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${OUT}" "${mode}" > "${REC}" || check=$?
# The waveforms are large and regenerable; the reports, decks and logs are kept,
# the raw traces are not. This runs whether or not the checker passed, because
# --wrong-load is EXPECTED to fail and its record is kept as the demonstration.
find "${OUT}" -name 'waveform.raw' -delete -o -name 'waveform.raw.json' -delete
echo "run.sh: record ${REC}"
(( check == 0 && failed == 0 )) || exit 1
exit 0
