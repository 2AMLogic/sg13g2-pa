"""npn13G2 breakdown minima, VBIC model-validity window and the Rth model.

These are the limits every large-signal verdict in this repo is graded against
(spec/target-spec.md, "Device stress (breakdown / window)" and "Model validity
window"). They live HERE and nowhere else, and record prose is FORMATTED from
these names rather than retyped: a second copy means a PDK or model-card bump
corrects one of them and leaves the other grading against the old limit, while
still printing "inside window, within breakdown minima".

Stdlib only -- the summarizers run with `python3 -I`, which puts neither the
script's directory nor site-packages on sys.path, so importers add sim/lib
themselves:

    sys.path.insert(0, os.path.join(HERE, "..", "lib"))
    from device_limits import BVCEO_MIN, VCE_WIN, rth

Provenance of the numbers:
  (P) SG13G2 Process Specification Rev. 1.2, npn13g2: DC process-control minima.
      A dynamic excursion above them is judged a violation, per the spec.
  (M) sg13g2_hbt_mod.lib v0.3.0, npn13G2 card header: the VBIC validity window
      (and the Rth model below). A result outside it is labelled as such, never
      quoted as a pass.
"""

BVCEO_MIN = 1.4          # V, (P) npn13g2 minimum
BVCBO_MIN = 3.8          # V, (P) npn13g2 minimum
VCE_WIN = (0.4, 2.0)     # V, (M) card window
VBE_WIN = (0.65, 0.96)   # V, (M)
IC_WIN_PER_NX = 3e-3     # A per Nx, (M)
TJ_MAX = 125.0           # C, (M) window top

LIMITS_NOTE = ("BVCEO/BVCBO are DC process-control minima (spec/target-spec.md); a dynamic "
               "excursion above them is judged a violation, per the spec. Window = card "
               "header of sg13g2_hbt_mod.lib v0.3.0 (npn13G2).")


def rth(nx):
    """Thermal resistance, K/W, of one Nx-unit npn13G2 array device. (M) card scaling:
    3.26 kK/W at Nx=4, scaled as (4/Nx)**0.9."""
    return 3.26e3 * (4.0 / nx) ** 0.9
