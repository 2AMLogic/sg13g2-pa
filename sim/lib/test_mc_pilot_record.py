"""`mc_pilot_record.py` reduces the runs it is given, not the runs it wishes for.

The pilot record's whole point (issue #174) is separating two mechanisms:

* **per-instance mismatch** -- the 14 identically biased output devices differ
  *within* one draw (`hbt_typ_mismatch`), and the same-draw pair difference
  `ic1-ic2` moves across draws;
* **common process movement** -- every device moves together across draws
  (`hbt_typ_stat`), the within-draw spread is exactly zero, and the mirror
  reference moves too (so a reference-to-output difference alone proves
  nothing about independent draws).

The tests feed synthetic reports where every candidate quantity has a
DIFFERENT value, so a reducer that averaged the array before differencing
(warning in the issue: "the nominal stress reducer divides array current by
14, which would erase the mismatch being measured"), that read the wrong
device's vector, or that swapped the two sections' roles produces a different
number rather than the same one. No simulator or PDK is needed.
"""
import importlib.util
import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)


def _load_mc_pilot_record():
    spec = importlib.util.spec_from_file_location(
        "mc_pilot_record", os.path.join(REPO, "sim", "mc-pilot", "mc_pilot_record.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_pilot_record"] = mod
    spec.loader.exec_module(mod)
    return mod


mpr = _load_mc_pilot_record()


def _dc_report(section, per_draw_offsets, pair_delta):
    """A synthetic op report: 14 devices, each draw moving each device by its
    own offset (mismatch) or by one shared offset (process); `pair_delta` is an
    extra systematic difference between ic1 and ic2 so a swapped or averaged
    reduction is detectable."""
    corners = []
    for k, offs in enumerate(per_draw_offsets):
        vals = {}
        for i in range(1, 15):
            vals[f"ic{i}"] = 1.0e-3 + offs[i - 1] + (pair_delta if i == 1 else 0.0)
        vals["ic_total"] = sum(v for key, v in vals.items() if key.startswith("ic"))
        vals["ic_diff_12"] = vals["ic1"] - vals["ic2"]
        vals["ic_ref"] = 0.5e-3 + 0.01e-3 * k
        vals["icc_vcc"] = -(vals["ic_total"] + vals["ic_ref"])
        corners.append({
            "corner_id": f"{section}/novdd/27C/mc{k}",
            "status": "pass",
            "measurements": [{"name": n, "value": v, "unit": "A", "status": "pass"}
                             for n, v in vals.items()],
        })
    return {
        "status": "pass",
        "environment": {
            "backend": "batch",
            "engine_version": "ngspice-47 (synthetic)",
            "models_lib_sha256_scope": "client",
            "monte_carlo": {"n": len(per_draw_offsets), "seed": 174, "vary": "mismatch",
                            "family_mismatch": [{"family": "bipolar", "active": None,
                                                 "note": "synthetic"}]},
        },
        "corners": corners,
    }


def _ac_report(root, section, s21_by_draw, s11_by_draw):
    """A synthetic AC report: the complex_vectors sidecar has the six port
    vectors of the two-copy deck; S21/S11 magnitudes encode the per-draw dB
    values being fed (a flat S21 of s21 dB across the 11 points, and an S11
    whose |S11| equals the target dB)."""
    corners = []
    for k, (s21, s11) in enumerate(zip(s21_by_draw, s11_by_draw)):
        # The reducer reads S21 = 2 v(out1)/v(s1) and S11 = 2 v(in1)/v(s1) - 1
        # with v(s1) = 1, so v(out1) = S21/2 and v(in1) = (S11 + 1)/2; a flat
        # magnitude per draw makes the per-draw min/worst trivially that draw's
        # target dB value.
        side = root / "job" / f"mc{k}" / "complex_vectors.json"
        side.parent.mkdir(parents=True)
        mag21 = 10 ** (s21 / 20.0)
        mag11 = 10 ** (s11 / 20.0)
        with open(side, "w") as fh:
            json.dump({"frequency_hz": [1.0] * 11,
                       "data": {
                           "v(s1)": {"real": [1.0] * 11, "imag": [0.0] * 11},
                           "v(in1)": {"real": [(mag11 + 1) / 2] * 11, "imag": [0.0] * 11},
                           "v(out1)": {"real": [mag21 / 2] * 11, "imag": [0.0] * 11},
                           "v(in2)": {"real": [0.0] * 11, "imag": [0.0] * 11},
                           "v(out2)": {"real": [0.0] * 11, "imag": [0.0] * 11},
                           "v(s2)": {"real": [1.0] * 11, "imag": [0.0] * 11},
                       }}, fh)
        corners.append({"corner_id": f"{section}/novdd/27C/mc{k}", "status": "pass",
                        "artifacts": {"complex_vectors": str(side)}})
    return {"status": "pass",
            "environment": {"backend": "batch", "monte_carlo": {"n": len(corners)},
                            "remote": {"fleet": [{"runner_klt_version": "0.9.3"}]}},
            "corners": corners}


def _write(path, doc):
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return str(path)


def test_dc_draws_keeps_one_draws_devices_apart():
    # mismatch: device 1 sits 1e-4 above device 2 in EVERY draw; an averaging
    # reducer would report ic_diff_12 == 0.
    draws_offs = [[0.0] * 14 for _ in range(3)]
    for offs in draws_offs:
        offs[1] = -1.0e-4
    rep = _dc_report("hbt_typ_mismatch", draws_offs, pair_delta=2.0e-4)
    draws = mpr.dc_draws(rep)
    assert len(draws) == 3
    for d in draws:
        assert abs(d["ic_diff_12"] - 3.0e-4) < 1e-12  # pair_delta, not 0
        spread = max(d[f"ic{i}"] for i in range(1, 15)) - min(d[f"ic{i}"] for i in range(1, 15))
        assert abs(spread - 3.0e-4) < 1e-12


def test_stats_reports_sample_stddev_and_range():
    st = mpr.stats([1.0, 2.0, 3.0])
    assert st["n"] == 3
    assert abs(st["mean"] - 2.0) < 1e-12
    assert abs(st["stddev_sample"] - 1.0) < 1e-12  # sample sigma, ddof=1
    assert st["min"] == 1.0 and st["max"] == 3.0
    assert mpr.stats([]) is None


def test_ac_draws_reads_forward_copy_s21_s11_after_relocation(tmp_path):
    original = tmp_path / "submit-host"
    rep = _ac_report(original / "mc_ac_mismatch", "hbt_typ_mismatch", [17., 16.], [-1.5, -2.])
    report_name = "mc_ac_mismatch.report.json"
    _write(original / report_name, rep)
    relocated = tmp_path / "fresh-checkout"
    shutil.move(original, relocated)
    path = relocated / report_name
    draws = mpr.ac_draws(mpr.load_run(path), path)
    assert len(draws) == 2
    assert abs(draws[0][0] - 17.0) < 1e-6   # min in-band S21, dB
    assert abs(draws[0][1] - (-1.5)) < 1e-6  # worst in-band S11, dB
    assert abs(draws[1][0] - 16.0) < 1e-6


def test_probe_capture_parses_envelope_among_noise(tmp_path):
    cap = tmp_path / "cap.json"
    cap.write_text('some log line\n{"schema_version": 1, "error": {\n'
                   '"command": "sim", "message": "refused: no switch"}}\ntail\n')
    probe = mpr.load_probe(str(cap))
    assert probe["kind"] == "refusal"
    assert probe["message"] == "refused: no switch"


def test_record_renders_both_sections_and_refusals(tmp_path, capsys):
    # stat: shared offset per draw (common movement, zero within-draw spread);
    # mismatch: per-device offsets. The pair delta is only in the mismatch feed.
    stat_offs = [[(0.05e-3) * k] * 14 for k in range(4)]
    mm_offs = []
    for k in range(4):
        mm_offs.append([0.02e-3 * ((i + k) % 3 - 1) for i in range(14)])
    files = {
        "dc_stat": _write(tmp_path / "dc_stat.json", _dc_report("hbt_typ_stat", stat_offs, 0.0)),
        "dc_mismatch": _write(tmp_path / "dc_mm.json",
                              _dc_report("hbt_typ_mismatch", mm_offs, 1.0e-4)),
        "ac_stat": _write(tmp_path / "ac_stat.report.json", _ac_report(tmp_path / "ac_stat", "hbt_typ_stat",
                                                                 [17.5, 17.4], [-1.2, -1.1])),
        "ac_mismatch": _write(tmp_path / "ac_mm.report.json", _ac_report(tmp_path / "ac_mm", "hbt_typ_mismatch",
                                                                   [17.3, 17.2], [-1.3, -1.2])),
    }
    (tmp_path / "scale.json").write_text(
        '{"schema_version":1,"error":{"command":"sim","message":"only gf180mcu, sky130"}}')
    (tmp_path / "inst.json").write_text(
        '{"schema_version":1,"error":{"command":"sim","message":"needs a known switch"}}')
    models = tmp_path / "models"
    models.mkdir()
    for name in mpr.MODEL_FILES:
        (models / name).write_text("* synthetic\n")
    json_out = tmp_path / "rec.json"
    rc = mpr.main(["mc_pilot_record.py", "20261120-000000-deadbee", "deadbee", "0",
                   "klt 0.9.0", "ngspice-47",
                   "--models-dir", str(models), "--json-out", str(json_out),
                   "--run", f"dc_stat={files['dc_stat']}",
                   "--run", f"dc_mismatch={files['dc_mismatch']}",
                   "--run", f"ac_stat={files['ac_stat']}",
                   "--run", f"ac_mismatch={files['ac_mismatch']}",
                   "--probe", f"scale={tmp_path / 'scale.json'}",
                   "--probe", f"instances={tmp_path / 'inst.json'}"])
    assert rc == 0
    text = capsys.readouterr().out
    # The two mechanisms are told apart in the tool-check answer.
    assert "Yes, from completed draws" in text
    # The process-only section's within-draw spread is reported as exactly zero.
    assert "process section, 4 draws. The mean within-array range is 0 A (maximum 0 A)" in text
    # Both refusals are quoted verbatim and linked.
    assert "only gf180mcu, sky130" in text
    assert "needs a known switch" in text
    assert "2AMLogic/klayout-tools#5486" in text
    assert "2AMLogic/klayout-tools#5487" in text
    # All four runs are summarised with their section labels.
    for key in ("dc_stat", "dc_mismatch", "ac_stat", "ac_mismatch"):
        assert key in text
    assert "hbt_typ_stat" in text and "hbt_typ_mismatch" in text
    # The batch answer reads the summaries.
    assert "Yes. 4/4 baseline requests completed" in text
    assert "Fleet runner versions 0.9.3" in text
    # The JSON side output carries the per-device distributions.
    side = json.loads(json_out.read_text())
    assert set(side["dc_mismatch"]["per_device"]) == {f"ic{i}" for i in range(1, 15)}
    assert side["dc_mismatch"]["per_draw_device_spread"]["mean"] > 0
    assert side["dc_stat"]["per_draw_device_spread"]["mean"] == 0.0
    assert side["probes"]["scale"]["kind"] == "refusal"
    assert side["runs"]["dc_mismatch"]["n_completed"] == 4


def test_record_renders_a_total_refusal_as_the_evidence(tmp_path, capsys):
    # Nothing completed anywhere: the record is the refusal, and the tool-check
    # answer must NOT claim measured spread (issue: "Record zero spread only
    # when completed draws support it" -- and never invent nonzero either).
    models = tmp_path / "models"
    models.mkdir()
    for name in mpr.MODEL_FILES:
        (models / name).write_text("* synthetic\n")
    empty = tmp_path / "gone.json"
    empty.write_text("")
    bad_stderr = tmp_path / "gone.stderr"
    bad_stderr.write_text("batch_no_capacity: refused\nsecond line\n")
    rc = mpr.main(["mc_pilot_record.py", "20261120-000000-deadbee", "deadbee", "0",
                   "klt 0.9.0", "ngspice-47",
                   "--models-dir", str(models), "--json-out", str(tmp_path / "j.json"),
                   "--run", f"dc_stat={empty}:{bad_stderr}",
                   "--run", f"dc_mismatch={empty}:{bad_stderr}",
                   "--run", f"ac_stat={empty}:{bad_stderr}",
                   "--run", f"ac_mismatch={empty}:{bad_stderr}"])
    assert rc == 0
    text = capsys.readouterr().out
    assert "**REFUSED/FAILED**" in text
    assert "batch_no_capacity: refused" in text
    assert "No completed mismatch draws" in text
    assert "Not established. 0/4 baseline requests completed" in text
    assert "no local fallback" in text


@pytest.mark.parametrize(("offsets", "conclusion"), [
    ([[0] * 14] * 2, "No within-array spread was observed"),
    ([[0] * 14], "One completed mismatch draw is insufficient"),
    ([[1e-4] + [0] * 13] * 2, "No draw-to-draw change"),
])
def test_conclusions_follow_draws_and_accepted_probe(tmp_path, capsys, offsets, conclusion):
    rep = _dc_report("hbt_typ_mismatch", offsets, 0)
    rep["environment"]["monte_carlo"]["n"] = 100
    path = _write(tmp_path / "op.json", rep)
    side = tmp_path / "out.json"
    mpr.main(["record", "fixture", "deadbee", "0", "klt 0.9.0", "ngspice",
              "--models-dir", str(tmp_path), "--json-out", str(side),
              "--run", f"dc_mismatch={path}", "--probe", f"scale={path}"])
    md = capsys.readouterr().out
    assert conclusion in md
    assert "Completed control draws for scale" in md
    assert "No negative control completed" not in md
    assert "Not established. 0/4 baseline requests completed" in md
    stats = json.loads(side.read_text())["probes"]["scale"]["ic_diff_12"]
    assert stats["n"] == len(offsets)
    if len(offsets) == 1:
        assert stats["stddev_sample"] is None
