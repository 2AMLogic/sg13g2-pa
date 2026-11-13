#!/usr/bin/env bash
# The repository's CI gate, written once.
#
#   scripts/check-ci.sh
#
# Runs every check `.github/workflows/signoff.yml` runs, in the same order,
# and is the whole body of `npm run check:ci`. Both entry points call this
# file, so the local gate and CI cannot check different things -- they did
# for six days (issue #80, #76), which is why this script exists. Adding a
# check here adds it to both.
#
# The checks, all of which run on a stock host without the PDK:
#
#   1. unit-tests     python3 -m pytest -q sim/lib
#   2. attest-item-1  re-attest T1 item 1 (design sources) against the
#                     committed envelope. The envelope hashes the schematic,
#                     xschemrc and the derived netlist, so a design edit --
#                     or an envelope left behind a klt pin bump -- fails here.
#                     Its one PDK-dependent check (`klt netlist --check`) is
#                     local_only, so --check skips it and compares hashes only.
#   3. attest-item-10 re-attest T1 item 10 (repo hygiene). The envelope hashes
#                     README.md, LICENSE and .github/workflows/signoff.yml
#                     byte-for-byte, so editing any of them without
#                     regenerating it fails here.
#   4. signoff-record re-render the tier verdict from the committed block
#                     manifest and byte-compare it against the committed
#                     verdict of record (manifests/sg13g2-pa.signoff.json).
#                     A manifest, vendored-checklist or klt-pin change
#                     without a regenerated record fails here.
#
# Items 2, 3 and 9 are deliberately not re-attested: item 2 needs the GDS
# generator, item 3 the DRC deck, item 9 runs the benches. See
# manifests/README.md for how to regenerate each envelope and the record.
#
# Every check runs even after one fails, so a single run names everything
# that is stale. Exit status: 0 all passed, 1 at least one check failed,
# 3 a precondition is not met (nothing was checked).
#
# Environment:
#   KLT   the klt command to use. Default: a throwaway uvx environment at
#         KLT_PIN below, the way sim/env.sh resolves klt for the benches.
#         CI sets KLT=klt so the checks run against the interpreter its
#         `pip install` put numpy and pytest in. Whatever it resolves to,
#         `klt --version` must equal KLT_PIN or this script stops -- that is
#         what keeps the workflow's one literal `pip install` pin honest.
#
# Precondition: the `python3` on PATH has `numpy` and `pytest` (README.md,
# "Unit tests"). This is not optional and `uvx --with` cannot supply it:
# `klt signoff --attest` removes its own virtualenv's bin directory from
# PATH before running an inventory check, so the item-10 `unit-tests` check
# always runs the host interpreter. A host without them is reported here by
# name rather than failing inside klt with "No module named pytest".
set -uo pipefail

KLT_PIN="0.9.1"
SELF="scripts/check-ci.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 3

# --- reporting ------------------------------------------------------------
FAILED=()

note() { printf '\n== %s\n' "$*"; }

fail() {
  # fail <check-name> <message>
  FAILED+=("$1")
  echo "[FAIL] $1: $2" >&2
  [[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::error::$1: $2"
  return 0
}

die() {
  # die <NAMED_ERROR> <what is missing> -- a precondition, so nothing ran.
  echo "${SELF}: $1: $2" >&2
  [[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::error::${SELF}: $1: $2"
  exit 3
}

# --- preconditions --------------------------------------------------------
command -v python3 >/dev/null 2>&1 \
  || die PYTHON3_NOT_FOUND "python3 is not on PATH."

for mod in pytest numpy; do
  python3 -c "import ${mod}" >/dev/null 2>&1 || die PYTEST_ENV_INCOMPLETE \
    "the python3 on PATH ($(command -v python3)) has no '${mod}'. The unit
tests and the item-10 'unit-tests' inventory check both run the host
interpreter -- 'uvx --with ${mod}' does not reach it, because klt drops its
own virtualenv from PATH. Install numpy and pytest into the python3 you run
this with (a venv is enough: python3 -m venv .venv && .venv/bin/pip install
numpy pytest, then run this script from it), or pass KLT= pointing at a klt
installed beside them, the way CI does."
done

# The klt command, and the assertion that it is the pinned release.
if [[ -n "${KLT:-}" ]]; then
  read -r -a KLT_CMD <<< "${KLT}"
else
  KLT_CMD=(uvx --from "klayout-tools==${KLT_PIN}" klt)
fi

KLT_VERSION="$("${KLT_CMD[@]}" --version 2>&1 | tail -1 | awk '{print $NF}')" \
  || die KLT_NOT_RUNNABLE "'${KLT_CMD[*]} --version' failed."
[[ "${KLT_VERSION}" == "${KLT_PIN}" ]] \
  || die KLT_VERSION_MISMATCH "'${KLT_CMD[*]}' is klt ${KLT_VERSION:-<unknown>},
but this gate is pinned to ${KLT_PIN}. Every envelope and the signoff record
were produced at the pin; a different klt grades them differently. Unset KLT
to use the pinned throwaway environment, or bump KLT_PIN in ${SELF} and
regenerate the evidence (manifests/README.md)."

echo "${SELF}: klt ${KLT_VERSION} via '${KLT_CMD[*]}'; python3 $(python3 -c 'import platform;print(platform.python_version())') at $(command -v python3)"

# --- 1. unit tests --------------------------------------------------------
note "unit-tests: python3 -m pytest -q sim/lib"
python3 -m pytest -q sim/lib \
  || fail unit-tests "python3 -m pytest -q sim/lib exited $?"

# --- 2, 3. re-attest the committed envelopes ------------------------------
for item in 1 10; do
  note "attest-item-${item}: klt signoff --attest ${item} --check evidence/item${item}.json"
  "${KLT_CMD[@]}" signoff --attest "${item}" \
      --inventory "attest/item${item}.json" \
      --check "evidence/item${item}.json" \
    || fail "attest-item-${item}" "evidence/item${item}.json no longer reproduces at klt ${KLT_PIN}
(exit $?). An input it hashes was edited, or the envelope is behind a pin
bump. Regenerate it -- and then the signoff record -- in this same change;
see manifests/README.md."
done

# --- 4. re-render the signoff record and byte-compare ---------------------
note "signoff-record: klt signoff --manifest ... | cmp manifests/sg13g2-pa.signoff.json"
TMPDIR_GATE="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_GATE}"' EXIT
fresh="${TMPDIR_GATE}/fresh-signoff.json"

rc=0
"${KLT_CMD[@]}" signoff --manifest manifests/sg13g2-pa.json \
    --tiers-doc manifests/design-evidence-tiers.md \
    --format json > "${fresh}" || rc=$?
# 0 = every T1 item met; 3 = the grader ran clean and at least one item is
# unmet. Both are valid runs and both write the record. Anything else means
# the manifest, the vendored tier doc or a cited evidence file is broken.
if [[ "${rc}" -ne 0 && "${rc}" -ne 3 ]]; then
  fail signoff-record "klt signoff exited ${rc} (expected 0 or 3): the manifest,
the vendored tier doc, or cited evidence is broken."
elif ! cmp -s "${fresh}" manifests/sg13g2-pa.signoff.json; then
  fail signoff-record "the committed verdict is stale -- a fresh klt signoff
differs from manifests/sg13g2-pa.signoff.json. Regenerate and commit the
record in this same change (see manifests/README.md)."
  diff <(python3 -I -m json.tool "${fresh}") \
       <(python3 -I -m json.tool manifests/sg13g2-pa.signoff.json) || true
else
  echo "Committed signoff record is fresh."
fi

# --- verdict --------------------------------------------------------------
if (( ${#FAILED[@]} )); then
  printf '\n%s: FAILED: %s\n' "${SELF}" "${FAILED[*]}" >&2
  exit 1
fi
printf '\n%s: all 4 checks passed (klt %s).\n' "${SELF}" "${KLT_PIN}"
