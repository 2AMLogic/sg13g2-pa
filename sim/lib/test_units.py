"""units is the single watts-to-dBm conversion, and stays the single one.

Two layers, mirroring `test_record_provenance.py`:

* value tests for `dbm`/`db10`, including the bit-identical equivalence with
  the inlined spelling the renderers used before the consolidation -- the
  refactor's no-figure-moves property asserted, not argued;
* the single-copy guard: no module outside `units.py` defines or inlines the
  conversion, except the expected-value sites that must stay independent of
  the code they check (issue #125, Out of Scope). Without this a sixth copy
  appears -- this is the third issue of its class (#111, #119, #125).
"""
import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import units  # noqa: E402

# Representative wattages: the 1 mW reference, 1 W, the deck's ceiling
# (140 x 0.3 mW as computed in `match_network`, not an exact 0.042) and
# sub-mW powers. Includes every value the curator's equivalence check used.
WATTS = (1e-3, 1.0, 0.042, 140 * 0.0003, 3.75e-4, 0.375, 2.5e-3, 1e-6)

# The guard's pattern (issue #125 acceptance criteria): `def _?dbm` for
# definitions, `log10(...1e-3)` for inlined watts-to-dBm. The trailing `\)`
# is load-bearing -- a bare `1e-3` also matches sparams.py's `1e-300` floor.
# `units.dbm`'s two-step body (`db10(w / 1e-3)`) deliberately matches only
# its `def dbm` line: `db10(` is not `log10(`.
DBM_PATTERN = re.compile(r"def _?dbm|log10\(.*1e-3\)")

# Where a match may still appear, and why: `units.py` owns the conversion;
# `P_SINE_DBM` is the known-answer check's analytic reference (expected-side
# arithmetic must stay independent of the code under test, or a fault in
# `units.dbm` would cancel in the delta); the three `test_rf_extract.py`
# sites are expected values computed against `reduce_sweep`'s output.
ALLOWED = (
    "sim/lib/units.py",
    "sim/known-answer/check_known_answer.py",
    "sim/lib/test_rf_extract.py",
)


def test_known_values():
    assert units.dbm(1e-3) == 0.0
    assert units.dbm(1.0) == 30.0
    assert f"{units.dbm(0.042):.2f}" == "16.23"  # the committed deck's ceiling
    assert units.db10(1.0) == 0.0
    assert units.db10(10) == 10.0


def test_bit_identical_to_the_inlined_spelling():
    """`units.dbm(w)` == the inlined forms it replaced, exactly, no rounding."""
    for w in WATTS:
        assert units.dbm(w) == 10 * math.log10(w / 1e-3)
        assert units.dbm(w) == 10.0 * math.log10(w / 1e-3)


def test_zero_and_negative_fail_loudly():
    """No nan/None fallback: a bad extraction must raise, not render."""
    with pytest.raises(ValueError):
        units.dbm(0.0)
    with pytest.raises(ValueError):
        units.dbm(-1e-3)


def _py_modules():
    """Every tracked-shaped .py under the repo (dotted dirs are not tracked)."""
    for root, dirs, files in os.walk(REPO):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if fn.endswith(".py"):
                yield os.path.relpath(os.path.join(root, fn), REPO)


def test_the_conversion_is_defined_once():
    """Only units.py defines dbm; no sixth copy anywhere (issue #125)."""
    hits = {}
    for rel in _py_modules():
        if rel == "sim/lib/test_units.py":
            continue  # this guard's own pattern literals, not a conversion
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if DBM_PATTERN.search(line):
                    hits.setdefault(rel, []).append((i, line.strip()))
    offenders = {rel: found for rel, found in hits.items() if rel not in ALLOWED}
    assert not offenders, (
        "a second watts-to-dBm copy appeared -- import sim/lib/units.py "
        "instead (expected-value sites must stay inlined on purpose, see "
        "issue #125 Out of Scope); found:\n"
        + "\n".join(f"  {rel}:{n}: {t}" for rel, found in offenders.items()
                    for n, t in found)
    )
    # `P_SINE_DBM` is the only allowed inlined match outside units.py, and the
    # test_rf_extract.py sites are expected values, never definitions.
    ka = [t for _, t in hits.get("sim/known-answer/check_known_answer.py", [])]
    assert len(ka) == 1 and ka[0].startswith("P_SINE_DBM = "), ka
    assert not any(
        "def dbm" in t
        for rel in ALLOWED if rel != "sim/lib/units.py"
        for _, t in hits.get(rel, [])
    ), "a test file defined its own dbm() -- compute the expected value inline"
