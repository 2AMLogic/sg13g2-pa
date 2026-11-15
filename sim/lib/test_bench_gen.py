"""The shared write/`--check` driver must act on `--check` and on nothing else.

`sim/lib/bench_gen.py` holds the one copy of the `klt sim` request skeleton and
of the driver both bench generators gate their committed output with. Before
issue #111 there were two drivers, and the weaker one tested `"--check" in
argv` by membership: any *other* argument fell through to the write branch, so a
typo'd flag (`--chek`) rewrote the decks that `evidence/item9.json` and
`attest/item9.json` content-hash -- a staleness gate that passes by overwriting
the attested evidence. The tests below pin the strict behaviour, for the driver
and for both generators that now route through it, rather than restating it in
a comment.

The request-skeleton tests pin the serialised key order, because the committed
`*.request.json` files are content-hashed evidence: a reordered dict is a
changed file. No simulator or PDK is needed.
"""
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import bench_gen as bg  # noqa: E402
import gen_dut_benches as gdb  # noqa: E402

GEN_BENCH_PY = os.path.join(REPO, "sim", "device-npn13g2", "gen_bench.py")
_spec = importlib.util.spec_from_file_location("gen_bench", GEN_BENCH_PY)
gen_bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_bench)   # the device generator lives outside sim/lib/

GENERATORS = [gen_bench, gdb]
GENERATOR_IDS = ["gen_bench", "gen_dut_benches"]

# Anything that is not exactly ["--check"]: a typo, a near-miss, a repeat, an
# extra argument beside a valid one, a bare word, and the empty string.
BAD_ARGS = [["--chek"], ["-c"], ["check"], ["--check", "--check"],
            ["--check", "extra"], ["--write"], [""], ["--help"]]
BAD_IDS = ["+".join(a) or "empty-string" for a in BAD_ARGS]

OUTPUTS = {"a.txt": "alpha\n", "sub/b.txt": "beta\n"}


def _written(root):
    return {rel: (root / rel).read_text() for rel in OUTPUTS if (root / rel).is_file()}


# --- the driver -----------------------------------------------------------


def test_no_argument_writes_every_output(tmp_path):
    assert bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py") == 0
    assert _written(tmp_path) == OUTPUTS


def test_check_on_a_matching_tree_passes(tmp_path):
    bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py")
    assert bg.write_or_check(OUTPUTS, ["--check"], "t.py", tmp_path, "t.py") == 0


def test_check_reports_a_stale_file_without_rewriting_it(tmp_path, capsys):
    bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py")
    (tmp_path / "a.txt").write_text("stale\n")
    assert bg.write_or_check(OUTPUTS, ["--check"], "t.py", tmp_path, "regen-me") == 1
    err = capsys.readouterr().err
    assert "STALE_BENCH" in err and "a.txt" in err and "regen-me" in err
    assert (tmp_path / "a.txt").read_text() == "stale\n"   # the gate did not "fix" it


def test_check_reports_a_missing_file_without_writing_it_back(tmp_path):
    bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py")
    (tmp_path / "a.txt").unlink()
    assert bg.write_or_check(OUTPUTS, ["--check"], "t.py", tmp_path, "t.py") == 1
    assert not (tmp_path / "a.txt").exists()


def test_the_ok_message_is_printed_only_on_a_passing_check(tmp_path, capsys):
    bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py", ok_message="all fresh")
    assert "all fresh" not in capsys.readouterr().out
    bg.write_or_check(OUTPUTS, ["--check"], "t.py", tmp_path, "t.py", ok_message="all fresh")
    assert "t.py: all fresh" in capsys.readouterr().out


@pytest.mark.parametrize("args", BAD_ARGS, ids=BAD_IDS)
def test_an_argument_other_than_check_is_a_usage_error_and_writes_nothing(args, tmp_path, capsys):
    """The whole point of issue #111: no argument falls through to the write branch."""
    assert bg.write_or_check(OUTPUTS, args, "t.py", tmp_path, "t.py") == 2
    assert _written(tmp_path) == {}
    assert "usage: t.py [--check]" in capsys.readouterr().err


@pytest.mark.parametrize("args", BAD_ARGS, ids=BAD_IDS)
def test_a_bad_argument_leaves_an_already_written_tree_untouched(args, tmp_path):
    bg.write_or_check(OUTPUTS, [], "t.py", tmp_path, "t.py")
    (tmp_path / "a.txt").write_text("stale\n")
    assert bg.write_or_check(OUTPUTS, args, "t.py", tmp_path, "t.py") == 2
    assert (tmp_path / "a.txt").read_text() == "stale\n"


# --- both generators route through that one driver ------------------------


def _gen_bench_paths():
    here = os.path.dirname(GEN_BENCH_PY)
    return [os.path.join(here, name) for name in gen_bench.files()]


def _gdb_paths():
    return [os.path.join(REPO, rel) for rel in gdb.outputs()]


GENERATOR_PATHS = [_gen_bench_paths, _gdb_paths]


@pytest.mark.parametrize("gen", GENERATORS, ids=GENERATOR_IDS)
def test_both_generators_share_the_one_driver(gen):
    """Neither generator may grow a second copy of it."""
    assert gen.bench_gen is bg


@pytest.mark.parametrize("args", BAD_ARGS + [[], ["--check"]],
                         ids=BAD_IDS + ["no-args", "--check"])
@pytest.mark.parametrize("gen", GENERATORS, ids=GENERATOR_IDS)
def test_both_generators_hand_their_arguments_to_the_driver_verbatim(gen, args, monkeypatch):
    """No generator does its own argv parsing, so there is one rule to reason about.

    The driver's own tests above cover what each argument then *means*; this
    pins that the generator neither filters nor reinterprets them, and returns
    whatever the driver decides.
    """
    seen = {}

    def record(outputs, a, tool_name, root, regen_cmd, ok_message=None):
        seen.update(args=a, tool_name=tool_name, outputs=sorted(outputs))
        return 7                                  # a sentinel, not a real exit code

    monkeypatch.setattr(gen.bench_gen, "write_or_check", record)
    assert gen.main(args) == 7
    assert seen["args"] == args
    assert seen["outputs"], f"{gen.__name__} passed no outputs to the driver"


@pytest.mark.parametrize("args", BAD_ARGS, ids=BAD_IDS)
@pytest.mark.parametrize("gen,paths", list(zip(GENERATORS, GENERATOR_PATHS)),
                         ids=GENERATOR_IDS)
def test_an_unknown_argument_rewrites_none_of_the_committed_files(gen, paths, args):
    """End to end, against the real committed tree: exit 2 and not a byte moved.

    This is the regression the consolidation exists for. Both content *and*
    mtime are compared, because the committed tree is normally already fresh --
    a rewrite would reproduce the same bytes and only the mtime would betray it.
    """
    before = {p: (os.stat(p).st_mtime_ns, open(p, "rb").read()) for p in paths()}
    assert before, f"{gen.__name__} has no committed outputs to protect"
    assert gen.main(args) == 2
    after = {p: (os.stat(p).st_mtime_ns, open(p, "rb").read()) for p in paths()}
    assert after == before


# --- the request skeleton -------------------------------------------------


def test_process_block_uses_the_single_corner_library():
    assert bg.process_block(["hbt_typ", "hbt_wcs"]) == [
        {"name": "hbt_typ", "sections": [{"lib": bg.CORNER_LIB, "section": "hbt_typ"}]},
        {"name": "hbt_wcs", "sections": [{"lib": bg.CORNER_LIB, "section": "hbt_wcs"}]}]


def test_request_key_order_without_measurements_or_batch():
    req = bg.request("n.spice", {"kind": "ac"}, {"timeout_s": 1},
                     process=["hbt_typ"], temperature_c=[27])
    assert list(req) == ["netlist", "models", "corners", "analysis", "options"]
    assert list(req["corners"]) == ["process", "temperature_c"]
    assert req["models"] == {"pdk": bg.PDK_NAME}
    assert "batch" not in req


def test_request_key_order_with_measurements_corners_extra_and_batch():
    req = bg.request("n.spice", {"kind": "dc"}, {"timeout_s": 1},
                     process=["hbt_typ"], temperature_c=[27],
                     measurements=[{"name": "m"}],
                     corners_extra={"supply_v": {"vcc": [0.8]}}, batch=True)
    assert list(req) == ["netlist", "models", "corners", "analysis", "measurements",
                         "options", "batch"]
    assert list(req["corners"]) == ["process", "temperature_c", "supply_v"]
    assert req["batch"] == {"capacity_wait_s": bg.CAPACITY_WAIT_S}


def test_the_temperature_axis_is_a_list_even_when_given_a_tuple():
    """The generators pass tuples; the committed requests hold JSON lists."""
    req = bg.request("n.spice", {}, {}, process=("hbt_typ",), temperature_c=(-40, 27, 125))
    assert req["corners"]["temperature_c"] == [-40, 27, 125]
    json.dumps(req)


@pytest.mark.parametrize("build", [
    gen_bench.dc_request, gen_bench.ft_request,
    gdb.psat_request, gdb.ac_gain_request, gdb.ac_stability_request],
    ids=["dc_family", "ft", "psat", "ac_gain", "ac_stability"])
def test_every_generated_request_carries_the_shared_pdk_facts(build):
    req = build()
    assert req["models"] == {"pdk": bg.PDK_NAME}
    for entry in req["corners"]["process"]:
        assert [s["lib"] for s in entry["sections"]] == [bg.CORNER_LIB]
    if "batch" in req:
        assert req["batch"] == {"capacity_wait_s": bg.CAPACITY_WAIT_S}


@pytest.mark.parametrize("src", ["sim/lib/gen_dut_benches.py",
                                 "sim/device-npn13g2/gen_bench.py"])
def test_neither_generator_retypes_a_constant_bench_gen_owns(src):
    """A PDK release that moves the corner library is one edit, in bench_gen.py."""
    text = open(os.path.join(REPO, src)).read()
    for literal in (bg.CORNER_LIB, bg.PDK_NAME, "capacity_wait_s"):
        assert literal not in text, f"{src} retypes {literal!r}; bench_gen.py owns it"
