"""The one watts-to-dBm conversion (and its dB cousin) every sim/ renderer shares.

`dbm` lives HERE and nowhere else: a record's table columns and its headline
figures must reach dBm through the same function, or a rounding/reference
change corrects one and leaves the other quoting the old number -- in
append-only evidence that can only be superseded, never fixed in place.
`rf_extract` re-exports `dbm` under its public name for its own callers, so
`rx.dbm` and `units.dbm` are the same function object.

Stdlib only -- several consumers (`sim/lib/gen_dut_benches.py`,
`sim/device-npn13g2/loadline.py`) run with `python3 -I`, which puts neither
the script's directory nor site-packages on sys.path, so importers add sim/lib
themselves:

    sys.path.insert(0, os.path.join(HERE, "..", "lib"))
    from units import dbm

No `nan`/`None` fallback: `dbm(0)` and negative power raise from `math.log10`,
so a bad extraction fails loudly instead of rendering as a figure.
"""
import math


def db10(x):
    """A power *ratio* -> dB."""
    return 10.0 * math.log10(x)


def dbm(w):
    """Power in watts -> dBm (reference 1 mW). The one conversion sim/ shares."""
    return db10(w / 1e-3)
