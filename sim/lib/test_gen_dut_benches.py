"""The AC decks may only be built when the two port impedances are equal.

`sim/lib/sparams.py` `s_from_nodes` reads these decks with the voltage-ratio
forms `2 v(out)/vs`, which are S21/S12 only when the source and load
resistances are equal, and `_ac_deck` drives port 2 behind `RL_OHM` while the
records label the reference `RS_OHM`. `RS_OHM` and `RL_OHM` are two independent
constants, so nothing but the guard tested here stops a one-constant edit from
producing records whose S21, transducer gain and S22 reference are not what
their labels say (issue #99). No simulator or PDK is needed.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402

AC_BUILDERS = [gdb.ac_gain_deck, gdb.ac_stability_deck]
AC_BUILDER_IDS = [f.__name__ for f in AC_BUILDERS]


@pytest.mark.parametrize("build", AC_BUILDERS, ids=AC_BUILDER_IDS)
def test_unequal_port_impedances_refuse_to_build_an_ac_deck(build, monkeypatch):
    """Both AC decks come from `_ac_deck`, so both must refuse."""
    monkeypatch.setattr(gdb, "RL_OHM", 2 * gdb.RS_OHM)
    with pytest.raises(ValueError) as exc:
        build()
    msg = str(exc.value)
    assert f"RS_OHM={gdb.RS_OHM:g}" in msg and f"RL_OHM={gdb.RL_OHM:g}" in msg
    assert "sparams.s_from_nodes" in msg


def test_unequal_port_impedances_refuse_to_render_the_generated_files(monkeypatch):
    """`outputs()` is what `--check` and the run scripts' pre-flight call."""
    monkeypatch.setattr(gdb, "RL_OHM", 2 * gdb.RS_OHM)
    with pytest.raises(ValueError, match="sparams.s_from_nodes"):
        gdb.outputs()


@pytest.mark.parametrize("build", AC_BUILDERS, ids=AC_BUILDER_IDS)
def test_equal_non_default_port_impedances_do_not_raise(build, monkeypatch):
    """The guard is on inequality, not on the value 50."""
    monkeypatch.setattr(gdb, "RS_OHM", 75.0)
    monkeypatch.setattr(gdb, "RL_OHM", 75.0)
    build()


def test_ac_deck_header_ports_are_formatted_from_the_constants(monkeypatch):
    """The two X1/X2 header lines are derived, not retyped as `50 ohm` literals."""
    monkeypatch.setattr(gdb, "RS_OHM", 75.0)
    monkeypatch.setattr(gdb, "RL_OHM", 75.0)
    header = gdb.ac_gain_deck().split("* ---- DUT", 1)[0]
    assert "75 ohm load at RFOUT" in header
    assert "75 ohm termination at RFIN" in header
    assert "reference 75 ohm" in header
    assert "50 ohm" not in header


def _port_lines(text):
    return [ln for ln in text.splitlines() if ln.startswith(("*   X1:", "*   X2:"))]


@pytest.mark.parametrize("build,deck", list(zip(AC_BUILDERS, [
    "sim/ac-gain/ac_gain.spice", "sim/ac-stability/ac_stability.spice"])),
    ids=AC_BUILDER_IDS)
def test_formatted_port_lines_match_the_committed_decks(build, deck):
    """At today's equal constants the formatted lines render byte-identically.

    Formatting them from `RL_OHM` / `RS_OHM` must not move a byte of committed
    evidence (`sim/ac-*/corners/` holds copies of these decks), so this compares
    the generated lines against the committed ones rather than retyping them.
    """
    committed = _port_lines(open(os.path.join(REPO, deck)).read())
    assert len(committed) == 2
    assert _port_lines(build()) == committed
