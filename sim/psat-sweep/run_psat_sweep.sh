#!/usr/bin/env bash
# run_psat_sweep.sh -- psat-sweep bench: Psat / P1dB / PAE / device stress from a transient
# drive sweep (simulated evidence, not a result).
#
#   scripts/setup-env.sh && sim/psat-sweep/run_psat_sweep.sh
#
# The sweep is one `klt sim` request with one corner per drive point
# (corners.supply_v sets the source amplitude), i.e. a grid: on the dispatch worker
# KLT_SIM_BACKEND=batch sends it to the Spot batch fleet, and the request's
# batch.capacity_wait_s (600) waits for capacity instead of failing. A failed submit is
# reported and never rerun locally; no `ngspice -b` loop is launched here.
# Needs python3 + numpy. Writes the append-only records/<timestamp>-<sha>.{md,json} and the klt
# artifacts under corners/<id>/.
# Exit codes: 0 ok; 1 a run or the record failed; 3 preflight failed; 4 id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_psat_sweep.sh
python3 -I -c 'import numpy' 2>/dev/null || { echo "run_psat_sweep.sh: PREFLIGHT: python3 numpy missing." >&2; exit 3; }
sim_resolve_klt

# The deck must match the DUT netlist. (The extractor's known-answer record,
# sim/known-answer/records/, is the gate before any DUT record and is not re-run here.)
python3 -I "${SCRIPT_DIR}/../lib/gen_dut_benches.py" --check

SIM_SCRIPT_NAME=run_psat_sweep.sh
sim_begin_record --pathspec sim --pathspec design --pathspec ':!sim/psat-sweep/records' --pathspec ':!sim/psat-sweep/corners'
failed=0
# Not sim_run_one: a waveform-only request declares no measurements, so klt exits 4
# (not_checked) with every corner `pass`; the corner statuses gate (psat_record.py,
# sim_gate_logs). A capacity refusal is resubmitted to the batch fleet (bounded),
# never run locally.
for attempt in 1 2 3 4; do
  echo "run_psat_sweep.sh: klt sim psat_sweep (attempt ${attempt})"
  rc=0
  ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --format json -o "${OUT}/psat_sweep" \
      psat_sweep.request.json > "${OUT}/psat_sweep.report.json" 2> "${OUT}/psat_sweep.stderr" ) || rc=$?
  (( rc == 0 || rc == 4 )) && break
  if grep -q 'BATCH_MAX_VCPU\|vCPU already running\|batch_no_capacity\|BATCH_MAX_CONCURRENT_INSTANCES' \
       "${OUT}/psat_sweep.report.json" "${OUT}/psat_sweep.stderr" 2>/dev/null && (( attempt < 4 )); then
    echo "run_psat_sweep.sh: fleet at capacity; resubmitting to batch in 60 s" >&2
    sleep 60
    continue
  fi
  break
done
if (( rc != 0 && rc != 4 )); then
  echo "run_psat_sweep.sh: klt sim exited ${rc} (see ${OUT}/psat_sweep.stderr); no local fallback is attempted." >&2
  exit 1
fi
sim_gate_logs
(( failed == 0 )) || exit 1

REC="${RECORDS_DIR}/${RECORD_ID}.md"
python3 -I "${SCRIPT_DIR}/psat_record.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${NGSPICE_VERSION}" "${OUT}/psat_sweep.report.json" \
  "${RECORDS_DIR}/${RECORD_ID}.json" > "${REC}" || exit 1
# The waveforms are large (tens of MB per drive point) and regenerable; the reports, logs and the
# record's JSON are kept, the raw traces are not.
find "${OUT}" -name 'waveform.raw' -delete -o -name 'waveform.raw.json' -delete
echo "run_psat_sweep.sh: record ${REC}"
