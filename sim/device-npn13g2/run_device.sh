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

KLT_PIN="0.7.0"
# shellcheck disable=SC2206  # intentional word-splitting of the command
KLT_CMD=(${KLT:-uvx --from "klayout-tools==${KLT_PIN}" klt})
KLT_VERSION="$("${KLT_CMD[@]}" --version 2>&1 | tail -1)"

# Known-answer gate before any DUT number is used, and the committed decks must
# match their generator.
python3 -I "${SCRIPT_DIR}/loadline.py" --self-test
python3 -I "${SCRIPT_DIR}/gen_bench.py" --check

REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
DIRTY=0
[[ -z "$(git -C "${REPO_ROOT}" status --porcelain -- sim scripts 2>/dev/null)" ]] || DIRTY=1
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"
OUT="${SCRIPT_DIR}/corners/${RECORD_ID}"
RECORDS_DIR="${SCRIPT_DIR}/records"
if [[ -e "${OUT}" ]] || compgen -G "${RECORDS_DIR}/${RECORD_ID}*" >/dev/null; then
  echo "run_device.sh: record id ${RECORD_ID} already has artifacts; refusing to reuse it. Wait a second and rerun." >&2
  exit 4
fi
mkdir -p "${OUT}" "${RECORDS_DIR}"
PROV="${RECORDS_DIR}/${RECORD_ID}.pdk-provenance.json"
printf '%s\n' "${SIM_PDK_PROVENANCE_JSON}" > "${PROV}"

failed=0
run_one() { # run_one <name>
  # Batch-capacity refusals are resubmitted to the batch fleet (4 attempts, 60 s
  # apart). Any other failure is reported; nothing is ever retried locally.
  local name="$1" attempt rc
  for attempt in 1 2 3 4; do
    echo "run_device.sh: klt sim ${name} (attempt ${attempt})"
    rc=0
    ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --format json -o "${OUT}/${name}" \
        "${name}.request.json" > "${OUT}/${name}.report.json" 2> "${OUT}/${name}.stderr" ) || rc=$?
    (( rc == 0 )) && return 0
    if grep -q 'BATCH_MAX_CONCURRENT_INSTANCES\|batch_no_capacity\|batch_concurrency_cap' \
         "${OUT}/${name}.report.json" "${OUT}/${name}.stderr" 2>/dev/null && (( attempt < 4 )); then
      echo "run_device.sh: ${name}: fleet at capacity; resubmitting to batch in 60 s" >&2
      sleep 60
      continue
    fi
    break
  done
  echo "run_device.sh: ${name}: klt sim exited ${rc} (see ${OUT}/${name}.stderr); no local fallback is attempted." >&2
  failed=1
}
run_one dc_family
run_one ft

SIM_LOG_REQUIRE_COMPLETE=0
for log in "${OUT}"/*/*/ngspice.log; do
  [[ -f "${log}" ]] || continue
  # A "singular matrix" warning that ngspice's dynamic gmin stepping recovered from
  # (klt grades the corner `pass` with a warning diagnostic) is listed in the
  # record's solver-diagnostics section rather than failing the gate; every other
  # error pattern still fails it.
  filtered="$(mktemp)"
  if grep -q 'Dynamic gmin stepping completed' "${log}"; then
    grep -v '^Warning: singular matrix' "${log}" > "${filtered}" || true
  else
    cp "${log}" "${filtered}"
  fi
  sim_check_log "${log#"${OUT}/"}" "${filtered}" 0 || failed=1
  rm -f "${filtered}"
done

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
