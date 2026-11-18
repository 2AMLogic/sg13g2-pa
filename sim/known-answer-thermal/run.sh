#!/usr/bin/env bash
# run.sh -- thermal-node known-answer check for the npn13G2 VBIC self-heating
# network (spec/decision-records/0001-ratify-target-spec.md Q4, deferred D-2;
# NOT a design result).
#
#   sim/known-answer-thermal/run.sh        # the positive cases
#   sim/known-answer-thermal/run.sh --neg  # negative control: selft=0, EXPECTED to fail
#
# Runs its deck through `klt sim` (single corner, so `--backend local`; no
# `ngspice -b` is ever launched directly). The request declares graded
# `measurements`, so klt itself gates every value against limits gen_bench.py
# computes from sim/lib/device_limits.rth() -- the card's own rth expression.
# Writes the append-only record
# sim/known-answer-thermal/records/<timestamp>-<sha>[-neg].md and the klt
# artifacts under sim/known-answer-thermal/corners/<same id>/. This bench
# instantiates a PDK device, so unlike sim/known-answer/run.sh it calls
# sim_require_pdk: the PDK pin lands in the record's provenance.
#
# `klt` is the release pinned in sim/toolchain.json, through uvx (sim_resolve_klt
# in sim/env.sh); override with KLT="path/to/klt" (word-split).
# Exit codes: 0 every value inside tolerance; 1 a value outside tolerance or a
# run failed (--neg is EXPECTED to exit 1 and its record is kept as the
# demonstration); 2 unknown argument; 3 preflight failed; 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mode=normal
case_="thermal"
suffix=""
case "${1:-}" in
  "") ;;
  --neg) mode=neg; case_="thermal_neg"; suffix="-neg" ;;
  *) echo "run.sh: unknown argument '$1'" >&2; exit 2 ;;
esac

for tool in ngspice python3; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "run.sh: PREFLIGHT: ${tool} not on PATH." >&2; exit 3; }
done

# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run.sh
sim_resolve_klt

# The committed decks must match the generator (fails loudly on a stale copy).
python3 -I "${SCRIPT_DIR}/gen_bench.py" --check

# shellcheck disable=SC2034  # read by sim_begin_record
SIM_SCRIPT_NAME=run.sh
# Earlier records/corners of this directory are evidence, not inputs: ignore them.
sim_begin_record --suffix "${suffix}" --pathspec sim \
  --pathspec ':!sim/known-answer-thermal/records' --pathspec ':!sim/known-answer-thermal/corners'
failed=0
# The request declares graded measurements, so klt grades the check itself and
# exits non-zero on any out-of-tolerance value, with no waiver, and no waveform
# post-processing (an op run has no waveform). sim_run_one submits once,
# never reruns locally, and sets failed=1 rather than exiting, so the test at
# the end is what stops the run. --neg reaches here too: its klt
# failure is the EXPECTED one, and its record is still written below.
sim_run_one "${case_}" --backend local
# No --tolerate-recovered-gmin, deliberately: the injection decks' NaN
# temperature-limiter note and recovered gmin stepping match no error pattern
# in sim_gate_logs (checked; the record quotes them from the run's own log).
sim_gate_logs

REC="${RECORDS_DIR}/${RECORD_ID}.md"
check=0
python3 -I "${SCRIPT_DIR}/thermal_record.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${PROV}" "${OUT}" "${mode}" > "${REC}" || check=$?
echo "run.sh: record ${REC}"
# --neg lands here with failed=1 and check=1: that is its passing condition,
# and its exit code is 1 by contract (see header).
(( check == 0 && failed == 0 )) || exit 1
exit 0
