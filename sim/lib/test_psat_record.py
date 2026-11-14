"""`psat_record.py` reduces the deck it was told to, through that deck's own nodes.

The psat bench has two variants (issue #116): the default `bare` deck, which drives a
flat 50 ohm from `RFOUT`, and `match`, which puts an ideal off-chip L-section between
`RFOUT` and that load. They do not differ only in a filename -- the matched deck moves
BOTH extraction nodes:

* **`P_out`/H2/H3.** In the bare deck `Vlsense` is a 0 V source directly on `out`, so
  `v(out) * i(vlsense)` is the load power. With a network in between, `v(out)` and the
  load current are at different nodes and their product is not a power at all.
* **Per-device `I_C`.** `stress()` takes it as `(i(Lchoke) - <boundary>) / N_UNITS`,
  which is KCL at `COLL` only when `<boundary>` is `Cblock`'s current. In the bare deck
  the load branch *is* that current; through an L-section the shunt capacitor takes part
  of it, so the load current under-reports every `I_C` **silently** -- no KeyError, no
  ExtractError, just a wrong `Ic pk mA` column and a wrong `frac_ic_outside`.

Neither failure raises anything, so the tests below are what catch them: the synthetic
waveform deliberately gives every candidate trace a DIFFERENT amplitude, so a record
reduced through the wrong node produces a different number rather than the same one.
No simulator or PDK is needed.
"""
import importlib.util
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen_dut_benches as gdb  # noqa: E402


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PSAT = _load("_psat_record_e2e", "sim/psat-sweep/psat_record.py")

# A steady sinusoid, long enough and fine enough for rf_extract (>= 100 periods,
# step <= T/200). Amplitudes are deliberately all different -- see the module docstring.
F0 = gdb.F0_HZ
N_PER = 120
PER_STEP = 400
V_OUT_A = 2.0          # v(out), the chip-boundary voltage (bare deck's load node)
V_OUTL_A = 1.2         # v(outl), the 50 ohm resistor's own node (matched deck)
I_LOAD_A = 0.030       # i(vlsense), the load current
I_BOUND_A = 0.080      # i(vbsense), the chip-boundary current -- distinctly larger
I_CHOKE = 0.200        # i(l.xdut.lchoke), the DC feed
VCC = gdb.VCC_NOM_V
I_VCC = -0.210         # ngspice sign: delivered = -i(vcc)


def _waveform(path):
    """A settled steady-state trace carrying every node both variants may ask for."""
    n = N_PER * PER_STEP + 1
    t = np.arange(n) / (F0 * PER_STEP)
    s = np.sin(2 * math.pi * F0 * t)
    traces = {
        "v(out)": V_OUT_A * s,
        "v(outl)": V_OUTL_A * s,
        "v(in)": 0.1 * s,
        "v(vcc)": np.full(n, VCC),
        "v(amp)": np.full(n, 1.0),
        "i(vbsense)": I_BOUND_A * s,
        "i(vlsense)": I_LOAD_A * s,
        "i(vcc)": np.full(n, I_VCC),
        "i(bs)": -0.002 * s,
        "i(l.xdut.lchoke)": np.full(n, I_CHOKE),
        "v(xdut.coll)": VCC + 0.5 * s,
        "v(xdut.vb)": np.full(n, 0.85),
        "v(xdut.xq1.t)": np.full(n, 0.6),
    }
    names = ["time"] + list(traces)
    cols = [t] + list(traces.values())
    doc = {"variables": [{"name": nm} for nm in names],
           "points": np.column_stack(cols).tolist()}
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return traces


def _render(tmp_path, variant):
    """Run psat_record.main for one variant; returns (markdown, json)."""
    wav = os.path.join(tmp_path, "waveform.raw.json")
    _waveform(wav)
    report = {
        "environment": {"backend": "test", "remote": "n/a"},
        "corners": [{
            "corner_id": "hbt_typ/vamp=1.000_vcc=0.800V/27C", "status": "pass",
            "supply_v": {"vamp": 1.0, "vcc": VCC}, "temperature_c": 27,
            "artifacts": {"waveform": wav},
        }],
    }
    rep_path = os.path.join(tmp_path, "report.json")
    out_json = os.path.join(tmp_path, f"rec-{variant}.json")
    with open(rep_path, "w") as fh:
        json.dump(report, fh)

    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = PSAT.main(["psat_record.py", variant, f"id-{variant}", "deadbee", "0",
                        "klt 0.9.1", "ngspice-47", rep_path, out_json])
    # One point only, so reduce_sweep cannot find a linear region; the record still
    # renders (with `Reduction refused`) and the per-point and stress tables are what
    # these tests read.
    assert rc == 0
    return buf.getvalue(), json.load(open(out_json))


# --- the node that carries per-device I_C (AC 10) --------------------------


@pytest.mark.parametrize("variant,sense_amp", [("bare", I_LOAD_A), ("match", I_BOUND_A)])
def test_ic_is_taken_from_the_variants_own_boundary_trace(tmp_path, variant, sense_amp):
    """`(i(Lchoke) - <this variant's boundary>) / N_UNITS`, and not the other one's."""
    _md, doc = _render(str(tmp_path), variant)
    st = doc["points"][0]["stress"]
    want = (I_CHOKE + sense_amp) / gdb.output_array()[0]
    assert st["ic_pk_a"] == pytest.approx(want, rel=1e-6)
    # ...and it is NOT what the other variant's node would have given. This is the
    # assertion that fails if the matched deck's I_C silently keeps using the load branch.
    other = (I_CHOKE + (I_BOUND_A if variant == "bare" else I_LOAD_A)) / gdb.output_array()[0]
    assert st["ic_pk_a"] != pytest.approx(other, rel=1e-3)


# --- the node that carries P_out and the harmonics ------------------------


@pytest.mark.parametrize("variant,v_amp", [("bare", V_OUT_A), ("match", V_OUTL_A)])
def test_p_out_is_extracted_from_the_variants_own_load_node(tmp_path, variant, v_amp):
    """P_out = <V, I> at the LOAD. The matched deck's V is the resistor's, not RFOUT's."""
    _md, doc = _render(str(tmp_path), variant)
    # Fundamental power of two co-phase sinusoids: A_v * A_i / 2.
    assert doc["points"][0]["p_out_w"] == pytest.approx(v_amp * I_LOAD_A / 2, rel=1e-6)


def test_an_unknown_variant_is_refused_rather_than_defaulted(tmp_path):
    with pytest.raises(ValueError, match="unknown psat variant"):
        _render(str(tmp_path), "matched")


# --- the prose the record must and must not carry -------------------------


COMMITTED_BARE = os.path.join(
    REPO, "sim/psat-sweep/records/20261107-125209-93cf5ae.md")


def test_the_bare_records_load_and_terminations_line_has_not_moved(tmp_path):
    """Formatting it from the bench must render the committed wording byte-for-byte.

    `20261107-125209-93cf5ae.md` is append-only evidence and is never re-rendered, so
    this compares against its committed line rather than retyping the sentence.
    """
    md, _doc = _render(str(tmp_path), "bare")
    committed = [ln for ln in open(COMMITTED_BARE).read().splitlines()
                 if ln.startswith("- Load:")]
    assert len(committed) == 1
    assert [ln for ln in md.splitlines() if ln.startswith("- Load:")] == committed


def test_the_bare_record_still_names_its_own_deck(tmp_path):
    md, _doc = _render(str(tmp_path), "bare")
    assert "Bench `sim/psat-sweep/psat_sweep.spice`" in md
    assert "psat_sweep_match" not in md
    # ...and does not grow the matched record's sections.
    assert "## Output network and the chip boundary" not in md


def test_the_matched_record_states_the_terminations_and_refuses_the_comparison(tmp_path):
    """AC 8."""
    md, _doc = _render(str(tmp_path), "match")
    net = gdb.match_network()
    assert "Bench `sim/psat-sweep/psat_sweep_match.spice`" in md
    # It must NOT claim the labelled ideal-50-ohm default.
    assert "(the default, labelled; a flat resistor)" not in md
    assert "no longer the labelled ideal-50-ohm" in md
    # Both impedances, at f0 / 2 f0 / 3 f0, at BOTH nodes.
    assert "Into the network at `RFOUT`" in md and "Seen by `COLL` through `Cblock`" in md
    for lab, _f, z_rfout, z_coll in gdb.match_impedances(net):
        assert f"{z_rfout.real:.3f} {z_rfout.imag:+.3f}j ohm" in md
        assert f"{z_coll.real:.3f} {z_coll.imag:+.3f}j ohm" in md
    # And the explicit refusal to compare with the bare record.
    assert "20261107-125209-93cf5ae" in md
    assert "are not compared" in md
    assert "not** presented as an improvement" in md
    assert "different benches, not two measurements of one quantity" in md


def test_the_matched_record_states_the_chip_boundary_and_the_ideality(tmp_path):
    """AC 3 and AC 11."""
    md, _doc = _render(str(tmp_path), "match")
    assert "chip boundary is `RFOUT`" in md
    # which elements are on which side
    assert "`Lchoke`, `Cblock`, `Cin`" in md
    assert "`Vbsense`, `Lmatch`" in md
    assert "ideal and lossless" in md.lower()
    assert "no inductor model is used" in md.lower()
    assert "DR 0001 D-1" in md
    assert "Fallback" in md and "unevidenced" in md
    assert "not counted as the chip's" in md
    assert "not a pass/fail claim" in md.lower()


def test_the_matched_record_derives_ropt_and_cites_the_load_line_row(tmp_path):
    """AC 2: the number and its provenance, not a pasted constant."""
    md, doc = _render(str(tmp_path), "match")
    net = gdb.match_network()
    assert f"Ropt = {net['ropt_ohm']:.4f} ohm at the collector" in md
    assert net["loadline_record"] in md
    assert "swing_mode saturated" in md
    # It says, in the record, that the recommended array's figure was not used.
    assert "2.5157" in md and "106-Nx" in md
    # The derivation is carried in the JSON too, so the record is checkable.
    assert doc["output_network"]["ropt_ohm"] == pytest.approx(net["ropt_ohm"], rel=1e-12)
    assert doc["variant"] == "match"
    assert doc["bench"] == "psat_sweep_match"


def test_the_matched_record_labels_tj_as_unchecked(tmp_path):
    """AC 13: the self-heating node has no known-answer check (issue #115)."""
    md, _doc = _render(str(tmp_path), "match")
    assert "#115" in md
    assert "has no \"known-answer\" check" in md or "no known-answer check yet" in md
    assert "Tj max C" in md       # the column it qualifies is still there
    assert "rest on the model card as supplied" in md
