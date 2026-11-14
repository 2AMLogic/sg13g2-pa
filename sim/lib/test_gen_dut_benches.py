"""The AC decks may only be built when the two port impedances are equal.

`sim/lib/sparams.py` `s_from_nodes` reads these decks with the voltage-ratio
forms `2 v(out)/vs`, which are S21/S12 only when the source and load
resistances are equal, and `_ac_deck` drives port 2 behind `RL_OHM` while the
records label the reference `RS_OHM`. `RS_OHM` and `RL_OHM` are two independent
constants, so nothing but the guard tested here stops a one-constant edit from
producing records whose S21, transducer gain and S22 reference are not what
their labels say (issue #99). No simulator or PDK is needed.
"""
import json
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


# --- The matched psat variant: an ideal off-chip output match (issue #116) ---
#
# Everything the matched deck presents to the array is DERIVED -- from the load-line
# record's nominal cell and from the DUT netlist's own array size and `Cblock`. These
# tests pin that derivation, and in particular that it tracks `output_array()`: the
# failure these guard against is a resistance that stays at today's 1.9048 ohm after the
# array is resized, which would load the devices nothing like the study sized them for
# and raise nothing. They mirror the `output_array()` failure-mode tests in
# `test_device_limits.py`. No simulator or PDK is needed.

_LL_CELL = {
    "supply_nominal_v": 0.8, "tolerance": "nominal", "swing_mode": "saturated",
    "vswing_v": 0.4,
    "pout": {"iq_per_nx_a": 0.0015, "pout_per_nx_w": 3.0e-4},
}


def _array(n_units, nx, cblock="100p"):
    """A minimal DUT netlist: an n_units x Nx array, the bias reference, and Cblock."""
    return ("".join(f"XQ{i} COLL VB GND GND npn13G2 Nx={nx}\n"
                    for i in range(1, n_units + 1))
            + "XQref VREF VREF GND GND npn13G2 Nx=10\n"
            + f"Cblock RFOUT COLL {cblock} m=1\n")


def test_match_network_reproduces_the_committed_derivation():
    """1.9048 ohm / 6.5506 pF / 0.6663 nH from the committed record and netlist."""
    net = gdb.match_network()
    assert net["nx_total"] == 140                       # 14 devices x Nx=10
    assert net["r_per_nx_ohm"] == pytest.approx(266.6667, abs=1e-4)
    assert net["ropt_ohm"] == pytest.approx(1.9048, abs=1e-4)
    assert net["q"] == pytest.approx(5.0249, abs=1e-4)
    assert net["cp_f"] == pytest.approx(6.5506e-12, rel=1e-5)
    assert net["ls_h"] == pytest.approx(0.6663e-9, rel=1e-4)
    # The ceiling that goes with this load line, and the gain the drop costs.
    assert net["pout_ceiling_w"] == pytest.approx(0.042, rel=1e-9)
    assert net["gain_drop_db"] == pytest.approx(-14.19, abs=0.01)


def test_match_network_tracks_output_array_rather_than_a_stale_divisor():
    """A different array must give a different Ropt -- not today's 1.9048 ohm.

    The resistance is `(vswing/iq per Nx) / total Nx`, so halving the array doubles it.
    A hardcoded or cached divisor passes every other test here and fails only this one.
    """
    ten = gdb.match_network(text=_array(10, 10), cell=_LL_CELL)
    assert ten["nx_total"] == 100
    assert ten["ropt_ohm"] == pytest.approx(266.6667 / 100, abs=1e-4)
    assert ten["ropt_ohm"] != pytest.approx(gdb.match_network()["ropt_ohm"], abs=1e-6)
    # and the Q / element values move with it, rather than being carried over
    assert ten["q"] == pytest.approx((50.0 / ten["ropt_ohm"] - 1) ** 0.5, rel=1e-9)
    assert ten["cp_f"] != pytest.approx(gdb.match_network()["cp_f"], rel=1e-6)


def test_match_network_does_not_use_the_recommended_arrays_load_ohm_ideal():
    """`nx_needed.load_ohm_ideal` (2.5157 ohm) belongs to the 106-Nx recommendation."""
    net = gdb.match_network()
    assert net["ropt_ohm"] != pytest.approx(2.5157, abs=1e-3)
    # It is the 140-Nx value, and the record's own figure is recovered at 106 Nx.
    assert net["r_per_nx_ohm"] / 106 == pytest.approx(2.515723, abs=1e-6)


def test_match_network_refuses_an_array_too_large_to_step_down_from_50_ohm():
    """Ropt >= RL_OHM has no two-element L-section: Q would be imaginary."""
    with pytest.raises(ValueError, match="L-section can only step a load DOWN"):
        gdb.match_network(text=_array(1, 2), cell=_LL_CELL)   # 266.667/2 = 133 ohm


def test_match_network_absorbs_cblock_so_the_collector_sees_a_real_load():
    """The point of the absorption: COLL, not RFOUT, is purely resistive at f0."""
    net = gdb.match_network()
    rows = {lab: (zr, zc) for lab, _f, zr, zc in gdb.match_impedances(net)}
    z_rfout, z_coll = rows["f0"]
    assert z_coll.real == pytest.approx(net["ropt_ohm"], rel=1e-9)
    assert z_coll.imag == pytest.approx(0.0, abs=1e-9)
    # RFOUT is NOT the same number -- Cblock's reactance is still in series there.
    assert z_rfout.imag == pytest.approx(-net["cblock_x_ohm"], rel=1e-9)
    assert abs(z_rfout.imag) > 0.3 * net["ropt_ohm"]
    # 2 f0 / 3 f0 are nothing like 50 ohm, which is why the record must say so.
    for lab in ("2 f0", "3 f0"):
        assert abs(rows[lab][1] - 50.0) > 20.0


def test_match_network_reads_cblock_from_the_netlist():
    """A changed Cblock must move the series branch, not be assumed 100p."""
    base = gdb.match_network(text=_array(14, 10), cell=_LL_CELL)
    half = gdb.match_network(text=_array(14, 10, cblock="50p"), cell=_LL_CELL)
    assert base["cblock_f"] == pytest.approx(100e-12, rel=1e-12)
    assert half["cblock_f"] == pytest.approx(50e-12, rel=1e-12)
    # Same Ropt, so the plain L-section is identical and only the absorption moves.
    assert half["ls_plain_h"] == pytest.approx(base["ls_plain_h"], rel=1e-12)
    assert half["ls_h"] > base["ls_h"]


@pytest.mark.parametrize("text,count", [(_array(14, 10) * 2, 2), (_array(14, 10).replace(
    "Cblock RFOUT COLL 100p m=1\n", ""), 0)])
def test_cblock_farads_refuses_anything_but_one_cblock_line(text, count):
    with pytest.raises(ValueError, match=f"found {count}"):
        gdb.cblock_farads(text)


@pytest.mark.parametrize("text,want", [
    ("100p", 100e-12), ("1e-10", 1e-10), ("4.7meg", 4.7e6), ("2.2n", 2.2e-9),
    ("3m", 3e-3), ("100pF", 100e-12), ("5", 5.0), (".5n", 0.5e-9),
])
def test_spice_value_reads_the_suffixes_ngspice_documents(text, want):
    """`meg` must not be read as `m` -- a 10^9 error on a passive value."""
    assert gdb._spice_value(text) == pytest.approx(want, rel=1e-12)


def test_loadline_cell_selects_exactly_one_nominal_saturated_row():
    """The committed record has both a `saturated` and a `fixed-nominal` 0.8 V row."""
    cell = gdb.loadline_cell()
    assert cell["swing_mode"] == gdb.LOADLINE_SWING_MODE == "saturated"
    assert cell["tolerance"] == "nominal"
    assert cell["supply_nominal_v"] == gdb.VCC_NOM_V


def test_loadline_cell_refuses_an_ambiguous_or_absent_cell():
    with pytest.raises(ValueError, match="expected exactly one cell"):
        gdb.loadline_cell({"cells": [_LL_CELL, dict(_LL_CELL)]})
    with pytest.raises(ValueError, match="expected exactly one cell"):
        gdb.loadline_cell({"cells": []})


# --- psat_bench / the two decks: the variants must not be confusable ---


def _save_set(deck_text):
    """The `.save` line's trace names, as a set."""
    lines = [ln for ln in deck_text.splitlines() if ln.startswith(".save ")]
    assert len(lines) == 1
    return set(lines[0][len(".save "):].split())


def test_psat_bench_rejects_an_unknown_variant():
    with pytest.raises(ValueError, match="unknown psat variant"):
        gdb.psat_bench("matched")           # the plausible typo for "match"


def test_the_bare_psat_deck_and_request_are_byte_identical_to_the_committed_ones():
    """AC 6: adding the matched variant must not move a byte of the default bench.

    `sim/psat-sweep/records/20261107-125209-93cf5ae.*` is append-only evidence produced
    by the committed deck, and `evidence/item9.json` content-hashes the request.
    """
    assert gdb.psat_deck("bare") == open(
        os.path.join(REPO, "sim/psat-sweep/psat_sweep.spice")).read()
    assert gdb.psat_request("bare") == json.load(
        open(os.path.join(REPO, "sim/psat-sweep/psat_sweep.request.json")))
    # and the default argument is the bare variant, which the runner relies on
    assert gdb.psat_deck() == gdb.psat_deck("bare")
    assert gdb.psat_request() == gdb.psat_request("bare")


def test_the_matched_deck_saves_both_the_boundary_and_the_load_nodes():
    """AC 10. Both extraction nodes must be in the saved set or the reducer KeyErrors.

    The bare deck needs neither: one 0 V source is both its load sense and its chip
    boundary. The matched deck separates them, and this is the test that fails if a
    future edit saves only one.
    """
    bare, match = gdb.psat_bench("bare"), gdb.psat_bench("match")
    saved = _save_set(gdb.psat_deck("match"))
    for key in ("p_out_v", "p_out_i", "ic_sense_i"):
        assert match[key] in saved, f"{match[key]} ({key}) missing from the matched .save"
    # The two senses really are different traces here, and the same one in the bare deck.
    assert match["ic_sense_i"] != match["p_out_i"]
    assert bare["ic_sense_i"] == bare["p_out_i"]
    # The load's V and I are co-located (Vlsense is 0 V), which is what makes v*i a power.
    assert match["p_out_v"] == "v(outl)" and match["p_out_i"] == "i(vlsense)"
    assert match["ic_sense_i"] == "i(vbsense)"
    # Nothing the bare deck saved was dropped: the stress and port columns still work.
    assert _save_set(gdb.psat_deck("bare")) <= saved


def test_the_matched_deck_instantiates_the_derived_element_values():
    """The deck carries the derived numbers, not a rounded or retyped pair."""
    net = gdb.match_network()
    body = gdb.psat_deck("match").split("* ---- end DUT ----", 1)[1]
    ls = [ln for ln in body.splitlines() if ln.startswith("Lmatch ")]
    cp = [ln for ln in body.splitlines() if ln.startswith("Cmatch ")]
    assert len(ls) == len(cp) == 1
    assert float(ls[0].split()[3]) == pytest.approx(net["ls_h"], rel=1e-12)
    assert float(cp[0].split()[3]) == pytest.approx(net["cp_f"], rel=1e-12)
    # Series L toward the chip, shunt C across the 50 ohm side, load behind the sense.
    assert "Vbsense out onet 0" in body            # the chip boundary, at RFOUT
    assert "Lmatch onet oload" in ls[0]
    assert "Cmatch oload 0" in cp[0]
    assert f"Rl outl 0 {gdb.RL_OHM:g}" in body


def test_the_matched_deck_header_restates_the_topology_and_its_provenance():
    """AC 1 and AC 2: declared once in the generator, restated in the deck header."""
    net = gdb.match_network()
    header = gdb.psat_deck("match").split("* ---- DUT", 1)[0]
    assert f"{net['ropt_ohm']:.6f} ohm at the COLLECTOR" in header
    assert f"{1e12 * net['cp_f']:.6f} pF" in header
    assert f"{1e9 * net['ls_h']:.6f} nH" in header
    assert net["loadline_record"] in header          # cites the record it came from
    assert "swing_mode saturated" in header          # ...and the row
    assert "nx_needed.load_ohm_ideal" in header      # ...and says what it did NOT use
    # The boundary, the ideality and the deferred decision are all stated.
    assert "CHIP BOUNDARY IS RFOUT" in header
    assert "IDEAL and LOSSLESS" in header
    assert "DR 0001 D-1" in header
    assert "FALLBACK" in header
    # The harmonic terminations are called out as no longer the default.
    assert "NO LONGER THE LABELLED IDEAL-50-OHM DEFAULT" in header


def test_the_matched_terminations_prose_refuses_the_default_label():
    """The record's termination sentence must not claim the flat-resistor default."""
    bare = gdb.psat_bench("bare")["terminations_md"]
    match = gdb.psat_bench("match")["terminations_md"]
    assert "the default, labelled" in bare
    assert "the default, labelled" not in match
    assert "NOT the labelled ideal-50-ohm default" in match
    assert "is not compared" in match
    # It quotes the actual harmonic impedances, so the record cannot be read as 50 ohm.
    assert "at 2 f0" in match and "at 3 f0" in match
    assert "50 ohm" not in match.replace("ideal-50-ohm", "")


def test_the_matched_bench_record_suffix_cannot_collide_with_a_bare_record():
    assert gdb.psat_bench("bare")["suffix"] == ""
    assert gdb.psat_bench("match")["suffix"] == "-match"


def test_outputs_carries_both_psat_variants():
    """AC 6: `--check` byte-compares whatever `outputs()` lists, so both must be in it."""
    paths = set(gdb.outputs())
    assert "sim/psat-sweep/psat_sweep.spice" in paths
    assert "sim/psat-sweep/psat_sweep.request.json" in paths
    assert "sim/psat-sweep/psat_sweep_match.spice" in paths
    assert "sim/psat-sweep/psat_sweep_match.request.json" in paths


# --- The matched drive grid and its batch sharding ---


def test_the_matched_grid_is_the_bare_grid_shifted_up_and_extended():
    """AC 9's precondition: the grid has to reach where saturation moved to."""
    bare, match = gdb.drive_grid_dbm(), gdb.drive_grid_match_dbm()
    net = gdb.match_network()
    shift = round(-net["gain_drop_db"] / 0.4) * 0.4
    assert shift == pytest.approx(14.0, abs=1e-9)
    assert len(match) == len(bare) + int(round(gdb.PSAT_MATCH_HEADROOM_DB / 0.4))
    # Every bare point is present, shifted by the derived amount.
    for b, m in zip(bare, match):
        assert m == pytest.approx(b + shift, abs=1e-9)
    # ...and the extension continues the fine step past the bare grid's top.
    assert match[-1] == pytest.approx(bare[-1] + shift + gdb.PSAT_MATCH_HEADROOM_DB, abs=1e-9)
    assert match[0] == pytest.approx(-22.0, abs=1e-9)


def test_the_matched_grid_keeps_the_specs_step_limits():
    """<= 1 dB to saturation, <= 0.5 dB through compression (spec: Psat, P1dB rows)."""
    grid = gdb.drive_grid_match_dbm()
    assert grid == sorted(grid)
    steps = [round(b - a, 6) for a, b in zip(grid, grid[1:])]
    assert max(steps) <= 1.0                      # never coarser than the Psat limit
    assert set(steps) <= {0.4, 0.8}               # the bare grid's two steps, unchanged
    # The whole top of the sweep -- where P1dB and Psat land -- is on the 0.4 dB step.
    assert set(steps[len(gdb.drive_grid_dbm()) - 47:]) == {0.4}


def test_the_matched_grid_shift_tracks_the_network_rather_than_a_literal():
    """A different load line must move the grid, not leave it at today's +14 dB."""
    far = dict(_LL_CELL, vswing_v=0.04)           # 10x lower Ropt -> 10 dB more drive
    net = gdb.match_network(text=_array(14, 10), cell=far)
    grid = gdb.drive_grid_match_dbm(net)
    assert grid[0] > gdb.drive_grid_match_dbm()[0] + 9.0


def test_batch_hosts_keeps_every_shard_inside_the_fleet_ceiling():
    """The matched request's `remote.hosts`, derived the way klt assesses it."""
    import math as _math
    for units, timeout in [(87, 300), (87, 1800), (10, 300), (1, 60)]:
        hosts = gdb.batch_hosts(units, timeout)
        per_shard = _math.ceil(units / hosts)
        bound = per_shard * timeout + gdb.BATCH_JOB_OVERHEAD_S
        assert bound <= gdb.BATCH_MAX_JOB_S, (units, timeout, hosts, bound)
        # ...and it is the SMALLEST such hosts (one fewer must not fit).
        if hosts > 1:
            worse = _math.ceil(units / (hosts - 1)) * timeout + gdb.BATCH_JOB_OVERHEAD_S
            assert worse > gdb.BATCH_MAX_JOB_S
    # The bare request's 1800 s is what forces one unit per job (recommended_hosts: 72).
    assert gdb.batch_hosts(72, 1800) == 72


def test_batch_hosts_refuses_a_timeout_no_sharding_can_rescue():
    with pytest.raises(ValueError, match="no remote.hosts value fits"):
        gdb.batch_hosts(10, gdb.BATCH_MAX_JOB_S)


def test_the_matched_request_shards_and_the_bare_one_does_not():
    bare, match = gdb.psat_request("bare"), gdb.psat_request("match")
    assert "remote" not in bare                   # unchanged; its run carries the warning
    assert match["remote"]["hosts"] == gdb.batch_hosts(
        len(gdb.drive_grid_match_dbm()), gdb.PSAT_MATCH_TIMEOUT_S)
    # One corner per drive point, in both.
    for req, grid in ((bare, gdb.drive_grid_dbm()), (match, gdb.drive_grid_match_dbm())):
        assert len(req["corners"]["supply_v"]["vamp"]) == len(grid)
        assert len(req["corners"]["supply_v"]["vcc"]) == len(grid)
        # The host rule's capacity wait rides on every grid request.
        assert req["batch"]["capacity_wait_s"] == 600
    assert match["netlist"] == "psat_sweep_match.spice"
    assert match["options"]["timeout_s"] == gdb.PSAT_MATCH_TIMEOUT_S
