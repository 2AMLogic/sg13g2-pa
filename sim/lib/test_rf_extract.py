"""Unit tests for rf_extract on synthetic waveforms (no simulator needed)."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rf_extract as rx  # noqa: E402

F0 = 1e9
T = 1 / F0


def grid(n_periods=150, per=400):
    return np.arange(n_periods * per + 1) * (T / per)


def sine_into_50(t, v0=1.0, rs=50.0, rl=50.0, h3=0.0):
    """Source behind rs into rl; returns (v_load, i_load, v_src, i_src)."""
    vs = v0 * np.sin(2 * np.pi * F0 * t) + h3 * np.sin(2 * np.pi * 3 * F0 * t)
    vl = vs * rl / (rs + rl)
    il = vl / rl
    return vl, il, vs, vs / (rs + rl)


def test_sine_power_matches_analytic():
    t = grid()
    vl, il, vs, isrc = sine_into_50(t)
    r = rx.extract(t, F0, vl, il, supplies=[], v_in=vs, i_in=isrc)
    assert 10 * math.log10(r["p_out_w"] / 1e-3) == pytest.approx(3.979, abs=0.001)
    assert r["pae"] is None  # no supply: PAE undefined, not 0
    assert r["h3_dbc"] is None  # no third harmonic energy


def test_third_harmonic_dbc():
    t = grid()
    vl, il, vs, isrc = sine_into_50(t, h3=0.1)
    r = rx.extract(t, F0, vl, il, supplies=[])
    assert r["h3_dbc"] == pytest.approx(-20.0, abs=0.001)
    assert r["h2_dbc"] is None


def test_dc_into_resistor_pdc_and_zero_pae():
    t = grid()
    v = np.full_like(t, 3.3)
    i = v / 100.0
    r = rx.extract(t, F0, v, i, supplies=[(v, i)], v_in=np.zeros_like(t), i_in=np.zeros_like(t))
    assert r["p_dc_w"] == pytest.approx(3.3 ** 2 / 100.0, rel=1e-9)
    assert abs(r["pae"]) < 1e-9
    assert r["p_out_w"] == pytest.approx(0.0, abs=1e-15)


def test_pae_with_gain():
    t = grid()
    vl, il, vs, isrc = sine_into_50(t)
    i_dc = np.full_like(t, 0.02)
    v_dc = np.full_like(t, 1.0)
    r = rx.extract(t, F0, vl, il, supplies=[(v_dc, i_dc)], v_in=vs * 0.1, i_in=isrc * 0.1)
    assert r["pae"] == pytest.approx((r["p_out_w"] - r["p_in_w"]) / 0.02, rel=1e-9)


def test_wrong_load_is_visible():
    t = grid()
    vl, il, *_ = sine_into_50(t, rl=75.0)
    r = rx.extract(t, F0, vl, il, supplies=[])
    delta = 10 * math.log10(r["p_out_w"] / 1e-3) - 3.979
    assert delta == pytest.approx(-0.18, abs=0.01)


def test_resampling_from_nonuniform_trace():
    rng = np.random.default_rng(1)
    base = grid(per=800)
    jitter = rng.uniform(-0.3, 0.3, len(base)) * (T / 800)
    jitter[0] = jitter[-1] = 0.0
    t = base + jitter  # non-uniform, max step < T/200
    vl, il, *_ = sine_into_50(t)
    r = rx.extract(t, F0, vl, il, supplies=[])
    assert 10 * math.log10(r["p_out_w"] / 1e-3) == pytest.approx(3.979, abs=0.01)


# --- negative controls -----------------------------------------------------

@pytest.mark.parametrize("n", [20.5, 0, -3, 2.0000001])
def test_non_integer_window_rejected(n):
    t = grid()
    vl, il, *_ = sine_into_50(t)
    with pytest.raises(rx.ExtractError) as e:
        rx.extract(t, F0, vl, il, supplies=[], n_periods=n)
    assert e.value.code == "NON_INTEGER_WINDOW"


def test_unsettled_trace_rejected():
    t = grid()
    vl, il, *_ = sine_into_50(t)
    env = 1 - np.exp(-t / (60 * T))  # envelope still moving after 150 periods
    with pytest.raises(rx.ExtractError) as e:
        rx.extract(t, F0, vl * env, il * env, supplies=[])
    assert e.value.code == "UNSETTLED"


def test_unsettled_supply_current_rejected():
    t = grid()
    vl, il, *_ = sine_into_50(t)
    i_dc = 0.02 * (1 + 2e-3 * t / T)  # P_out flat, current drifting 0.2 %/period
    with pytest.raises(rx.ExtractError) as e:
        rx.extract(t, F0, vl, il, supplies=[(np.ones_like(t), i_dc)])
    assert e.value.code == "UNSETTLED"


def test_fewer_than_100_periods_rejected():
    t = grid(n_periods=99)
    vl, il, *_ = sine_into_50(t)
    with pytest.raises(rx.ExtractError) as e:
        rx.extract(t, F0, vl, il, supplies=[])
    assert e.value.code == "TOO_FEW_PERIODS"


def test_coarse_time_step_rejected():
    t = grid(per=100)  # T/100 > T/200
    vl, il, *_ = sine_into_50(t)
    with pytest.raises(rx.ExtractError) as e:
        rx.extract(t, F0, vl, il, supplies=[])
    assert e.value.code == "STEP_TOO_COARSE"


def test_zero_valued_trace_is_settled():
    # 0 vs 0 cycle-to-cycle change is defined as settled (not 0/0).
    assert rx._power_change_ok(0.0, 0.0)
    assert rx._rel_change_ok(0.0, 0.0, 1e-3)
    assert not rx._power_change_ok(0.0, 1e-3)
    assert not rx._rel_change_ok(1e-3, 0.0, 1e-3)
    t = grid()
    z = np.zeros_like(t)
    r = rx.extract(t, F0, z, z, supplies=[(z, z)])
    assert r["p_out_w"] == 0.0 and r["pae"] is None and r["h3_dbc"] is None


def test_mismatched_input_port_args_rejected():
    t = grid()
    vl, il, vs, _ = sine_into_50(t)
    with pytest.raises(rx.ExtractError):
        rx.extract(t, F0, vl, il, supplies=[], v_in=vs)


# --- sweep reducer -----------------------------------------------------------

def compressing_sweep(pin_dbm, g=10.0, psat_dbm=15.0, pae=None):
    """Soft-limiter: Pout = -10log10(10^(-(Pin+g)/10) + 10^(-psat/10))."""
    out = []
    for p in pin_dbm:
        po = -10 * math.log10(10 ** (-(p + g) / 10) + 10 ** (-psat_dbm / 10))
        out.append({"p_in_w": 1e-3 * 10 ** (p / 10), "p_out_w": 1e-3 * 10 ** (po / 10), "pae": pae})
    return out


def test_sweep_psat_and_p1db():
    pin = np.arange(-20, 30.01, 0.5)
    r = rx.reduce_sweep(compressing_sweep(pin))
    assert r["p1db_status"] == "reached"
    # soft limiter: 1 dB compression where 10^(c/10) = 1 + x, x = Pout_lin/Psat
    assert r["gain_linear_db"] == pytest.approx(10.0, abs=0.05)
    comp_at_p1 = r["gain_linear_db"] - (r["p1db_out_dbm"] - r["p1db_in_dbm"])
    assert comp_at_p1 == pytest.approx(1.0, abs=1e-9)
    assert r["psat_dbm"] == pytest.approx(15.0, abs=0.1)
    assert r["psat_at_sweep_end"]


def test_sweep_p1db_not_reached_is_not_extrapolated():
    pin = np.arange(-20, -5, 0.5)
    r = rx.reduce_sweep(compressing_sweep(pin))
    assert r["p1db_status"] == "not_reached"
    assert r["p1db_in_dbm"] is None and r["p1db_out_dbm"] is None


def test_sweep_coarse_step_rejected():
    pin = np.concatenate((np.arange(-20, -8, 0.5), np.arange(-8, 12, 2.0)))
    with pytest.raises(rx.ExtractError) as e:
        rx.reduce_sweep(compressing_sweep(pin))
    assert e.value.code == "SWEEP_STEP_TOO_COARSE"


def test_sweep_psat_not_at_end_when_output_falls():
    pin = np.arange(-20, 12.01, 0.5)
    pts = compressing_sweep(pin)
    pts[-3]["p_out_w"] *= 1.5  # clear maximum before the end
    r = rx.reduce_sweep(pts)
    assert r["psat_index"] == len(pts) - 3 and not r["psat_at_sweep_end"]


def test_sweep_nonlinear_start_rejected():
    pts = compressing_sweep(np.arange(-5, 12, 0.5))  # already compressed at low end
    with pytest.raises(rx.ExtractError) as e:
        rx.reduce_sweep(pts)
    assert e.value.code == "LINEAR_REGION_NOT_FOUND"
