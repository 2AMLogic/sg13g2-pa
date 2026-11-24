"""Test-only helper: import a repo script (not a package) by path.

Scripts outside ``sim/lib/`` (summarizers, bench generators, record renderers)
are not importable by name, so the unit tests load them by repo-relative path.
This is not imported by any renderer, so it is outside every renderer's
``sim/lib`` import closure.
"""
import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_script(name, relpath):
    """Execute ``relpath`` (relative to the repo root) as module ``name``."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
