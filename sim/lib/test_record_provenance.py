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

Issue #144 adds the inventory-completeness guard on the same principle: every
renderer that renders a sha256 inventory must pin every `sim/lib` module in its
transitive import closure, and a renderer that renders no inventory must be
that way by recorded decision -- so an edit can never again change a record's
numbers while every digest in it stays byte-identical (the #125/#137 failure
mode, where `units.py` reached the graded figure through `rx.dbm` unrecorded).
"""
import ast
import os
import re
import sys

import pytest

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


# --- Inventory completeness (issue #144) ------------------------------------
#
# A record's `### ... (sha256)` inventory is the only thing tying a rendered
# figure to the code that produced it. A module that runs during rendering but
# is absent from the inventory lets an edit change the record's numbers while
# every digest in it stays byte-identical -- evidence silently stops being
# evidence. The guard: a renderer that renders an inventory must pin the whole
# transitive `sim/lib` import closure of its graded path. The whole closure,
# not a dataflow-analysed "graded" subset: separating a module that feeds a
# verdict from one that only renders text needs judgement, a closure rule
# needs none, and it fails closed -- a new `sim/lib` module entering any
# renderer's closure fails the test until it is pinned.

LIB_DIR = os.path.join(SIM, "lib")

# Renderers that render a `### ... (sha256)` inventory section today.
# sim/known-answer-thermal/thermal_record.py renders one too but is not in
# RENDERERS yet -- PR #145 (issue #133) adds it to the roster; when that
# lands, add it here as well (its pins are already in place).
INVENTORY_RENDERERS = (
    "sim/known-answer/check_known_answer.py",
    "sim/smoke/summarize.py",
    "sim/device-npn13g2/summarize.py",
)

# Renderers that render no inventory, on purpose. The reason is recorded so a
# renderer cannot dodge the guard above by simply shipping without an
# inventory; giving either one an inventory is deliberate separate work.
NO_INVENTORY_BY_DECISION = (
    ("sim/lib/ac_record.py",
     "renders no sha256 inventory section; recording the decision, not an "
     "accidental exemption (issue #144)"),
    ("sim/psat-sweep/psat_record.py",
     "renders no sha256 inventory section; recording the decision, not an "
     "accidental exemption (issue #144)"),
)

# The pin bullet's rendered shape: ``- `sim/lib/<name>.py` `<sha>` ``. The
# trailing backtick keeps a prose mention of a path from counting as a pin.
_PINNED_LIB_RE = re.compile(r"-\s+`sim/lib/([A-Za-z_][A-Za-z0-9_]*)\.py`\s+`")


def _read_source(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _sim_lib_module_path(name):
    """Absolute path of the `sim/lib` module `name`, or None when it is not one."""
    path = os.path.join(LIB_DIR, name + ".py")
    return path if os.path.isfile(path) else None


def _imported_module_names(src, filename):
    """Top-level module names imported anywhere in `src`, docstrings excluded.

    AST-based because the real files carry import-shaped lines inside their
    docstrings (`sim/lib/device_limits.py:15`, and the usage examples in
    `provenance.py` and `units.py`); a line regex reports those as imports.
    Function-body imports count: anything imported anywhere in the file runs
    during rendering.
    """
    names = set()
    for node in ast.walk(ast.parse(src, filename=filename)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _top_level_bindings(tree):
    """`name -> value expression` for every simple module-level assignment.

    The dynamic-load hop binds its directory to a name first (`HERE = ...`),
    so folding a `spec_from_file_location` path needs those bindings.
    """
    bindings = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            bindings[node.targets[0].id] = node.value
    return bindings


def _fold_path(node, filename, bindings):
    """Fold a path expression to a literal string, or raise ValueError.

    Understands exactly what the tree's dynamic loads use: string constants,
    `__file__`, module-level names bound to folds of the same, and
    `os.path.join`/`abspath`/`dirname` over those. Anything else -- a name of
    unknown origin, an f-string, a subscript, a call we do not know -- refuses
    to fold, and the caller fails the guard rather than skipping it.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return filename
        if node.id in bindings:
            return _fold_path(bindings[node.id], filename, bindings)
        raise ValueError(f"unresolvable dynamic-load path: unknown name `{node.id}`")
    if isinstance(node, ast.Call):
        func = node.func
        fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if fname == "join":
            return os.path.join(*(_fold_path(a, filename, bindings) for a in node.args))
        if fname in ("abspath", "dirname") and len(node.args) == 1:
            folded = _fold_path(node.args[0], filename, bindings)
            return os.path.abspath(folded) if fname == "abspath" else os.path.dirname(folded)
        raise ValueError(f"unresolvable dynamic-load path: call `{fname or '?'}`")
    raise ValueError(f"unresolvable dynamic-load path: non-literal "
                     f"{type(node).__name__} expression")


def _dynamic_siblings(src, filename):
    """Files the module exec()s via `spec_from_file_location`, as absolute paths.

    Mirrors the tree's only dynamic-load form (both call sites pass a literal
    `os.path.join(HERE, "gen_bench.py")`). A path argument that cannot be
    folded to a literal raises: a dynamic load the scan cannot resolve must
    fail the guard, never pass silently.
    """
    tree = ast.parse(src, filename=filename)
    bindings = _top_level_bindings(tree)
    siblings = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "spec_from_file_location"):
            continue
        if len(node.args) < 2:
            raise ValueError("spec_from_file_location call without a path argument")
        path = _fold_path(node.args[1], filename, bindings)
        if not path.endswith(".py"):
            raise ValueError(f"spec_from_file_location path does not name a .py "
                             f"file: `{path}`")
        siblings.append(os.path.abspath(path))
    return siblings


def _sim_lib_closure(entry_path, read=_read_source, module_path=_sim_lib_module_path,
                     _seen=None):
    """Every `sim/lib` module name in the file's transitive import closure.

    `read` and `module_path` are injectable so the negative tests can feed
    fixture sources (including a synthetic import cycle) without touching the
    real tree. The `spec_from_file_location` sibling hop is followed and its
    own closure folded in. `_seen` memoises visited files, so an import cycle
    terminates the walk rather than hanging it.
    """
    if _seen is None:
        _seen = set()
    if entry_path in _seen:
        return set()
    _seen.add(entry_path)
    src = read(entry_path)
    closure = set()
    for name in sorted(_imported_module_names(src, entry_path)):
        target = module_path(name)
        if target is not None:
            closure.add(name)
            closure |= _sim_lib_closure(target, read, module_path, _seen)
    for sibling in _dynamic_siblings(src, entry_path):
        closure |= _sim_lib_closure(sibling, read, module_path, _seen)
    return closure


def _pinned_sim_lib_modules(src):
    """The `sim/lib` modules a renderer's inventory pins, read as source text."""
    return set(_PINNED_LIB_RE.findall(src))


def _inventory_problems(closure, pinned):
    """(missing, stale): closure modules the inventory omits, and pins for
    modules the closure does not import. A stale pin states a digest nothing
    in the graded path produced, so it fails like a missing one does."""
    return sorted(closure - pinned), sorted(pinned - closure)


def test_every_inventory_renderer_pins_its_full_sim_lib_closure():
    """The #125/#137 failure mode, made mechanical: closure -> inventory."""
    for rel in INVENTORY_RENDERERS:
        path = os.path.join(REPO, rel)
        closure = _sim_lib_closure(path)
        missing, stale = _inventory_problems(
            closure, _pinned_sim_lib_modules(_read_source(path)))
        assert not missing, (
            f"{rel}'s inventory omits sim/lib module(s) its graded path imports: "
            f"{missing}. A sim/lib module that runs during rendering must have "
            "its sha256 in the record's inventory, or an edit to it changes the "
            "record's numbers with every digest in it unchanged.")
        assert not stale, (
            f"{rel} pins sim/lib module(s) its graded path does not import "
            f"(stale pins): {stale}. Drop them or give the module a graded role.")


def _partition_problems(renderers, inventory, no_inventory):
    """Ways the two buckets fail to partition the renderer roster."""
    problems = []
    overlap = sorted(set(inventory) & set(no_inventory))
    if overlap:
        problems.append(f"bucketed both ways: {overlap}")
    unbucketed = sorted(set(renderers) - set(inventory) - set(no_inventory))
    if unbucketed:
        problems.append(f"in neither bucket, so no guard covers them: {unbucketed}")
    unknown = sorted((set(inventory) | set(no_inventory)) - set(renderers))
    if unknown:
        problems.append(f"bucket entries that are not in RENDERERS: {unknown}")
    return problems


def test_inventory_and_no_inventory_buckets_partition_the_renderer_roster():
    """A new renderer in neither bucket fails; so does a stale bucket entry."""
    problems = _partition_problems(
        RENDERERS, INVENTORY_RENDERERS, [p for p, _reason in NO_INVENTORY_BY_DECISION])
    assert not problems, "; ".join(problems)


# Fixture source shaped like check_known_answer.py before #137: it pins
# rf_extract.py only, while the graded figure renders through rx.dbm ->
# units.dbm -- one import hop down, which a one-level import scan would miss.
_ISSUE_137_FIXTURE = '''\
"""Render a record from klt sim reports."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import rf_extract as rx  # noqa: E402
from provenance import commit_line, sha  # noqa: E402


def render(out):
    out.append(f"- `sim/lib/rf_extract.py` `{sha('rf_extract.py')}`")
    return commit_line("deadbee", "0") + str(rx.dbm(1e-3))
'''


def _fixture_read(sources):
    """A read() over fixture sources, falling back to the real tree for any
    other path -- the closure walk must reach the real sim/lib modules."""
    return lambda p: sources[p] if p in sources else _read_source(p)


def test_the_guard_bites_on_the_issue_137_shape_reached_transitively():
    """An omitted module one import hop down must still fail the guard."""
    fixture_path = "/fixtures/check_known_answer.py"
    closure = _sim_lib_closure(
        fixture_path, read=_fixture_read({fixture_path: _ISSUE_137_FIXTURE}))
    # units is in the closure, and reaches it only through rf_extract: a
    # one-level scan of the fixture's own imports would not see it.
    assert "units" in closure
    assert "units" not in _imported_module_names(_ISSUE_137_FIXTURE, fixture_path)
    missing, _stale = _inventory_problems(
        closure, _pinned_sim_lib_modules(_ISSUE_137_FIXTURE))
    assert "units" in missing, f"guard did not catch the transitively-reached module: {missing}"


def test_an_import_shaped_line_inside_a_docstring_is_not_an_import():
    """Prose quoting the code, as sim/lib/device_limits.py:15 does, must not
    put a phantom module in the closure."""
    fixture = '''\
"""Usage:

    from device_limits import BVCEO_MIN, VCE_WIN, rth

The line above is documentation, not an import.
"""
import json
'''
    closure = _sim_lib_closure("/fixtures/docstringy.py", read=lambda p: fixture)
    assert closure == set(), f"docstring import leaked into the closure: {closure}"


def test_an_import_inside_a_function_body_still_counts():
    """A lazy import runs during rendering all the same."""
    fixture = ("def render(out):\n"
               "    import provenance\n"
               "    out.append(provenance.commit_line('deadbee', '0'))\n")
    closure = _sim_lib_closure("/fixtures/lazy.py", read=lambda p: fixture)
    assert "provenance" in closure


def test_an_import_cycle_terminates_the_walk():
    """Two fixture modules importing each other must close, not loop."""
    sources = {
        "/fixtures/lib/zz_cycle_a.py": "import zz_cycle_b\n",
        "/fixtures/lib/zz_cycle_b.py": "import zz_cycle_a\n",
    }

    def module_path(name):
        path = f"/fixtures/lib/{name}.py"
        return path if path in sources else _sim_lib_module_path(name)

    closure = _sim_lib_closure(
        "/fixtures/lib/zz_cycle_a.py",
        read=lambda p: sources.get(p) or _read_source(p),
        module_path=module_path)
    assert {"zz_cycle_a", "zz_cycle_b"} <= closure


_DYNAMIC_LOAD_FIXTURE = '''\
import os
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("gen_bench", os.path.join(HERE, "gen_bench.py"))
gb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gb)
'''


def test_the_spec_from_file_location_sibling_hop_is_followed():
    """The exec'd sibling's own sim/lib closure belongs to the renderer's."""
    sources = {
        "/fixtures/dir/renderer.py": _DYNAMIC_LOAD_FIXTURE,
        "/fixtures/dir/gen_bench.py": "from zz_fix_helper import X\n",
        "/fixtures/lib/zz_fix_helper.py": "",
    }

    def module_path(name):
        return ("/fixtures/lib/zz_fix_helper.py" if name == "zz_fix_helper"
                else _sim_lib_module_path(name))

    closure = _sim_lib_closure("/fixtures/dir/renderer.py",
                               read=_fixture_read(sources), module_path=module_path)
    assert "zz_fix_helper" in closure


def test_a_dynamic_load_that_cannot_be_resolved_fails_rather_than_being_skipped():
    """A non-literal spec_from_file_location path must fail the guard, not
    quietly contribute nothing."""
    src = _DYNAMIC_LOAD_FIXTURE.replace(
        'os.path.join(HERE, "gen_bench.py")', 'os.environ["BENCH_PATH"]')
    with pytest.raises(ValueError, match="unresolvable dynamic-load path"):
        _sim_lib_closure("/fixtures/dir/renderer.py", read=lambda p: src)


def test_a_pin_for_a_module_the_renderer_does_not_import_fails_as_stale():
    """A digest for a module nothing in the graded path imports states
    provenance for code that did not run; it fails like a missing pin."""
    src = 'out.append(f"- `sim/lib/units.py` `{sha something}`")\n'
    _missing, stale = _inventory_problems(set(), _pinned_sim_lib_modules(src))
    assert stale == ["units"]


def test_a_renderer_in_neither_bucket_and_an_overlap_are_partition_problems():
    assert any("in neither bucket" in p for p in
               _partition_problems(["a.py", "b.py"], ["a.py"], []))
    assert any("bucketed both ways" in p for p in
               _partition_problems(["a.py"], ["a.py"], ["a.py"]))
    assert any("not in RENDERERS" in p for p in
               _partition_problems(["a.py"], ["a.py", "ghost.py"], []))
