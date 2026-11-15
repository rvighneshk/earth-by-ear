"""Pipeline checks: colour-ramp values, time labels, unique voices, and the importer's re-encode fallback.
Run:  python tests/test_pipeline.py     (the importer test is skipped if ffmpeg is not installed)
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import dates, hue, voices  # noqa: E402
from pipeline.jukebox_render import load_grid  # noqa: E402

IDX = json.load(open(os.path.join(ROOT, "app/static/data/index.json"), encoding="utf-8"))["datasets"]


def test_hue_ramp_is_physical():
    """Blue is cold (low), red is warm (high); grey and black are silent."""
    img = np.zeros((4, 4, 3), np.uint8)
    img[0, 0] = (255, 0, 0)      # BGR blue
    img[0, 1] = (0, 0, 255)      # red
    img[0, 2] = (128, 128, 128)  # grey land
    v = hue.hue_values(img)
    assert v[0, 0] < 10 and v[0, 1] > 90 and np.isnan(v[0, 2]) and np.isnan(v[1, 1])


def test_ocean_tropics_warmer_than_poles():
    ds = next(d for d in IDX if d["id"] == "eic-ocean-current-temperature")
    assert ds.get("valueSource") == "hue"
    g = load_grid(ds, ds["frames"][0])
    z = np.array([np.nanmean(r) if (~np.isnan(r)).sum() > 3 else np.nan for r in g])
    r = len(z)
    assert np.nanmean(z[int(r * .42):int(r * .58)]) > np.nanmean(z[:int(r * .12)]) + 40


def test_time_labels():
    entry = {"start": "2017-03-01T03:27", "end": "2017-03-01T12:01", "format": "%d %b %Y %H:%M"}
    assert dates.label_for(0.5, entry) == "01 Mar 2017 07:44"            # the on-screen mid stamp
    assert dates.label_for(0, {"start": "2020-01-14T22:00", "end": "2020-02-27T16:00", "approx": True}).startswith("~14 Jan")
    ds = {"id": "x", "frames": [{"label": "0.0 s"}, {"label": "5.0 s"}], "diagnostics": [{}, {}]}
    dates.relabel(ds, {})
    assert [f["label"] for f in ds["frames"]] == ["Frame 1 of 2", "Frame 2 of 2"]


def test_every_dataset_has_its_own_voice():
    seen = [(d["sonification"]["scale"], d["sonification"]["root"], d["sonification"]["wave"]) for d in IDX]
    assert len(set(seen)) == len(seen), seen
    assert voices.voice_for("eic-brand-new") == voices.voice_for("eic-brand-new")      # stable
    assert voices.voice_for("eic-brand-new") != voices.voice_for("eic-other-new")


def test_importer_falls_back_to_h264_copy():
    if not shutil.which("ffmpeg"):
        print("   (skipped: ffmpeg not installed)"); return
    import cv2
    from pipeline import import_svs_media as m
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "clip.avi"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x160:rate=10:duration=3",
                    "-c:v", "mpeg4", str(src)], check=True)
    real = cv2.VideoCapture

    class CannotDecodeOriginal:                       # pretend OpenCV cannot read the original codec
        def __init__(s, p, *a): s.c = real(p) if str(p).endswith(".h264.mp4") else None
        def isOpened(s): return s.c is not None and s.c.isOpened()
        def release(s): pass
        def __getattr__(s, k): return getattr(s.c, k)

    m.MEDIA = tmp / "media"
    cv2.VideoCapture = CannotDecodeOriginal
    try:
        cap = m.open_video(src)
        assert cap.isOpened() and (tmp / "media/_proxy/clip.h264.mp4").exists()
        try:
            m.open_video(tmp / "missing.mp4"); assert False
        except FileNotFoundError as e:
            assert "missing.mp4" in str(e)
    finally:
        cv2.VideoCapture = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_importer_skips_blank_intro():
    """A video that opens with blank frames (or a fade) must not produce blank frames in the dataset."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: ffmpeg not installed)"); return
    from pipeline import import_svs_media as m
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "intro.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x160:d=3:r=10",
                    "-f", "lavfi", "-i", "testsrc2=size=320x160:rate=10:duration=9", "-filter_complex", "[0:v][1:v]concat=n=2:v=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    m.DATA = tmp / "data"; m.DATA.mkdir(); m.MEDIA = tmp / "media"
    m.ingest(src, "eic-atmospheric-river", None, "relative brightness", [0, 1, 2, 5, 8], (0, 0, 1, 1), 10, 20, "viridis")
    idx = json.loads((m.DATA / "index.json").read_text(encoding="utf-8"))["datasets"][0]
    secs = [f["seconds"] for f in idx["frames"]]
    assert min(secs) >= 3.0, secs                       # nothing from the 3-second black intro
    assert len(secs) == len(set(secs)) and len(secs) >= 3, secs   # and no duplicates from nudging 0, 1, 2 forward
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for t in (test_hue_ramp_is_physical, test_ocean_tropics_warmer_than_poles, test_time_labels,
              test_every_dataset_has_its_own_voice, test_importer_falls_back_to_h264_copy, test_importer_skips_blank_intro):
        t(); print("ok", t.__name__)
