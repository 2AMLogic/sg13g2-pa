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


def _cell_of(corner):
    return {"process": corner.get("process", "?"),
            "temperature_c": float(corner.get("temperature_c", 27)),
            "vcc": float(corner.get("supply_v", {}).get("vcc", gdb.VCC_NOM_V))}


def _cell_md(cell):
    return f"`{cell['process']}` / {cell['temperature_c']:g} C / {cell['vcc']:g} V"


def _rung(ok_target, ok_fallback):
    return "met" if ok_target else ("fallback" if ok_fallback else "missed")


def _render_matrix(kind, rid, git_sha, dirty, klt_v, ng_v, rep):
    """The PVT-matrix record (issue #173): one row per declared cell, graded
    against the RATIFIED rows, labelled provisional while the Supply row is
    DRAFT. Full per-frequency sweeps stay in the klt artifacts."""
    import spec_rows as sr
    rows, failures = [], []
    for c in rep["corners"]:
        cell = _cell_of(c)
        if c.get("status") != "pass":
            failures.append((cell, c.get("corner_id", "?"), c.get("status")))
            continue
        freq, d = _load_complex_vectors(c["artifacts"]["complex_vectors"])
        s = sp.s_from_nodes(d)
        st = sp.stability(s)
        rows.append({"cell": cell, "freq": freq, "s": s, "st": st,
                     "corner_id": c.get("corner_id", "?")})
    out = []
    w = out.append
    bench_dir = "ac-gain" if kind == "gain" else "ac-stability"
    w(f"# {'ac-gain' if kind == 'gain' else 'ac-stability'} record {rid} -- PVT matrix, "
      f"{len(rows)} cells")
    w("")
    w(f"**PROVISIONAL: Supply row DRAFT.** The {gdb.VCC_NOM_V:g} V nominal the "
      f"{gdb.PVT_VCC_V[0]:g}/{gdb.VCC_NOM_V:g}/{gdb.PVT_VCC_V[2]:g} V supply points hang "
      "off is DR 0003, PROPOSED -- the spec's Supply row is not ratified, so no verdict "
      "below is a pass claim; each is a per-cell finding.")
    w("")
    w("**Simulated** (ngspice), **through ideal passives** (the DUT's `Lchoke`/`Cblock`/"
      "`Cin` are lossless, no self-resonance, no inductor model). The network is not "
      "matched (placeholder passives), so a poor S11 is the honest bench output.")
    w("")
    w("## Conditions")
    w("")
    w(f"- Bench: `sim/{bench_dir}/` (spec rows: {SPEC})")
    w(f"- **Declared matrix**: `sim/pvt-matrix.json` -- {len(gdb.PVT_PROCESS_SECTIONS)} HBT "
      f"sections ({', '.join(gdb.PVT_PROCESS_SECTIONS)}) x {len(gdb.PVT_TEMP_C)} ambient "
      f"temperatures ({'/'.join(f'{t:g}' for t in gdb.PVT_TEMP_C)} C) x supply "
      f"{gdb.PVT_VCC_V[0]:g}/{gdb.VCC_NOM_V:g}/{gdb.PVT_VCC_V[2]:g} V (nominal +/-10 %) "
      f"= **{gdb.pvt_cell_count()} cells**; this report covers {len(rows)} of "
      f"{gdb.pvt_cell_count()} declared cells (`klt corner-matrix` verdicts committed under "
      f"`corners/{rid}/`). Quiescent point: the DUT's own mirror bias at the cell's "
      "Vcc. Self-heating on (card default).")
    w("- **R/C process sections**: the spec pairs `res_*`/`cap_*` with the HBT corner of "
      "the same name, but the DUT's passives are ideal ngspice elements, so no R/C "
      "corner applies to them; only the HBT section moves.")
    w(f"- Source and load: {_port_z()}, S-parameter reference {gdb.RS_OHM:g} ohm; "
      "two independent DUT copies (forward and reverse excitation) per cell.")
    w(commit_line(git_sha, dirty))
    w(f"- klt {klt_v}; {ng_v}; PDK per `sim/pdk.json`.")
    w("")
    if kind == "gain":
        w("## Per-cell band results (11 points, 2400-2483.5 MHz)")
        w("")
        w("| Cell | min S21 dB | worst S11 dB | Power gain | S11 |")
        w("|---|---|---|---|---|")
        for r in rows:
            s21 = sp.db20(r["s"]["s21"])
            s11 = sp.db20(r["s"]["s11"])
            mn, wx = float(np.min(s21)), float(np.max(s11))
            w(f"| {_cell_md(r['cell'])} | {mn:.2f} | {wx:.2f} "
              f"| {_rung(mn > sr.GAIN_TARGET_DB, mn > sr.GAIN_FALLBACK_DB)} "
              f"| {_rung(wx < sr.S11_TARGET_DB, wx < sr.S11_FALLBACK_DB)} |")
        w("")
        w(f"Rungs against the RATIFIED rows (Target / Fallback): power gain > "
          f"{sr.GAIN_TARGET_DB:g} / > {sr.GAIN_FALLBACK_DB:g} dB (min in-band S21); "
          f"S11 < {sr.S11_TARGET_DB:g} / < {sr.S11_FALLBACK_DB:g} dB (worst in-band). "
          "The spec binds the worst cell as the figure.")
        if rows:
            w("")
            w(f"**Worst cell over the matrix**: min S21 "
              f"{min(float(np.min(sp.db20(r['s']['s21']))) for r in rows):.2f} dB, worst "
              f"S11 {max(float(np.max(sp.db20(r['s']['s11']))) for r in rows):.2f} dB.")
    else:
        w(f"## Per-cell stability, {rows[0]['freq'][0] / 1e6:.0f} MHz - "
          f"{rows[0]['freq'][-1] / 1e9:.0f} GHz" if rows else "## Per-cell stability")
        w("")
        w("| Cell | min mu | at GHz | min k | max \\|delta\\| | max \\|S11\\| | max \\|S22\\| | mu > 1 |")
        w("|---|---|---|---|---|---|---|---|")
        for r in rows:
            st, freq = r["st"], r["freq"]
            imin = int(np.argmin(st["mu"]))
            mn = float(st["mu"][imin])
            w(f"| {_cell_md(r['cell'])} | {mn:.4f} | {freq[imin] / 1e9:.4g} "
              f"| {float(np.min(st['k'])):.3g} | {float(np.max(st['abs_delta'])):.3g} "
              f"| {st['max_abs_s11']:.4f} | {st['max_abs_s22']:.4f} "
              f"| {_rung(mn > sr.MU_MIN, mn > sr.MU_MIN)} |")
        w("")
        w("mu > 1 (Edwards-Sinsky) is the pass metric at every point; k and |delta| are "
          "reported, not graded (k is ill-conditioned on low-S12 topologies). The spec's "
          "Fallback column for this row is \"same\" -- there is no relaxed rung. The "
          "spec binds the worst cell as the figure.")
        if rows:
            w("")
            w("**Worst cell over the matrix**: min mu "
              f"{min(float(np.min(r['st']['mu'])) for r in rows):.4f}.")
    w("")
    if failures:
        w("## Cells that did not simulate")
        w("")
        for cell, cid, status in failures:
            w(f"- {_cell_md(cell)} (`{cid}`): status `{status}` -- no figure, not a pass.")
        w("")
    w("Full per-frequency sweeps: klt artifacts under `corners/<id>/`. Points per decade "
      "and the negative-resistance check are unchanged from the nominal-cell bench "
      "(spec: >= 40 pts/decade).")
    w("")
    print("\n".join(out))
    return 0 if rows else 1


def main(argv):
    kind, rid, git_sha, dirty, klt_v, ng_v, report_path = argv[1:8]
    rep = json.load(open(report_path))
    if len(rep.get("corners", [])) != 1:
        return _render_matrix(kind, rid, git_sha, dirty, klt_v, ng_v, rep)
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
