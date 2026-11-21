"""Unit tests for the missing-dpkg-deb diagnostic in sim/tools/build-osdi.sh
(issue #176).

`ensure_libllvm21` extracts the checksum-pinned libLLVM.so.21 .deb itself
when its cache is empty. The manual recovery recipe the diagnostic used to
print beside reaches `dpkg-deb -x` under the very condition (no dpkg-deb on
PATH) that made the script exit, so it was unusable as written; the
diagnostic must now only name the package prerequisite (the package that
provides dpkg-deb) and the retry step (rerun the build), and exit 3.

No network, PDK or system dpkg-deb is needed: the test extracts the real
pins and the real `ensure_libllvm21` helper from the script and runs them
against a scratch cache with a PATH the test controls.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD_OSDI = REPO / "sim" / "tools" / "build-osdi.sh"

# The diagnostic branch needs only `cat` (for the heredoc) on PATH; every
# command before it is a bash builtin. Reuse the host cat so the test says
# nothing about the host's dpkg-deb.
CAT = shutil.which("cat")

DIAG_HARNESS = """
set -uo pipefail
__PINS__
__FUNC__
export PATH="__BIN__"
CACHE_DIR="__CACHE__"
ensure_libllvm21
echo "UNREACHED rc=0"
"""


def _extract():
    """Return (pins_source, ensure_libllvm21_source) from the real script."""
    text = BUILD_OSDI.read_text()
    pins = re.findall(r"^(?:OPENVAF_TAG|LIBLLVM21_DEB_[A-Z0-9_]+)=.*$",
                      text, re.M)
    assert pins, "no libLLVM21 pins found in build-osdi.sh"
    func = re.search(r"^ensure_libllvm21\(\) \{.*?^\}", text, re.M | re.S)
    assert func, "ensure_libllvm21 not found in build-osdi.sh"
    return "\n".join(pins) + "\n", func.group(0)


def _run_harness(script, bin_entries):
    """Run a bash harness with PATH limited to bin_entries; return (rc, out, err)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for name, target in bin_entries.items():
            link = bin_dir / name
            link.symlink_to(target)
        script = (script.replace("__BIN__", str(bin_dir))
                  .replace("__CACHE__", str(tmp / "cache")))
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, env=dict(os.environ), timeout=120)
        return proc.returncode, proc.stdout, proc.stderr


def test_missing_dpkg_deb_names_package_and_rerun():
    """Empty cache + no dpkg-deb: package prerequisite, retry step, exit 3."""
    pins, func = _extract()
    harness = (DIAG_HARNESS
               .replace("__PINS__", pins)
               .replace("__FUNC__", func))
    rc, out, err = _run_harness(harness, {"cat": CAT})
    assert rc == 3, (rc, err)
    assert "UNREACHED" not in out
    # The missing tool is named.
    assert "dpkg-deb" in err
    # The package prerequisite: install the package that provides dpkg-deb.
    assert "apt-get install dpkg" in err
    # The retry step: rerun the build.
    assert "rerun sim/tools/build-osdi.sh" in err


def test_missing_dpkg_deb_drops_the_manual_recipe():
    """Empty cache + no dpkg-deb: no five-command recipe, no host-LLVM claim."""
    pins, func = _extract()
    harness = (DIAG_HARNESS
               .replace("__PINS__", pins)
               .replace("__FUNC__", func))
    rc, _, err = _run_harness(harness, {"cat": CAT})
    assert rc == 3, (rc, err)
    # The five-command manual recipe is gone: it reaches dpkg-deb -x under
    # the very condition that made the script exit.
    for gone in ("curl -fsSL", "dpkg-deb -x", "LD_LIBRARY_PATH=",
                 "sha256sum libllvm21.deb"):
        assert gone not in err, gone
    # The assertion about the host's system LLVM installation is gone too.
    assert "tops out at" not in err
    assert "noble" not in err
