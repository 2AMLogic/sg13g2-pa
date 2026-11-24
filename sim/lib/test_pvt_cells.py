"""The PVT cell, its label and its verdict rung are defined once, and shared.

`sim/lib/pvt_cells.py` holds the cell a report corner names, the label every
matrix record prints for it and the rung a cell is graded to -- the vocabulary
`finding_trackers.line_md` counts. `sim/lib/ac_record.py` and
`sim/psat-sweep/psat_record.py` each carried a private copy of all three, and
the two cell extractions had already drifted: a corner whose `supply_v` is an
explicit null crashed the AC renderer and not the Psat one (issue #221).

Nothing raises when a second copy reappears -- it renders perfectly happily --
so the guard below is what catches it, the way `test_record_provenance.py` and
`test_units.py` guard the provenance bullet and the watts-to-dBm conversion.
The last test pins the label against the append-only evidence itself: every
committed matrix record must still read as the shared formatter renders its
cells. No simulator or PDK is needed.
"""
import ast
import glob
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIM = os.path.join(REPO, "sim")
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402
import pvt_cells  # noqa: E402
from finding_trackers import line_md  # noqa: E402

OWNER = os.path.join("sim", "lib", "pvt_cells.py")
HELPERS = ("cell_of", "cell_md", "rung")
COPIED_NAMES = set(HELPERS) | {"_" + name for name in HELPERS}
SIDECARS = sorted(
    path for path in glob.glob(os.path.join(SIM, "psat-sweep", "records", "*.json"))
    if not path.endswith((".pdk-provenance.json", ".dut.json")))


def _sim_modules():
    """Every module under sim/ except the tests, as repo-relative paths."""
    for root, _dirs, files in os.walk(SIM):
        for fn in sorted(files):
            if fn.endswith(".py") and not fn.startswith("test_"):
                yield os.path.relpath(os.path.join(root, fn), REPO)


def _function_names(rel):
    """Every function the module defines, at any nesting level."""
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=rel)
    return {node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_the_helpers_are_defined_only_in_pvt_cells_py():
    """A renderer that retypes one of the three fails here, whichever it is.

    Under either name -- the public one they share now or the private one each
    copy used to carry. The check is "no module under sim/ but pvt_cells.py
    defines them", not a list of the two renderers that used to: a third one
    cannot reintroduce a copy without joining this guard.
    """
    copies = []
    for rel in _sim_modules():
        if rel == OWNER:
            continue
        for name in sorted(_function_names(rel) & COPIED_NAMES):
            copies.append(f"{rel}: {name}")
    assert not copies, (
        "the PVT cell helpers are defined in sim/lib/pvt_cells.py and nowhere else; "
        "import cell_of / cell_md / rung instead of retyping them:\n  "
        + "\n  ".join(copies))


@pytest.mark.parametrize("ok_target,ok_fallback,want", [
    (True, True, "met"), (True, False, "met"),
    (False, True, "fallback"), (False, False, "missed")])
def test_a_rung_is_met_fallback_or_missed(ok_target, ok_fallback, want):
    assert pvt_cells.rung(ok_target, ok_fallback) == want


def test_the_rungs_are_the_vocabulary_line_md_counts():
    """`finding_trackers.line_md` counts a row's rungs by name.

    A rung word that moves here without moving there leaves every findings
    section reading "no verdict falls below its rung" over a matrix of misses.
    """
    assert line_md("Row", [pvt_cells.rung(True, False)], None) is None
    assert "`fallback`" in line_md("Row", [pvt_cells.rung(False, True)], None)
    assert "`missed`" in line_md("Row", [pvt_cells.rung(False, False)], None)


def test_a_corner_names_a_cell_by_process_temperature_and_supply():
    corner = {"corner_id": "hbt_wcs/vamp=0.050_vcc=0.720V/-40C", "status": "pass",
              "process": "hbt_wcs", "temperature_c": -40,
              "supply_v": {"vamp": 0.05, "vcc": 0.72}}
    assert pvt_cells.cell_of(corner) == {"process": "hbt_wcs", "temperature_c": -40.0,
                                         "vcc": 0.72}


@pytest.mark.parametrize("supply", [None, {}], ids=["null", "empty"])
def test_a_corner_whose_supply_is_null_or_empty_sits_at_the_nominal(supply):
    """The form the Psat copy already had: an explicit null is an absent supply.

    The AC copy called `.get` on the null and crashed before writing a record.
    """
    corner = {"status": "error", "process": "hbt_bcs", "temperature_c": 125,
              "supply_v": supply}
    assert pvt_cells.cell_of(corner) == {"process": "hbt_bcs", "temperature_c": 125.0,
                                         "vcc": gdb.VCC_NOM_V}


def test_a_corner_that_states_nothing_is_still_named():
    assert pvt_cells.cell_of({}) == {"process": "?", "temperature_c": 27.0,
                                     "vcc": gdb.VCC_NOM_V}


def test_the_nominal_supply_is_the_deck_generators(monkeypatch):
    monkeypatch.setattr(gdb, "VCC_NOM_V", 1.25)
    assert pvt_cells.cell_of({})["vcc"] == 1.25


@pytest.mark.parametrize("cell,label", [
    ({"process": "hbt_typ", "temperature_c": 27.0, "vcc": 0.8}, "`hbt_typ` / 27 C / 0.8 V"),
    ({"process": "hbt_wcs", "temperature_c": -40.0, "vcc": 0.72},
     "`hbt_wcs` / -40 C / 0.72 V"),
    ({"process": "hbt_bcs", "temperature_c": 125.0, "vcc": 0.88},
     "`hbt_bcs` / 125 C / 0.88 V")])
def test_the_label_is_the_one_every_matrix_record_prints(cell, label):
    assert pvt_cells.cell_md(cell) == label


@pytest.mark.parametrize("sidecar", SIDECARS, ids=os.path.basename)
def test_every_committed_matrix_record_still_renders_its_committed_cell_labels(sidecar):
    """`sim/psat-sweep/records/` is append-only evidence and is never re-rendered.

    A matrix sidecar carries each cell as its report named it, so the label the
    shared formatter renders from it must still be the one the committed record
    prints: single-sourcing the helpers changed how a record is built, not what
    it says. The single-cell records name no cell, so there is nothing to pin.
    """
    with open(sidecar, encoding="utf-8") as fh:
        cells = [cell["cell"] for cell in json.load(fh).get("cells", [])]
    if not cells:
        pytest.skip("single-cell record: names no PVT cell")
    with open(os.path.splitext(sidecar)[0] + ".md", encoding="utf-8") as fh:
        committed = fh.read()
    for cell in cells:
        assert pvt_cells.cell_md(cell) in committed, cell
