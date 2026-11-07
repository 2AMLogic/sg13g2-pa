"""Known-answer tests for sparams.py (no simulator needed)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import sparams as sp  # noqa: E402


def test_matched_through_line():
    # Ideal 50 ohm through: v(in)=vs/2, v(out)=vs/2 -> S11=0, S21=1.
    one = np.ones(3, complex)
    d = {"v(s1)": one, "v(s2)": one, "v(in1)": 0.5 * one, "v(out1)": 0.5 * one,
         "v(out2)": 0.5 * one, "v(in2)": 0.5 * one}
    s = sp.s_from_nodes(d)
    assert np.allclose(s["s11"], 0) and np.allclose(s["s21"], 1)
    assert np.allclose(s["s22"], 0) and np.allclose(s["s12"], 1)


def test_stability_unilateral_known():
    s = {k: np.array([v], complex) for k, v in
         dict(s11=0.5, s12=0.0, s21=2.0, s22=0.5).items()}
    st = sp.stability(s)
    # mu = (1-|S11|^2)/(|S22 - D S11*| + |S12 S21|); D = 0.25 -> 0.75/(0.5-0.125)=2
    assert abs(st["mu"][0] - 2.0) < 1e-12
    assert st["max_abs_s11"] == 0.5


def test_unstable_has_mu_below_one():
    s = {k: np.array([v], complex) for k, v in
         dict(s11=1.2, s12=0.1, s21=3.0, s22=0.4).items()}
    assert sp.stability(s)["mu"][0] < 1


def test_read_ascii_raw(tmp_path):
    p = tmp_path / "x.raw"
    p.write_text(
        "Title: t\nPlotname: AC Analysis\nFlags: complex\nNo. Variables: 2\nNo. Points: 2\n"
        "Variables:\n\t0\tfrequency\tfrequency\n\t1\tv(a)\tvoltage\nValues:\n"
        " 0\t1.0e+09,0.0e+00\n\t1.0e+00,2.0e+00\n\n"
        " 1\t2.0e+09,0.0e+00\n\t3.0e+00,-4.0e+00\n\n")
    f, d = sp.read_ascii_raw(str(p))
    assert list(f) == [1e9, 2e9] and d["v(a)"][1] == 3 - 4j
