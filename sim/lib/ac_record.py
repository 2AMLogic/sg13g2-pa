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
# Every bench fact this record restates -- the nominal cell, the port impedances and the
# S-parameter reference -- lives once in gen_dut_benches.py, which generates both AC
# decks; the swept band is read back from the data. Nothing below is a retyped bench
# number, so a record cannot fall behind the deck that produced it (same rule as
# sim/psat-sweep/psat_record.py; see gen_dut_benches.py's module docstring).

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


def main(argv):
    kind, rid, sha, dirty, klt_v, ng_v, report_path = argv[1:8]
    rep = json.load(open(report_path))
    corner = rep["corners"][0]
    if corner.get("status") != "pass":
        print(f"ac_record.py: corner status {corner.get('status')!r}", file=sys.stderr)
        return 1
    freq, d = sp.read_ascii_raw(corner["artifacts"]["raw"])
    s = sp.s_from_nodes(d)
    st = sp.stability(s)
    out = []
    w = out.append
    w(f"# {'ac-gain' if kind == 'gain' else 'ac-stability'} record {rid}")
    w("")
    w("**Simulated** (ngspice), nominal cell only, **through ideal passives** (the DUT's "
      "`Lchoke`/`Cblock`/`Cin` are lossless, no self-resonance, no inductor model). "
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
    w(f"- Repo `{sha}` (dirty={dirty}); klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`.")
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
        w(f"Transducer gain = |S21|^2 with {gdb.RS_OHM:g} ohm source and {gdb.RL_OHM:g} ohm "
          "load. Spec targets "
          "(power gain > 15 dB, S11 < -10 dB) are reported against, not asserted: "
          f"min S21 over band {_fmt(float(np.min(sp.db20(s['s21']))))} dB, "
          f"worst S11 {_fmt(float(np.max(sp.db20(s['s11']))))} dB.")
        w("The network is not matched -- the DUT's `Cin`/`Cblock`/`Lchoke` are placeholder parts "
          f"(values in `{NETLIST_REL}`) -- so a poor S11 is expected and is the honest bench "
          "output.")
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
