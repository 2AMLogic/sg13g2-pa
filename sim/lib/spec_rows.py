"""The RATIFIED target-spec row thresholds the bench records grade cells against.

Provenance: ``spec/target-spec.md`` ("Ratified target table"), DR 0001. They
live HERE and nowhere else, and record prose is formatted from these names
rather than retyped -- a spec revision that moves a threshold corrects this
file and every record grades against the new number, instead of one bench
keeping a stale copy (the same rule ``device_limits.py`` states for the
breakdown minima and the model window).

Only RATIFIED rows with numeric thresholds live here. DRAFT rows (back-off
PAE, harmonics, large-signal stability, thermal, supply) are reported, never
graded -- a record that graded them would be inventing a threshold the spec
has not set. The Supply row being DRAFT is why every PVT-matrix record is
labelled provisional: the 0.8 V nominal (DR 0003, PROPOSED) that the +/-10 %
supply points hang off is not itself ratified.
"""

# Saturated output power (Psat), dBm: Target / Fallback (Stretch moves nothing).
PSAT_TARGET_DBM = 15.0
PSAT_FALLBACK_DBM = 10.0
# Output P1dB, dBm.
P1DB_TARGET_DBM = 12.0
P1DB_FALLBACK_DBM = 7.0
# Power gain (small-signal, in band), dB.
GAIN_TARGET_DB = 15.0
GAIN_FALLBACK_DB = 10.0
# Peak PAE, fraction (25 % / 15 %).
PAE_TARGET = 0.25
PAE_FALLBACK = 0.15
# Input match (S11), dB (more negative is better).
S11_TARGET_DB = -10.0
S11_FALLBACK_DB = -8.0
# Small-signal stability: mu > 1 is the pass metric at every point; the spec's
# Fallback column says "same", so there is no relaxed rung.
MU_MIN = 1.0
