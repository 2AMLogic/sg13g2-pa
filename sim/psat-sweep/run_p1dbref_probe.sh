#!/usr/bin/env bash
# run_p1dbref_probe.sh -- P1dB linear-reference probe (issue #192, acceptance
# criterion 1: "check the compression measurement first").
#
#   scripts/setup-env.sh && sim/psat-sweep/run_p1dbref_probe.sh [matrix-record.json]
#
# Runs the committed matched deck under the sparse low-drive axis declared in
# sim/lib/gen_dut_benches.py (`P1DBREF_PROBE_GRID_DBM`, one fleet submit like
# every grid), then renders the append-only verification record
# records/<timestamp>-<sha>-p1dbref.{md,json} that compares every probed cell
# against the committed matched MATRIX record:
#
#   * the extrapolated zero-drive gain vs the matrix record's reference gain
#     (is the committed reference compressed, and by how much),
#   * the error that reference compression propagates into the P1dB_out figure
#     through the crossing bracket's slope,
#   * the bracket's measured step against the row's 0.5 dB limit,
#   * the quiescent operating point (P_DC, total supply current) per cell.
#
# The reference defaults to the newest matched PVT matrix with the same DUT
# netlist SHA-256. An explicit reference passes the same check before submit.
# The reducer independently verifies the probe report's deck and the matrix DUT.
#
# NOT a matrix bench: no `klt corner-matrix` gate runs here (the probe's
# coverage is its own low-drive axis, not the declared 27-cell box); the
# pre-submit corner-id screen still runs, and the record says what ran. Like
# the matched deck, the probe is a study bench outside the item-9 inventory.
#
# Needs python3 + numpy. Exit codes: 0 ok; 1 the run, a gate or the record
# failed; 3 preflight failed; 4 id collision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_p1dbref_probe.sh
sim_require_numpy
sim_resolve_klt

BENCH="psat_sweep_match_p1dbref"

# The deck must match the DUT netlist (the probe borrows the matched deck
# verbatim; a drifted deck would bench a stale DUT).
python3 -I "${SCRIPT_DIR}/../lib/gen_dut_benches.py" --check

# The committed matrix record this probe verifies against.
MATRIX_RECORD="$(python3 -I "${SCRIPT_DIR}/p1dbref_record.py" --select-matrix \
    "${SCRIPT_DIR}/records" "$@")" || exit 1

sim_begin_record --suffix "-p1dbref" --pathspec sim --pathspec design \
    --pathspec ':!sim/psat-sweep/records' --pathspec ':!sim/psat-sweep/corners'
failed=0
sim_dry_run_corner_ids "${BENCH}" || failed=1
if (( failed == 0 )); then
  sim_run_one "${BENCH}" --allow-errored-corners
  sim_gate_logs --skip-errored-from "${OUT}/${BENCH}.report.json"
fi
(( failed == 0 )) || exit 1

REC="${RECORDS_DIR}/${RECORD_ID}.md"
python3 -I "${SCRIPT_DIR}/p1dbref_record.py" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
  "${KLT_VERSION}" "${NGSPICE_VERSION}" "${OUT}/${BENCH}.report.json" \
  "${MATRIX_RECORD}" "${RECORDS_DIR}/${RECORD_ID}.json" > "${REC}" || exit 1
find "${OUT}" -name 'waveform.raw' -delete -o -name 'waveform.raw.json' -delete
echo "run_p1dbref_probe.sh: record ${REC} (against ${MATRIX_RECORD})"
