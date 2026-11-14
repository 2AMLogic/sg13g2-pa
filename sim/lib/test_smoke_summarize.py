"""The smoke record's model-input statements come from each bench's own report.

The record exists to say which PDK, models and tools ran together, so every
provenance sentence in it has to be derived from the run. Two were not, and both
went wrong the first time the toolchain moved underneath them (issue #96):

- a literal "too old to load the OSDI objects" printed beside whatever local
  ngspice banner the host had, and
- one client-side hash list, headed "OSDI objects and model inputs", printed for
  every bench as though it described what each had loaded -- which the 0.9.0 run
  disproves: its two batch benches resolved their own OSDI objects from the
  runner's install and never saw the client's files, while the 0.7.0 run's were
  staged with the request.

The regression guarded here is any return to a provenance statement a report does
not support. The fixtures are the two committed runs themselves, one from each
side of the klt 0.7.0 -> 0.9.0 change in how OSDI objects reach the simulator, so
the assertions are against real reports, not a hand-written shape.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SUMMARIZE_PY = os.path.join(REPO, "sim", "smoke", "summarize.py")


def _load(name, path):
    """Import a summarizer by path (they are scripts, not packages)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SUMMARIZE = _load("_smoke_summarize_record", SUMMARIZE_PY)

# The two committed runs. STAGED_RUN shipped its OSDI objects with the request
# (klt 0.7.0); RUNNER_RUN's batch worker loaded its own (klt 0.9.0).
STAGED_RUN = "20261017-220907-cacd3b5"
RUNNER_RUN = "20261107-125608-93cf5ae"

# The three objects the 0.9.0 batch worker resolved from its own install.
RUNNER_RESOLVED = ("psp103.osdi", "psp103_nqs.osdi", "mosvar.osdi")


def _prov_path(rid):
    return os.path.join(REPO, "sim", "smoke", "records", f"{rid}.pdk-provenance.json")


def client_osdi_hashes(rid):
    """sha256 of every `.osdi` `sim_require_pdk` hashed on the submitting host."""
    prov = json.load(open(_prov_path(rid)))
    return {f["sha256"] for f in prov["model_inputs"] if f["path"].endswith(".osdi")}


def render(rid):
    """Run summarize.py over a committed run; return (exit status, record text)."""
    argv = [
        SUMMARIZE_PY, rid, "abc1234", "0", "klt 0.9.0",
        "** ngspice-46 : Circuit level simulation program",
        _prov_path(rid), os.path.join(REPO, "sim", "smoke", "corners", rid),
        "inverter_dc", "inverter_tran", "npn_op",
    ]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = SUMMARIZE.main(argv)
    return rc, out.getvalue()


def result_blocks(text):
    """The `## Results` section, split into {bench name: its block}."""
    body = text.split("\n## Results\n", 1)[1].split("\n## Statement\n", 1)[0]
    blocks, cur = {}, None
    for line in body.splitlines():
        if line.startswith("### "):
            cur = line[4:].strip()
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(line)
    return {k: "\n".join(v) for k, v in blocks.items()}


@pytest.fixture(scope="module")
def rendered():
    return {rid: render(rid) for rid in (STAGED_RUN, RUNNER_RUN)}


def test_committed_runs_render_clean(rendered):
    for rid, (rc, text) in rendered.items():
        assert rc == 0, f"{rid} did not render as all-pass"
        assert text.startswith(f"# Toolchain smoke record {rid}")


def test_no_hard_coded_claim_about_the_local_engine(rendered):
    """The "too old" sentence was a constant, true of the first run and of no other."""
    assert "too old" not in open(SUMMARIZE_PY).read()
    for _, text in rendered.values():
        assert "too old" not in text
        assert ("- Local ngspice: `** ngspice-46 : Circuit level simulation program` "
                "(runs the single-unit npn13G2 op)") in text


def test_client_osdi_hashes_absent_where_the_runner_resolved_its_own(rendered):
    """The 0.9.0 MOS benches ran on objects the client never shipped."""
    hashes = client_osdi_hashes(RUNNER_RUN)
    assert len(hashes) == 4, "fixture drift: expected four client-side .osdi hashes"
    assert {h[:8] for h in hashes} == {"2e4299c4", "839b1644", "25e64a37", "4fead17b"}
    blocks = result_blocks(rendered[RUNNER_RUN][1])
    for bench in ("inverter_dc", "inverter_tran"):
        for h in hashes:
            assert h not in blocks[bench], f"{bench} prints client hash {h[:8]}"


def test_runner_resolved_objects_are_named_with_their_missing_digest(rendered):
    """A report field with no sha256 is stated as such, never filled in from elsewhere."""
    blocks = result_blocks(rendered[RUNNER_RUN][1])
    for bench in ("inverter_dc", "inverter_tran"):
        block = blocks[bench]
        for obj in RUNNER_RESOLVED:
            line = [ln for ln in block.splitlines()
                    if "resolved on the runner" in ln and ln.rstrip().endswith(
                        "the report carries no sha256 for it") and obj in ln]
            assert len(line) == 1, f"{bench} does not name {obj} as runner-resolved"
            assert "`env_var`" in line[0]


def test_staged_osdi_hashes_are_printed_where_the_client_shipped_them(rendered):
    """The same code prints the digests when the report does carry them."""
    blocks = result_blocks(rendered[STAGED_RUN][1])
    report = json.load(open(os.path.join(
        REPO, "sim", "smoke", "corners", STAGED_RUN, "inverter_dc.report.json")))
    staged = [m for m in report["environment"]["staged_model_inputs"]
              if m["kind"] == "osdi"]
    assert {m["name"] for m in staged} == set(RUNNER_RESOLVED)
    for m in staged:
        assert f"`{m['name']}` (osdi) `{m['sha256']}`" in blocks["inverter_dc"]
    assert "resolved on the runner" not in blocks["inverter_dc"]


def test_local_bench_states_its_corner_section_lib(rendered):
    """npn_op has neither staged nor runner-resolved inputs; its lib is the fact."""
    for rid, (_, text) in rendered.items():
        block = result_blocks(text)["npn_op"]
        lib = json.load(open(os.path.join(
            REPO, "sim", "smoke", "corners", rid,
            "npn_op.report.json")))["environment"]["corner_section_libs"][0]
        assert f"- corner section lib: `{lib['name']}` `{lib['sha256']}`" in block


def test_client_preflight_list_is_kept_once_and_labelled_as_the_host_s(rendered):
    """Kept as evidence about the submitting host, not as what the run loaded."""
    for rid, (_, text) in rendered.items():
        head = text.split("\n## Results\n", 1)[0]
        assert "### OSDI objects and model inputs (sha256)" not in text
        assert "### Submitting host's preflight inputs (sha256)" in head
        # The heading states only what is always true: whose hashes these are,
        # and that each bench's own block is the statement about what it
        # loaded. It must not assert how a runner comes by its OSDI objects --
        # that is conditional on the klt version and the runner's environment
        # (the 0.9.0 run gives reason `env_var`), and STAGED_RUN's batch bench
        # loaded the client's staged objects, so any such sentence is false for
        # one of these two records and goes stale on the next klt change.
        para = " ".join(head.split())
        assert "What `sim_require_pdk` hashed on **this** host before submitting." in para
        assert ("It is not a statement about what any bench loaded: each bench under "
                "`## Results` names the model inputs its own `klt sim` report "
                "records.") in para
        assert "batch worker" not in para
        # Listed once, ahead of the results, and never again except where a
        # bench's own report puts the same object in its model inputs.
        for h in client_osdi_hashes(rid):
            assert head.count(h) == 1


def test_report_without_any_model_input_field_renders(tmp_path):
    """A bench whose report names no model input says so, rather than failing."""
    out_dir = tmp_path / "corners"
    out_dir.mkdir()
    (out_dir / "solo.report.json").write_text(json.dumps({
        "status": "pass", "passed": 1, "failed": 0, "errored": 0, "corner_count": 1,
        "environment": {"engine_version": "46"},
        "corners": [{"corner_id": "tt", "status": "pass",
                     "measurements": [{"name": "v", "value": 1.0}]}],
    }))
    prov = tmp_path / "prov.json"
    prov.write_text(json.dumps({
        "pinned_release_tag": "v0.3.0", "installed_release_raw": "0.3.0",
        "identity_route": "tarball-marker", "model_inputs": [],
    }))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = SUMMARIZE.main([SUMMARIZE_PY, "rid", "abc1234", "0", "klt 0.9.0",
                             "ngspice-46", str(prov), str(out_dir), "solo"])
    assert rc == 0
    assert "- model inputs: this bench's report lists none." in result_blocks(
        buf.getvalue())["solo"]
