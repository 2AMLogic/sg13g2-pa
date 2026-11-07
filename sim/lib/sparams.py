"""Two-port S-parameters and stability metrics from the ac benches' ngspice raw files.

Pure layer (numpy only): ``read_ascii_raw`` parses ngspice's ASCII complex raw
file; ``s_from_nodes`` turns the two-DUT-copy node voltages of
``sim/lib/gen_dut_benches.py`` into S11/S21/S12/S22 (reference 50 ohm);
``stability`` returns Edwards-Sinsky mu, mu', Rollett k, |delta| and the
negative-resistance check (max |S11|, max |S22|).
"""
import numpy as np


def read_ascii_raw(path):
    """-> (freq_hz ndarray, {name: complex ndarray}) for an AC-analysis ASCII raw file."""
    names = []
    rows = []
    with open(path) as fh:
        lines = fh.read().splitlines()
    nvar = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("No. Variables:"):
            nvar = int(ln.split(":")[1])
        elif ln.startswith("Variables:"):
            for k in range(nvar):
                names.append(lines[i + 1 + k].split("\t")[2])
            i += nvar
        elif ln.startswith("Values:"):
            i += 1
            break
        i += 1
    cur = []
    for ln in lines[i:]:
        if not ln.strip():
            continue
        tok = ln.split("\t")
        val = tok[-1].strip()
        if tok[0].strip().isdigit():   # " 0\t<first value>"
            if cur:
                rows.append(cur)
            cur = []
            val = tok[1].strip()
        re, im = val.split(",")
        cur.append(complex(float(re), float(im)))
    if cur:
        rows.append(cur)
    arr = np.array(rows)
    if arr.shape[1] != len(names):
        raise ValueError(f"raw file shape {arr.shape} does not match {len(names)} variables")
    data = {n: arr[:, k] for k, n in enumerate(names)}
    freq = data.pop(names[0]).real
    return freq, data


def s_from_nodes(d):
    """S-parameters (reference 50 ohm both ports, 1 V AC EMF behind 50 ohm)."""
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
