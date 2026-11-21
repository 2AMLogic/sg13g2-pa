#!/usr/bin/env bash
# run_mc_pilot.sh -- Monte Carlo pilot (issue #174): what variation the pinned HBT
# statistical sections and the batch runner can measure, at the nominal cell.
#
#   scripts/setup-env.sh && sim/mc-pilot/run_mc_pilot.sh
#
# The cold start in attest/item9.json runs four `klt sim`
# monte_carlo requests (DC op + AC gain, each against hbt_typ_stat and
# hbt_typ_mismatch) plus two negative-control probes, reduced into one append-only
# record records/<timestamp>-<sha>.{md,json}. The four baseline runs
# explicitly select the batch backend (the requests'
# batch.capacity_wait_s 600 makes klt wait for capacity instead of failing); a
# submit that still fails is reported, never rerun locally, and the refusal is
# committed as the record. The two probes are run with --backend local on purpose:
# at the pinned client they are refused client-side before any draw (that refusal
# is the evidence), and a probe that someday RUNS is kept as a completed control.
#
# Exit codes: 0 baseline completed, 1 submit/log/render failure, 3 preflight
# failure, 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_mc_pilot.sh
sim_require_numpy
sim_resolve_klt

# The committed decks must match the DUT netlist and the attested ac-gain deck.
python3 -I "${SCRIPT_DIR}/gen_mc_pilot.py" --check

sim_begin_record --pathspec sim --pathspec design \
  --pathspec ":!sim/mc-pilot/records" --pathspec ":!sim/mc-pilot/corners"

# --- The negative-control probes (client-side, expected to be refused at 0.9.0)
for probe in scale instances; do
  echo "${SIM_SCRIPT_NAME}: probe ${probe} (local, refusal expected at this pin)"
  set +e
  ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --format json --backend local \
      -o "${OUT}/probe_${probe}" "probe_${probe}.request.json" \
      > "${OUT}/probe_${probe}.capture.json" 2>&1 )
  rc=$?
  set -e
  # klt prints its error envelope into the capture on a refusal (exit 1); on a
  # completed run the report lands in the capture too. Either way the file is
  # what the record quotes; the exit code is only reported.
  echo "${SIM_SCRIPT_NAME}: probe ${probe}: klt sim exited ${rc} (see ${OUT}/probe_${probe}.capture.json)"
done

# --- The four fleet runs -----------------------------------------------------
failed=0
for key in stat mismatch; do
  sim_run_one "mc_op_${key}" --backend batch
  sim_run_one "mc_ac_${key}" --backend batch
done
# A submit refusal belongs in the feasibility record, but fails the cold start.
# A simulator error invalidates the measurements; stop before reducing them.
submit_failed=${failed}
failed=0
sim_gate_logs
(( failed == 0 )) || exit 1

# --- The record --------------------------------------------------------------
python3 -I "${SCRIPT_DIR}/mc_pilot_record.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${NGSPICE_VERSION}" \
  --models-dir "${SG13G2_NGSPICE_MODELS}" \
  --json-out "${RECORDS_DIR}/${RECORD_ID}.json" \
  --run "dc_stat=${OUT}/mc_op_stat.report.json:${OUT}/mc_op_stat.stderr" \
  --run "dc_mismatch=${OUT}/mc_op_mismatch.report.json:${OUT}/mc_op_mismatch.stderr" \
  --run "ac_stat=${OUT}/mc_ac_stat.report.json:${OUT}/mc_ac_stat.stderr" \
  --run "ac_mismatch=${OUT}/mc_ac_mismatch.report.json:${OUT}/mc_ac_mismatch.stderr" \
  --probe "scale=${OUT}/probe_scale.capture.json" \
  --probe "instances=${OUT}/probe_instances.capture.json" \
  > "${RECORDS_DIR}/${RECORD_ID}.md" || exit 1

echo "${SIM_SCRIPT_NAME}: record ${RECORDS_DIR}/${RECORD_ID}.md"
exit "${submit_failed}"
