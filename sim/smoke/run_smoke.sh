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

sim_begin_record

failed=0
sim_run_one inverter_dc
sim_run_one inverter_tran
sim_run_one npn_op --backend local

sim_gate_logs

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
