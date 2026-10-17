#!/usr/bin/env bash
# setup-env.sh -- the single cold-start entry for this repo's simulation
# environment.
#
#   scripts/setup-env.sh           # fetch the pinned PDK, build OSDI, verify
#   scripts/setup-env.sh --check   # verify only (offline, no fetch, no build)
#
# Steps:
#   1. preflight the host tools (ngspice, python3, curl, tar);
#   2. fetch klayout-tools' scripts/fetch-ihp-sg13g2.sh at the commit pinned
#      below, verify its sha256, and run it (it downloads IHP-Open-PDK at
#      the release pinned in sim/pdk.json and fails closed on its own
#      tarball checksum);
#   3. verify the installed release against sim/pdk.json
#      (sim/tools/pdk_identity.py);
#   4. build the OSDI models with sim/tools/build-osdi.sh and check they load.
#
# Everything lands in $SG13G2_TOOLS_CACHE (default ~/.cache/sg13g2-pa); no
# host-wide tool is installed or modified. Exit codes: 0 ok; 2 usage;
# 3 a named precondition failed; 4 a checksum mismatch. Every failure prints
# "setup-env.sh: <NAMED_ERROR>: ...":
#   NGSPICE_NOT_FOUND  PYTHON_NOT_FOUND  CURL_NOT_FOUND
#   FETCH_SCRIPT_CHECKSUM_MISMATCH  PDK_CHECKSUM_MISMATCH  PDK_FETCH_FAILED
#   PDK_IDENTITY_MISMATCH  PDK_IDENTITY_UNVERIFIABLE  PDK_NOT_FOUND
#   OSDI_MISSING (names sim/tools/build-osdi.sh)  OSDI_BUILD_FAILED
set -euo pipefail

# --------------------------------------------------------------------------
# Pins. KLT_COMMIT is a klayout-tools `main` commit; FETCH_SCRIPT_SHA256 is
# the sha256 of scripts/fetch-ihp-sg13g2.sh at that commit (re-derive with
# curl -fsSL .../<commit>/scripts/fetch-ihp-sg13g2.sh | sha256sum when
# bumping both). The PDK release itself is pinned inside that script and in
# sim/pdk.json; pdk_identity.py cross-checks the two.
# --------------------------------------------------------------------------
KLT_REPO="2AMLogic/klayout-tools"
KLT_COMMIT="e88f211fa485959b382e2596c86648ce4e66ea78"
FETCH_SCRIPT_SHA256="bdb2c8debbe345797fa4334d5272a99f9596a932891f8d9da01b0c14b33140f7"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CHECK_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "setup-env.sh: unknown argument '${arg}'" >&2; exit 2 ;;
  esac
done

die() { # die <code> <NAME> <message>
  local code="$1" name="$2"; shift 2
  echo "setup-env.sh: ${name}: $*" >&2
  exit "${code}"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# --- 1. host tools --------------------------------------------------------
command -v ngspice >/dev/null 2>&1 || die 3 NGSPICE_NOT_FOUND "ngspice is not on PATH (this script does not install host tools; see sim/toolchain.json for the floor)."
command -v python3 >/dev/null 2>&1 || die 3 PYTHON_NOT_FOUND "python3 is not on PATH."
if (( ! CHECK_ONLY )); then
  command -v curl >/dev/null 2>&1 || die 3 CURL_NOT_FOUND "curl is not on PATH."
  command -v tar  >/dev/null 2>&1 || die 3 CURL_NOT_FOUND "tar is not on PATH."
fi

CACHE="${SG13G2_TOOLS_CACHE:-${HOME}/.cache/sg13g2-pa}"
export SG13G2_TOOLS_CACHE="${CACHE}"
KLT_DIR="${CACHE}/klayout-tools-${KLT_COMMIT:0:12}"
FETCHED_ROOT="${KLT_DIR}/pdks/ihp-open-pdk"

# --- 2. fetch the PDK ------------------------------------------------------
if (( ! CHECK_ONLY )) && [[ -z "${PDK_ROOT:-}" ]]; then
  mkdir -p "${KLT_DIR}/scripts"
  fetch="${KLT_DIR}/scripts/fetch-ihp-sg13g2.sh"
  if [[ ! -f "${fetch}" ]] || [[ "$(sha256_of "${fetch}")" != "${FETCH_SCRIPT_SHA256}" ]]; then
    curl -fsSL -o "${fetch}.part" \
      "https://raw.githubusercontent.com/${KLT_REPO}/${KLT_COMMIT}/scripts/fetch-ihp-sg13g2.sh" \
      || die 3 PDK_FETCH_FAILED "could not download fetch-ihp-sg13g2.sh from ${KLT_REPO}@${KLT_COMMIT:0:12}."
    got="$(sha256_of "${fetch}.part")"
    if [[ "${got}" != "${FETCH_SCRIPT_SHA256}" ]]; then
      rm -f "${fetch}.part"
      die 4 FETCH_SCRIPT_CHECKSUM_MISMATCH "fetch-ihp-sg13g2.sh@${KLT_COMMIT:0:12}: expected ${FETCH_SCRIPT_SHA256}, got ${got}; refusing to run it."
    fi
    mv "${fetch}.part" "${fetch}"
  fi
  chmod +x "${fetch}"
  fetch_log="$(mktemp)"
  if ! "${fetch}" >"${fetch_log}" 2>&1; then
    cat "${fetch_log}" >&2
    if grep -q 'checksum mismatch' "${fetch_log}"; then
      rm -f "${fetch_log}"
      die 4 PDK_CHECKSUM_MISMATCH "the IHP-Open-PDK tarball failed its pinned sha256 (see above); nothing was installed."
    fi
    rm -f "${fetch_log}"
    die 3 PDK_FETCH_FAILED "fetch-ihp-sg13g2.sh failed (see above)."
  fi
  tail -3 "${fetch_log}"
  rm -f "${fetch_log}"
  ln -sfn "${FETCHED_ROOT}" "${CACHE}/pdk-root"
fi

# --- 3. resolve + verify identity -----------------------------------------
# shellcheck source=/dev/null
source "${REPO_ROOT}/sim/env.sh"
[[ -n "${PDK_ROOT:-}" && -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]] \
  || die 3 PDK_NOT_FOUND "no ${PDK} install resolved; run scripts/setup-env.sh without --check."

if ! python3 -I "${REPO_ROOT}/sim/tools/pdk_identity.py" \
      "${REPO_ROOT}/sim/pdk.json" "${PDK_ROOT}/${PDK}" \
      "${SG13G2_NGSPICE_MODELS}/cornerHBT.lib" >/dev/null; then
  # pdk_identity.py already printed PDK_IDENTITY_MISMATCH / _UNVERIFIABLE /
  # PDK_MODEL_INPUT_MISSING on stderr; re-label it with this script's prefix.
  die 3 PDK_IDENTITY_MISMATCH "installed PDK at ${PDK_ROOT}/${PDK} does not match sim/pdk.json (see the line above)."
fi
echo "setup-env.sh: PDK identity OK ($(cat "${PDK_ROOT}/.fetched-version" 2>/dev/null || cat "${PDK_ROOT}/${PDK}/.fetched-version" 2>/dev/null || echo "git tag"))"

# --- 4. OSDI ---------------------------------------------------------------
# build-osdi.sh status 5 = objects present but this host's ngspice is too old
# to load OSDI 0.4 (NGSPICE_TOO_OLD_FOR_OSDI). The objects are still what
# `klt sim --backend batch` stages to the fleet, so with the batch backend
# exported that is a warning; otherwise it is a failure.
osdi_rc=0
if (( CHECK_ONLY )); then
  "${REPO_ROOT}/sim/tools/build-osdi.sh" --check || osdi_rc=$?
else
  "${REPO_ROOT}/sim/tools/build-osdi.sh" || osdi_rc=$?
fi
case "${osdi_rc}" in
  0) ;;
  5)
    if [[ "${KLT_SIM_BACKEND:-}" == "batch" ]]; then
      echo "setup-env.sh: WARNING NGSPICE_TOO_OLD_FOR_OSDI: the MOS (OSDI) decks cannot run on this host's ngspice; KLT_SIM_BACKEND=batch, so they run on the fleet. Local MOS simulation is unavailable here." >&2
    else
      die 3 NGSPICE_TOO_OLD_FOR_OSDI "OSDI objects are built but ngspice on PATH is older than 44, so MOS decks cannot run locally; export KLT_SIM_BACKEND=batch to run them on the fleet, or use ngspice >= 44."
    fi
    ;;
  *) die 3 OSDI_MISSING "OSDI models absent, not built or not loadable; run sim/tools/build-osdi.sh (or scripts/setup-env.sh without --check)." ;;
esac

echo "setup-env.sh: ready. PDK_ROOT=${PDK_ROOT} PDK=${PDK}"
echo "setup-env.sh: next: sim/smoke/run_smoke.sh"
