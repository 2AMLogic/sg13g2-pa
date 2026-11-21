#!/usr/bin/env python3
"""Render the append-only record for the ac-gain / ac-stability benches.

    ac_record.py {gain|stability} <record-id> <git-sha> <dirty> <klt-version> <ngspice-version> <klt-report.json> > record.md
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_dut_benches as gdb  # noqa: E402
import sparams as sp  # noqa: E402
from provenance import commit_line  # noqa: E402
# Every bench fact this record restates -- the nominal cell, the port impedances and the
# S-parameter reference -- lives once in gen_dut_benches.py, which generates both AC
# decks; the swept band is read back from the data. Nothing below is a retyped bench
# number, so a record cannot fall behind the deck that produced it (same rule as
# sim/psat-sweep/psat_record.py; see gen_dut_benches.py's module docstring).
# The same rule covers the record's own provenance bullet: its commit half is
# provenance.commit_line, the one place every sim/ renderer gets it from -- never
# retyped here, so every record states its provenance identically.

SPEC = "spec/target-spec.md (RATIFIED rows: Power gain, Input match, Stability small-signal)"

NETLIST_REL = "design/netlist/sg13g2-pa.spice"


def _fmt(x, n=2):
    return f"{x:.{n}f}"


def _port_z():
    """The port impedances as the record states them, from the deck generator.

    `sparams.s_from_nodes` normalizes to the source resistance, so the "both ports"
    phrasing is only honest while the two are equal -- it is tested, not typed.
    """
    if gdb.RS_OHM == gdb.RL_OHM:
        return f"{gdb.RS_OHM:g} ohm both ports"
    return f"{gdb.RS_OHM:g} ohm source, {gdb.RL_OHM:g} ohm load"


def _load_complex_vectors(path):
    """-> (freq_hz ndarray, {name: complex ndarray}) from klt's complex_vectors.json sidecar."""
    with open(path) as fh:
        side = json.load(fh)
    freq = np.array(side["frequency_hz"], dtype=float)
    data = {name: np.array(v["real"], dtype=float) + 1j * np.array(v["imag"], dtype=float)
            for name, v in side["data"].items()}
    return freq, data


def main(argv):
    kind, rid, git_sha, dirty, klt_v, ng_v, report_path = argv[1:8]
    rep = json.load(open(report_path))
    corner = rep["corners"][0]
    if corner.get("status") != "pass":
        print(f"ac_record.py: corner status {corner.get('status')!r}", file=sys.stderr)
        return 1
    freq, d = _load_complex_vectors(corner["artifacts"]["complex_vectors"])
    s = sp.s_from_nodes(d)
    st = sp.stability(s)
    out = []
    w = out.append
    w(f"# {'ac-gain' if kind == 'gain' else 'ac-stability'} record {rid}")
    w("")
    w("**Simulated** (ngspice), nominal cell only, **through ideal passives** (the DUT's "
      "`Lchoke`/`Cblock`/`Cin` are lossless, no self-resonance, no inductor model; the "
      "issue-#172 stabilisation resistors `Rin`/`Rshm`/`Rsho`/`Rdchoke` are ideal and "
      "lossy by design). "
      "Not a pass/fail claim: this record shows the bench runs cold. The topology "
      "(DR 0003) is PROPOSED and the Supply row is DRAFT.")
    w("")
    w("## Conditions")
    w("")
    w(f"- Bench: `sim/{'ac-gain' if kind == 'gain' else 'ac-stability'}/` (spec rows: {SPEC})")
    w(f"- Cell: process `{gdb.PROCESS_NOM}`, {gdb.TEMP_NOM_C:g} C ambient, "
      f"Vcc {gdb.VCC_NOM_V:g} V (nominal of DR 0003, PROPOSED); "
      f"corner id `{corner.get('corner_id', '?')}`. Not a PVT matrix (item 5).")
    w("- Quiescent point: DC operating point of the DUT's own mirror bias "
      f"(`Iref`/`Rb` of `{NETLIST_REL}`).")
    w(f"- Source and load: {_port_z()}, S-parameter reference {gdb.RS_OHM:g} ohm; "
      "two independent DUT copies (forward and reverse excitation) in one analysis.")
    w(commit_line(git_sha, dirty))
    w(f"- klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`.")
    w("")
    if kind == "gain":
        w(f"## Band results ({len(freq)} points, {freq[0] / 1e6:g}-{freq[-1] / 1e6:g} MHz)")
        w("")
        w("| f (MHz) | S21 (dB) | S11 (dB) | S22 (dB) |")
        w("|---|---|---|---|")
        for i, f in enumerate(freq):
            w(f"| {_fmt(f / 1e6, 2)} | {_fmt(sp.db20(s['s21'][i]))} | {_fmt(sp.db20(s['s11'][i]))} | "
              f"{_fmt(sp.db20(s['s22'][i]))} |")
        w("")
        s21_min = float(np.min(sp.db20(s["s21"])))
        s11_max = float(np.max(sp.db20(s["s11"])))
        w(f"Transducer gain = |S21|^2 with {gdb.RS_OHM:g} ohm source and {gdb.RL_OHM:g} ohm "
          "load. Spec targets "
          "(power gain > 15 dB, S11 < -10 dB) are reported against, not asserted: "
          f"min S21 over band {_fmt(s21_min)} dB "
          f"({s21_min - 15.0:+.2f} dB against the > 15 dB row), "
          f"worst S11 {_fmt(s11_max)} dB "
          f"({-10.0 - s11_max:+.2f} dB of margin to the -10 dB Target).")
        w("The input is **resistively matched, not losslessly matched** (issue #172): "
          "`Rin`/`Rshm` are ideal resistors and no inductor was added (DR 0001 D-1 "
          "open), so the band S11 above is that lossy network's and its gain cost is "
          "paid in S21 -- a lower S11 through resistors alone would cost more S21 "
          "than the > 15 dB row has left.")
    else:
        w(f"## Stability, {_fmt(freq[0] / 1e6, 1)} MHz - {_fmt(freq[-1] / 1e9, 2)} GHz ({len(freq)} points)")
        w("")
        imin = int(np.argmin(st["mu"]))
        w(f"- min mu = {st['mu'][imin]:.4f} at {freq[imin] / 1e9:.4g} GHz "
          f"(Edwards-Sinsky; the pass metric is mu > 1)")
        w(f"- min mu' = {float(np.min(st['mu_prime'])):.4f}")
        w(f"- min k = {float(np.min(st['k'])):.4g} (reported, not graded), "
          f"max |delta| = {float(np.max(st['abs_delta'])):.4g}")
        w(f"- negative-resistance check: max |S11| = {st['max_abs_s11']:.4f}, "
          f"max |S22| = {st['max_abs_s22']:.4f} (both must be < 1)")
        w(f"- points per decade: {len(freq) / np.log10(freq[-1] / freq[0]):.1f} (spec: >= 40)")
        verdict = "mu > 1 at every point" if float(np.min(st["mu"])) > 1 else "mu <= 1 at one or more points"
        w(f"- observation (this cell only): {verdict}.")
        w("")
        w("### Cause of the pre-#172 instability, and what changed")
        w("")
        w("Before the issue-#172 network (`records/20261118-225926-ef3c005.md`, same cell), "
          "mu was 0.0228 at 0.176 GHz and below 1 at **every** one of the 174 points. The "
          f"cause is circuit-level: the array idles with V_CE = {gdb.VCC_NOM_V:g} - V_BE "
          "≈ 22 mV (the draft supply cannot support 2 V_BE), so the BC junction is "
          "weakly forward-biased and reverse transmission through the device is only "
          "~-25 dB; with 17-29 dB of forward gain below the band, the loop product "
          "|S12*S21| ≈ 0.7 from 60 MHz to 30 GHz. At low frequency the collector "
          "additionally resonates: `Lchoke` is only j110 ohm at 176 MHz -- not a choke "
          "there -- and the load it forms with the array capacitance and the port peaks "
          "the gain at 29 dB around 176 MHz, where mu bottoms.")
        w("")
        w("The fix is four ideal resistors (no inductor added, DR 0001 D-1 open): `Rin` "
          "(series at RFIN) and `Rshm` (shunt at the `Cin` tap node) pad the input and "
          "cut the loop product in both directions; `Rsho` (shunt at RFOUT) gives the "
          "10-30 MHz output port the resistive loss it otherwise lacks (Cblock makes it "
          "a near-lossless reactance there, |S22| ≈ 1.0); `Rdchoke` (across "
          "`Lchoke`) damps the bias-feed resonance that peaks the gain below the band. "
          "The cost is in-band gain (see the ac-gain record of this design revision).")
        w("")
        w("| f (GHz) | mu | k | abs(delta) | S21 (dB) |")
        w("|---|---|---|---|---|")
        step = max(1, len(freq) // 30)
        for i in range(0, len(freq), step):
            w(f"| {freq[i] / 1e9:.4g} | {st['mu'][i]:.4g} | {st['k'][i]:.4g} | {st['abs_delta'][i]:.4g} | "
              f"{_fmt(sp.db20(s['s21'][i]))} |")
        w("")
        w("(Every ~Nth point shown; the full sweep is in the klt artifacts under `corners/<id>/`.)")
    w("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
