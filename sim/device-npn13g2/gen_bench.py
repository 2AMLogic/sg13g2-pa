#!/usr/bin/env python3
"""Generate the npn13G2 device benches (decks + klt sim requests).

Usage: python3 -I gen_bench.py [--check]

Writes dc_family.spice / dc_family.request.json and ft.spice / ft.request.json
next to this file. The decks hold one `npn13G2` instance per (Nx, Vbe) pair,
each with its own base source and a zero-volt collector ammeter, so one
`klt sim` corner request (process x temperature) covers the whole Nx x Vbe
family. With --check, regenerate in memory and exit 1 if the committed files
differ (the committed files are what the record hashes).
"""
import json
import os
import sys

NX = (1, 4, 10)
VBE = (0.70, 0.74, 0.78, 0.82, 0.86, 0.90)  # inside the card's 0.65-0.96 V window
VCE = (0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0)  # the card's window; 1.0 is the fT point
FT_VCE = 1.0
FT_FREQS = ("20e9", "50e9")
PROCESS = ("hbt_typ", "hbt_bcs", "hbt_wcs")
TEMPS = (-40, 27, 125)


def tag(nx, vbe):
    return "n%d_v%d" % (nx, round(vbe * 100))


def process_block():
    return [{"name": p, "sections": [{"lib": "libs.tech/ngspice/models/cornerHBT.lib", "section": p}]}
            for p in PROCESS]


def dc_deck():
    out = ["* npn13G2 Ic-Vce family: Nx 1/4/10 x Vbe 0.70..0.90 V, Vce swept 0..2 V.",
           "* Each device has its own base source (Vb_*) and a 0 V collector ammeter (Vs_*),",
           "* Ic = +i(Vs_*) (current into the + terminal), exposed as v(ico_*) through a 1 ohm CCVS (ngspice limits .meas par() to 99",
           "* calls per file). 4-terminal subckt, card default selft=1 (self-heating on).",
           "* Process corner and temperature come from the klt sim request.",
           "* Circuit body only (klt sim owns .control/.end).",
           "Vc c 0 dc 1.0"]
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            out += ["Vb_%s b_%s 0 dc %.2f" % (t, t, vbe),
                    "Vs_%s c c_%s 0" % (t, t),
                    "Xq_%s c_%s b_%s 0 0 npn13G2 Nx=%d" % (t, t, t, nx),
                    "Hic_%s ico_%s 0 Vs_%s 1" % (t, t, t),
                    "Rico_%s ico_%s 0 1G" % (t, t)]
    return "\n".join(out) + "\n"


def dc_request():
    meas = []
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            for vce in VCE:
                name = "ic_%s_vce%d" % (t, round(vce * 100))
                meas.append({"name": name, "spice": ".meas dc %s FIND v(ico_%s) AT=%g" % (name, t, vce),
                             "unit": "A"})
    return {
        "netlist": "dc_family.spice",
        "models": {"pdk": "ihp-sg13g2"},
        "corners": {"process": process_block(), "temperature_c": list(TEMPS)},
        "analysis": {"kind": "dc", "args": "Vc 0.0 2.0 0.1"},
        "measurements": meas,
        "options": {"timeout_s": 300, "keep_artifacts": True, "ngspice_init": ["set numdgt=8"]},
    }


def ft_deck():
    out = ["* npn13G2 small-signal current gain h21 at Vce = %.1f V, Nx 1/4/10 x Vbe 0.70..0.90 V." % FT_VCE,
           "* Base driven by a 1 V ac voltage source, collector ac-shorted (dc source only), so",
           "* Ib_ac = i(Vb_*) and Ic_ac = i(Vs_*); CCVS H sources (1 ohm) expose them as voltages",
           "* for .meas. h21 = |Ic_ac|/|Ib_ac|; fT ~ |h21|*f0 (see README). Bias Ic comes from the",
           "* dc family (same Nx, Vbe, corner, temperature, Vce).",
           "* Circuit body only (klt sim owns .control/.end).",
           "Vc c 0 dc %.1f" % FT_VCE]
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            out += ["Vb_%s b_%s 0 dc %.2f ac 1" % (t, t, vbe),
                    "Vs_%s c c_%s 0" % (t, t),
                    "Xq_%s c_%s b_%s 0 0 npn13G2 Nx=%d" % (t, t, t, nx),
                    "Hic_%s ico_%s 0 Vs_%s 1" % (t, t, t),
                    "Hib_%s ibo_%s 0 Vb_%s 1" % (t, t, t),
                    "Rico_%s ico_%s 0 1G" % (t, t),
                    "Ribo_%s ibo_%s 0 1G" % (t, t)]
    return "\n".join(out) + "\n"


def ft_request():
    meas = []
    for nx in NX:
        for vbe in VBE:
            t = tag(nx, vbe)
            for f in FT_FREQS:
                for q, node in (("ic", "ico"), ("ib", "ibo")):
                    name = "%sac_%s_f%s" % (q, t, f)
                    meas.append({"name": name, "spice": ".meas ac %s FIND vm(%s_%s) AT=%s" % (name, node, t, f),
                                 "unit": "A"})
    return {
        "netlist": "ft.spice",
        "models": {"pdk": "ihp-sg13g2"},
        "corners": {"process": process_block(), "temperature_c": list(TEMPS)},
        "analysis": {"kind": "ac", "args": "dec 20 10e9 100e9"},
        "measurements": meas,
        "options": {"timeout_s": 300, "keep_artifacts": True, "ngspice_init": ["set numdgt=8"]},
    }


def files():
    return {"dc_family.spice": dc_deck(), "ft.spice": ft_deck(),
            "dc_family.request.json": json.dumps(dc_request(), indent=2) + "\n",
            "ft.request.json": json.dumps(ft_request(), indent=2) + "\n"}


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    bad = 0
    for name, text in files().items():
        path = os.path.join(here, name)
        if "--check" in argv:
            if not os.path.isfile(path) or open(path).read() != text:
                print("gen_bench.py: %s differs from the generator" % name, file=sys.stderr)
                bad = 1
        else:
            with open(path, "w") as fh:
                fh.write(text)
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
