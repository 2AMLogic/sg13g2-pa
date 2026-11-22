"""The design-iteration issues that PVT-matrix findings are tracked by.

A matrix record states per-cell verdicts (``met`` / ``fallback`` / ``missed``,
plus simulation errors); without this map those verdicts point nowhere -- the
reader of the permanent record has to find the tracker through ``ROADMAP.md``,
which outlives neither the record nor the reader's patience. The map is keyed
by finding, not by spec row, because one iteration can own several rows (#172
owns both small-signal stability and input match).

Discipline: a finding class gets a number here only when an issue tracks
exactly that finding; anything else renders UNLINKED (``tracker=None``), never
linked to the nearest-sounding issue. Keep this file in step with the roadmap:
an issue that closes removes its entry, a finding class that recurs gets one.
The renderer never reads the forge -- the numbers are repo knowledge, and a
stale number is caught here in review, not by a network call at render time.
"""

# Small-signal stability (mu > 1) and input match (S11 -- small-signal in the
# ac-gain bench, large-signal in the psat sweep) below their rungs: #172.
STABILITY_AND_MATCH = 172

# PVT cells that do not simulate at all (klt corner status != pass, e.g. the
# 125 C singular-matrix cells): #188.
DID_NOT_SIMULATE = 188

# The large-signal power rows -- output P1dB, Psat, peak PAE -- below their
# rungs: #192.
POWER_ROWS = 192


def plural(n, word):
    """"1 cell" / "2 cells" -- the record's findings lines read as prose."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def line_md(name, rungs, tracker, noun="cell", rung="the Fallback rung"):
    """One findings bullet for a graded row, or None when every rung is `met`.

    ``rungs`` are the per-cell verdicts (``met`` / ``fallback`` / ``missed``, or
    None where no figure exists -- a refusal or an errored cell grades nothing
    and links nowhere). A row that never leaves ``met`` gets no line: a passing
    row must not acquire a failure link. ``rung`` names what was missed -- the
    spec's Fallback, or "the rung" where (stability) there is no relaxed one.
    """
    missed = sum(1 for r in rungs if r == "missed")
    fallback = sum(1 for r in rungs if r == "fallback")
    if not missed and not fallback:
        return None
    parts = [f"{missed} `missed`"]
    if fallback:
        parts.append(f"{fallback} `fallback`")
    link = f"design iteration #{tracker}" if tracker else "no design-iteration tracker"
    return (f"- {name}: {plural(missed + fallback, noun)} below {rung} "
            f"({', '.join(parts)}) -- {link}.")


def units_md(n, noun, detail, tracker):
    """One findings bullet for a non-rung finding (a refusal, an error class)."""
    link = f"design iteration #{tracker}" if tracker else "no design-iteration tracker"
    return f"- {plural(n, noun)} {detail} -- {link}."
