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
SIM_LOG_REQUIRE_COMPLETE=1 # 0 = do not require a BENCH_COMPLETE line (klt-generated logs have none)
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

sim_check_log() {
  # sim_check_log <point-id> <log> <rc>
  #
  # The per-point pass/fail gate: a non-zero ngspice exit, a missing
  # "BENCH_COMPLETE" marker (unless SIM_LOG_REQUIRE_COMPLETE=0), or any model/convergence error pattern fails
  # the point (returns 1 and names it on stderr).
  local point_id="$1" log="$2" rc="$3"
  local base='Unable to find definition of model|couldn.t be loaded|Unknown model type|no such file|singular matrix|Timestep too small|convergence problem|doAnalyses: .*(failed|error)|Error:'
  if [[ "${rc}" -ne 0 ]] \
    || grep -qiE "${base}" "${log}" \
    || { [[ "${SIM_LOG_REQUIRE_COMPLETE}" == 1 ]] && ! grep -q "^BENCH_COMPLETE" "${log}"; }; then
    echo "${SIM_SCRIPT_NAME}: FAILED ${point_id} (rc=${rc}) -- see ${log}" >&2
    return 1
  fi
  return 0
}

sim_resolve_klt() {
  # sim_resolve_klt
  #
  # Resolves the klt command: the version pinned in sim/toolchain.json through
  # uvx, or KLT="path/to/klt" to override. Sets, in the caller: KLT_PIN,
  # KLT_CMD (array) and KLT_VERSION.
  KLT_PIN="0.7.0"
  # shellcheck disable=SC2206,SC2034  # intentional word-splitting; consumed by the runner
  KLT_CMD=(${KLT:-uvx --from "klayout-tools==${KLT_PIN}" klt})
  # shellcheck disable=SC2034
  KLT_VERSION="$("${KLT_CMD[@]}" --version 2>&1 | tail -1)"
}

sim_run_one() {
  # sim_run_one <name> [extra klt args]
  #
  # Runs `klt sim` on <name>.request.json (in the caller's SCRIPT_DIR) into
  # ${OUT}/<name>, with the report and stderr beside it. A batch submit refused
  # for fleet capacity is resubmitted to the batch fleet (bounded: 4 attempts,
  # 60 s apart) -- a resubmit, not a job pool. Any other failure, and a capacity
  # refusal that outlasts the attempts, is reported and sets the caller's
  # `failed=1`; nothing is ever retried locally.
  #
  # Needs, from the caller: SCRIPT_DIR, OUT, KLT_CMD (sim_resolve_klt), SIM_SCRIPT_NAME.
  local name="$1" attempt rc
  shift
  for attempt in 1 2 3 4; do
    echo "${SIM_SCRIPT_NAME}: klt sim ${name} $* (attempt ${attempt})"
    rc=0
    ( cd "${SCRIPT_DIR}" && "${KLT_CMD[@]}" sim --format json -o "${OUT}/${name}" "$@" \
        "${name}.request.json" > "${OUT}/${name}.report.json" 2> "${OUT}/${name}.stderr" ) || rc=$?
    (( rc == 0 )) && return 0
    if grep -q 'BATCH_MAX_CONCURRENT_INSTANCES\|batch_no_capacity\|batch_concurrency_cap' \
         "${OUT}/${name}.report.json" "${OUT}/${name}.stderr" 2>/dev/null && (( attempt < 4 )); then
      echo "${SIM_SCRIPT_NAME}: ${name}: fleet at capacity; resubmitting to batch in 60 s" >&2
      sleep 60
      continue
    fi
    break
  done
  echo "${SIM_SCRIPT_NAME}: ${name}: klt sim exited ${rc} (see ${OUT}/${name}.stderr); no local fallback is attempted." >&2
  # shellcheck disable=SC2034  # read by the sourcing runner
  failed=1
}
