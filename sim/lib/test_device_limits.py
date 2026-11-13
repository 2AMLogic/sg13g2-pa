"""The breakdown/window limits and the bench facts are defined once, and the
summarizers hold the *same objects* (no simulator or PDK needed).

These are the numbers every large-signal verdict in this repo is graded against, so
the regression this guards is a second copy drifting from the first: the identity
assertions below fail the moment a summarizer re-declares a limit locally instead of
importing it, which is how `sim/psat-sweep/psat_record.py` came to grade against its
own copy (issue #71).
"""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import device_limits as dl  # noqa: E402
import gen_dut_benches as gdb  # noqa: E402


def _load(name, relpath):
    """Import a summarizer by path (they are scripts, not packages)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


LOADLINE = _load("_loadline", "sim/device-npn13g2/loadline.py")
SUMMARIZE = _load("_summarize", "sim/device-npn13g2/summarize.py")
PSAT = _load("_psat_record", "sim/psat-sweep/psat_record.py")
SMOKE = _load("_smoke_summarize", "sim/smoke/summarize.py")

# (module, attribute) pairs that must be the shared object, not a local copy.
CONSUMERS = [(LOADLINE, n) for n in ("BVCEO_MIN", "BVCBO_MIN", "VCE_WIN", "VBE_WIN",
                                     "IC_WIN_PER_NX", "TJ_MAX", "LIMITS_NOTE", "rth")]
CONSUMERS += [(SUMMARIZE, n) for n in ("IC_WIN_PER_NX", "TJ_MAX", "VBE_WIN", "VCE_WIN", "rth")]
CONSUMERS += [(PSAT, n) for n in ("BVCEO_MIN", "BVCBO_MIN", "VCE_WIN", "VBE_WIN",
                                  "IC_WIN_PER_NX", "TJ_MAX")]
CONSUMERS += [(SMOKE, n) for n in ("IC_WIN_PER_NX", "VBE_WIN", "VCE_WIN")]


@pytest.mark.parametrize("mod,name", CONSUMERS, ids=lambda x: getattr(x, "__name__", x))
def test_limit_is_the_shared_object(mod, name):
    assert getattr(mod, name) is getattr(dl, name), (
        f"{mod.__name__}.{name} is not sim/lib/device_limits.{name} -- a second copy of a "
        "graded limit has reappeared")


def test_smoke_ic_limit_follows_the_bench_array_size():
    """The smoke record's ic limit is the per-Nx window limit times the bench's Nx.

    `sim/smoke/npn_op.spice` instantiates `npn13G2` with no Nx override, so the
    device is one unit; the record must not restate `3 mA` independently of that.
    """
    assert SMOKE.SMOKE_NX == 1
    text = open(os.path.join(REPO, "sim/smoke/npn_op.spice")).read()
    inst = [ln for ln in text.splitlines() if "npn13G2" in ln and not ln.startswith("*")]
    assert len(inst) == 1, f"expected one npn13G2 instance in npn_op.spice, got {inst}"
    assert "Nx=" not in inst[0], (
        f"npn_op.spice now sets Nx explicitly ({inst[0]!r}); SMOKE_NX in "
        "sim/smoke/summarize.py must follow it")


def test_psat_per_device_current_limit_is_derived():
    """The per-device I_C limit follows the window limit and the array's Nx."""
    assert PSAT.IC_MAX_PER_DEVICE == dl.IC_WIN_PER_NX * PSAT.NX


def test_psat_bench_facts_come_from_the_deck_generator():
    """F0/Rs are restated in the record; they must be the deck's own, not a retype."""
    assert PSAT.F0 is gdb.F0_HZ
    assert PSAT.RS is gdb.RS_OHM


def test_psat_array_size_comes_from_the_netlist():
    assert (PSAT.N_UNITS, PSAT.NX) == gdb.output_array()


def test_window_bounds_are_ordered_and_minima_ranked():
    assert dl.VCE_WIN[0] < dl.VCE_WIN[1]
    assert dl.VBE_WIN[0] < dl.VBE_WIN[1]
    assert 0 < dl.BVCEO_MIN < dl.BVCBO_MIN
    assert dl.IC_WIN_PER_NX > 0 and dl.TJ_MAX > 0


def test_rth_known_answer():
    """Card scaling: 3.26 kK/W at Nx=4, (4/Nx)**0.9 elsewhere (hand-checkable)."""
    assert dl.rth(4) == pytest.approx(3.26e3)
    assert dl.rth(10) == pytest.approx(3.26e3 * 0.4 ** 0.9)
    assert dl.rth(10) < dl.rth(4)


# --- output_array(): the array size is read from the netlist, never hand-copied ---

_REF_DEVICE = "XQref VREF VREF GND GND npn13G2 Nx=10\n"


def test_output_array_counts_only_the_shared_coll_vb_devices():
    text = ("* a DUT\n"
            + "".join(f"XQ{i} COLL VB GND GND npn13G2 Nx=8\n" for i in range(1, 4))
            + _REF_DEVICE
            + "RL OUT 0 50\n")
    assert gdb.output_array(text) == (3, 8)


def test_output_array_rejects_a_mixed_nx_array():
    text = ("XQ1 COLL VB GND GND npn13G2 Nx=10\n"
            "XQ2 COLL VB GND GND npn13G2 Nx=4\n")
    with pytest.raises(ValueError, match="mixes Nx"):
        gdb.output_array(text)


def test_output_array_rejects_a_netlist_with_no_array():
    with pytest.raises(ValueError, match="no npn13G2 instance"):
        gdb.output_array("* no output stage\n" + _REF_DEVICE)


def test_output_array_matches_the_committed_dut_netlist():
    n_units, nx = gdb.output_array()
    text = gdb.netlist_text()
    # Every npn13G2 instance is either an array device or the single bias reference.
    assert sum(1 for ln in text.splitlines() if "npn13G2" in ln) == n_units + 1
    assert nx > 0
