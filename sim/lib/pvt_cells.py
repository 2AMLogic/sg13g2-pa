"""The PVT cell, its label and its verdict rung, shared by every matrix record.

They live HERE and nowhere else. `sim/lib/ac_record.py` and
`sim/psat-sweep/psat_record.py` name each corner's cell one way and grade it
on the same three rungs -- the vocabulary `finding_trackers.line_md` counts --
and `sim/psat-sweep/p1dbref_record.py` labels its cells the same way. A
private copy per renderer lets an edit to the label or to a rung correct one
record while the others keep quoting the old one, in append-only evidence; the
copies had already drifted, an explicit null `supply_v` crashing one renderer
and not the other (issue #221). The null-tolerant form is the one kept.

Importers put sim/lib on sys.path (the renderers run with -I, which puts
neither the script's directory nor the current one on it):

    from pvt_cells import cell_md, cell_of, rung
"""
import gen_dut_benches as gdb


def cell_of(corner):
    """The PVT cell a report corner names (process, temperature, VCC).

    Whatever the corner leaves out -- no supply at all, or `supply_v` present
    but null -- falls back rather than raising: the process to `?`, the
    ambient to 27 C and the supply to the generator's nominal.
    """
    return {"process": corner.get("process", "?"),
            "temperature_c": float(corner.get("temperature_c", 27)),
            "vcc": float((corner.get("supply_v") or {}).get("vcc", gdb.VCC_NOM_V))}


def cell_md(cell):
    """The cell as every matrix record labels it (``process``, ambient, Vcc)."""
    return f"`{cell['process']}` / {cell['temperature_c']:g} C / {cell['vcc']:g} V"


def rung(ok_target, ok_fallback):
    """A row verdict rung: met (Target), fallback, or missed (below Fallback)."""
    return "met" if ok_target else ("fallback" if ok_fallback else "missed")
