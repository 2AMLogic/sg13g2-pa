"""summarize.py reads npn13G2 currents from the captured sweep and fails loudly on gaps (issue #87)."""
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SUM = os.path.join(os.path.dirname(HERE), "device-npn13g2", "summarize.py")
_spec = importlib.util.spec_from_file_location("dev_summarize", SUM)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
gb = S.gb


def _dc(tmp_path, drop_col=None, drop_point=None):
    axis = [round(0.1 * k, 1) for k in range(21)]
    names = ["v-sweep"] + ["i(vs_%s)" % gb.tag(nx, v) for nx in gb.NX for v in gb.VBE]
    if drop_col:
        names.remove(drop_col)
    pts = [[x] + [x * 1e-3] * (len(names) - 1) for x in axis if x != drop_point]
    p = tmp_path / "waveform.raw.json"
    p.write_text(json.dumps({"variables": [{"name": n} for n in names], "points": pts}))
    return {"artifacts": {"waveform": str(p)}}


def test_dc_reads_ic_at_vce_points(tmp_path):
    ic = S.read_dc(_dc(tmp_path))
    assert ic[(4, 0.82, 1.0)] == pytest.approx(1e-3)
    assert len(ic) == len(gb.NX) * len(gb.VBE) * len(gb.VCE)


def test_dc_missing_column_fails(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        S.read_dc(_dc(tmp_path, drop_col="i(vs_n4_v82)"))


def test_dc_missing_point_fails(tmp_path):
    with pytest.raises(ValueError, match="not on the captured grid"):
        S.read_dc(_dc(tmp_path, drop_point=1.0))


def _ft(tmp_path, freqs=(20e9, 35e9, 50e9), drop=None):
    data = {}
    for nx in gb.NX:
        for v in gb.VBE:
            for q, mag in (("vs", 3.0), ("vb", 1.0)):
                data["i(%s_%s)" % (q, gb.tag(nx, v))] = {"real": [mag] * len(freqs), "imag": [4.0 * mag / 3] * len(freqs)}
    data.pop(drop, None)
    p = tmp_path / "complex_vectors.json"
    p.write_text(json.dumps({"frequency_hz": list(freqs), "data": data}))
    return {"artifacts": {"complex_vectors": str(p)}}


def test_ft_magnitudes(tmp_path):
    ft = S.read_ft(_ft(tmp_path))
    assert ft[(1, 0.7)][0] == (pytest.approx(5.0), pytest.approx(5.0 / 3))


def test_ft_missing_frequency_fails(tmp_path):
    with pytest.raises(ValueError, match="not on the captured grid"):
        S.read_ft(_ft(tmp_path, freqs=(20e9, 35e9)))


def test_ft_missing_column_fails(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        S.read_ft(_ft(tmp_path, drop="i(vb_n4_v82)"))
