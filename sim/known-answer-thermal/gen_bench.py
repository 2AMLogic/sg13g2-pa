#!/usr/bin/env python3
"""Generate the npn13G2 thermal-node known-answer benches (decks + klt sim requests).

Usage: python3 -I gen_bench.py [--check]

Writes thermal.spice / thermal.request.json and thermal_neg.spice /
thermal_neg.request.json next to this file. Every expected value is computed
from sim/lib/device_limits.rth() -- the card's own rth expression, defined
once for the repo -- so the model card's constants are never retyped here.

The check (spec/decision-records/0001-ratify-target-spec.md Q4, deferred as
D-2): an idle 5-terminal `npn13G2_5t` carries a known constant power into its
thermal node `t` (an `op` solve; current in amperes is watts), and V(t) must
read P * rth(Nx). Cases: 2 Nx x 2 powers (injection), one biased case where
the device's own dissipation drives the node (Vce 1.0 V, Vbe 0.85 V, Nx=4,
power reconstructed from terminal V and I), and one 4-terminal `npn13G2` at
the same bias probed hierarchically as `v(x4t.t)` -- the node psat-sweep's
record actually reads. thermal_neg.* repeats the injection cases with
`selft=0`, which drops the thermal network: the negative control, expected to
fail its grading.

Each subckt ends with `Rt t 0 R = 1e9`, so the node sees `rth || 1e9` and
every reading sits low by `-rth/1e9` relative. The graded tolerances below
are wider than that systematic on purpose (TOL_INJ_REL / R_SHUNT_OHM ~ 30x at
Nx=4, ~9x at Nx=1), so passing it is by design, not by luck. With --check,
regenerate in memory and exit 1 if the committed files differ (the committed
files are what the record hashes).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from device_limits import rth  # noqa: E402
# The PDK constants, the request skeleton and the strict write/--check driver live
# once in sim/lib/bench_gen.py, shared with the other bench generators; never
# retype the corner-library path or the PDK name here.
import bench_gen  # noqa: E402

NX_INJ = (1, 4)          # the two array sizes the injection cases check
I_INJ_A = (1e-3, 10e-3)  # the two injected power levels, W (current in amperes)
BIAS_NX = 4
BIAS_VCE_V = 1.0
BIAS_VBE_V = 0.85        # inside the card's 0.65-0.96 V window
R_SHUNT_OHM = 1e9        # the card's `Rt t 0 R = 1e9` at the end of both subckts
TOL_INJ_REL = 1e-4       # 0.01 % relative on the injection cases
TOL_BIAS_REL = 1e-3      # 0.1 % relative on the biased case (looser: P is
                         # reconstructed from terminal V/I, not the model's
                         # internal power)
TOL_4T_ABS_V = 1e-6      # 4-terminal vs 5-terminal node agreement, V
PROCESS = "hbt_typ"      # rth carries no process/temperature coefficient in
TEMPERATURE_C = 27       # the card (no xrth/trth), so one corner suffices


def inj_name(nx, i_a):
    return "vt5_n%d_%s" % (nx, {1e-3: "1m", 10e-3: "10m"}[i_a])


def inj_node(nx, i_a):
    return "t_n%d_%s" % (nx, {1e-3: "1m", 10e-3: "10m"}[i_a])


def limits(analytic, tol_rel):
    return {"min": analytic * (1.0 - tol_rel), "max": analytic * (1.0 + tol_rel)}


def p_bias_expr():
    return "-(v(c5b)*i(vc5b) + v(b5b)*i(vb5b))"


def injection_measurements():
    """The graded v(t) cases the two requests share (positive and negative)."""
    meas = []
    for nx in NX_INJ:
        for i in I_INJ_A:
            meas.append({"name": inj_name(nx, i), "expr": "v(%s)" % inj_node(nx, i),
                         "unit": "V", "limits": limits(i * rth(nx), TOL_INJ_REL)})
    return meas


def thermal_request():
    meas = injection_measurements() + [
        {"name": "ic_bias", "expr": "-i(vc5b)", "unit": "A"},
        {"name": "p_bias", "expr": p_bias_expr(), "unit": "W"},
        {"name": "vt5_bias", "expr": "v(t5b)", "unit": "V"},
        # The biased known answer, graded as a ratio so its limits are computable
        # from rth() alone: V(t) per watt of reconstructed power, expected rth(4).
        {"name": "rth_meas", "expr": "v(t5b)/(%s)" % p_bias_expr(), "unit": "K/W",
         "limits": limits(rth(BIAS_NX), TOL_BIAS_REL)},
        {"name": "vt4_bias", "expr": "v(x4t.t)", "unit": "V"},
        {"name": "vt4_minus_vt5", "expr": "v(x4t.t) - v(t5b)", "unit": "V",
         "limits": {"min": -TOL_4T_ABS_V, "max": TOL_4T_ABS_V}},
    ]
    return bench_gen.request(
        netlist="thermal.spice",
        analysis={"kind": "op", "args": ""},
        options={"timeout_s": 60, "keep_artifacts": True, "ngspice_init": ["set numdgt=8"]},
        process=[PROCESS], temperature_c=[TEMPERATURE_C], measurements=meas)


def thermal_neg_request():
    return bench_gen.request(
        netlist="thermal_neg.spice",
        analysis={"kind": "op", "args": ""},
        options={"timeout_s": 60, "keep_artifacts": True, "ngspice_init": ["set numdgt=8"]},
        process=[PROCESS], temperature_c=[TEMPERATURE_C],
        measurements=injection_measurements())


def injection_lines(neg=False):
    """The idle 5t devices with a current source into the thermal node.

    All signal terminals are grounded, so the device dissipates nothing of its
    own and V(t) comes only from the injection. With neg=True every instance
    overrides `selft=0`, which zeroes rth and drops the thermal network.
    """
    out = []
    for nx in NX_INJ:
        for i in I_INJ_A:
            n = inj_node(nx, i)
            selft = " selft=0" if neg else ""
            out += ["Iin_%s 0 %s dc %g" % (n[2:], n, i),
                    "Xt5_%s 0 0 0 0 %s npn13G2_5t Nx=%d%s" % (n[2:], n, nx, selft)]
    return out


def bias_lines():
    return ["* biased case: the device's own dissipation drives the node",
            "Vc5b c5b 0 dc %g" % BIAS_VCE_V,
            "Vb5b b5b 0 dc %g" % BIAS_VBE_V,
            "Xt5b c5b b5b 0 0 t5b npn13G2_5t Nx=%d" % BIAS_NX,
            "* 4-terminal comparison at the same bias; its thermal node is",
            "* internal, probed hierarchically as v(x4t.t) -- the node",
            "* sim/psat-sweep/psat_record.py reads",
            "Vc4b c4b 0 dc %g" % BIAS_VCE_V,
            "Vb4b b4b 0 dc %g" % BIAS_VBE_V,
            "X4t c4b b4b 0 0 npn13G2 Nx=%d" % BIAS_NX]


def thermal_deck():
    out = ["* Thermal-node known-answer check, positive cases (issue #115).",
           "* GENERATED by gen_bench.py -- do not edit; rerun it.",
           "* Idle 5-terminal npn13G2_5t devices, current injected into the thermal",
           "* node `t` (amperes are watts here); V(t) must read P * rth(Nx). One biased",
           "* case where the device dissipates its own power, and one 4-terminal npn13G2",
           "* at the same bias for the hierarchical-node comparison. Card default",
           "* selft=1 (self-heating on). Process corner and temperature come from the",
           "* klt sim request (hbt_typ, 27 C; rth has no PVT coefficient).",
           "* Circuit body only (klt sim owns .control/.end)."]
    out += injection_lines()
    out += bias_lines()
    return "\n".join(out) + "\n"


def thermal_neg_deck():
    out = ["* Thermal-node known-answer check, NEGATIVE CONTROL (issue #115).",
           "* GENERATED by gen_bench.py -- do not edit; rerun it.",
           "* The injection cases of thermal.spice with selft=0: the card's rth",
           "* collapses to 0 and only the subckt's own `Rt t 0 R = 1e9` shunt remains,",
           "* so V(t) reads I * 1e9 -- wrong by five orders of magnitude. Expected to",
           "* fail its grading; kept as the demonstration.",
           "* Circuit body only (klt sim owns .control/.end)."]
    out += injection_lines(neg=True)
    return "\n".join(out) + "\n"


def files():
    return {"thermal.spice": thermal_deck(),
            "thermal.request.json": json.dumps(thermal_request(), indent=2) + "\n",
            "thermal_neg.spice": thermal_neg_deck(),
            "thermal_neg.request.json": json.dumps(thermal_neg_request(), indent=2) + "\n"}


def main(args):
    return bench_gen.write_or_check(
        files(), args, "gen_bench.py", HERE,
        "python3 -I sim/known-answer-thermal/gen_bench.py")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
