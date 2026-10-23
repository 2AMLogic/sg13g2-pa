"""Large-signal extraction from ngspice transient waveforms (no harmonic balance).

Implements spec/target-spec.md, section "Large-signal extraction without
harmonic balance": settling test, integer-period window, coherent rectangular
DFT with P_k = 1/2 Re(V_k I_k*), PAE, and the Psat / P1dB sweep reducer.

Two layers, so the unit tests need no simulator:

* pure functions (arrays in, numbers out): ``resample_uniform``,
  ``period_means``, ``check_settled``, ``extract``, ``reduce_sweep``;
* a thin reader, ``load_klt_waveform``, for the ``waveform.raw.json`` that
  ``klt sim`` writes when the request sets ``options.waveforms``.

Sign conventions (the caller supplies currents already in these senses):

* load current ``i_load``: into the load (so ``v*i`` is power delivered);
* supply current in ``supplies``: delivered by the source into the circuit.
  ngspice reports ``i(Vname)`` flowing into the + terminal, so pass ``-i(V)``;
* input-port current ``i_in``: into the port (power drawn by the DUT).

Every power is a simulated figure; nothing here knows about ideal versus
modelled passives, the record that calls the library must say so.
"""
import json
import math

import numpy as np

# Spec tolerances (ratified): settling and the known-answer check.
SETTLE_POWER_DB = 0.01      # cycle-to-cycle change of P_out, dB
SETTLE_CURRENT_REL = 1e-3   # cycle-to-cycle change of supply current, 0.1 %
SETTLE_RUN = 10             # consecutive periods
MIN_PERIODS = 100           # at least this many RF periods simulated
DEFAULT_WINDOW = 20         # integration window, integer periods
MAX_STEP_FRAC = 1.0 / 200   # raw max time step, fraction of T
GRID_PER_PERIOD = 400       # uniform grid points per period
# Quantities at or below this are "zero" for the relative settling test
# (a DC-only deck has P_out(fundamental) = 0, so 0 vs 0 is "unchanged").
ZERO_FLOOR = 1e-18
# Sweep steps (spec): <= 0.5 dB through 1 dB compression, <= 1 dB to Psat.
STEP_P1DB_DB = 0.5
STEP_SAT_DB = 1.0
# Rawfile times are printed to ~7 digits; allow that much slack on window
# and step checks.
TIME_RTOL = 1e-6


class ExtractError(ValueError):
    """The trace cannot be extracted under the spec (named reason in .code)."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


_trapz = getattr(np, "trapezoid", None) or np.trapz  # numpy 1.x / 2.x


def _db10(x):
    return 10.0 * math.log10(x)


def _dbm(w):
    return _db10(w / 1e-3)


def load_klt_waveform(path):
    """Read klt's ``waveform.raw.json`` -> ``(time, {name: array})``.

    ``variables[0]`` is ``time`` for a transient; names are lower-cased by
    ngspice (``v(out)``, ``i(vs)``).
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    names = [v["name"] for v in doc["variables"]]
    if names[0] != "time":
        raise ExtractError("NOT_TRANSIENT", f"first variable is {names[0]!r}, not 'time'")
    data = np.asarray(doc["points"], dtype=float)
    return data[:, 0], {n: data[:, k] for k, n in enumerate(names) if k > 0}


def resample_uniform(t, y, dt, t0, n_samples):
    """Linear interpolation of ``y(t)`` onto ``t0 + k*dt``, k = 0..n_samples-1."""
    grid = t0 + dt * np.arange(n_samples)
    return np.interp(grid, t, y)


def _check_grid(t, f0):
    period = 1.0 / f0
    if len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ExtractError("BAD_TIME", "time axis must be strictly increasing")
    worst = float(np.max(np.diff(t)))
    if worst > period * MAX_STEP_FRAC * (1 + TIME_RTOL):
        raise ExtractError(
            "STEP_TOO_COARSE",
            f"max time step {worst:.4g} s exceeds T/200 = {period * MAX_STEP_FRAC:.4g} s")


def period_means(t, y, f0, periods, t0=None, per_period=GRID_PER_PERIOD):
    """Mean of ``y`` over each of the first ``periods`` RF periods.

    Trapezoid rule on the uniform interpolation of ``y``; period k covers
    [t0 + k*T, t0 + (k+1)*T].
    """
    period = 1.0 / f0
    t0 = float(t[0]) if t0 is None else t0
    dt = period / per_period
    out = np.empty(periods)
    for k in range(periods):
        seg = resample_uniform(t, y, dt, t0 + k * period, per_period + 1)
        out[k] = _trapz(seg, dx=dt) / period
    return out


def _whole_periods(t, f0):
    span = (t[-1] - t[0]) * f0
    return int(math.floor(span * (1 + TIME_RTOL) + 1e-9))


def _rel_change_ok(a, b, tol_rel):
    """|b/a - 1| <= tol_rel with the explicit zero rule (0 vs 0 is settled)."""
    if abs(a) <= ZERO_FLOOR and abs(b) <= ZERO_FLOOR:
        return True
    if abs(a) <= ZERO_FLOOR or abs(b) <= ZERO_FLOOR:
        return False
    return abs(b / a - 1.0) <= tol_rel


def _power_change_ok(a, b):
    """Cycle-to-cycle change of a power below 0.01 dB (zero rule as above)."""
    if abs(a) <= ZERO_FLOOR and abs(b) <= ZERO_FLOOR:
        return True
    if a <= ZERO_FLOOR or b <= ZERO_FLOOR:
        return False  # one side zero/negative: not a small dB change
    return abs(_db10(b / a)) <= SETTLE_POWER_DB


def check_settled(p_out_means, supply_current_means, n_window=DEFAULT_WINDOW):
    """Spec settling test on per-period means; raises ``UNSETTLED`` if it fails.

    ``p_out_means``: per-period mean load power; ``supply_current_means``: a
    list of per-period mean current arrays, one per supply. Required: at
    least 100 periods, and every cycle-to-cycle change below 0.01 dB (P_out)
    / 0.1 % (each supply current) over the SETTLE_RUN periods before the
    window *and* throughout the window (the last ``n_window`` periods).
    Returns the index of the first period of the window.
    """
    n = len(p_out_means)
    if n < MIN_PERIODS:
        raise ExtractError("TOO_FEW_PERIODS", f"{n} RF periods simulated, need >= {MIN_PERIODS}")
    start = n - n_window
    first = start - SETTLE_RUN
    if first < 0:
        raise ExtractError("TOO_FEW_PERIODS", "no room for the settling run before the window")
    for k in range(first, n - 1):
        if not _power_change_ok(p_out_means[k], p_out_means[k + 1]):
            raise ExtractError(
                "UNSETTLED", f"P_out changes by more than {SETTLE_POWER_DB} dB between periods {k} and {k + 1}")
        for j, cur in enumerate(supply_current_means):
            if not _rel_change_ok(cur[k], cur[k + 1], SETTLE_CURRENT_REL):
                raise ExtractError(
                    "UNSETTLED", f"supply {j} current changes by more than 0.1 % between periods {k} and {k + 1}")
    return start


def _phasor(y, harmonic, n_window, per_period):
    """Peak phasor of harmonic k over the window: (2/NT) int y e^{-jkwt} dt."""
    m = len(y) - 1  # samples per window = n_window * per_period
    ph = np.exp(-2j * np.pi * harmonic * np.arange(m + 1) / per_period)
    integrand = y * ph
    area = _trapz(integrand, dx=1.0)
    return 2.0 * area / m


def _harmonic_power(v, i, harmonic, n_window, per_period):
    return 0.5 * (_phasor(v, harmonic, n_window, per_period)
                  * np.conj(_phasor(i, harmonic, n_window, per_period))).real


def extract(t, f0, v_load, i_load, supplies, v_in=None, i_in=None,
            n_periods=DEFAULT_WINDOW, per_period=GRID_PER_PERIOD):
    """Spec extraction for one drive point.

    ``t``: simulator time points; ``f0``: fundamental in Hz; ``supplies``:
    list of ``(v, i_delivered)`` arrays (all of them, bias and driver
    included). ``n_periods`` must be a positive integer (the window is an
    integer number of RF periods); anything else raises ``NON_INTEGER_WINDOW``.

    Returns a dict (watts, dB): ``p_out_w``/``p_in_w`` (fundamental only),
    ``p_dc_w`` (total, window average), ``pae`` (None if P_DC is zero),
    ``h2_dbc``/``h3_dbc`` (None if the fundamental is zero), plus the window
    bookkeeping. Raises :class:`ExtractError` for a coarse time grid, too
    few periods or an unsettled trace.
    """
    if isinstance(n_periods, bool) or int(n_periods) != n_periods or n_periods < 1:
        raise ExtractError("NON_INTEGER_WINDOW", f"window of {n_periods!r} periods is not a positive integer")
    n_periods = int(n_periods)
    t = np.asarray(t, dtype=float)
    _check_grid(t, f0)
    total = _whole_periods(t, f0)
    if total < MIN_PERIODS:
        raise ExtractError("TOO_FEW_PERIODS", f"{total} RF periods simulated, need >= {MIN_PERIODS}")
    if (v_in is None) != (i_in is None):
        raise ExtractError("BAD_INPUT", "v_in and i_in go together")

    v_load, i_load = np.asarray(v_load, float), np.asarray(i_load, float)
    p_inst = v_load * i_load
    p_means = period_means(t, p_inst, f0, total, per_period=per_period)
    cur_means = [period_means(t, np.asarray(i, float), f0, total, per_period=per_period)
                 for _, i in supplies]
    start = check_settled(p_means, cur_means, n_period_guard(n_periods, total))

    period = 1.0 / f0
    dt = period / per_period
    t_win = float(t[0]) + start * period
    m = n_periods * per_period
    grid = lambda y: resample_uniform(t, np.asarray(y, float), dt, t_win, m + 1)  # noqa: E731

    vl, il = grid(v_load), grid(i_load)
    p_out = _harmonic_power(vl, il, 1, n_periods, per_period)
    if v_in is not None:
        p_in = _harmonic_power(grid(v_in), grid(i_in), 1, n_periods, per_period)
    else:
        p_in = 0.0
    p_dc = 0.0
    for v, i in supplies:
        p_dc += _trapz_mean(grid(np.asarray(v, float) * np.asarray(i, float)), dt, m)

    h = {}
    for k in (2, 3):
        pk = _harmonic_power(vl, il, k, n_periods, per_period)
        h[k] = _db10(pk / p_out) if p_out > ZERO_FLOOR and pk > ZERO_FLOOR else None
    return {
        "f0_hz": f0,
        "periods_simulated": total,
        "window_periods": n_periods,
        "window_start_period": start,
        "window_start_s": t_win,
        "grid_points_per_period": per_period,
        "p_out_w": p_out,
        "p_in_w": p_in,
        "p_dc_w": p_dc,
        "pae": (p_out - p_in) / p_dc if abs(p_dc) > ZERO_FLOOR else None,
        "h2_dbc": h[2],
        "h3_dbc": h[3],
    }


def n_period_guard(n_periods, total):
    if n_periods + SETTLE_RUN > total:
        raise ExtractError("TOO_FEW_PERIODS", f"{total} periods cannot hold a {n_periods}-period window plus the settling run")
    return n_periods


def _trapz_mean(y, dt, m):
    return _trapz(y, dx=dt) / (m * dt)


def reduce_sweep(points, linear_points=3, linear_spread_db=0.1):
    """Psat and P1dB from a drive sweep.

    ``points``: dicts with ``p_in_w`` and ``p_out_w`` (fundamental, from
    :func:`extract`) and optionally ``pae``. Sorted by drive. Linear gain is
    the median gain of the ``linear_points`` lowest-drive points, which must
    agree within ``linear_spread_db`` (else ``LINEAR_REGION_NOT_FOUND``).
    P1dB: linear interpolation in dB between the two bracketing points where
    compression (linear gain minus gain) crosses 1 dB; if the sweep never
    gets there the result is ``p1db_status == 'not_reached'`` with no
    extrapolation. Step limits (<= 0.5 dB at the bracket, <= 1 dB up to
    Psat) raise ``SWEEP_STEP_TOO_COARSE``.
    """
    pts = sorted(points, key=lambda p: p["p_in_w"])
    if len(pts) < linear_points + 1:
        raise ExtractError("SWEEP_TOO_SHORT", f"need at least {linear_points + 1} drive points")
    pin = np.array([_dbm(p["p_in_w"]) for p in pts])
    pout = np.array([_dbm(p["p_out_w"]) for p in pts])
    gain = pout - pin
    lin = gain[:linear_points]
    if lin.max() - lin.min() > linear_spread_db:
        raise ExtractError("LINEAR_REGION_NOT_FOUND",
                           f"lowest {linear_points} points differ by {lin.max() - lin.min():.3f} dB in gain")
    g_lin = float(np.median(lin))
    comp = g_lin - gain
    i_sat = int(np.argmax(pout))
    steps = np.diff(pin)
    if np.any(steps[:i_sat] > STEP_SAT_DB + 1e-9):
        raise ExtractError("SWEEP_STEP_TOO_COARSE", f"drive step above {STEP_SAT_DB} dB before Psat")

    res = {
        "psat_dbm": float(pout[i_sat]),
        "psat_index": i_sat,
        "psat_at_sweep_end": i_sat == len(pts) - 1,
        "pae_at_psat": pts[i_sat].get("pae"),
        "peak_pae": max((p["pae"] for p in pts if p.get("pae") is not None), default=None),
        "gain_linear_db": g_lin,
        "p1db_status": "not_reached",
        "p1db_in_dbm": None,
        "p1db_out_dbm": None,
    }
    for k in range(1, len(pts)):
        if comp[k] >= 1.0 > comp[k - 1]:
            step = pin[k] - pin[k - 1]
            if step > STEP_P1DB_DB + 1e-9:
                raise ExtractError("SWEEP_STEP_TOO_COARSE",
                                   f"drive step {step:.3f} dB across 1 dB compression exceeds {STEP_P1DB_DB} dB")
            frac = (1.0 - comp[k - 1]) / (comp[k] - comp[k - 1])
            p1_in = pin[k - 1] + frac * step
            res.update(p1db_status="reached", p1db_in_dbm=float(p1_in),
                       p1db_out_dbm=float(p1_in + g_lin - 1.0))
            break
    return res
