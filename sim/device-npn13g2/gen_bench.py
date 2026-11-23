#!/usr/bin/env python3
"""Generate the npn13G2 device benches (decks + klt sim requests).

Usage: python3 -I gen_bench.py [--check]

Writes dc_family.spice / dc_family.request.json and ft.spice / ft.request.json
next to this file. The decks hold one `npn13G2` instance per (Nx, Vbe) pair,
each with its own base source and a zero-volt collector ammeter (currents come
from the captured sweep, `options.waveforms`; no probe elements or `.meas`), so one
`klt sim` corner request (process x temperature) covers the whole Nx x Vbe
family. With --check, regenerate in memory and exit 1 if the committed files
differ (the committed files are what the record hashes); any other argument is
a usage error (exit 2) and writes nothing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
# The PDK constants, the request skeleton and the strict write/--check driver live
# once in sim/lib/bench_gen.py, shared with sim/lib/gen_dut_benches.py; never retype
# the corner-library path or the capacity wait here.
import bench_gen  # noqa: E402

NX = (1, 4, 10)
VBE = (0.70, 0.74, 0.78, 0.82, 0.86, 0.90)  # inside the card's 0.65-0.96 V window
VCE = (0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0)  # the card's window; 1.0 is the fT point
FT_VCE = 1.0
FT_FREQS = ("20e9", "50e9")
PROCESS = ("hbt_typ", "hbt_bcs", "hbt_wcs")
TEMPS = (-40, 27, 125)


def tag(nx, vbe):
    return "n%d_v%d" % (nx, round(vbe * 100))


def dc_deck():
    out = ["* npn13G2 Ic-Vce family: Nx 1/4/10 x Vbe 0.70..0.90 V, Vce swept 0..2 V.",
           "* Each device has its own base source (Vb_*) and a 0 V collector ammeter (Vs_*),",
           "* Ic = +i(Vs_*) (current into the + terminal), read from the captured sweep.",
           "* 4-terminal subckt, card default selft=1 (self-heating on).",
           "* Process corner and temperature come from the klt sim request.",
           "* Circuit body only (klt sim owns .control/.end).",
           "Vc c 0 dc 1.0"]
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            out += ["Vb_%s b_%s 0 dc %.2f" % (t, t, vbe),
                    "Vs_%s c c_%s 0" % (t, t),
                    "Xq_%s c_%s b_%s 0 0 npn13G2 Nx=%d" % (t, t, t, nx)]
    return "\n".join(out) + "\n"


def dc_request():
    return bench_gen.request(
        "dc_family.spice",
        {"kind": "dc", "args": "Vc 0.0 2.0 0.1"},
        {"timeout_s": 300, "keep_artifacts": True, "waveforms": True, "capture_only": True,
         "save_mode": "netlist", "ngspice_init": ["set numdgt=8"]},
        process=PROCESS, temperature_c=TEMPS, batch=True)


def ft_deck():
    out = ["* npn13G2 small-signal current gain h21 at Vce = %.1f V, Nx 1/4/10 x Vbe 0.70..0.90 V." % FT_VCE,
           "* Base driven by a 1 V ac voltage source, collector ac-shorted (dc source only), so",
           "* Ib_ac = i(Vb_*) and Ic_ac = i(Vs_*), read from the captured sweep at 20 and 50 GHz.",
           "* h21 = |Ic_ac|/|Ib_ac|; fT ~ |h21|*f0 (see README). Bias Ic comes from the",
           "* dc family (same Nx, Vbe, corner, temperature, Vce).",
           "* Circuit body only (klt sim owns .control/.end).",
           "Vc c 0 dc %.1f" % FT_VCE]
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            out += ["Vb_%s b_%s 0 dc %.2f ac 1" % (t, t, vbe),
                    "Vs_%s c c_%s 0" % (t, t),
                    "Xq_%s c_%s b_%s 0 0 npn13G2 Nx=%d" % (t, t, t, nx)]
    return "\n".join(out) + "\n"


def ft_vectors():
    """The branch currents h21 is formed from; AC data is complex, so klt writes them to the
    complex_vectors.json sidecar."""
    return ["i(%s_%s)" % (p, tag(nx, vbe)) for nx in NX for vbe in VBE for p in ("vs", "vb")]


def ft_request():
    return bench_gen.request(
        "ft.spice",
        {"kind": "ac", "args": "lin 3 20e9 50e9"},  # both FT_FREQS on the grid (lin 2 returned one row on ngspice 42)
        {"timeout_s": 300, "keep_artifacts": True, "waveforms": True, "capture_only": True,
         "complex_vectors": ft_vectors(), "save_vectors": ft_vectors(),
         "ngspice_init": ["set numdgt=8"]},
        process=PROCESS, temperature_c=TEMPS, batch=True)


def files():
    return {"dc_family.spice": dc_deck(), "ft.spice": ft_deck(),
            "dc_family.request.json": json.dumps(dc_request(), indent=2) + "\n",
            "ft.request.json": json.dumps(ft_request(), indent=2) + "\n"}


def main(args):
    return bench_gen.write_or_check(
        files(), args, "gen_bench.py", os.path.dirname(os.path.abspath(__file__)),
        "python3 -I sim/device-npn13g2/gen_bench.py")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
