"""The breakdown/window limits and the bench facts are defined once, and the
summarizers hold the *same objects* (no simulator or PDK needed).

These are the numbers every large-signal verdict in this repo is graded against, so
the regression this guards is a second copy drifting from the first: the identity
assertions below fail the moment a summarizer re-declares a limit locally instead of
importing it, which is how `sim/psat-sweep/psat_record.py` came to grade against its
own copy (issue #71).
"""
import glob
import importlib.util
import json
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
AC = _load("_ac_record", "sim/lib/ac_record.py")

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


# --- the ac-gain / ac-stability renderer restates the same bench facts (issue #92) ---

# A two-port that is neither matched nor unilateral, so every metric the record prints
# is finite and nothing below depends on a degenerate case: S11 = S22 = 0.2, S21 = 3.0,
# S12 = 0.1 under sparams.s_from_nodes' 1 V EMF behind Rs.
_AC_NODES = {"v(s1)": 1.0, "v(in1)": 0.6, "v(out1)": 1.5,
             "v(s2)": 1.0, "v(in2)": 0.05, "v(out2)": 0.6}


def _ac_report(tmp_path, freqs_hz):
    """Write a minimal passing klt report + ASCII AC raw file; return the report path."""
    names = ["frequency"] + list(_AC_NODES)
    lines = ["Title: synthetic", "Plotname: AC Analysis", "Flags: complex",
             f"No. Variables: {len(names)}", f"No. Points: {len(freqs_hz)}", "Variables:"]
    lines += [f"\t{k}\t{n}\t{'frequency' if k == 0 else 'voltage'}"
              for k, n in enumerate(names)]
    lines.append("Values:")
    for i, f in enumerate(freqs_hz):
        vals = [f"{f:.8e},0.0e+00"] + [f"{v:.8e},0.0e+00" for v in _AC_NODES.values()]
        lines.append(f" {i}\t{vals[0]}")
        lines += [f"\t{v}" for v in vals[1:]] + [""]
    raw = tmp_path / "ac.raw"
    raw.write_text("\n".join(lines) + "\n")
    rep = tmp_path / "report.json"
    rep.write_text(json.dumps({"corners": [{"status": "pass", "corner_id": "synthetic/corner",
                                            "artifacts": {"raw": str(raw)}}]}))
    return str(rep)


def _render_ac(kind, tmp_path, capsys, freqs_hz=(2.4e9, 2.4835e9)):
    rc = AC.main(["ac_record.py", kind, "rid", "sha", "0", "klt 0", "ngspice 0",
                  _ac_report(tmp_path, list(freqs_hz))])
    assert rc == 0
    return capsys.readouterr().out


def test_ac_record_holds_the_deck_generator_itself():
    """The AC renderer must import the module that owns the bench facts, not copy them."""
    assert AC.gdb is gdb


@pytest.mark.parametrize("kind", ["gain", "stability"])
def test_ac_record_conditions_follow_the_deck_generator(kind, tmp_path, capsys, monkeypatch):
    """Move the generator's nominal cell or port impedance; the record must move with it.

    This is the regression the issue describes: `VCC_NOM_V` is DR 0003 (PROPOSED), so if
    it changes the generator rewrites both AC decks and requests and the benches run at
    the new supply -- a record that had retyped "Vcc 0.8 V" would keep printing the old
    corner, which the project forbids (every figure carries its own corner).
    """
    monkeypatch.setattr(gdb, "PROCESS_NOM", "hbt_moved")
    monkeypatch.setattr(gdb, "TEMP_NOM_C", 85)
    monkeypatch.setattr(gdb, "VCC_NOM_V", 1.25)
    monkeypatch.setattr(gdb, "RS_OHM", 75.0)
    monkeypatch.setattr(gdb, "RL_OHM", 75.0)
    text = _render_ac(kind, tmp_path, capsys)
    assert "- Cell: process `hbt_moved`, 85 C ambient, Vcc 1.25 V " in text
    assert "- Source and load: 75 ohm both ports, S-parameter reference 75 ohm; " in text
    # No retyped copy of today's bench or netlist values survives anywhere in the record.
    for stale in ("hbt_typ", "27 C", "0.8 V", "50 ohm", "1 mA", "1 kohm", "100 pF", "100 nH"):
        assert stale not in text, f"sim/lib/ac_record.py still retypes {stale!r}"


def test_ac_record_port_phrasing_does_not_assume_equal_impedances(monkeypatch):
    """"both ports" is a claim about RS == RL, so it is derived rather than typed."""
    monkeypatch.setattr(gdb, "RL_OHM", 2 * gdb.RS_OHM)
    assert AC._port_z() == f"{gdb.RS_OHM:g} ohm source, {gdb.RL_OHM:g} ohm load"


def test_ac_gain_band_header_is_read_from_the_sweep(tmp_path, capsys):
    """The gain header's point count and band edges come from the data, not a literal."""
    text = _render_ac("gain", tmp_path, capsys, freqs_hz=(1.0e9, 1.5e9, 2.0e9))
    assert "## Band results (3 points, 1000-2000 MHz)" in text


def _conditions_line(lines, prefix):
    return next(ln for ln in lines if ln.startswith(prefix))


@pytest.mark.parametrize("record", sorted(glob.glob(os.path.join(
    REPO, "sim/ac-*/records/*.md"))), ids=os.path.basename)
def test_ac_record_renders_the_committed_conditions_unchanged(record, tmp_path, capsys):
    """At today's constants the two formerly-retyped lines render byte-identically.

    `sim/ac-*/records/` is append-only evidence, so this pins that single-sourcing the
    facts changed how the record is built and not what it says.
    """
    kind = "gain" if "/ac-gain/" in record else "stability"
    rendered = _render_ac(kind, tmp_path, capsys).splitlines()
    committed = open(record).read().splitlines()
    # The corner id is the run's own, so compare the nominal cell up to it.
    assert (_conditions_line(rendered, "- Cell:").split("; corner id")[0]
            == _conditions_line(committed, "- Cell:").split("; corner id")[0])
    assert (_conditions_line(rendered, "- Source and load:")
            == _conditions_line(committed, "- Source and load:"))


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
