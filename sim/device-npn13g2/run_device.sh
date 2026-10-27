#!/usr/bin/env bash
# run_device.sh -- npn13G2 single-device load-line study (simulated evidence).
#
#   scripts/setup-env.sh          # once
#   sim/device-npn13g2/run_device.sh
#
# Runs through `klt sim` (grids: batch fleet when KLT_SIM_BACKEND=batch, which
# the dispatch worker exports; no `ngspice -b` loop is ever launched here, and a
# failed batch submit is reported, never retried locally):
#   dc_family  Ic-Vce family, Nx 1/4/10 x Vbe x 3 HBT corners x -40/27/125 C
#   ft         h21 / fT at Vce = 1.0 V, same Nx x Vbe x corners x temperatures
# then, after the loadline.py known-answer self-test, writes the append-only
#   records/<timestamp>-<sha>.md, .dc.json, .pdk-provenance.json, .loadline.json
# and the corner artifacts under corners/<id>/. `klt` is the pinned release
# (sim/toolchain.json) through uvx; override with KLT="path/to/klt".
# Exit codes: 0 ok; 1 a run failed or a corner did not pass; 3 preflight failed;
# 4 record id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_device.sh

sim_resolve_klt

# Known-answer gate before any DUT number is used, and the committed decks must
# match their generator.
python3 -I "${SCRIPT_DIR}/loadline.py" --self-test
python3 -I "${SCRIPT_DIR}/gen_bench.py" --check

sim_begin_record

failed=0
sim_run_one dc_family
sim_run_one ft

sim_gate_logs --tolerate-recovered-gmin

REC="${RECORDS_DIR}/${RECORD_ID}.md"
DCJSON="${RECORDS_DIR}/${RECORD_ID}.dc.json"
python3 -I "${SCRIPT_DIR}/summarize.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
    "${KLT_VERSION}" "${NGSPICE_VERSION}" "${PROV}" "${OUT}" "${DCJSON}" > "${REC}" || failed=1

LLJSON="${RECORDS_DIR}/${RECORD_ID}.loadline.json"
if [[ -s "${DCJSON}" ]]; then
  python3 -I "${SCRIPT_DIR}/loadline.py" --dc-json "${DCJSON}" --out "${LLJSON}" || failed=1
else
  python3 -I "${SCRIPT_DIR}/loadline.py" --out "${LLJSON}" || failed=1
fi
if [[ -s "${LLJSON}" ]]; then
  python3 -I "${SCRIPT_DIR}/loadline.py" --render "${LLJSON}" >> "${REC}" || failed=1
fi
echo "run_device.sh: record ${REC}"
exit "${failed}"
