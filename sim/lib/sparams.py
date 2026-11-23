"""Two-port S-parameters and stability metrics from the ac benches' complex node voltages.

Pure layer (numpy only): ``s_from_nodes`` turns the two-DUT-copy node voltages of
``sim/lib/gen_dut_benches.py`` into S11/S21/S12/S22, valid only when the source
and load resistances are equal (``gen_dut_benches._ac_deck`` refuses to build a
deck otherwise);
``stability`` returns Edwards-Sinsky mu, mu', Rollett k, |delta| and the
negative-resistance check (max |S11|, max |S22|).
"""
import numpy as np


def s_from_nodes(d):
    """S-parameters, one reference impedance both ports, 1 V AC EMF behind it.

    ASSUMES the source and load resistances are equal: `s21`/`s12` below are the
    voltage-ratio forms `2 v(out)/vs`, which equal S21/S12 only in that case.
    With unequal resistances the transducer gain is `4 |Vout|^2 Rs / (|Vs|^2 Rl)`,
    so `|2 Vout/Vs|^2` is off by `Rs/Rl`. `gen_dut_benches._ac_deck` enforces
    `RS_OHM == RL_OHM`, so no deck this reads can violate it; teaching per-port
    reference impedances here is what lifts that restriction.
    """
    vs1, vs2 = d["v(s1)"], d["v(s2)"]
    return {
        "s11": 2 * d["v(in1)"] / vs1 - 1,
        "s21": 2 * d["v(out1)"] / vs1,
        "s22": 2 * d["v(out2)"] / vs2 - 1,
        "s12": 2 * d["v(in2)"] / vs2,
    }


def db20(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-300))


def stability(s):
    s11, s12, s21, s22 = s["s11"], s["s12"], s["s21"], s["s22"]
    delta = s11 * s22 - s12 * s21
    ad = np.abs(delta)
    a21 = np.maximum(np.abs(s12 * s21), 1e-300)
    mu = (1 - np.abs(s11) ** 2) / (np.abs(s22 - delta * np.conj(s11)) + np.abs(s12 * s21))
    mup = (1 - np.abs(s22) ** 2) / (np.abs(s11 - delta * np.conj(s22)) + np.abs(s12 * s21))
    k = (1 - np.abs(s11) ** 2 - np.abs(s22) ** 2 + ad ** 2) / (2 * a21)
    return {"mu": mu, "mu_prime": mup, "k": k, "abs_delta": ad,
            "max_abs_s11": float(np.max(np.abs(s11))), "max_abs_s22": float(np.max(np.abs(s22)))}
