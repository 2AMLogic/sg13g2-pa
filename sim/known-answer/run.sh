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
# reports/logs under sim/known-answer/corners/<same id>/.
#
# `klt` is the release pinned in sim/toolchain.json, through uvx (sim_resolve_klt
# in sim/env.sh); override with KLT="path/to/klt" (word-split).
# Exit codes: 0 every value inside tolerance; 1 a value outside tolerance or a
# run/extraction failed (--wrong-load is EXPECTED to exit 1); 3 preflight
# failed; 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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

REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
DIRTY=0
# Earlier records/corners of this directory are evidence, not inputs: ignore them.
[[ -z "$(git -C "${REPO_ROOT}" status --porcelain -- sim ':!sim/known-answer/records' ':!sim/known-answer/corners' 2>/dev/null)" ]] || DIRTY=1
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}${suffix}"
RECORDS_DIR="${SCRIPT_DIR}/records"
KEEP="${SCRIPT_DIR}/corners/${RECORD_ID}"
if [[ -e "${KEEP}" ]] || compgen -G "${RECORDS_DIR}/${RECORD_ID}*" >/dev/null; then
  echo "run.sh: record id ${RECORD_ID} already has artifacts; refusing to reuse it. Wait a second and rerun." >&2
  exit 4
fi
mkdir -p "${RECORDS_DIR}" "${KEEP}"

# The waveforms are large and regenerable; they live in a scratch dir. The
# reports and ngspice logs are kept under corners/<id>/.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/known-answer.XXXXXX")"
trap 'rm -rf "${WORK}"' EXIT

failed=0
for name in "${cases[@]}"; do
  echo "run.sh: klt sim ${name} --backend local"
  rc=0
  ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --backend local --format json -o "${WORK}/${name}" \
      "${name}.request.json" > "${WORK}/${name}.report.json" 2> "${WORK}/${name}.stderr" ) || rc=$?
  # 4 = "not_checked": a waveform-only request declares no measurements. The
  # corner status in the report is what the checker gates on.
  if (( rc != 0 && rc != 4 )); then
    echo "run.sh: ${name}: klt sim exited ${rc} (see ${WORK}/${name}.stderr); no local fallback is attempted." >&2
    cat "${WORK}/${name}.stderr" >&2 || true
    failed=1
  fi
  cp "${WORK}/${name}.report.json" "${WORK}/${name}.stderr" "${KEEP}/" 2>/dev/null || true
  for log in "${WORK}/${name}"/*/ngspice.log; do
    [[ -f "${log}" ]] && cp "${log}" "${KEEP}/${name}.ngspice.log"
  done
done

REC="${RECORDS_DIR}/${RECORD_ID}.md"
check=0
python3 -I "${SCRIPT_DIR}/check_known_answer.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${WORK}" "${mode}" > "${REC}" || check=$?
echo "run.sh: record ${REC}"
(( check == 0 && failed == 0 )) || exit 1
exit 0
