#!/usr/bin/env bash
# run_ac_stability.sh -- ac-stability bench: mu, k, |delta|, negative-resistance check,
# 10 MHz - 30 GHz, 50 pts/decade (simulated evidence, not a result).
#
#   scripts/setup-env.sh && sim/ac-stability/run_ac_stability.sh
#
# One nominal cell (hbt_typ, 27 C, Vcc 0.8 V), a single unit, so it runs through
# `klt sim --backend local` (no ngspice -b is launched directly). Writes the
# append-only record records/<timestamp>-<sha>.md and the klt artifacts under
# corners/<id>/. Needs python3 + numpy (a venv, or `uvx --with numpy`).
# Exit codes: 0 ok; 1 the run or the record failed; 3 preflight failed; 4 id collision.
#
# The body is `sim_run_ac_bench` in ../env.sh, shared with the ac-gain bench --
# the two differ only in the bench name. This file stays the bench's own entry
# point: attest/item9.json pins it as the cold-start argv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
sim_require_pdk run_ac_stability.sh
sim_require_numpy
sim_run_ac_bench stability
