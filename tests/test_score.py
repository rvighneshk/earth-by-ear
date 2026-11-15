"""Run:  python -m pytest tests -q     (or: python tests/test_score.py)

1. JS and Python versions of the jukebox score choose the SAME notes (so the audio files match the app).
2. Globe datasets are masked; flat maps are not.
3. Rendered audio is audible, not clipped, and stereo.
"""
import json, os, subprocess, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline.jukebox_render import load_grid  # noqa: E402
from pipeline.sonify import compose_bar, stretch_of, render_performance  # noqa: E402

IDX = json.load(open(os.path.join(ROOT, "app/static/data/index.json"), encoding="utf-8"))["datasets"]


def test_js_and_python_agree():
    js = json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tests/score.mjs")]))
    for ds in IDX:
        grids = [load_grid(ds, f) for f in ds["frames"]]
        seq = grids if len(grids) > 1 else [grids[0]] * 4
        st = stretch_of(seq)
        for i, g in enumerate(seq):
            b = compose_bar(g, ds, 16, st)
            m = lambda x: None if x.get("rest") or x.get("silent") else x["midi"]
            assert [m(x) for x in b["melody"]] == js[ds["id"]][i]["melody"], (ds["id"], i, "melody")
            assert [m(x) for x in b["sparkle"]] == js[ds["id"]][i]["sparkle"], (ds["id"], i, "sparkle")
            pad = None if b["pad"].get("rest") else [p["midi"] for p in b["pad"]["partials"]]
            assert pad == js[ds["id"]][i]["pad"], (ds["id"], i, "pad")


def test_browser_render_matches_python_render():
    """The browser builds the performance with synth.js; the downloadable files use sonify.py. They must be the same audio."""
    import tempfile
    from pipeline.sonify import render_performance
    for sid in ("eic-night-lights", "eic-iss-lightning", "eic-gedi-forest-height"):    # triangle, sawtooth + globe mask, sine
        ds = next(d for d in IDX if d["id"] == sid)
        f = os.path.join(tempfile.mkdtemp(), "mix.f32")
        subprocess.check_call(["node", os.path.join(ROOT, "tests/synth_dump.mjs"), sid, f])
        js = np.fromfile(f, dtype=np.float32).reshape(-1, 2).astype(np.float64)
        py = render_performance([load_grid(ds, fr) for fr in ds["frames"]], ds, reverb=False)
        assert js.shape == py.shape, (sid, js.shape, py.shape)
        js *= 0.85 / np.abs(js).max()                       # both peak-normalised the same way
        err = np.abs(js - py).max()
        assert err < 2e-3, (sid, "max sample difference", err)


def test_geometry_and_masks():
    for ds in IDX:
        valid = 1 - np.isnan(load_grid(ds, ds["frames"][0])).mean()
        if ds["id"] in ("eic-dyamond-co2", "eic-air-quality", "eic-gedi-forest-height"):
            assert ds["geometry"] == "view" and valid < 0.6
        if ds["geometry"] == "map":
            assert valid > 0.4            # flat maps are mostly data (ocean/hue maps blank the grey land)


def test_globe_sweep_has_no_dead_air():
    """The sweep covers only real data: every step's slice of a globe holds data (a quiet step is rhythm, never empty sky)."""
    from pipeline.sonify import data_extent, slice_cols
    for ds in IDX:
        if ds["id"] in ("eic-dyamond-co2", "eic-air-quality", "eic-gedi-forest-height"):
            for fr in ds["frames"]:
                g = load_grid(ds, fr)
                ext = data_extent(g)
                for s in range(16):
                    c0, c1 = slice_cols(ext, s, 16)
                    assert (~np.isnan(g[:, c0:c1])).mean() >= 0.2, (ds["id"], fr["label"], s)


def test_audio_is_audible():
    ds = IDX[0]
    a = render_performance([load_grid(ds, f) for f in ds["frames"]], ds)
    assert a.shape[1] == 2 and a.shape[0] > 44100 * 10
    assert 0.02 < np.sqrt((a ** 2).mean()) < 0.5 and np.abs(a).max() <= 0.86
    assert np.abs(a[:, 0] - a[:, 1]).mean() > 1e-4          # real stereo image


if __name__ == "__main__":
    for t in (test_js_and_python_agree, test_browser_render_matches_python_render, test_geometry_and_masks, test_globe_sweep_has_no_dead_air, test_audio_is_audible):
        t(); print("ok", t.__name__)
