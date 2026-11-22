#!/usr/bin/env python3
"""Generate the DUT bench decks and `klt sim` requests (T1 item 9 benches).

    python3 -I sim/lib/gen_dut_benches.py            # (re)write the committed decks
    python3 -I sim/lib/gen_dut_benches.py --check    # fail if a committed deck is stale

Any other argument is a usage error (exit 2) and writes nothing; the shared driver
in ``bench_gen.py`` says why.

Writes, for the DUT `design/netlist/sg13g2-pa.spice` (`.subckt sg13g2-pa RFIN
RFOUT VCC GND`):

* ``sim/psat-sweep/psat_sweep.{spice,request.json}``  transient drive sweep
* ``sim/psat-sweep/psat_sweep_match.{spice,request.json}`` the same sweep through an
  ideal off-chip output match (``match`` variant; see ``psat_bench``), drive grid
  crossed with the declared PVT matrix
* ``sim/ac-gain/ac_gain.{spice,request.json}``        S-parameters over the band
* ``sim/ac-stability/ac_stability.{spice,request.json}`` S-parameters 10 MHz-30 GHz
* ``sim/pvt-matrix.json`` + ``sim/psat-sweep/psat_sweep_match.pvt-matrix.json``
  the declared PVT matrix (27 cells; the latter crossed with the drive grid)
  for ``klt corner-matrix check``

The DUT netlist is **inlined verbatim** into each deck (klt sim owns the
`.control` block, and an `.include` path would be resolved against an unknown
working directory), behind a header that records its sha256. ``--check``
recomputes that hash from the netlist on disk and byte-compares every generated
file, so a netlist change that is not regenerated fails loudly instead of
silently benching a stale copy.

The bench facts a record must restate -- ``F0_HZ``, ``RS_OHM``, ``RL_OHM``, the
nominal cell (``PROCESS_NOM``, ``TEMP_NOM_C``, ``VCC_NOM_V``), the declared PVT
matrix (``PVT_PROCESS_SECTIONS`` x ``PVT_TEMP_C`` x ``PVT_VCC_V``) and the DUT's
output array via ``output_array()`` -- are declared (or derived from the
netlist) here once; the reducers import them rather than keeping their own
copies. The two psat variants differ in more than a filename (load, harmonic
terminations, and which nodes carry the load power and the chip-boundary
current), so every one of those facts is declared in ``psat_bench(variant)``
and read from there by ``psat_record.py``: a deck whose extraction nodes moved
cannot leave a record quoting the other variant's labels.

The AC requests and the matched psat request declare the full PVT matrix (27
cells, T1 item 5); the committed ``sim/pvt-matrix.json`` and
``sim/psat-sweep/psat_sweep_match.pvt-matrix.json`` are the same declaration
in the two shapes ``klt corner-matrix`` checks requests and reports against.
The bare psat request stays at the nominal cell -- the ratified large-signal
rows are judged on the matched bench, whose harmonic terminations make the
bare deck's P_out/PAE not comparable with it.

The parts that are not specific to this DUT -- the pinned PDK name and corner-library
path, the host's capacity wait, the request skeleton and the write/``--check`` driver
-- live once in ``sim/lib/bench_gen.py``, shared with
``sim/device-npn13g2/gen_bench.py``.

Nothing here is a result; the decks are simulated benches. The output network
of the DUT is ideal passives (see `design/README.md`), and every bench says so.
"""
import cmath
import hashlib
import json
import math
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The PDK constants, the request skeleton and the strict write/--check driver live
# once in sim/lib/bench_gen.py, shared with sim/device-npn13g2/gen_bench.py; never
# retype the corner-library path or the capacity wait here.
import bench_gen  # noqa: E402
from units import dbm  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
NETLIST = REPO / "design" / "netlist" / "sg13g2-pa.spice"

F0_HZ = 2.44175e9           # band centre (spec: Band row)
BAND_LO_HZ = 2.4e9
BAND_HI_HZ = 2.4835e9
RS_OHM = 50.0
RL_OHM = 50.0
VCC_NOM_V = 0.8             # DR 0003 (PROPOSED) nominal; the Supply row is DRAFT
PROCESS_NOM = "hbt_typ"
TEMP_NOM_C = 27

# --- The PVT corner matrix (spec "PVT corner box"; T1 item 5, issue #173) ---
#
# The 27 cells the grid benches cover: the three HBT sections of the pinned
# corner library x the spec's three ambient temperatures x the Supply row's
# +/-10 %. This triple is THE declaration -- the request axes, the committed
# matrix files `sim/pvt-matrix.json` and
# `sim/psat-sweep/psat_sweep_match.pvt-matrix.json`, and every matrix record
# derive from it, never from a second list. The Supply row is DRAFT (DR 0003
# PROPOSED), so every result off this matrix is provisional by construction.
PVT_PROCESS_SECTIONS = ("hbt_typ", "hbt_bcs", "hbt_wcs")
PVT_TEMP_C = (-40.0, 27.0, 125.0)
PVT_VCC_V = (round(0.9 * VCC_NOM_V, 3), float(VCC_NOM_V), round(1.1 * VCC_NOM_V, 3))
# The two committed matrix files: the 27-cell box (the small-signal benches'
# shape) and its drive-crossed expansion (the matched psat bench's shape --
# one full drive sweep per cell).
PVT_MATRIX_REL = "sim/pvt-matrix.json"
PSAT_MATCH_MATRIX_REL = "sim/psat-sweep/psat_sweep_match.pvt-matrix.json"

# Transient: the base-bias node settles with a time constant of ~70 RF periods
# (Cin x the mirror's Rb), so 500 periods (>= 100 required) give the spec's settling
# criterion room; step 2.0 ps < T/200 = 2.048 ps (the spec's maximum).
N_PERIODS = 500
T_PERIOD_S = 1.0 / F0_HZ
TRAN_STEP_S = 2.0e-12
TRAN_STOP_S = (N_PERIODS + 0.1) * T_PERIOD_S

# --- The off-chip output match (the `match` psat variant) -----------------
#
# The default psat deck drives a bare RL_OHM from RFOUT, so nothing transforms the
# load and the array is not loaded as the load-line study sized it. The `match`
# variant puts an IDEAL, LOSSLESS L-section between RFOUT and that same RL_OHM, so
# the collector sees the load-line resistance. It evidences the spec's **Fallback**
# Output-port cell ("50 ohm, off-chip output match (stated boundary)") and nothing
# else: the chip boundary is RFOUT (`design/README.md`), every element of the network
# is off chip, and no inductor model is involved (DR 0001 D-1 stays deferred).
#
# Nothing here is tuned to a result. The resistance comes from the load-line record's
# nominal cell and the DUT's own array size; the two element values are the closed-form
# L-section for that resistance, with the DUT's on-chip `Cblock` absorbed into the
# series branch so the COLLECTOR, not RFOUT, sees a real load-line resistance.
LOADLINE_RECORD = (REPO / "sim" / "device-npn13g2" / "records"
                   / "20261107-125027-93cf5ae.loadline.json")
# The load-line cell to size against: the nominal supply, nominal tolerance,
# saturated-swing row. `saturated` is the swing mode the study's own recommendation
# is drawn from; the `fixed-nominal` row of the same cell carries identical numbers
# today, so the selector names the mode rather than relying on that coincidence.
LOADLINE_SWING_MODE = "saturated"

# The batch fleet's whole-job ceiling and per-job overhead, as `klt` reports them in
# `environment.remote.job_ceiling` (fleet_config; see the job_ceiling block of
# sim/psat-sweep/records/20261107-125209-93cf5ae.md). They are the fleet's values, not
# this repo's: `klt` re-assesses every submit and warns if they have moved, so a stale
# copy here shows up as a warning on the run rather than as a silently oversized job.
BATCH_MAX_JOB_S = 3600.0
BATCH_JOB_OVERHEAD_S = 120.0
# Per-unit timeout for the matched sweep. The committed bare-deck run measured
# 6.87-7.54 s per drive point (72 corners, `psat_sweep.report.json` `runtime_s`), and the
# matched deck simulates the same transient with two extra ideal passives, so 300 s is
# ~40x the worst measured unit. The bare deck's 1800 s is ~250x it, which is what forces
# that request's one-unit-per-job sharding (`recommended_hosts: 72`); 300 s lets whole
# shards fit the ceiling, so `remote.hosts` below is a handful rather than one per point.
PSAT_MATCH_TIMEOUT_S = 300
# Top of the matched drive grid, dBm available. The matched sweep EXTENDS the bare grid
# upward; it does not shift it (see `drive_grid_match_dbm`). Both ends are set by the
# first matched run, `sim/psat-sweep/records/20261114-032358-651c0cf-match.{md,json}`,
# which is committed as the evidence for them:
#
#   * P_out peaks at Pavail +5.2 dBm and has rolled off ~4 dB by +10, so +10.0 puts Psat
#     well inside the sweep (`psat_at_sweep_end: false`) without chasing it.
#   * Above roughly +17 dBm available the deck stops solving: that run's top 12 points
#     came back `KLT_STATUS_error` with ngspice's `timestep_too_small` (the transient
#     aborted, flagged on the bias-reference device `XQref`) and the two below them
#     `UNSETTLED`. Those drive levels also sit at collector peaks near 6 V against a
#     BVCEO(min) of 1.4 V. Either way there is nothing extractable up there, so the grid
#     stops below it rather than spending fleet units on points no record can use.
#
# This is a measured bound, not a fitted one: `reduce_sweep`'s `psat_at_sweep_end` still
# judges every run, and a record that reaches its sweep end is extended and rerun.
PSAT_MATCH_TOP_DBM = 10.0
# Top of the matched grid's COARSE (0.8 dB) tail. Above it every point is on the 0.4 dB
# fine step. The coarse tail exists only to establish the reference gain cheaply, in the
# flat region; everything that might be compressing is fine-stepped, because
# `reduce_sweep` requires <= 0.5 dB of *measured* P_in across the 1 dB compression
# bracket and that bracket's position is a property of the run, not of the grid.
#
# The bare deck can afford a coarse tail up to -16.8 dBm: it compresses 1 dB at
# P_in -16.6 dBm. The matched deck compresses far earlier in available drive -- the
# second matched run (`records/20261114-033006-28e69b9-match.*`, committed) measured the
# 1 dB point between Pavail -25.6 and -24.8 dBm, and was refused
# `SWEEP_STEP_TOO_COARSE` (0.912 dB across the bracket) for exactly that reason. Hence a
# coarse tail that stops at -28.0 dBm, which leaves the whole compressing range -- the
# bracket with ~3 dB to spare below it -- on the fine step.
PSAT_MATCH_COARSE_TOP_DBM = -28.0

# --- The P1dB linear-reference probe (issue #192) ---------------------------
#
# The spec's Output P1dB row takes its reference gain from "the linear region of the
# same sweep (drive >= 20 dB below the compressing level)". The committed matched grid
# CANNOT satisfy that sentence, and not by oversight: its bottom (-36.0 dBm available)
# sits at the floor klt's corner-id encoding allows. klt names each unit by a corner id
# whose supply-axis values are formatted to three decimals (`vamp=0.010`), and rounds
# the artifact directory to the same slug, so two drive points whose source amplitudes
# fall in one millivolt bucket collapse onto one unit (the klayout-tools#5870 class of
# collision; `assert_pvt_corner_ids_distinct` refuses it at generation time, and the
# matrix record's committed corner ids show the 3-decimal format live). Below roughly
# 10 mV of amplitude -- about -35.7 dBm available into 50 ohm -- no <= 1 dB spaced
# grid stays one bucket per point, and `reduce_sweep` forbids steps above 1 dB before
# Psat, so the committed bench cannot reach a reference region 20 dB under any cell
# that compresses above -48 dBm available. Every cell of the matrix record does: the
# earliest measured 1 dB point is at Pavail -25.6 dBm (nominal cell), which leaves the
# committed reference points only ~8-16 dB below compression depending on the cell.
# The encoding gap is filed with klayout-tools (friction protocol); until it closes,
# this probe is the bench that measures what the committed grid cannot.
#
# It reuses the committed MATCHED deck unchanged (same load, harmonic terminations and
# extraction nodes -- it changes no bench fact) and swaps only the drive axis for a
# SPARSE low-drive one: 4 dB spacing, the coarsest that keeps every corner id distinct
# down to -56 dBm available (2 dB spacing collides below about -44 dBm: consecutive
# amplitudes share the `vamp=0.003` bucket). -56 dBm is itself 28 dB below the
# earliest measured compression, so the probe's own lowest points already satisfy the
# spec sentence the committed grid violates; the top probe point IS the committed
# grid's bottom, so the two measurements bridge. The probe is NOT a drive sweep: its
# steps are 4 dB, its points bracket no compression, and `reduce_sweep` is never run
# on it -- its record extrapolates each cell's gain-vs-drive deficit to zero drive
# (`p1dbref_record.py`) and reports the error the committed three-lowest-points
# reference carries.
P1DBREF_PROBE_GRID_DBM = (-56.0, -52.0, -48.0, -44.0, -40.0, -36.0)
P1DBREF_PROBE_REQUEST_REL = "sim/psat-sweep/psat_sweep_match_p1dbref.request.json"


def drive_grid_dbm():
    """Available drive power, dBm, ascending. The reducer's step limits apply to the
    *measured* input power, which moves with the input match as the device
    compresses, so the available-power steps are kept below the limits with margin:
    0.8 dB in the linear region (limit 1 dB to Psat), 0.4 dB from -16.4 dBm up
    through compression and saturation (limit 0.5 dB across the 1 dB point)."""
    pts = [round(-36.0 + 0.8 * k, 1) for k in range(25)]            # -36.0 .. -16.8
    pts += [round(-16.4 + 0.4 * k, 1) for k in range(47)]           # -16.4 .. +2.0
    return pts


def drive_grid_match_dbm():
    """Available drive power, dBm, ascending, for the matched deck.

    Same start, same two step sizes and the same step limits as ``drive_grid_dbm()``,
    but the coarse/fine boundary and the top are the matched load's own. Both were
    settled by real runs rather than argued from the bare grid, because translating or
    reusing the bare grid does not work and the two failures are instructive:

    * **The bottom must not move.** A grid shifted up by the ~14.2 dB the load-drop
      estimate had predicted starts at -22.0 dBm, where this deck is already
      compressing, so the three lowest-drive points ``reduce_sweep`` takes its
      reference gain from disagree (0.391 dB against a 0.1 dB limit) and the whole
      reduction is refused ``LINEAR_REGION_NOT_FOUND``. First matched run,
      ``…-651c0cf-match``. The bottom also cannot move DOWN: klt's corner-id
      encoding rounds supply-axis values to three decimals, so below ~10 mV of
      source amplitude no <= 1 dB spaced grid keeps one bucket per point (see
      ``P1DBREF_PROBE_GRID_DBM`` -- the low-drive probe that measures the
      reference region this floor keeps the committed grid out of).
    * **The coarse tail must stop early.** With the bare grid's boundary (-16.8 dBm) the
      1 dB compression point lands inside the 0.8 dB region: measured P_in steps 0.912 dB
      across the bracket against a 0.5 dB limit, refused ``SWEEP_STEP_TOO_COARSE``.
      Second matched run, ``…-28e69b9-match``.

    So: 0.8 dB up to ``PSAT_MATCH_COARSE_TOP_DBM`` (the linear reference tail only), then
    0.4 dB the whole way to ``PSAT_MATCH_TOP_DBM``, which puts the entire compressing and
    saturating range on the fine step and the P1dB bracket well inside it. The measured
    P_in step tracks the available step at up to ~1.15x here (the input match improves as
    the device compresses), so 0.4 dB of available drive stays under the 0.5 dB limit.
    """
    lo, coarse_top, top, coarse, fine = -36.0, PSAT_MATCH_COARSE_TOP_DBM, PSAT_MATCH_TOP_DBM, 0.8, 0.4
    if not lo < coarse_top < top:
        raise ValueError(
            f"the matched grid needs {lo:g} < PSAT_MATCH_COARSE_TOP_DBM "
            f"({coarse_top:g}) < PSAT_MATCH_TOP_DBM ({top:g}): a coarse tail that does "
            "not end leaves the P1dB bracket on the 0.8 dB step, and a top below it "
            "never reaches saturation")
    n_coarse = int(round((coarse_top - lo) / coarse)) + 1
    pts = [round(lo + coarse * k, 1) for k in range(n_coarse)]
    n_fine = int(round((top - coarse_top) / fine))
    pts += [round(coarse_top + fine * (k + 1), 1) for k in range(n_fine)]
    return pts

def batch_hosts(unit_count, per_unit_timeout_s):
    """The smallest ``remote.hosts`` whose largest shard stays inside the fleet ceiling.

    Mirrors `klt`'s own pre-submit assessment (`sim_batch._assess_job_ceiling`): a job's
    conservative bound is ``units * options.timeout_s + overhead``, every shard holds at
    most ``ceil(units / hosts)`` units, and a bound *equal* to the ceiling is inside it.
    Deriving it here rather than writing a number keeps `remote.hosts` tracking the grid
    length: adding drive points cannot quietly push a shard past the ceiling, where every
    unit of an over-running job is reported ``batch_job_timeout``.
    """
    per_job = 0
    while ((per_job + 1) * per_unit_timeout_s + BATCH_JOB_OVERHEAD_S) <= BATCH_MAX_JOB_S:
        per_job += 1
    if per_job < 1:
        raise ValueError(
            f"a single unit's bound ({per_unit_timeout_s:g}s + "
            f"{BATCH_JOB_OVERHEAD_S:g}s) already exceeds the fleet's whole-job ceiling "
            f"({BATCH_MAX_JOB_S:g}s); no remote.hosts value fits -- lower the timeout")
    return math.ceil(unit_count / per_job)


def amp_v(p_avail_dbm):
    """Source EMF amplitude giving the available power into RS (P = A^2/(8 RS))."""
    p_w = 1e-3 * 10 ** (p_avail_dbm / 10.0)
    return math.sqrt(8.0 * RS_OHM * p_w)


def pvt_cell_count():
    """The cell count of the declared PVT matrix (3 sections x 3 temps x 3 supplies)."""
    return len(PVT_PROCESS_SECTIONS) * len(PVT_TEMP_C) * len(PVT_VCC_V)


def pvt_psat_supply_axis(variant="match"):
    """The matched psat bench's `corners.supply_v`: the drive grid CROSSED with
    the supply points, as parallel per-index lists (klt sweeps multiple supply
    keys together by index, never as a cross product of their own).

    Supply-major, so the crossed expansion (process x supply x temperature)
    runs each cell's drive sweep as one contiguous run of units; `vcc` repeats
    the supply point across its whole sweep and `vamp` repeats the grid once
    per supply point.
    """
    grid = drive_grid_match_dbm() if variant == "match" else drive_grid_dbm()
    vamps, vccs = [], []
    for vcc in PVT_VCC_V:
        for p in grid:
            vamps.append(round(amp_v(p), 9))
            vccs.append(vcc)
    return {"vamp": vamps, "vcc": vccs}


def pvt_psat_units(variant="match"):
    """Every (cell, drive) unit of the psat matrix request, as explicit
    `{process, temperature_c, supply_v}` records in klt's own odometer order
    (process, supply, temperature) -- the expansion `klt sim` performs on the
    crossed axes above, enumerated here so the corner-id screen below sees
    exactly the units a submit would dispatch."""
    axis = pvt_psat_supply_axis(variant)
    return _crossed_units(axis)


def _crossed_units(axis):
    units = []
    for proc in PVT_PROCESS_SECTIONS:
        for vamp, vcc in zip(axis["vamp"], axis["vcc"]):
            for temp in PVT_TEMP_C:
                units.append({"process": proc, "temperature_c": temp,
                              "supply_v": {"vamp": vamp, "vcc": vcc}})
    return units


def p1dbref_probe_axis():
    """The probe request's `corners.supply_v`: the sparse low-drive grid crossed
    with the supply points, supply-major exactly like `pvt_psat_supply_axis`
    (vamp/vcc sweep together by index, one contiguous run of probe points per
    cell)."""
    vamps, vccs = [], []
    for vcc in PVT_VCC_V:
        for p in P1DBREF_PROBE_GRID_DBM:
            vamps.append(round(amp_v(p), 9))
            vccs.append(vcc)
    return {"vamp": vamps, "vcc": vccs}


def p1dbref_probe_units():
    """Every (cell, probe drive) unit of the reference-probe request, for the
    same pre-submit corner-id screen the matrix units get."""
    return _crossed_units(p1dbref_probe_axis())


def p1dbref_probe_request():
    """The P1dB linear-reference probe request (issue #192): every declared PVT
    cell x the sparse low-drive grid, on the committed matched deck.

    Same options, timeout and sharding arithmetic as the matched matrix bench
    (it is the same per-unit transient); it is NOT a declared-matrix bench, so
    it gets no `klt corner-matrix` gate -- its coverage is the probe grid, and
    its record states both."""
    units = p1dbref_probe_units()
    n_units = assert_pvt_corner_ids_distinct(units)
    req = _matrix_request(
        "psat_sweep_match.spice",
        {"kind": "tran", "args": f"{TRAN_STEP_S * 1e12:.6g}p {TRAN_STOP_S * 1e9:.6g}n"},
        {"timeout_s": PSAT_MATCH_TIMEOUT_S, "keep_artifacts": True, "waveforms": True,
         "capture_only": True, "save_mode": "netlist"},
        corners_extra={"supply_v": p1dbref_probe_axis()},
    )
    req["remote"] = {"hosts": batch_hosts(n_units, PSAT_MATCH_TIMEOUT_S)}
    return req


def klt_corner_id(process, supply_v, temperature_c):
    """The per-unit corner id `klt sim` names a unit with.

    Mirrors klayout-tools `sim_corner_point.CornerPoint.corner_id` at the
    pinned 0.9.0: ``<process>/<supply>V/<temp>C``, the supply label either
    ``<value>.3f V`` (one key) or sorted ``key=value.3f`` pairs joined by
    ``_`` (several keys), and an integer-valued temperature without its
    ``.0``. The 3-decimal rounding is the hazard klayout-tools#5870 is
    about -- two axis values inside one millivolt collapse onto one id and
    one artifact directory -- which is why this mirror exists at all:
    `assert_pvt_corner_ids_distinct()` screens every (cell, drive) pair with
    the same text klt will name the unit with, BEFORE any submit. The
    runners' `--dry-run` re-check is the authoritative one if this mirror
    ever drifts from the tool.
    """
    if not supply_v:
        supply_label = "novdd"
    elif len(supply_v) == 1:
        supply_label = f"{next(iter(supply_v.values())):.3f}V"
    else:
        supply_label = "_".join(f"{k}={v:.3f}" for k, v in sorted(supply_v.items())) + "V"
    temp = int(temperature_c) if float(temperature_c).is_integer() else temperature_c
    return f"{process}/{supply_label}/{temp}C"


def assert_pvt_corner_ids_distinct(units):
    """Refuse a matrix whose per-unit corner ids collide (klayout-tools#5870).

    klt names each unit by its corner id and stores that unit's artifacts
    under the id's slug, so two units inside one 3-decimal supply bucket share
    both and one silently masks the other. Raised at generation time (so a
    drifting drive grid fails `--check` loudly) and re-checked by the runners
    against `klt sim --dry-run`'s authoritative unit list before any submit.
    """
    seen = {}
    for u in units:
        cid = klt_corner_id(u["process"], u["supply_v"], u["temperature_c"])
        if cid in seen:
            raise ValueError(
                f"matrix units {seen[cid]!r} and {u!r} share the corner id {cid!r}: "
                "klt formats supply axis values to three decimals, so close values "
                "collapse onto one unit (klayout-tools#5870). Keep every (cell, "
                "drive) pair distinct at three decimals or the drive grid step "
                "is too fine for the axis encoding.")
        seen[cid] = u
    return len(seen)


def pvt_matrix():
    """The declared 27-cell matrix as a committed `klt corner-matrix` file: the
    small-signal benches' shape (one cell per unit, supply = the Vcc axis)."""
    return {
        "description": (
            "sg13g2-pa PVT corner box (spec/target-spec.md), declared once by "
            "sim/lib/gen_dut_benches.py: 3 cornerHBT.lib sections x -40/27/125 C "
            "x supply nominal +/-10 % (nominal 0.8 V, DR 0003 PROPOSED -- Supply "
            "row DRAFT, so results are provisional). Checked against the "
            "ac-gain / ac-stability requests and reports with "
            "`klt corner-matrix check`."),
        "process": list(PVT_PROCESS_SECTIONS),
        "supply_v": {"vcc": list(PVT_VCC_V)},
        "temperature_c": list(PVT_TEMP_C),
    }


def psat_match_pvt_matrix():
    """The same declared 27 cells, crossed with the matched bench's drive grid
    (one full sweep per cell): the shape `klt corner-matrix` checks the
    matched psat request and report against. The cells are exactly
    `pvt_matrix()`'s; only the drive axis is added."""
    m = pvt_matrix()
    m["supply_v"] = pvt_psat_supply_axis("match")
    m["description"] = (
        "sg13g2-pa PVT corner box drive-crossed for sim/psat-sweep's matched "
        "bench: the 27 cells of sim/pvt-matrix.json x the matched drive grid "
        "(one full sweep per cell; vamp/vcc pairs sweep together by index). "
        "Declared once by sim/lib/gen_dut_benches.py; Supply row DRAFT, so "
        "results are provisional. Checked with `klt corner-matrix check`.")
    return m


def netlist_text():
    return NETLIST.read_text()


def netlist_sha256():
    return hashlib.sha256(NETLIST.read_bytes()).hexdigest()


# One output-array device: an npn13G2 instance on the shared COLL/VB nodes. The bias
# reference (XQref, on VREF) is deliberately not matched.
_ARRAY_DEVICE_RE = re.compile(r"^X\S+\s+COLL\s+VB\s+GND\s+GND\s+npn13G2\s+Nx=(\d+)\s*$",
                              re.IGNORECASE | re.MULTILINE)


def output_array(text=None):
    """``(device_count, nx)`` of the DUT's output array, read from the netlist.

    The reducers divide the collector current by the device count, so a hand-copied
    count silently under-reports per-device I_C when the array is resized. Raises
    ValueError when the netlist has no such array or mixes Nx values, so the record
    fails loudly instead of being graded against a stale divisor.
    """
    nxs = [int(m) for m in _ARRAY_DEVICE_RE.findall(netlist_text() if text is None else text)]
    if not nxs:
        raise ValueError("no npn13G2 instance on the shared COLL/VB nodes "
                         f"(expected the output array in {NETLIST})")
    if len(set(nxs)) != 1:
        raise ValueError(f"output array mixes Nx values {sorted(set(nxs))} in {NETLIST}; "
                         "per-device stress is not well defined")
    return len(nxs), nxs[0]


# The DUT's on-chip DC block, between RFOUT and the collector. The matched network
# absorbs its reactance, so its value is read from the netlist for the same reason the
# array size is: a hand-copied 100p would silently stop cancelling if the DUT changed,
# leaving the collector reactively mismatched with no error raised.
_CBLOCK_RE = re.compile(r"^Cblock\s+RFOUT\s+COLL\s+(\S+)", re.IGNORECASE | re.MULTILINE)

_SI_SUFFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
              "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12}


def _spice_value(text):
    """A SPICE element value (``100p``, ``1e-10``, ``4.7meg``) as a float.

    Only the suffixes ngspice documents, longest first so ``meg`` is not read as
    ``m``. A trailing unit word (``100pF``) is ignored the way ngspice ignores it.
    """
    s = text.strip().lower()
    m = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-z]*)$", s)
    if not m:
        raise ValueError(f"cannot read {text!r} as a SPICE element value")
    mantissa, suffix = float(m.group(1)), m.group(2)
    for name in sorted(_SI_SUFFIX, key=len, reverse=True):
        if suffix.startswith(name):
            return mantissa * _SI_SUFFIX[name]
    return mantissa


def cblock_farads(text=None):
    """The DUT's ``Cblock`` (RFOUT-COLL) in farads, read from the netlist."""
    hits = _CBLOCK_RE.findall(netlist_text() if text is None else text)
    if len(hits) != 1:
        raise ValueError(f"expected exactly one `Cblock RFOUT COLL <value>` line in "
                         f"{NETLIST}, found {len(hits)}; the matched output network "
                         "absorbs that element and cannot be derived without it")
    return _spice_value(hits[0])


def loadline_cell(doc=None):
    """The load-line study's nominal cell, from the committed record.

    Selects on supply, tolerance and swing mode rather than an index, and refuses
    anything but exactly one hit -- the resistance the matched network presents is
    derived from this row, so picking the wrong cell (or silently picking the first of
    several) would size the network for an operating point the bench does not run.
    """
    doc = json.loads(LOADLINE_RECORD.read_text()) if doc is None else doc
    hits = [c for c in doc["cells"]
            if c.get("supply_nominal_v") == VCC_NOM_V
            and c.get("tolerance") == "nominal"
            and c.get("swing_mode") == LOADLINE_SWING_MODE]
    if len(hits) != 1:
        raise ValueError(
            f"{LOADLINE_RECORD.name}: expected exactly one cell with "
            f"supply_nominal_v={VCC_NOM_V:g}, tolerance='nominal', "
            f"swing_mode='{LOADLINE_SWING_MODE}', found {len(hits)}")
    return hits[0]


def match_network(text=None, cell=None):
    """The ideal off-chip L-section, derived (never tuned, never hardcoded).

    ``r_per_nx_ohm`` is the load-line cell's own array-independent quantity,
    ``vswing_v / iq_per_nx_a``; dividing it by the DUT's **actual** total Nx gives
    the resistance the collector must see. The study's ``nx_needed.load_ohm_ideal``
    is deliberately NOT used: it is the load for the 106-Nx array the study
    *recommends*, not the array the netlist has, so reading it would size the
    network for a DUT that does not exist.

    Topology, series L toward the chip and shunt C across the 50 ohm side::

        COLL --[Cblock, ON CHIP]-- RFOUT |boundary| --[ls_h]--+--[RL_OHM]
                                                             |
                                                           [cp_f]
                                                             |
                                                            GND

    ``ls_h`` carries the plain L-section reactance ``q*ropt`` **plus** ``Cblock``'s
    ``1/(w0*Cblock)``, so at f0 the collector sees ``ropt_ohm`` with no residual
    reactance. That absorption is closed form, not a tuned cancellation.
    """
    n_units, nx = output_array(text)
    cell = loadline_cell() if cell is None else cell
    pout = cell["pout"]
    r_per_nx = cell["vswing_v"] / pout["iq_per_nx_a"]
    nx_total = n_units * nx
    ropt = r_per_nx / nx_total
    if not 0.0 < ropt < RL_OHM:
        raise ValueError(
            f"load-line resistance {ropt:g} ohm is not inside (0, {RL_OHM:g}): a "
            "two-element L-section can only step a load DOWN to the collector "
            f"(Q = sqrt({RL_OHM:g}/Ropt - 1) needs Ropt < {RL_OHM:g}). An array of "
            f"{nx_total} total Nx needs a different matching topology.")
    cblock = cblock_farads(text)
    w0 = 2.0 * math.pi * F0_HZ
    q = math.sqrt(RL_OHM / ropt - 1.0)
    return {
        "n_units": n_units, "nx": nx, "nx_total": nx_total,
        "r_per_nx_ohm": r_per_nx,
        "ropt_ohm": ropt,
        "q": q,
        "cp_f": q / (w0 * RL_OHM),
        "ls_h": (q * ropt + 1.0 / (w0 * cblock)) / w0,
        "ls_plain_h": q * ropt / w0,
        "cblock_f": cblock,
        "cblock_x_ohm": -1.0 / (w0 * cblock),
        # The analytic ceiling this load line goes with: the cell's per-Nx fundamental
        # power times the array. Hand arithmetic over the record, not a simulated result.
        "pout_ceiling_w": pout["pout_per_nx_w"] * nx_total,
        # Hand arithmetic (10*log10), not a simulated gain: the power ratio a fixed
        # collector current delivers into ropt vs RL_OHM (-14.19 dB here). It is NOT
        # the gain this bench loses -- the matched run measures ~2.97 dB of linear-gain
        # difference (records/20261114-034225-54cb27b-match.json against the bare
        # 20261107-125209-93cf5ae.json) -- and it is not, by itself, how far up the
        # drive grid had to move either, which measured +10.8 dB (Psat at Pavail
        # -5.6 -> +5.2 dBm, through the ideal lossless off-chip match). Same
        # direction as each measurement, a different number from both.
        "gain_drop_db": 10.0 * math.log10(ropt / RL_OHM),
        "loadline_record": LOADLINE_RECORD.relative_to(REPO).as_posix(),
        "loadline_cell": {"supply_nominal_v": cell["supply_nominal_v"],
                          "tolerance": cell["tolerance"],
                          "swing_mode": cell["swing_mode"],
                          "vswing_v": cell["vswing_v"],
                          "iq_per_nx_a": pout["iq_per_nx_a"],
                          "pout_per_nx_w": pout["pout_per_nx_w"]},
    }


def match_impedances(net=None, freqs=None):
    """``[(label, f_hz, z_into_network_at_RFOUT, z_seen_by_COLL), ...]``.

    Both are needed and they are not the same number: ``Cblock`` is a third of the
    load line at f0, so a record that quoted only one of them would not say what the
    array is actually loaded by. Arithmetic over ideal elements, not simulated.
    """
    net = match_network() if net is None else net
    rows = freqs if freqs is not None else [
        ("f0", F0_HZ), ("2 f0", 2.0 * F0_HZ), ("3 f0", 3.0 * F0_HZ),
        ("band low", BAND_LO_HZ), ("band high", BAND_HI_HZ)]
    out = []
    for label, f in rows:
        w = 2.0 * math.pi * f
        z_c = 1.0 / (1j * w * net["cp_f"])
        z_rfout = 1j * w * net["ls_h"] + (RL_OHM * z_c) / (RL_OHM + z_c)
        z_coll = z_rfout + 1.0 / (1j * w * net["cblock_f"])
        out.append((label, f, z_rfout, z_coll))
    return out


def _header(title, lines):
    out = [f"* {title}", "* GENERATED by sim/lib/gen_dut_benches.py -- do not edit; rerun it.",
           f"* DUT: design/netlist/sg13g2-pa.spice, sha256 {netlist_sha256()}, inlined verbatim below."]
    out += [f"* {line}".rstrip() for line in lines]
    return "\n".join(out) + "\n"


def _dut_block():
    return "\n* ---- DUT (verbatim copy of design/netlist/sg13g2-pa.spice) ----\n" \
        + netlist_text().rstrip("\n") + "\n* ---- end DUT ----\n\n"


PSAT_VARIANTS = ("bare", "match")


def _eng(x):
    """An element value for a deck line: plain scientific notation, no SI suffix.

    ngspice reads ``6.663497911019e-10`` and there is no suffix to mis-parse (and no
    in-line ``$`` comment to depend on). 13 significant digits, so the deck carries
    the derived value rather than a rounding of it; the engineering form and the
    derivation are spelled out in the deck header.
    """
    return f"{x:.12e}"


def psat_bench(variant="bare"):
    """Every fact the deck and the record must agree on, for one psat variant.

    ``psat_record.py`` reads the bench name, the load and harmonic-termination prose
    and the three extraction node names from here. That is the point: the two variants
    put the load power and the chip-boundary current on DIFFERENT nodes, and both
    moves fail silently if the reducer keeps its own copy. `i(vlsense)` is `Cblock`'s
    current in the bare deck (nothing else sits on `out`) and the *load* current in the
    matched one, so a reducer that kept using it for per-device `I_C` would print a
    wrong `Ic pk mA` column with no error raised; and `v(out) * i(vlsense)` is a power
    only while the two are the same node, which the matched deck's network breaks.
    """
    if variant not in PSAT_VARIANTS:
        raise ValueError(f"unknown psat variant {variant!r} (want one of {PSAT_VARIANTS})")
    if variant == "bare":
        return {
            "variant": "bare",
            "name": "psat_sweep",
            "suffix": "",
            # The load branch is the only other element on `out`, so one 0 V source
            # serves as both the load sense and the chip-boundary sense.
            "p_out_v": "v(out)", "p_out_i": "i(vlsense)",
            "ic_sense_i": "i(vlsense)",
            "ic_sense_md": "i(load)",
            "network": None,
            "load_md": f"Load: {RL_OHM:g} ohm resistive.",
            "terminations_md": (
                f"**Harmonic terminations: ideal {RL_OHM:g} ohm at 2 f0 and 3 f0 "
                "(the default, labelled; a flat resistor).** Results under other "
                "terminations are not comparable."),
        }
    net = match_network()
    return {
        "variant": "match",
        "name": "psat_sweep_match",
        "suffix": "-match",
        # P_out and the harmonics come from the 50 ohm resistor's OWN V and I (the spec's
        # "DFT of the load voltage/current"); `I_C` comes from the chip boundary.
        "p_out_v": "v(outl)", "p_out_i": "i(vlsense)",
        "ic_sense_i": "i(vbsense)",
        "ic_sense_md": "i(RFOUT boundary)",
        "network": net,
        "load_md": (
            f"Load: {RL_OHM:g} ohm resistive **through an ideal, lossless off-chip "
            f"L-section** (Ls {1e9 * net['ls_h']:.4f} nH series, Cp "
            f"{1e12 * net['cp_f']:.4f} pF shunt, Q {net['q']:.3f}), so the collector "
            f"sees {net['ropt_ohm']:.4f} ohm at f0."),
        "terminations_md": (
            "**Harmonic terminations are NOT the labelled ideal-50-ohm default: the "
            "output network sets them.** The collector sees "
            f"{_z_md(net, '2 f0')} at 2 f0 and {_z_md(net, '3 f0')} at 3 f0. Per "
            "`spec/target-spec.md` (\"Harmonic terminations\"), a bench that changes "
            "them says so and its P_out or PAE **is not compared** with a run under "
            "other terminations."),
    }


def _z_md(net, label):
    for lab, _f, _z_rfout, z_coll in match_impedances(net):
        if lab == label:
            return f"{z_coll.real:.2f} {z_coll.imag:+.2f}j ohm"
    raise ValueError(f"no impedance row labelled {label!r}")


def psat_deck(variant="bare"):
    b = psat_bench(variant)
    if variant == "bare":
        h = _header(
            "Psat / P1dB / PAE drive sweep, transient (simulated bench, not a result)",
            [
                f"Source: EMF behind Rs = {RS_OHM:g} ohm; amplitude = v(amp), set per drive point by",
                "  klt sim corners.supply_v (`alter vamp=`), f0 = 2.44175 GHz (band centre).",
                f"Load: {RL_OHM:g} ohm resistive at f0 and, being a flat resistor, at 2 f0 and 3 f0",
                "  (the DEFAULT harmonic terminations: ideal 50 ohm, labelled so).",
                "Output network: IDEAL passives (Lchoke, Cblock, Cin in the DUT) -- no inductor model.",
                "P_DC = full supply Vcc power, bias reference included (Iref is an ideal source from Vcc).",
                "Load current is measured through the 0 V source Vlsense (into the load);",
                "supply current through Vcc (delivered = -i(vcc)); input current is -i(bs).",
            ],
        )
        body = f"""Vcc vcc 0 dc {VCC_NOM_V}
Vamp amp 0 dc 0.1
Bs src 0 V = v(amp)*sin(2*3.14159265358979*{F0_HZ:.8g}*time)
Rs src in {RS_OHM:g}
Xdut in out vcc 0 sg13g2-pa
Vlsense out outl 0
Rl outl 0 {RL_OHM:g}
* Saved set: port/supply waveforms for rf_extract, plus the collector/base nodes and the
* self-heating temperature node of the first array device (the 14 devices share COLL/VB and
* are identical, so one is representative; the record says so).
.save v(out) v(in) v(vcc) v(amp) i(vlsense) i(vcc) i(bs) i(l.xdut.lchoke) v(xdut.coll) v(xdut.vb) v(xdut.xq1.t)
"""
        return h + _dut_block() + body

    net = b["network"]
    zrows = match_impedances(net)
    z = {lab: (zr, zc) for lab, _f, zr, zc in zrows}
    h = _header(
        "Psat / P1dB / PAE drive sweep through an IDEAL OFF-CHIP OUTPUT MATCH "
        "(simulated bench, not a result)",
        [
            f"Source: EMF behind Rs = {RS_OHM:g} ohm; amplitude = v(amp), set per drive point by",
            "  klt sim corners.supply_v (`alter vamp=`), f0 = 2.44175 GHz (band centre). The",
            "  PVT matrix crosses that drive axis with the supply points and the HBT",
            f"  sections/temperatures ({pvt_cell_count()} cells x the drive grid): vcc is",
            f"  `alter vcc=` per unit, the deck's own Vcc line is the {VCC_NOM_V:g} V nominal.",
            "",
            "CHIP BOUNDARY IS RFOUT (node `out`; design/README.md). On the chip side:",
            "  the DUT only (Lchoke, Cblock, Cin). Off chip: Vbsense, Lmatch, Cmatch,",
            f"  Vlsense and the {RL_OHM:g} ohm load below -- all IDEAL and LOSSLESS (no Q, no",
            "  self-resonance, no inductor model). This bench evidences the spec's FALLBACK",
            "  Output-port cell (`50 ohm, off-chip output match (stated boundary)`) and its",
            "  convention that an off-chip network's loss is NOT counted as the chip's.",
            "  The on-chip-match Target row stays unevidenced while DR 0001 D-1 is open.",
            "",
            "OUTPUT NETWORK (two-element L-section, derived -- not tuned to a result):",
            "",
            f"  COLL --[Cblock {1e12 * net['cblock_f']:g}p, ON CHIP]-- RFOUT |boundary| --[Lmatch]--+--[Rl]",
            "                                                              |",
            "                                                           [Cmatch]",
            "                                                              |",
            "                                                             GND",
            "",
            f"  Ropt  = {net['ropt_ohm']:.6f} ohm at the COLLECTOR",
            f"        = (vswing_v / iq_per_nx_a) / (total Nx) = ({net['loadline_cell']['vswing_v']:g}"
            f" / {net['loadline_cell']['iq_per_nx_a']:g}) / {net['nx_total']}",
            f"        from {net['loadline_record']}, cell",
            f"        supply_nominal_v {net['loadline_cell']['supply_nominal_v']:g} / "
            f"tolerance {net['loadline_cell']['tolerance']} / swing_mode "
            f"{net['loadline_cell']['swing_mode']},",
            f"        over the array this netlist has ({net['n_units']} devices x Nx="
            f"{net['nx']} = {net['nx_total']} Nx). The study's own nx_needed.load_ohm_ideal",
            "        is NOT used: it belongs to the 106-Nx array the study recommends.",
            f"  Q     = sqrt({RL_OHM:g}/Ropt - 1) = {net['q']:.6f}",
            f"  Cmatch= Q/(w0*{RL_OHM:g})          = {1e12 * net['cp_f']:.6f} pF",
            f"  Lmatch= (Q*Ropt + 1/(w0*Cblock))/w0 = {1e9 * net['ls_h']:.6f} nH",
            f"        = {1e9 * net['ls_plain_h']:.6f} nH L-section + "
            f"{1e9 * (net['ls_h'] - net['ls_plain_h']):.6f} nH absorbing Cblock",
            f"  Cblock is {net['cblock_x_ohm']:.4f} ohm reactive at f0 -- "
            f"{100 * abs(net['cblock_x_ohm']) / net['ropt_ohm']:.0f}% of Ropt, so it is",
            "        absorbed in closed form rather than neglected; that is why the",
            "        COLLECTOR, not RFOUT, sees a real Ropt. That impedance includes",
            "        the series Cblock but not the DUT's shunt Lchoke at COLL; the",
            "        numerical case for leaving Lchoke alone, at the original design",
            "        point, is issue #116.",
            "",
            "HARMONIC TERMINATIONS ARE NO LONGER THE LABELLED IDEAL-50-OHM DEFAULT:",
            f"  at RFOUT / at COLL through Cblock (arithmetic over ideal elements):",
        ] + [
            f"    {lab:9s} {f / 1e9:7.5f} GHz   {zr.real:8.4f} {zr.imag:+8.4f}j   "
            f"{zc.real:8.4f} {zc.imag:+8.4f}j ohm"
            for lab, f, zr, zc in zrows
        ] + [
            "  Per spec/target-spec.md (\"Harmonic terminations\"), P_out and PAE from this",
            "  bench are NOT comparable with a run under other terminations.",
            "",
            "EXTRACTION NODES (they are not the bare deck's, and that is load-bearing):",
            f"  P_out, H2, H3 from the load's own V and I ({b['p_out_v']}, {b['p_out_i']}) --",
            "    the spec's `DFT of the load voltage/current`. Vlsense is 0 V, so",
            "    v(outl) == v(oload) and the pair is co-located at the resistor.",
            f"  Per-device I_C from the CHIP BOUNDARY ({b['ic_sense_i']}, through Vbsense at",
            "    RFOUT) = Cblock's current, so KCL at COLL is (i(Lchoke) - i(Vbsense)) / "
            f"{net['n_units']}.",
            "    The load branch is NOT that current here: Cmatch shunts part of it.",
            "",
            f"Analytic ceiling for this load line: {net['nx_total']} Nx x "
            f"{net['loadline_cell']['pout_per_nx_w']:g} W = {net['pout_ceiling_w']:g} W = "
            f"{dbm(net['pout_ceiling_w']):.2f} dBm",
            "  (hand arithmetic over the load-line record, NOT a simulated result).",
            "P_DC = full supply Vcc power, bias reference included (Iref is an ideal source from Vcc).",
            "Supply current through Vcc (delivered = -i(vcc)); input current is -i(bs).",
        ],
    )
    body = f"""Vcc vcc 0 dc {VCC_NOM_V}
Vamp amp 0 dc 0.1
Bs src 0 V = v(amp)*sin(2*3.14159265358979*{F0_HZ:.8g}*time)
Rs src in {RS_OHM:g}
Xdut in out vcc 0 sg13g2-pa
* ---- chip boundary: everything below this line is OFF CHIP and IDEAL ----
Vbsense out onet 0
Lmatch onet oload {_eng(net['ls_h'])}
Cmatch oload 0 {_eng(net['cp_f'])}
Vlsense oload outl 0
Rl outl 0 {RL_OHM:g}
* Saved set: the load's own V and I (v(outl)/i(vlsense)) for P_out and the harmonics, the
* chip-boundary current (i(vbsense)) for per-device I_C, the port/supply waveforms for
* rf_extract, and the collector/base nodes plus the self-heating temperature node of the
* first array device (the {net['n_units']} devices share COLL/VB and are identical, so one is
* representative; the record says so).
.save v(out) v(outl) v(in) v(vcc) v(amp) i(vbsense) i(vlsense) i(vcc) i(bs) i(l.xdut.lchoke) v(xdut.coll) v(xdut.vb) v(xdut.xq1.t)
"""
    return h + _dut_block() + body


def _ac_deck(title, extra_header):
    # The AC decks are only readable as S-parameters through
    # `sim/lib/sparams.py` `s_from_nodes`, whose 2 v(out)/vs forms are S21/S12
    # only when the source and load resistances are equal (with unequal ones the
    # transducer gain |2 Vout/Vs|^2 is off by Rs/Rl). Port 2 is also driven
    # behind RL_OHM here, so S22 would reference RL_OHM while the record labels
    # it RS_OHM. Refuse to build the deck rather than emit a silently
    # mislabelled S21 / transducer gain / S22 reference; whoever diverges the
    # two constants must teach `s_from_nodes` per-port reference impedances and
    # drop this guard in the same change.
    if RS_OHM != RL_OHM:
        raise ValueError(
            f"unequal port impedances RS_OHM={RS_OHM:g} ohm, RL_OHM={RL_OHM:g} ohm: "
            "sparams.s_from_nodes only supports equal port impedances, so the AC "
            "decks' S21, transducer gain and S22 reference would not be what the "
            "record labels them. Teach sparams.s_from_nodes per-port reference "
            "impedances before diverging the two constants.")
    h = _header(title, extra_header + [
        f"Two independent DUT copies so one analysis gives all four S-parameters (reference {RS_OHM:g} ohm):",
        f"  X1: AC source at port 1 (RFIN), {RL_OHM:g} ohm load at RFOUT      -> S11 = 2 v(in1)/vs - 1, S21 = 2 v(out1)/vs",
        f"  X2: AC source at port 2 (RFOUT), {RS_OHM:g} ohm termination at RFIN -> S22 = 2 v(out2)/vs - 1, S12 = 2 v(in2)/vs",
        f"Quiescent point: DC operating point at the cell's Vcc (the request sweeps the PVT",
        f"  matrix: {len(PVT_PROCESS_SECTIONS)} HBT sections x {len(PVT_TEMP_C)} temperatures x "
        f"{len(PVT_VCC_V)} supplies = {pvt_cell_count()} cells, klt `alter vcc=`; the deck's",
        f"  own Vcc line is the {VCC_NOM_V:g} V nominal). The bias is the DUT's own mirror.",
        "Output network: IDEAL passives (Lchoke, Cblock, Cin in the DUT).",
    ])
    body = f"""Vcc vcc 0 dc {VCC_NOM_V}
Vs1 s1 0 dc 0 ac 1
Rs1 s1 in1 {RS_OHM:g}
X1 in1 out1 vcc 0 sg13g2-pa
Rl1 out1 0 {RL_OHM:g}
Vs2 s2 0 dc 0 ac 1
Rs2 s2 out2 {RL_OHM:g}
X2 in2 out2 vcc 0 sg13g2-pa
Rt2 in2 0 {RS_OHM:g}
.save v(in1) v(out1) v(s1) v(in2) v(out2) v(s2)
"""
    return h + _dut_block() + body


def ac_gain_deck():
    return _ac_deck("Small-signal gain and S11 over the band (simulated bench, not a result)",
                    ["Sweep: 11 linear points 2400 .. 2483.5 MHz (includes 2441.75 MHz exactly)."])


def ac_stability_deck():
    return _ac_deck("Small-signal stability, 10 MHz - 30 GHz (simulated bench, not a result)",
                    ["Sweep: 50 points/decade, 10 MHz .. 30 GHz (spec: >= 40 pts/decade)."])


def _request(netlist, analysis, options, corners_extra=None, batch=False):
    """The nominal cell of this DUT's benches, in bench_gen's request skeleton."""
    return bench_gen.request(netlist, analysis, options,
                             process=[PROCESS_NOM], temperature_c=[TEMP_NOM_C],
                             corners_extra=corners_extra, batch=batch)


def _matrix_request(netlist, analysis, options, corners_extra=None):
    """A bench's PVT-matrix request: the 27 declared cells, one fleet submit.

    Every grid bench that covers the matrix goes through this shape -- the
    axes are the declared triple, never a per-request corner list, so
    `klt corner-matrix check --request` is clean by construction.
    """
    return bench_gen.request(netlist, analysis, options,
                             process=list(PVT_PROCESS_SECTIONS),
                             temperature_c=list(PVT_TEMP_C),
                             corners_extra=corners_extra, batch=True)


def psat_request(variant="bare"):
    b = psat_bench(variant)
    if variant == "bare":
        # The bare deck stays NOMINAL-ONLY. The ratified large-signal rows are
        # judged on the matched bench (the spec's Fallback output-port cell);
        # the bare deck's flat-50-ohm harmonic terminations make its P_out and
        # PAE not comparable with it, so running it across 27 cells would
        # spend 27 x 72 more fleet units evidencing no judged row. Its
        # nominal-cell run remains the item-9 cold start and the termination
        # the matched record's figures are explicitly NOT compared against.
        grid, timeout_s, hosts = drive_grid_dbm(), 1800, None
        req = _request(
            f"{b['name']}.spice",
            {"kind": "tran", "args": f"{TRAN_STEP_S * 1e12:.6g}p {TRAN_STOP_S * 1e9:.6g}n"},
            {"timeout_s": timeout_s, "keep_artifacts": True, "waveforms": True,
             "capture_only": True, "save_mode": "netlist"},
            corners_extra={"supply_v": {
                "vamp": [round(amp_v(p), 9) for p in grid],
                "vcc": [VCC_NOM_V] * len(grid),
            }},
            batch=True,
        )
    else:
        # The matched bench carries the whole PVT matrix: the drive axis crossed
        # with the supply points (pvt_psat_supply_axis), 27 cells x 106 drive
        # points = 2862 units. Screen the per-unit corner ids BEFORE anything
        # is built or submitted: klt names a unit by its corner id and rounds
        # supply values to three decimals, so close values collapse
        # (klayout-tools#5870) -- here that would silently merge two (cell,
        # drive) pairs into one unit and one artifact directory.
        units = pvt_psat_units("match")
        n_units = assert_pvt_corner_ids_distinct(units)
        grid = drive_grid_match_dbm()
        timeout_s = PSAT_MATCH_TIMEOUT_S
        # Every shard stays inside the fleet's whole-job ceiling
        # (units/shard x timeout + overhead <= 3600 s), so the 2862-unit grid
        # is 261 jobs, not one job the ceiling would kill.
        hosts = batch_hosts(n_units, timeout_s)
        req = _matrix_request(
            f"{b['name']}.spice",
            {"kind": "tran", "args": f"{TRAN_STEP_S * 1e12:.6g}p {TRAN_STOP_S * 1e9:.6g}n"},
            {"timeout_s": timeout_s, "keep_artifacts": True, "waveforms": True,
             "capture_only": True, "save_mode": "netlist"},
            corners_extra={"supply_v": pvt_psat_supply_axis("match")},
        )
    if hosts is not None:
        req["remote"] = {"hosts": hosts}
    return req


# The six port vectors `sparams.s_from_nodes` reads. Declared once, as both
# `complex_vectors` (klt writes them to the complex_vectors.json sidecar) and
# `save_vectors` (the saved set stays these six, not `save all`); both need the
# request to omit `save_mode`.
AC_PORT_VECTORS = ["v(s1)", "v(in1)", "v(out1)", "v(in2)", "v(out2)", "v(s2)"]


AC_TIMEOUT_S = 300


def _ac_options():
    return {"timeout_s": AC_TIMEOUT_S, "keep_artifacts": True, "waveforms": True,
            "capture_only": True, "complex_vectors": list(AC_PORT_VECTORS),
            "save_vectors": list(AC_PORT_VECTORS)}


def _ac_request(name, analysis):
    """One AC bench's matrix request: the 27 declared cells (supply = Vcc)."""
    req = _matrix_request(
        name,
        analysis,
        _ac_options(),
        corners_extra={"supply_v": {"vcc": list(PVT_VCC_V)}},
    )
    # 27 units x 300 s exceeds the fleet's whole-job ceiling in one job, so
    # shard the same way the matched psat bench does (3 jobs of <= 11 units).
    req["remote"] = {"hosts": batch_hosts(pvt_cell_count(), AC_TIMEOUT_S)}
    return req


def ac_gain_request():
    return _ac_request(
        "ac_gain.spice",
        {"kind": "ac", "args": f"lin 11 {BAND_LO_HZ:g} {BAND_HI_HZ:g}"},
    )


def ac_stability_request():
    return _ac_request(
        "ac_stability.spice",
        {"kind": "ac", "args": "dec 50 10Meg 30G"},
    )


def outputs():
    """{repo-relative path: text}"""
    def j(obj):
        return json.dumps(obj, indent=2) + "\n"
    return {
        "sim/psat-sweep/psat_sweep.spice": psat_deck("bare"),
        "sim/psat-sweep/psat_sweep.request.json": j(psat_request("bare")),
        "sim/psat-sweep/psat_sweep_match.spice": psat_deck("match"),
        "sim/psat-sweep/psat_sweep_match.request.json": j(psat_request("match")),
        "sim/ac-gain/ac_gain.spice": ac_gain_deck(),
        "sim/ac-gain/ac_gain.request.json": j(ac_gain_request()),
        "sim/ac-stability/ac_stability.spice": ac_stability_deck(),
        "sim/ac-stability/ac_stability.request.json": j(ac_stability_request()),
        # The declared matrix, once, in the two shapes `klt corner-matrix`
        # checks: the 27-cell box (AC benches) and its drive-crossed
        # expansion (the matched psat bench). Committed next to the benches
        # they gate, regenerated only here.
        PVT_MATRIX_REL: j(pvt_matrix()),
        PSAT_MATCH_MATRIX_REL: j(psat_match_pvt_matrix()),
        # The P1dB linear-reference probe's request (issue #192): the committed
        # matched deck under a sparse low-drive axis. No deck of its own and no
        # declared-matrix file -- it is not a matrix bench.
        P1DBREF_PROBE_REQUEST_REL: j(p1dbref_probe_request()),
    }


def main(args):
    return bench_gen.write_or_check(
        outputs(), args, "gen_dut_benches.py", REPO,
        "python3 -I sim/lib/gen_dut_benches.py",
        ok_message="committed decks match design/netlist/sg13g2-pa.spice "
                   f"(sha256 {netlist_sha256()[:12]})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
