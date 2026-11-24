"""Regression tests for the model-input closure in sim/tools/pdk_identity.py.

The scanner recognizes six model-file suffixes when following a reference,
but the missing-file diagnostic repeated only five of them, so a corner
library `.include`-ing a missing `.mod` file was silently skipped and
preflight exited 0 (issue #177).

These tests drive the helper end to end on a fixture PDK (tarball-marker
identity route, no network, no installed PDK): both files hashed when the
referenced `.mod` exists, exit 3 with PDK_MODEL_INPUT_MISSING when it does
not, and a single-argument `.lib` section name still accepted rather than
treated as a file reference.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "sim" / "tools" / "pdk_identity.py"

CORNER_LIB = """* fixture corner library
.lib hbt_typ
.include model.mod
.endl hbt_typ
"""

SECTION_ONLY_LIB = """* fixture library with only a section name
.lib hbt_typ
* model content inside the section
.endl hbt_typ
"""


def run_tool(tmp, corner_text):
    """Install a fixture PDK + corner library; return the completed process."""
    pdk_dir = tmp / "ihp-sg13g2"
    pdk_dir.mkdir()
    (pdk_dir / ".fetched-version").write_text("test-release\n")
    pin = tmp / "pdk.json"
    pin.write_text(json.dumps({"release_tag": "test-release",
                               "variant": "ihp-sg13g2"}))
    corner = tmp / "corner.lib"
    corner.write_text(corner_text)
    return subprocess.run(
        [sys.executable, "-I", str(TOOL), str(pin), str(pdk_dir), str(corner)],
        capture_output=True, text=True, timeout=60)


def model_inputs(proc):
    return {os.path.realpath(e["path"]): e["sha256"]
            for e in json.loads(proc.stdout)["model_inputs"]}


def test_mod_include_present_hashes_both_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "model.mod").write_text("* fixture model file\n")
        proc = run_tool(tmp, CORNER_LIB)
        assert proc.returncode == 0, proc.stderr
        want = {
            os.path.realpath(str(tmp / "corner.lib")):
                hashlib.sha256(b"* fixture corner library\n.lib hbt_typ\n"
                               b".include model.mod\n.endl hbt_typ\n").hexdigest(),
            os.path.realpath(str(tmp / "model.mod")):
                hashlib.sha256(b"* fixture model file\n").hexdigest(),
        }
        assert model_inputs(proc) == want


def test_missing_mod_include_fails_preflight():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_tool(Path(tmp), CORNER_LIB)
        assert proc.returncode == 3
        assert "PDK_MODEL_INPUT_MISSING" in proc.stderr
        assert "model.mod" in proc.stderr


def test_single_argument_lib_section_name_is_not_a_file_reference():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proc = run_tool(tmp, SECTION_ONLY_LIB)
        assert proc.returncode == 0, proc.stderr
        inputs = model_inputs(proc)
        assert list(inputs) == [os.path.realpath(str(tmp / "corner.lib"))]
