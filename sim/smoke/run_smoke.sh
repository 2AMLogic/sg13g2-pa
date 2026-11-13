#!/usr/bin/env bash
# run_smoke.sh -- toolchain smoke test (NOT a design result).
#
#   scripts/setup-env.sh        # once
#   sim/smoke/run_smoke.sh
#
# Runs, through `klt sim`:
#   inverter_dc    5 MOS corners (tt/ff/ss/fs/sf) -- a grid, so it goes to the
#   inverter_tran  batch fleet when KLT_SIM_BACKEND=batch (the dispatch worker
#                  exports it), with klt's own capacity wait (see BATCH_WAIT
#                  below). No `ngspice -b` loop is ever launched here, and a
#                  failed batch submit is reported, never retried locally.
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
# The fleet is vCPU-budgeted, so a grid submit refused for capacity
# (batch_no_capacity / batch_concurrency_cap) must be waited out on batch, never
# rerun locally (host rule). klt owns that wait; this just asks for it. The other
# grid benches declare it in the request (`batch.capacity_wait_s`: 600) -- these
# two cannot, because `evidence/item9.json` content-hashes both request files and
# re-attesting item 9 reruns every bench, so the flag carries the same 600 here.
#
# `--wait-for-capacity` is batch-only: klt exits 1 with "--wait-for-capacity
# requires backend 'batch'" on any other backend. These two calls pass no
# --backend and their requests declare none, so KLT_SIM_BACKEND alone decides,
# and the flag is passed only when it resolves to batch. Without it (a laptop,
# no KLT_SIM_BACKEND) the grids run locally and need no capacity wait.
# (`if`, not `[[ ... ]] && ...`: under `set -e` the && form would exit 1 here on
# every non-batch host. `${a[@]+"${a[@]}"}` expands an empty array safely under
# `set -u`.)
BATCH_WAIT=()
if [[ "${KLT_SIM_BACKEND:-}" == "batch" ]]; then
  BATCH_WAIT=(--wait-for-capacity 600)
fi
sim_run_one inverter_dc ${BATCH_WAIT[@]+"${BATCH_WAIT[@]}"}
sim_run_one inverter_tran ${BATCH_WAIT[@]+"${BATCH_WAIT[@]}"}
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
