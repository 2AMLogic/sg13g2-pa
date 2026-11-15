"""The `klt sim` request skeleton and the write/`--check` driver, declared once.

Both bench generators in this repo -- `sim/lib/gen_dut_benches.py` (the DUT
benches) and `sim/device-npn13g2/gen_bench.py` (the single-device benches) --
emit `klt sim` requests against the same pinned PDK and gate their committed
output the same way. The parts that are *not* bench-specific live here so a PDK
pin bump that moves the corner library, or a change to the host's capacity-wait
rule, is made in one place instead of in whichever generator happens to be run:

* ``PDK_NAME``, ``CORNER_LIB``, ``CAPACITY_WAIT_S`` -- the pinned PDK facts
* ``process_block(names)`` -- the ``corners.process`` entries for those sections
* ``request(...)``         -- the request dict, in the key order the committed
  requests are already serialised in
* ``write_or_check(...)``  -- write the generated files, or byte-compare them

``write_or_check`` is deliberately strict about its arguments: it acts on
`--check` and on nothing else, and returns 2 on any other argument instead of
falling through to the write branch. The generated decks and requests are
content-hashed by `evidence/item9.json` and `attest/item9.json`, so a driver
that writes on an unrecognised argument turns the staleness gate into a gate
that passes *by overwriting the attested evidence* (issue #111). Two copies of
this driver had already diverged on exactly that point; `test_bench_gen.py`
pins the strict behaviour.

The bench-specific parts -- decks, measurements, corner grids, which files are
written where -- stay in the generators. Nothing here is a result.
"""
import pathlib
import sys

# The pinned PDK (sim/pdk.json, sim/toolchain.json) as `klt sim` names it, and the
# corner library the HBT process sections come from. A PDK release that moves this
# path is a one-line change here, not one per generator.
PDK_NAME = "ihp-sg13g2"
CORNER_LIB = "libs.tech/ngspice/models/cornerHBT.lib"

# The fleet is vCPU-budgeted: wait with backoff instead of failing on
# batch_no_capacity (host rule; same effect as `--wait-for-capacity 600`).
# The field is inert off the batch backend, so it is safe to commit.
CAPACITY_WAIT_S = 600


def process_block(names):
    """``corners.process`` for the named sections of ``CORNER_LIB``."""
    return [{"name": p, "sections": [{"lib": CORNER_LIB, "section": p}]} for p in names]


def request(netlist, analysis, options, process, temperature_c,
            measurements=None, corners_extra=None, batch=False):
    """One `klt sim` request.

    ``process`` are section names for ``process_block``; ``corners_extra`` adds
    further corner axes (e.g. ``supply_v``) after ``temperature_c``. Pass
    ``measurements`` only for a bench whose request carries `.meas` cards, and
    ``batch=True`` for a grid that goes to the fleet.

    Key order matters: the committed request JSON is content-hashed evidence, so
    the insertion order below is the order those files are already serialised in.
    """
    corners = {"process": process_block(process), "temperature_c": list(temperature_c)}
    corners.update(corners_extra or {})
    req = {
        "netlist": netlist,
        "models": {"pdk": PDK_NAME},
        "corners": corners,
        "analysis": analysis,
    }
    if measurements is not None:
        req["measurements"] = measurements
    req["options"] = options
    if batch:
        req["batch"] = {"capacity_wait_s": CAPACITY_WAIT_S}
    return req


def write_or_check(outputs, args, tool_name, root, regen_cmd, ok_message=None):
    """Write ``outputs``, or byte-compare them when ``args == ["--check"]``.

    ``outputs`` maps a path relative to ``root`` to its full text; ``args`` is
    the argument list *without* the program name (``sys.argv[1:]``);
    ``tool_name`` and ``regen_cmd`` appear in the messages.

    Returns 0 (written, or every file matches), 1 (at least one file is stale)
    or 2 (unusable arguments -- nothing is written and nothing is compared).
    Anything other than exactly ``--check`` is a usage error on purpose: see the
    module docstring.
    """
    check = args == ["--check"]
    if args and not check:
        print("usage: %s [--check]" % tool_name, file=sys.stderr)
        return 2
    stale = []
    for rel, text in outputs.items():
        path = pathlib.Path(root) / rel
        if check:
            if not path.is_file() or path.read_text() != text:
                stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print("%s: STALE_BENCH: regenerate with `%s`: %s"
              % (tool_name, regen_cmd, ", ".join(stale)), file=sys.stderr)
        return 1
    if check and ok_message:
        print("%s: %s" % (tool_name, ok_message))
    return 0
