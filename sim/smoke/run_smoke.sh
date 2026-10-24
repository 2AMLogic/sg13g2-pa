#!/usr/bin/env bash
# run_smoke.sh -- toolchain smoke test (NOT a design result).
#
#   scripts/setup-env.sh        # once
#   sim/smoke/run_smoke.sh
#
# Runs, through `klt sim`:
#   inverter_dc    5 MOS corners (tt/ff/ss/fs/sf) -- a grid, so it goes to the
#   inverter_tran  batch fleet when KLT_SIM_BACKEND=batch (the dispatch worker
#                  exports it). No `ngspice -b` loop is ever launched here, and
#                  a failed batch submit is reported, never retried locally.
#   npn_op         one npn13G2 DC operating point, typical HBT corner; a single
#                  unit, so it runs locally (`--backend local`).
# then writes the append-only record sim/smoke/records/<timestamp>-<sha>.md and
# the corner artifacts under sim/smoke/corners/<timestamp>-<sha>/.
#
# `klt` is run as the pinned release (sim/toolchain.json) through uvx, a
# throwaway environment; override with KLT="path/to/klt" (word-split).
# Exit codes: 0 all corners pass; 1 a run failed or a corner did not pass;
# 3 preflight failed (named error from sim/env.sh); 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_smoke.sh --osdi

sim_resolve_klt

REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
DIRTY=0
[[ -z "$(git -C "${REPO_ROOT}" status --porcelain -- sim scripts 2>/dev/null)" ]] || DIRTY=1
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
OUT="${SCRIPT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${SCRIPT_DIR}/records"
if [[ -e "${OUT}" ]] || compgen -G "${RECORDS_DIR}/${RECORD_ID}*" >/dev/null; then
  echo "run_smoke.sh: record id ${RECORD_ID} already has artifacts; refusing to reuse it. Wait a second and rerun." >&2
  exit 4
fi
mkdir -p "${OUT}" "${RECORDS_DIR}"
PROV="${RECORDS_DIR}/${RECORD_ID}.pdk-provenance.json"
printf '%s\n' "${SIM_PDK_PROVENANCE_JSON}" > "${PROV}"

failed=0
sim_run_one inverter_dc
sim_run_one inverter_tran
sim_run_one npn_op --backend local

# Per-corner log gate: no missing-model / non-convergence error.
SIM_LOG_REQUIRE_COMPLETE=0
for log in "${OUT}"/*/*/ngspice.log; do
  [[ -f "${log}" ]] || continue
  sim_check_log "${log#"${OUT}/"}" "${log}" 0 || failed=1
done

REC="${RECORDS_DIR}/${RECORD_ID}.md"
if python3 -I "${SCRIPT_DIR}/summarize.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
     "${KLT_VERSION}" "${NGSPICE_VERSION}" "${PROV}" "${OUT}" \
     inverter_dc inverter_tran npn_op > "${REC}"; then
  :
else
  failed=1
fi
echo "run_smoke.sh: record ${REC}"
exit "${failed}"
