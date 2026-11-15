"""Every sim/ record states its provenance in one format, from one place.

`sim/lib/provenance.py` holds the record's `- Commit:` bullet so that all five
record renderers emit the same text for the same two CLI arguments. Two of them
(`sim/lib/ac_record.py`, `sim/psat-sweep/psat_record.py`) landed after that
helper and retyped their own differently-formatted bullet instead (issue #119),
so for a while the repo's own append-only evidence did not state its provenance
the same way twice.

Nothing raises when that drifts -- a retyped bullet renders perfectly happily --
so these tests are what catch it, and they catch it for a renderer that does not
exist yet as readily as for the five that do: the check is "no module under sim/
but provenance.py writes a provenance bullet literal", not a list of filenames.
No simulator or PDK is needed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIM = os.path.join(REPO, "sim")
sys.path.insert(0, HERE)
import provenance  # noqa: E402

# The literal forms a provenance bullet has ever taken in this repo: the shared one
# provenance.commit_line emits, and the retyped one issue #119 removed.
BULLET_LITERALS = ("- Commit:", "- Repo `")

# The five renderers that turn a `klt sim` report into a record under sim/*/records/.
RENDERERS = (
    "sim/lib/ac_record.py",
    "sim/psat-sweep/psat_record.py",
    "sim/known-answer/check_known_answer.py",
    "sim/smoke/summarize.py",
    "sim/device-npn13g2/summarize.py",
)


def _sim_modules():
    """Every module under sim/, except provenance.py itself and the tests."""
    for root, _dirs, files in os.walk(SIM):
        for fn in sorted(files):
            if not fn.endswith(".py") or fn.startswith("test_"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), REPO)
            if rel == os.path.join("sim", "lib", "provenance.py"):
                continue
            yield rel


def test_the_provenance_bullet_literal_lives_only_in_provenance_py():
    """A renderer must call commit_line, never retype what it returns."""
    offenders = []
    for rel in _sim_modules():
        with open(os.path.join(REPO, rel)) as fh:
            src = fh.read()
        for i, line in enumerate(src.splitlines(), 1):
            if any(lit in line for lit in BULLET_LITERALS):
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, (
        "the record provenance bullet is written in sim/lib/provenance.py and nowhere "
        "else; call commit_line(git_sha, dirty) instead of retyping it:\n  "
        + "\n  ".join(offenders))


def test_every_record_renderer_imports_the_shared_commit_bullet():
    """The positive half: each renderer actually reaches for the helper."""
    missing = [rel for rel in RENDERERS
               if "commit_line" not in open(os.path.join(REPO, rel)).read()]
    assert not missing, f"renderers not using provenance.commit_line: {missing}"


def test_commit_line_marks_a_dirty_tree_and_only_a_dirty_tree():
    """The behaviour the renderers are now delegating, pinned here once."""
    assert provenance.commit_line("deadbee", "0") == "- Commit: `deadbee`"
    assert provenance.commit_line("deadbee", "1") == (
        "- Commit: `deadbee` (**working tree dirty** when run)")
