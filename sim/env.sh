# Source me:  source sim/env.sh
#
# Resolves the SG13G2 PDK environment (PDK_ROOT/PDK env vars, falling back
# to the cache install scripts/setup-env.sh makes and then the usual
# open_pdks prefixes), so an interactive ngspice session and every sim/*
# runner agree on which PDK install is in use.
#
# Adapted from sg13g2-lna's sim/env.sh at a named commit; the provenance,
# what was kept and what was dropped are in
# spec/decision-records/0001-adopt-lna-sim-env.md. Deliberately NOT carried
# over: sim_jobs / sim_pool_* (a hand-rolled ngspice job pool -- grids go
# through `klt sim`, see sim/README.md) and the committed-DUT splice.
#
# Safe to source from any directory; does not require `klt`.
#
# This file is sourced, not executed, so it has no shebang; the directive
# below tells shellcheck which dialect to assume.
# shellcheck shell=bash

export PDK="${PDK:-ihp-sg13g2}"

SG13G2_TOOLS_CACHE="${SG13G2_TOOLS_CACHE:-${HOME}/.cache/sg13g2-pa}"

if [[ -z "${PDK_ROOT:-}" ]]; then
  # ${SG13G2_TOOLS_CACHE}/pdk-root is the symlink scripts/setup-env.sh
  # maintains to the klayout-tools fetch's install.
  for _sg13g2_candidate in "${SG13G2_TOOLS_CACHE}/pdk-root" \
                           /usr/share/pdk /usr/local/share/pdk \
                           "${HOME}/share/pdk" "${HOME}/.ciel" "${HOME}/.volare"; do
    if [[ -d "${_sg13g2_candidate}/${PDK}/libs.tech/ngspice" ]]; then
      export PDK_ROOT="${_sg13g2_candidate}"
      break
    fi
  done
fi

if [[ -n "${PDK_ROOT:-}" && -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  export SG13G2_NGSPICE_MODELS="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"
  echo "sg13g2-pa: PDK_ROOT=${PDK_ROOT} PDK=${PDK}"
else
  echo "sg13g2-pa: no ${PDK} install found under PDK_ROOT or the usual prefixes." >&2
  echo "sg13g2-pa: run scripts/setup-env.sh (fetches the pinned release), or set" >&2
  echo "sg13g2-pa:   export PDK_ROOT=/path/to/ihp-open-pdk PDK=ihp-sg13g2" >&2
  echo "sg13g2-pa: see sim/pdk.json for the pinned release this repo's records target." >&2
fi

unset _sg13g2_candidate

# --- Repo-relative anchors ------------------------------------------------
# Derived from THIS file's own location, so they are identical whichever
# runner (or interactive shell) sources it.
SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

# --- Shared runner surface -----------------------------------------------
SIM_SCRIPT_NAME=""         # set by sim_require_pdk; prefixes every message
SIM_PDK_PROVENANCE_JSON="" # set by sim_require_pdk: verified PDK identity + model hashes

sim_require_pdk() {
  # sim_require_pdk <script-name> [--osdi]
  #
  # The PDK/ngspice preflight every runner shares. EVERY failure path prints
  # "<script-name>: <NAMED_ERROR>: <what is missing>" on stderr and exits 3.
  # Named errors: PDK_NOT_FOUND, NGSPICE_NOT_FOUND, PDK_MODEL_MISSING,
  # OSDI_MISSING (names sim/tools/build-osdi.sh), and, from
  # sim/tools/pdk_identity.py, PDK_IDENTITY_MISMATCH /
  # PDK_IDENTITY_UNVERIFIABLE / PDK_MODEL_INPUT_MISSING.
  #
  # Sets, in the caller: SIM_SCRIPT_NAME, NGSPICE_VERSION, MODELS_LIB and --
  # with --osdi, for benches that instantiate a MOS/PSP103 device --
  # MOS_LIB (the LV corner library), OSDI_DIR and OSDI_FILES, each checked.
  local want_osdi=0
  SIM_SCRIPT_NAME="${1:?sim_require_pdk: <script-name> is required}"
  shift
  while (( $# > 0 )); do
    case "$1" in
      --osdi) want_osdi=1 ;;
      *) echo "sim_require_pdk: unknown option '$1'" >&2; exit 2 ;;
    esac
    shift
  done

  if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
    echo "${SIM_SCRIPT_NAME}: PDK_NOT_FOUND: no resolvable ${PDK:-ihp-sg13g2} install -- run scripts/setup-env.sh (see sim/env.sh output above)." >&2
    exit 3
  fi

  command -v ngspice >/dev/null 2>&1 || {
    echo "${SIM_SCRIPT_NAME}: NGSPICE_NOT_FOUND: ngspice not on PATH." >&2
    exit 3
  }
  # shellcheck disable=SC2034  # consumed by the sourcing runner's record
  NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

  MODELS_LIB="${SG13G2_NGSPICE_MODELS}/cornerHBT.lib"
  if [[ ! -f "${MODELS_LIB}" ]]; then
    echo "${SIM_SCRIPT_NAME}: PDK_MODEL_MISSING: cornerHBT.lib not found at ${MODELS_LIB}" >&2
    exit 3
  fi

  OSDI_DIR="${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi"
  OSDI_FILES=()
  MOS_LIB=""
  if (( want_osdi )); then
    MOS_LIB="${SG13G2_NGSPICE_MODELS}/cornerMOSlv.lib"
    OSDI_FILES=("${OSDI_DIR}/psp103.osdi" "${OSDI_DIR}/psp103_nqs.osdi" \
                "${OSDI_DIR}/r3_cmc.osdi" "${OSDI_DIR}/mosvar.osdi")
    if [[ ! -f "${MOS_LIB}" ]]; then
      echo "${SIM_SCRIPT_NAME}: PDK_MODEL_MISSING: cornerMOSlv.lib not found at ${MOS_LIB}" >&2
      exit 3
    fi
    local f
    for f in "${OSDI_FILES[@]}"; do
      if [[ ! -f "${f}" ]]; then
        echo "${SIM_SCRIPT_NAME}: OSDI_MISSING: ${f} not found -- run sim/tools/build-osdi.sh (or scripts/setup-env.sh); the MOS devices this bench instantiates will not simulate without it." >&2
        exit 3
      fi
    done
  fi

  # Installed-PDK identity: compare the install's verified release with the
  # sim/pdk.json pin, and hash the model inputs. Offline. A mismatch or an
  # unverifiable install exits 3 with a named error. A path / ngspice
  # version alone does not identify the models.
  command -v python3 >/dev/null 2>&1 || {
    echo "${SIM_SCRIPT_NAME}: PDK_IDENTITY_UNVERIFIABLE: python3 not on PATH." >&2
    exit 3
  }
  local __srp_extra=()
  if (( want_osdi )); then
    __srp_extra=("${MOS_LIB}" "${OSDI_FILES[@]}")
  fi
  local __srp_json
  if ! __srp_json="$(python3 -I "${SIM_DIR}/tools/pdk_identity.py" \
        "${SIM_DIR}/pdk.json" "${PDK_ROOT}/${PDK}" "${MODELS_LIB}" \
        "${__srp_extra[@]}")"; then
    echo "${SIM_SCRIPT_NAME}: PDK identity preflight failed (see above)." >&2
    exit 3
  fi
  SIM_PDK_PROVENANCE_JSON="${__srp_json}"
}

sim_require_numpy() {
  # sim_require_numpy
  #
  # The numpy preflight shared by every bench whose record is computed from the
  # waveform. Prints "<script-name>: PREFLIGHT: python3 numpy missing." on
  # stderr and exits 3 -- the same named-error-and-exit-3 shape sim_require_pdk
  # uses, and the same message the runners printed when each spelled it out.
  #
  # Needs, from the caller: SIM_SCRIPT_NAME (sim_require_pdk sets it; a runner
  # that does not call sim_require_pdk must set it first).
  #
  # sim/known-answer/run.sh deliberately does NOT use this: it runs its numpy
  # preflight before it sources this file, so a missing numpy is reported
  # without first resolving klt through uvx.
  python3 -I -c 'import numpy' 2>/dev/null || {
    echo "${SIM_SCRIPT_NAME}: PREFLIGHT: python3 numpy missing." >&2
    exit 3
  }
}

sim_begin_record() {
  # sim_begin_record [--suffix S] [--pathspec P]...
  #
  # The append-only record prelude every bench driver shares. Sets, in the
  # caller: REPO_GIT_SHA, DIRTY (1 if `git status --porcelain` over the
  # pathspecs is non-empty; default pathspecs: sim scripts), RECORD_ID
  # (UTC timestamp-sha[S]), OUT (${SCRIPT_DIR}/corners/<id>), RECORDS_DIR
  # (${SCRIPT_DIR}/records) and PROV. Creates OUT and RECORDS_DIR, and writes
  # PROV (${RECORDS_DIR}/<id>.pdk-provenance.json) when sim_require_pdk has run.
  # An id that already has artifacts exits 4 and nothing is overwritten.
  #
  # Needs, from the caller: SCRIPT_DIR and SIM_SCRIPT_NAME (sim_require_pdk, or
  # set it yourself).
  local suffix="" pathspec=()
  while (( $# > 0 )); do
    case "$1" in
      --suffix) (( $# >= 2 )) || { echo "sim_begin_record: --suffix needs a value" >&2; exit 2; }
                suffix="$2"; shift ;;
      --pathspec) pathspec+=("${2:?sim_begin_record: --pathspec needs a value}"); shift ;;
      *) echo "sim_begin_record: unknown option '$1'" >&2; exit 2 ;;
    esac
    shift
  done
  (( ${#pathspec[@]} )) || pathspec=(sim scripts)

  REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  DIRTY=0
  # shellcheck disable=SC2034  # DIRTY is consumed by the sourcing runner's record
  [[ -z "$(git -C "${REPO_ROOT}" status --porcelain -- "${pathspec[@]}" 2>/dev/null)" ]] || DIRTY=1
  RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}${suffix}"
  OUT="${SCRIPT_DIR}/corners/${RECORD_ID}"
  RECORDS_DIR="${SCRIPT_DIR}/records"
  if [[ -e "${OUT}" ]] || compgen -G "${RECORDS_DIR}/${RECORD_ID}*" >/dev/null; then
    echo "${SIM_SCRIPT_NAME}: record id ${RECORD_ID} already has artifacts; refusing to reuse it. Wait a second and rerun." >&2
    exit 4
  fi
  mkdir -p "${OUT}" "${RECORDS_DIR}"
  PROV="${RECORDS_DIR}/${RECORD_ID}.pdk-provenance.json"
  if [[ -n "${SIM_PDK_PROVENANCE_JSON}" ]]; then
    printf '%s\n' "${SIM_PDK_PROVENANCE_JSON}" > "${PROV}"
  fi
}

# shellcheck disable=SC2120  # the option below is passed by a caller in
# another file (sim/device-npn13g2/run_device.sh), which shellcheck cannot see.
sim_gate_logs() {
  # sim_gate_logs [--tolerate-recovered-gmin] [--skip-errored-from <report.json>]
  #
  # Per-corner log gate over every ngspice.log under ${OUT}: a log carrying any
  # model/convergence error pattern fails its point -- the point is named on
  # stderr and the caller's `failed=1` is set. This gate reads logs only; the
  # `klt sim` exit code is gated separately, in sim_run_one.
  #
  # `find`, not a fixed-depth glob: the batch backend's sharded collects land
  # per-corner logs at OUT/<bench>/<klt-sim-shard>/<corner>/ngspice.log (three
  # levels) while local and resumed collects land them at
  # OUT/<bench>/<corner>/ngspice.log (two); the one-level-deeper layout is the
  # committed evidence of every fleet-grid bench (sim/psat-sweep/corners/),
  # so a glob that matches only the shallow one gates nothing on those runs.
  #
  # --tolerate-recovered-gmin: a "singular matrix" warning that ngspice's
  # dynamic gmin stepping recovered from (klt grades the corner `pass` with a
  # warning diagnostic) is left to the record's solver-diagnostics section
  # instead of failing the gate; every other error pattern still fails it.
  #
  # --skip-errored-from <report.json>: the characterization-matrix waiver (issue
  # #173): exactly the logs of corners the report itself grades `status:
  # "error"` are skipped, each named on stderr as an errored corner -- their
  # diagnostics are the record's "did not simulate" cells, and failing them
  # here would refuse the honest record the spec asks for (a failing cell is a
  # finding, not a reason to narrow the box). NOTHING else is waived: a corner
  # the report grades pass/fail/inconclusive is still gated strictly, and an
  # unreadable report waives nothing (every log gates, the strict default). The
  # error statuses must come from klt's own report, never from a local re-parse
  # of the log text.
  #
  # Needs, from the caller: OUT, SIM_SCRIPT_NAME.
  local tolerate=0 skip_report="" log filtered
  local patterns='Unable to find definition of model|couldn.t be loaded|Unknown model type|no such file|singular matrix|Timestep too small|convergence problem|doAnalyses: .*(failed|error)|Error:'
  while (( $# > 0 )); do
    case "$1" in
      "") ;;
      --tolerate-recovered-gmin) tolerate=1 ;;
      --skip-errored-from)
        (( $# >= 2 )) || { echo "sim_gate_logs: --skip-errored-from needs a value" >&2; exit 2; }
        skip_report="$2"; shift ;;
      *) echo "sim_gate_logs: unknown option '$1'" >&2; exit 2 ;;
    esac
    shift
  done
  local -A skip_logs=()
  if [[ -n "${skip_report}" ]]; then
    while IFS= read -r __sl; do skip_logs["${__sl}"]=1; done < <(python3 -I - "${skip_report}" <<'PY' || true
import json
import sys

try:
    doc = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)  # unreadable report: waive nothing, gate everything
for c in doc.get("corners") or []:
    if c.get("status") == "error":
        log = (c.get("artifacts") or {}).get("log")
        if log:
            print(log)
PY
    )
  fi
  while IFS= read -r log; do
    [[ -f "${log}" ]] || continue
    if [[ -n "${skip_report}" && -n "${skip_logs[${log}]+x}" ]]; then
      echo "${SIM_SCRIPT_NAME}: errored corner (skipped, recorded as a cell that did not simulate): ${log#"${OUT}/"}" >&2
      continue
    fi
    filtered="${log}"
    if (( tolerate )) && grep -q 'Dynamic gmin stepping completed' "${log}"; then
      filtered="$(mktemp)"
      grep -v '^Warning: singular matrix' "${log}" > "${filtered}" || true
    fi
    if grep -qiE "${patterns}" "${filtered}"; then
      echo "${SIM_SCRIPT_NAME}: FAILED ${log#"${OUT}/"} -- see ${log}" >&2
      failed=1
    fi
    [[ "${filtered}" == "${log}" ]] || rm -f "${filtered}"
  done < <(find "${OUT}" -name ngspice.log -type f 2>/dev/null)
}

sim_resolve_klt() {
  # sim_resolve_klt
  #
  # Resolves the klt command: the version pinned in sim/toolchain.json through
  # uvx, or KLT="path/to/klt" to override. Sets, in the caller: KLT_PIN,
  # KLT_CMD (array) and KLT_VERSION.
  KLT_PIN="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["klt"]["pin"])' \
      "${SIM_DIR}/toolchain.json")" || { echo "sim_resolve_klt: cannot read klt.pin from ${SIM_DIR}/toolchain.json" >&2; return 1; }
  # shellcheck disable=SC2206,SC2034  # intentional word-splitting; consumed by the runner
  KLT_CMD=(${KLT:-uvx --from "klayout-tools==${KLT_PIN}" klt})
  # shellcheck disable=SC2034
  KLT_VERSION="$("${KLT_CMD[@]}" --version 2>&1 | tail -1)"
}

sim_run_one() {
  # sim_run_one <name> [--allow-errored-corners] [extra klt args]
  #
  # Runs `klt sim` on <name>.request.json (in the caller's SCRIPT_DIR) into
  # ${OUT}/<name>, with the report and stderr beside it. One invocation: a batch
  # submit refused for fleet capacity is waited out by klt itself -- every grid
  # bench asks for a 600 s wait, through the request's `batch.capacity_wait_s`
  # or a `--wait-for-capacity 600` passed in here (sim/README.md, "Running
  # grids") -- so there is no shell-level resubmit and no job pool. Any failure,
  # including a capacity refusal that outlasts that wait, is reported and sets
  # the caller's `failed=1`; nothing is ever retried locally.
  #
  # Any non-zero klt exit is a failure, for every bench -- except exit 4 under
  # `--allow-errored-corners`: klt exits 4 when corners ERRORED (report
  # envelope `status: error`, per-corner `status: error` with diagnostics), and
  # a characterization matrix bench (issue #173) must RECORD those corners as
  # cells that did not simulate, not refuse the record: the spec forbids
  # narrowing the box to make cells pass. The waiver is exit-4 only and the
  # coverage gates the callers run afterwards (sim_gate_logs
  # --skip-errored-from, sim_corner_matrix_check report mode) still judge the
  # report; every other exit, and every bench that does not ask, stays strict.
  # A waveform-only request sets `options.capture_only: true`, so klt itself
  # grades a run whose corners all passed `pass` and exits 0 (and refuses the
  # option on a request that declares measurements); the wrapper carries no
  # per-bench exception.
  #
  # Needs, from the caller: SCRIPT_DIR, OUT, KLT_CMD (sim_resolve_klt), SIM_SCRIPT_NAME.
  local name="$1" rc=0 allow_errored=0
  shift
  if [[ "${1:-}" == "--allow-errored-corners" ]]; then
    allow_errored=1
    shift
  fi
  echo "${SIM_SCRIPT_NAME}: klt sim ${name} $*"
  ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --format json -o "${OUT}/${name}" "$@" \
      "${name}.request.json" > "${OUT}/${name}.report.json" 2> "${OUT}/${name}.stderr" ) || rc=$?
  (( rc == 0 )) && return 0
  if (( rc == 4 && allow_errored )); then
    echo "${SIM_SCRIPT_NAME}: ${name}: klt sim exited 4 (errored corners; recorded" \
         "per corner in the report) -- allowed for this characterization bench;" \
         "the coverage gates judge the report." >&2
    return 0
  fi
  echo "${SIM_SCRIPT_NAME}: ${name}: klt sim exited ${rc} (see ${OUT}/${name}.stderr); no local fallback is attempted." >&2
  # shellcheck disable=SC2034  # read by the sourcing runner
  failed=1
}

sim_dry_run_corner_ids() {
  # sim_dry_run_corner_ids <name>
  #
  # The pre-submit unit screen for a matrix bench (issue #173): run
  # `klt sim --dry-run` on <name>.request.json (nothing is simulated or
  # submitted), then fail unless every expanded unit has a DISTINCT
  # corner_id. klt names a unit and its artifact directory by that id and
  # formats supply axis values to three decimals, so two close values
  # collapse onto one unit (2AMLogic/klayout-tools#5870) -- silently, unless
  # something counts. This is the authoritative screen (the generator holds a
  # mirror of the format that fails at generation time); both run before any
  # fleet submit. Writes ${OUT}/<name>.dry-run.json (committed evidence of
  # the check).
  #
  # Needs, from the caller: SCRIPT_DIR, OUT, KLT_CMD (sim_resolve_klt), SIM_SCRIPT_NAME.
  local name="$1" rc=0
  ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --dry-run --format json \
      "${name}.request.json" > "${OUT}/${name}.dry-run.json" 2> "${OUT}/${name}.dry-run.stderr" ) || rc=$?
  if (( rc != 0 )); then
    echo "${SIM_SCRIPT_NAME}: ${name}: klt sim --dry-run exited ${rc} (see ${OUT}/${name}.dry-run.stderr)" >&2
    return 1
  fi
  python3 -I - "${OUT}/${name}.dry-run.json" "${SIM_SCRIPT_NAME}: ${name}" <<'PY' || return 1
import collections
import json
import sys

doc = json.load(open(sys.argv[1]))
ids = [u.get("corner_id") for u in (doc.get("units") or [])]
dups = sorted(i for i, n in collections.Counter(ids).items() if n > 1 or i is None)
if not ids or dups:
    print(f"{sys.argv[2]}: DRY_RUN_CORNER_ID_COLLISION: {dups[:5]}"
          f" ({len(dups)} bad of {len(ids)} units) -- klt collapses close supply"
          " axis values onto one corner id (klayout-tools#5870); not submitting.",
          file=sys.stderr)
    sys.exit(1)
print(f"{sys.argv[2]}: dry run: {len(ids)} units, corner ids distinct")
PY
}

sim_corner_matrix_check() {
  # sim_corner_matrix_check <matrix.json> <request|report> <file> <dest-stem>
  #
  # The `klt corner-matrix` gate of a matrix bench (issue #173): diff the
  # declared matrix against the request BEFORE any submit (conformance:
  # missing/extra/duplicate tuples) and against the finished report AFTER
  # (completeness: every tuple once, simulated). Writes the JSON verdict to
  # ${OUT}/<dest-stem>.corner-matrix-<request|report>.json -- the committed
  # artifact the record cites.
  #
  # What fails the bench is INCOMPLETE COVERAGE, not a failing corner: a
  # characterization sweep that records a failing or errored corner is the
  # run's honest output (the spec forbids narrowing the box to make cells
  # pass). klt's own `complete` cannot say that: its `not_simulated` list
  # conflates a tuple that never ran with a tuple whose corner ran and errored,
  # so a matrix whose cells legitimately fail to converge can never check
  # clean (2AMLogic/klayout-tools#7008). The gate therefore reads the verdict's
  # tuple sets itself and accepts exactly the errored-cells case: missing /
  # extra / duplicate all empty (a non-empty one is the tool finding the
  # bench's own missing/duplicated-cell failure -- still a hard fail) AND
  # every not_simulated tuple a corner the REPORT itself grades non-pass
  # (cross-checked against the report, so a tuple that never ran still fails).
  # Outcome quality is the record's job either way.
  #
  # Needs, from the caller: OUT, KLT_CMD (sim_resolve_klt), SIM_SCRIPT_NAME.
  local matrix="$1" mode="$2" src="$3" dest="$4" rc=0
  "${KLT_CMD[@]}" corner-matrix check "${matrix}" "--${mode}" "${src}" --format json \
      > "${OUT}/${dest}.corner-matrix-${mode}.json" 2> "${OUT}/${dest}.corner-matrix-${mode}.stderr" || rc=$?
  if (( rc != 0 && rc != 3 )); then
    echo "${SIM_SCRIPT_NAME}: corner-matrix ${mode} check exited ${rc} (see ${OUT}/${dest}.corner-matrix-${mode}.stderr)" >&2
    return 1
  fi
  python3 -I - "${OUT}/${dest}.corner-matrix-${mode}.json" "${SIM_SCRIPT_NAME}" "${src}" <<'PY' || return 1
import json
import sys

doc = json.load(open(sys.argv[1]))
ok = doc.get("coverage_complete")
if ok is None:
    ok = doc.get("complete")
if ok is True:
    print(f"{sys.argv[2]}: corner-matrix {doc.get('mode')} check: covers all "
          f"{doc.get('matrix_size')} declared tuples")
    sys.exit(0)

def report_corner_states(path):
    try:
        rep = json.load(open(path))
    except Exception:
        return None
    corners = rep.get("corners")
    if not isinstance(corners, list):
        return None
    return {c.get("corner_id"): c.get("status") for c in corners}

not_simulated = doc.get("not_simulated") or []
clean_sets = not doc.get("missing") and not doc.get("extra") and not doc.get("duplicate")
if clean_sets and not_simulated and sys.argv[3]:
    # The errored-cells case (2AMLogic/klayout-tools#7008): every
    # not_simulated entry is a matrix tuple, and klt matches report corners to
    # tuples by corner_id string -- so each one must be a corner the REPORT
    # itself grades non-pass. An entry with no matching non-pass corner (a
    # tuple that never ran, or a verdict shape this cross-check cannot
    # confirm) still fails below.
    states = report_corner_states(sys.argv[3])
    if states is not None:
        observed_non_pass = {cid for cid, st in states.items() if st != "pass"}
        if set(not_simulated) and set(not_simulated) <= observed_non_pass:
            print(f"{sys.argv[2]}: corner-matrix {doc.get('mode')} check: all "
                  f"{doc.get('matrix_size')} declared tuples observed once; "
                  f"{len(not_simulated)} errored (recorded as cells that did "
                  "not simulate; klt cannot check this clean, "
                  "2AMLogic/klayout-tools#7008): "
                  + ", ".join(sorted(not_simulated)))
            sys.exit(0)
print(f"{sys.argv[2]}: CORNER_MATRIX_INCOMPLETE: "
      + json.dumps({k: doc.get(k) for k in ("missing", "extra", "duplicate",
                                            "not_simulated")})
      + " -- the request/report does not cover the declared matrix.",
      file=sys.stderr)
sys.exit(1)
PY
}

sim_run_ac_bench() {
  # sim_run_ac_bench <kind>
  #
  # The whole body of the two AC bench runners, which differ only in the bench
  # name: <kind> is `gain` or `stability`, the klt request is
  # ac_<kind>.request.json and the bench directory is sim/ac-<kind>/. Holds the
  # deck-staleness gate, the record prelude, the pre-submit matrix screens
  # (corner-id distinctness, `klt corner-matrix` conformance), the single
  # `klt sim` submit (fleet work on the dispatch worker), both run gates, the
  # post-run matrix completeness check and the ac_record.py render, so a
  # change to any of them reaches both benches at once -- a gate applied to
  # one runner and missed on the other would record one bench's append-only
  # evidence through a weaker gate.
  #
  # sim/psat-sweep/run_psat_sweep.sh is deliberately NOT a caller: it submits to
  # the batch backend, renders through its own psat_record.py with a JSON
  # side-output, and deletes its waveforms afterwards.
  #
  # Exits 1 if the run, either gate or the record render failed; 2 on a bad
  # <kind>; 4 on a record-id collision (sim_begin_record).
  #
  # Needs, from the caller: SCRIPT_DIR (the bench directory -- records and
  # corners land under it), SIM_SCRIPT_NAME and NGSPICE_VERSION
  # (sim_require_pdk). Calls sim_resolve_klt itself.
  local kind="${1:-}"
  case "${kind}" in
    gain|stability) ;;
    "") echo "sim_run_ac_bench: <kind> (gain or stability) is required" >&2; exit 2 ;;
    *) echo "sim_run_ac_bench: unknown kind '${kind}' (want gain or stability)" >&2; exit 2 ;;
  esac
  local bench="ac_${kind}" dir="ac-${kind}"

  sim_resolve_klt

  # The committed deck must match the DUT netlist (fails loudly on a stale copy).
  python3 -I "${SIM_DIR}/lib/gen_dut_benches.py" --check

  # Earlier records/corners of this bench are evidence, not inputs: ignore them.
  sim_begin_record --pathspec sim --pathspec design \
    --pathspec ":!sim/${dir}/records" --pathspec ":!sim/${dir}/corners"
  local failed=0
  # A matrix bench (27 cells): screen the per-unit corner ids and check the
  # request against the declared matrix BEFORE the submit, and the finished
  # report against it after. sim_run_* set failed=1 rather than exiting, so
  # the gates below are what stop the record.
  sim_dry_run_corner_ids "${bench}" || failed=1
  sim_corner_matrix_check "${SIM_DIR}/pvt-matrix.json" request \
      "${SCRIPT_DIR}/${bench}.request.json" "${bench}" || failed=1
  # The backend is the host's (KLT_SIM_BACKEND=batch on the dispatch worker:
  # a 27-cell grid is fleet work); sim_run_one submits once -- the capacity
  # wait is the request's batch.capacity_wait_s -- and never reruns locally.
  # A characterization matrix (issue #173) RECORDS corners that errored (a
  # cell that did not simulate is a finding, not a reason to narrow the box):
  # exit 4 is waived and exactly the report's errored-corner logs skip the log
  # gate, so the record carries them as "did not simulate" rows.
  sim_run_one "${bench}" --allow-errored-corners
  # shellcheck disable=SC2119  # no --tolerate-recovered-gmin: an AC corner that
  # needed gmin stepping is not evidence these benches record.
  sim_gate_logs --skip-errored-from "${OUT}/${bench}.report.json"
  sim_corner_matrix_check "${SIM_DIR}/pvt-matrix.json" report \
      "${OUT}/${bench}.report.json" "${bench}" || failed=1
  (( failed == 0 )) || exit 1
  local rec="${RECORDS_DIR}/${RECORD_ID}.md"
  python3 -I "${SIM_DIR}/lib/ac_record.py" "${kind}" "${RECORD_ID}" "${REPO_GIT_SHA}" "${DIRTY}" \
    "${KLT_VERSION}" "${NGSPICE_VERSION}" "${OUT}/${bench}.report.json" > "${rec}" || exit 1
  echo "${SIM_SCRIPT_NAME}: record ${rec}"
}
