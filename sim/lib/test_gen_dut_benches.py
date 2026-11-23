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
def test_ac_decks_carry_the_gmin_convergence_aid(build):
    """The DC-solve option is formatted from `AC_GMIN`, never retyped (issue #188).

    Raising gmin above ngspice's 1e-12 default is what keeps the 125 C PVT
    cells' operating-point stepping free of the singular-matrix warning klt
    grades `error` on, so the deck line and the constant must not diverge --
    and neither may drift back to the default, which re-breaks the three cells.
    """
    deck = build()
    assert f".options gmin={gdb.AC_GMIN:g}\n" in deck
    assert gdb.AC_GMIN > 1e-12


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
    # The ceiling that goes with this load line, and the ropt/RL_OHM load ratio
    # (hand arithmetic -- the measured gain difference is only ~2.97 dB).
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


def test_match_network_reads_cblock_from_the_netlist(tmp_path, monkeypatch):
    """A changed Cblock must move the series branch, not be assumed 100p."""
    base = gdb.match_network(text=_array(14, 10), cell=_LL_CELL)
    half = gdb.match_network(text=_array(14, 10, cblock="50p"), cell=_LL_CELL)
    assert base["cblock_f"] == pytest.approx(100e-12, rel=1e-12)
    assert half["cblock_f"] == pytest.approx(50e-12, rel=1e-12)
    # Same Ropt, so the plain L-section is identical and only the absorption moves.
    assert half["ls_plain_h"] == pytest.approx(base["ls_plain_h"], rel=1e-12)
    assert half["ls_h"] > base["ls_h"]
    # The deck must agree with itself: the header diagram and the embedded DUT
    # read the same netlist, so both carry the changed value -- a hand-copied
    # `100p` in the diagram would stay behind while the DUT moved (issue #187).
    alt = tmp_path / "dut-50p.spice"
    alt.write_text(_array(14, 10, cblock="50p"))
    monkeypatch.setattr(gdb, "NETLIST", alt)
    header, embedded = gdb.psat_deck("match").split("* ---- DUT", 1)
    assert "Cblock 50p, ON CHIP" in header
    assert "Cblock 100p" not in header
    assert "Cblock RFOUT COLL 50p m=1" in embedded
    assert "Cblock RFOUT COLL 100p" not in embedded


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
    # The choke is described by what the arithmetic covers, not by a reactance
    # copied from the original design point (issue #187).
    assert "series Cblock but not the DUT's shunt Lchoke" in header
    assert "issue #116" in header
    assert "+j1534" not in header and "0.12%" not in header


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


def test_the_matched_grid_starts_where_the_bare_one_does():
    """The bottom must not move: the linear reference gain is measured there.

    Pins the first matched run's failure -- a grid translated up by the ~14 dB of gain
    the load drop costs starts at -22.0 dBm, where this deck already compresses, and
    `reduce_sweep` refuses the reduction (`LINEAR_REGION_NOT_FOUND`, 0.391 dB of spread
    against a 0.1 dB limit) because its three reference points are no longer linear.
    """
    bare, match = gdb.drive_grid_dbm(), gdb.drive_grid_match_dbm()
    assert match[0] == bare[0] == -36.0
    assert match[:3] == bare[:3]          # the three reference points are the bare ones


def test_the_matched_grid_reaches_above_the_bare_grids_top():
    """Saturation sits ~11 dB further up in available drive -- measured, Psat at
    Pavail -5.6 -> +5.2 dBm through the ideal lossless off-chip match -- so the
    top has to move. The top is set by ``PSAT_MATCH_TOP_DBM`` from those runs,
    not derived from the load ratio."""
    bare, match = gdb.drive_grid_dbm(), gdb.drive_grid_match_dbm()
    assert match[-1] == pytest.approx(gdb.PSAT_MATCH_TOP_DBM, abs=1e-9)
    assert match[-1] > bare[-1]


def test_the_matched_grid_fine_steps_the_whole_compressing_range():
    """AC 9's real constraint, and the second matched run's failure.

    With the bare grid's coarse/fine boundary (-16.8 dBm) the 1 dB compression point
    landed inside the 0.8 dB region: 0.912 dB of measured P_in across the bracket
    against a 0.5 dB limit, refused `SWEEP_STEP_TOO_COARSE`. Everything that might be
    compressing has to be on the 0.4 dB step, with the measured bracket (-25.6 ..
    -24.8 dBm available) well inside it.
    """
    grid = gdb.drive_grid_match_dbm()
    steps = [round(b - a, 6) for a, b in zip(grid, grid[1:])]
    boundary = gdb.PSAT_MATCH_COARSE_TOP_DBM
    assert boundary == -28.0
    # coarse only in the reference tail, fine everywhere above it
    assert {s for g, s in zip(grid, steps) if g < boundary} == {0.8}
    assert {s for g, s in zip(grid, steps) if g >= boundary} == {0.4}
    # the measured 1 dB bracket is on the fine step, with margin below it
    assert boundary < -25.6 - 2.0
    # a 0.4 dB available step stays under the 0.5 dB P_in limit at the ~1.15x observed
    assert 0.4 * 1.15 < 0.5


def test_the_matched_grid_keeps_the_specs_step_limits():
    """<= 1 dB to saturation, <= 0.5 dB through compression (spec: Psat, P1dB rows)."""
    grid = gdb.drive_grid_match_dbm()
    assert grid == sorted(grid)
    assert len(grid) == len(set(grid)), "a repeated drive point would be a wasted unit"
    steps = [round(b - a, 6) for a, b in zip(grid, grid[1:])]
    assert max(steps) <= 1.0                      # never coarser than the Psat limit
    assert set(steps) <= {0.4, 0.8}               # the bare grid's two steps, unchanged


@pytest.mark.parametrize("coarse_top,top", [(-28.0, -28.0), (-40.0, 10.0), (-28.0, -30.0)])
def test_the_matched_grid_refuses_a_degenerate_range(coarse_top, top):
    """A tail that never ends, or a top that does not extend, defeats the bench."""
    import unittest.mock as _mock
    with _mock.patch.object(gdb, "PSAT_MATCH_COARSE_TOP_DBM", coarse_top), \
            _mock.patch.object(gdb, "PSAT_MATCH_TOP_DBM", top):
        with pytest.raises(ValueError, match="the matched grid needs"):
            gdb.drive_grid_match_dbm()


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


def test_the_matched_request_carries_the_matrix_and_the_bare_one_stays_nominal():
    """The matched bench is the PVT-matrix bench (issue #173); the bare deck's
    figures are not comparable with it (its harmonic terminations differ), so it
    stays a one-cell request and evidences no judged row."""
    bare, match = gdb.psat_request("bare"), gdb.psat_request("match")
    assert "remote" not in bare                   # unchanged; its run carries the warning
    n_units = gdb.pvt_cell_count() * len(gdb.drive_grid_match_dbm())
    assert match["remote"]["hosts"] == gdb.batch_hosts(n_units, gdb.PSAT_MATCH_TIMEOUT_S)
    # Bare: one corner per drive point, at the one nominal cell.
    grid = gdb.drive_grid_dbm()
    assert [p["name"] for p in bare["corners"]["process"]] == [gdb.PROCESS_NOM]
    assert bare["corners"]["temperature_c"] == [gdb.TEMP_NOM_C]
    assert len(bare["corners"]["supply_v"]["vamp"]) == len(grid)
    assert set(bare["corners"]["supply_v"]["vcc"]) == {gdb.VCC_NOM_V}
    # Match: the declared sections x temperatures, and the drive grid crossed
    # with the supply points as parallel per-index lists (klt sweeps multiple
    # supply keys together by index -- the crossing cannot be two keys).
    axis = match["corners"]["supply_v"]
    assert [p["name"] for p in match["corners"]["process"]] == list(gdb.PVT_PROCESS_SECTIONS)
    assert match["corners"]["temperature_c"] == list(gdb.PVT_TEMP_C)
    assert len(axis["vamp"]) == len(axis["vcc"]) == len(gdb.drive_grid_match_dbm()) * len(gdb.PVT_VCC_V)
    # Every supply point carries the whole drive sweep exactly once.
    for vcc in gdb.PVT_VCC_V:
        drives = [round(p, 9) for p in (gdb.amp_v(p) for p in gdb.drive_grid_match_dbm())]
        got = [v for v, c in zip(axis["vamp"], axis["vcc"]) if c == vcc]
        assert got == drives
    # The host rule's capacity wait rides on every grid request.
    for req in (bare, match):
        assert req["batch"]["capacity_wait_s"] == 600
    assert match["netlist"] == "psat_sweep_match.spice"
    assert match["options"]["timeout_s"] == gdb.PSAT_MATCH_TIMEOUT_S


# --- The PVT corner matrix (issue #173) -----------------------------------
#
# The matrix is THE declaration: the requests' axes, the two committed
# `klt corner-matrix` files and the records' cell counts all derive from
# PVT_PROCESS_SECTIONS x PVT_TEMP_C x PVT_VCC_V. These tests pin the cell
# count, the crossing, and -- the reason klt_corner_id exists at all -- that
# every (cell, drive) pair stays a distinct unit at the three decimals klt
# rounds supply axis values to (klayout-tools#5870). No simulator or PDK.

def _load_psat_record():
    spec = importlib.util.spec_from_file_location(
        "_psat_record_matrix", os.path.join(REPO, "sim/psat-sweep/psat_record.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_declared_matrix_is_27_cells_at_nominal_plus_minus_10pct():
    assert gdb.PVT_PROCESS_SECTIONS == ("hbt_typ", "hbt_bcs", "hbt_wcs")
    assert gdb.PVT_TEMP_C == (-40.0, 27.0, 125.0)
    assert gdb.PVT_VCC_V == (0.72, 0.8, 0.88)
    assert gdb.VCC_NOM_V in gdb.PVT_VCC_V
    assert gdb.pvt_cell_count() == 27


def test_the_committed_matrix_files_are_the_declaration():
    import json
    pvt = json.load(open(os.path.join(REPO, gdb.PVT_MATRIX_REL)))
    psat = json.load(open(os.path.join(REPO, gdb.PSAT_MATCH_MATRIX_REL)))
    assert pvt["process"] == list(gdb.PVT_PROCESS_SECTIONS)
    assert pvt["temperature_c"] == list(gdb.PVT_TEMP_C)
    assert pvt["supply_v"] == {"vcc": list(gdb.PVT_VCC_V)}
    # The psat file is the same cells crossed with the drive grid: the same
    # (vamp, vcc) pairs the request carries, cell for cell.
    axis = psat["supply_v"]
    assert len(axis["vamp"]) == len(axis["vcc"])
    req = gdb.psat_request("match")["corners"]["supply_v"]
    assert axis == req
    assert set(axis["vcc"]) == set(gdb.PVT_VCC_V)
    for vcc in gdb.PVT_VCC_V:
        assert sum(1 for c in axis["vcc"] if c == vcc) == len(gdb.drive_grid_match_dbm())


def test_the_ac_requests_declare_the_same_matrix():
    for req in (gdb.ac_gain_request(), gdb.ac_stability_request()):
        assert [p["name"] for p in req["corners"]["process"]] == list(gdb.PVT_PROCESS_SECTIONS)
        assert req["corners"]["temperature_c"] == list(gdb.PVT_TEMP_C)
        assert req["corners"]["supply_v"] == {"vcc": list(gdb.PVT_VCC_V)}
        # 27 units at 300 s need more than one ceiling-sized job: the request
        # says how many shards, the same way the psat bench does.
        assert req["remote"]["hosts"] == gdb.batch_hosts(27, gdb.AC_TIMEOUT_S)
        assert req["batch"]["capacity_wait_s"] == 600


def test_the_matrix_corner_ids_are_distinct_at_three_decimals():
    """Every (cell, drive) pair is one unit: 2862 units, 2862 distinct ids.

    klt formats each supply value to three decimals in the corner id (and in
    the artifact-directory slug), so two vamp values inside one millivolt
    would collapse onto one unit (klayout-tools#5870). The drive grids step
    0.8/0.4 dB, whose worst case (~1 me-ohm... ~0.96 mV at the -36 dBm floor)
    is one bucket wide but never two points deep; this pins that.
    """
    # the units a submit would dispatch, expanded from the emitted request's
    # own axis -- the same single axis the builder screened and submitted.
    units = gdb._crossed_units(gdb.psat_request("match")["corners"]["supply_v"])
    assert len(units) == gdb.pvt_cell_count() * len(gdb.drive_grid_match_dbm()) == 2862
    assert gdb.assert_pvt_corner_ids_distinct(units) == 2862


def test_the_corner_id_mirror_matches_klts_format():
    """The mirror is load-bearing: it is what screens units pre-submit."""
    assert gdb.klt_corner_id("hbt_typ", {"vamp": 0.010023745, "vcc": 0.8}, 27) \
        == "hbt_typ/vamp=0.010_vcc=0.800V/27C"
    assert gdb.klt_corner_id("hbt_typ", {"vamp": 2.0, "vcc": 0.88}, -40) \
        == "hbt_typ/vamp=2.000_vcc=0.880V/-40C"
    assert gdb.klt_corner_id("hbt_typ", {"vcc": 0.72}, 125) == "hbt_typ/0.720V/125C"
    assert gdb.klt_corner_id("hbt_typ", {}, 27) == "hbt_typ/novdd/27C"


def test_close_supply_values_are_refused_not_merged():
    """Two drive points inside one 3-decimal bucket must fail, not collapse."""
    units = [{"process": "hbt_typ", "temperature_c": 27,
              "supply_v": {"vamp": v, "vcc": 0.8}} for v in (0.01001, 0.01002)]
    with pytest.raises(ValueError, match="klayout-tools#5870"):
        gdb.assert_pvt_corner_ids_distinct(units)


def test_outputs_emits_the_matrix_files_and_refuses_a_colliding_grid(monkeypatch):
    assert gdb.PVT_MATRIX_REL in gdb.outputs()
    assert gdb.PSAT_MATCH_MATRIX_REL in gdb.outputs()
    # A drive grid fine enough to collide at three decimals fails generation
    # itself, so a drifting grid cannot silently merge two units.
    real = gdb.drive_grid_match_dbm

    def too_fine():
        pts = real()
        pts[1] = pts[0] + 1e-6          # inside one millivolt bucket
        return pts

    monkeypatch.setattr(gdb, "drive_grid_match_dbm", too_fine)
    with pytest.raises(ValueError, match="klayout-tools#5870"):
        gdb.outputs()


# --- The P1dB linear-reference probe (issue #192) ---------------------------
#
# The spec's Output P1dB row takes its reference gain from "the linear region of
# the same sweep (drive >= 20 dB below the compressing level)". The committed
# matched grid cannot reach that region: its bottom (-36.0 dBm available) sits at
# the floor klt's 3-decimal corner-id encoding allows for <= 1 dB spaced drive
# points, and every cell's compression is only ~8-16 dB above that bottom. The
# probe is the separate bench that measures the region the grid cannot.


def test_the_reference_probe_grid_reaches_below_the_20dB_reference_line():
    """Compression only ever happens in the fine-stepped region (the coarse tail
    exists to be linear), so 20 dB below the fine region's start bounds how low
    the reference measurement must go for EVERY cell."""
    grid = gdb.P1DBREF_PROBE_GRID_DBM
    assert grid[0] <= gdb.PSAT_MATCH_COARSE_TOP_DBM - 20.0
    # uniform 4 dB spacing: the finest tested that stays corner-id-distinct down to
    # the encoding's floor (2 dB collides below -44 dBm available)
    steps = {round(b - a, 6) for a, b in zip(grid, grid[1:])}
    assert steps == {4.0}
    # the top probe point IS the committed grid's bottom: the probe bridges the
    # committed reference points instead of floating free of them
    assert grid[-1] == gdb.drive_grid_match_dbm()[0]


def test_the_reference_probe_amplitudes_stay_one_bucket_apart():
    """Each consecutive probe amplitude rounds to a different 3-decimal bucket:
    the encoding constraint that sets the 4 dB spacing, pinned as arithmetic."""
    amps = [gdb.amp_v(p) for p in gdb.P1DBREF_PROBE_GRID_DBM]
    buckets = [f"{a:.3f}" for a in amps]
    assert len(set(buckets)) == len(buckets)


def test_the_reference_probe_covers_every_declared_cell_with_distinct_ids():
    # units expanded from the emitted request's own axis -- the same single
    # axis the builder screened and submitted.
    units = gdb._crossed_units(gdb.p1dbref_probe_request()["corners"]["supply_v"])
    assert len(units) == gdb.pvt_cell_count() * len(gdb.P1DBREF_PROBE_GRID_DBM)
    assert gdb.assert_pvt_corner_ids_distinct(units) == len(units)
    # every declared cell is probed at every probe drive
    cells = {(u["process"], u["temperature_c"], round(u["supply_v"]["vcc"], 3)) for u in units}
    assert len(cells) == gdb.pvt_cell_count()


def test_the_reference_probe_request_rides_the_committed_matched_deck():
    req = gdb.p1dbref_probe_request()
    n_units = gdb.pvt_cell_count() * len(gdb.P1DBREF_PROBE_GRID_DBM)
    # same committed deck the matrix bench uses (the probe changes NO bench
    # fact: load, terminations and extraction nodes are the matched bench's)
    assert req["netlist"] == "psat_sweep_match.spice"
    match = gdb.psat_request("match")
    assert req["analysis"] == match["analysis"]
    assert req["options"] == match["options"]
    assert req["remote"]["hosts"] == gdb.batch_hosts(n_units, gdb.PSAT_MATCH_TIMEOUT_S)
    assert req["batch"]["capacity_wait_s"] == 600
    axis = req["corners"]["supply_v"]
    assert [p["name"] for p in req["corners"]["process"]] == list(gdb.PVT_PROCESS_SECTIONS)
    assert req["corners"]["temperature_c"] == list(gdb.PVT_TEMP_C)
    assert len(axis["vamp"]) == len(axis["vcc"]) == len(gdb.P1DBREF_PROBE_GRID_DBM) * len(gdb.PVT_VCC_V)
    for vcc in gdb.PVT_VCC_V:
        got = [round(p, 9) for p in (gdb.amp_v(p) for p in gdb.P1DBREF_PROBE_GRID_DBM)]
        have = [v for v, c in zip(axis["vamp"], axis["vcc"]) if c == vcc]
        assert have == got


def test_outputs_emits_the_reference_probe_request_and_refuses_a_colliding_one(monkeypatch):
    assert gdb.P1DBREF_PROBE_REQUEST_REL in gdb.outputs()
    real = gdb.P1DBREF_PROBE_GRID_DBM

    def colliding():
        return list(real[:2]) + [real[1] + 1e-6]      # inside one millivolt bucket

    monkeypatch.setattr(gdb, "P1DBREF_PROBE_GRID_DBM", colliding())
    with pytest.raises(ValueError, match="klayout-tools#5870"):
        gdb.outputs()
