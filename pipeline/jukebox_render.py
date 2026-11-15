"""Render one audio track per dataset: the same piece the app plays for 'Play this visualization'.

  python -m pipeline.jukebox_render          # -> app/static/audio/<dataset>.mp3 (+ .wav in out/audio) and index.json notes
"""
import json, os, shutil, subprocess, zipfile

import numpy as np

from .sonify import normalise, write_wav, render_performance, planet_chord

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "static", "data")
AUDIO = os.path.join(ROOT, "app", "static", "audio")
WAVS = os.path.join(ROOT, "out", "audio")


def load_grid(ds, frame):
    g = json.load(open(os.path.join(DATA, frame["url"])))
    a = np.array([np.nan if v is None else v for v in g["data"]], dtype=float)
    return a.reshape(g["rows"], g["cols"])


def describe(ds, grids):
    """Plain-language caption built only from numbers in the data (also the screen-reader alternative to the audio)."""
    from .sonify import percentile
    mids = [percentile(sorted(g[~np.isnan(g)].tolist()), 0.5) for g in grids]
    f = lambda v: f"{v:.0f} {ds['unit']}"
    n = len(grids)
    move = (f"{n} movements of four seconds, one per frame." if n > 1 else "One still frame, repeated for four bars.")
    trend = ("" if n < 2 else f" The middle of the map goes from {f(mids[0])} to {f(mids[-1])}, so the pad "
             + ("rises." if mids[-1] > mids[0] + 1 else "falls." if mids[-1] < mids[0] - 1 else "stays put."))
    s = ds["sonification"]
    return (f"{move} {s['scale']} scale, home note {s['root']}, {s['wave']} sound. A pad plays the whole picture, a melody sweeps "
            f"{'left to right across the view' if ds.get('geometry') == 'view' else 'west to east'}, and a high sparkle appears where the picture is busy."
            + trend + (" Pitch follows each pixel's position along the colour ramp, not calibrated degrees." if ds.get("valueSource") == "hue"
               else " Sound is derived from image brightness, not calibrated measurements."))


if __name__ == "__main__":
    os.makedirs(AUDIO, exist_ok=True); os.makedirs(WAVS, exist_ok=True)
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    for ds in idx["datasets"]:
        grids = [load_grid(ds, f) for f in ds["frames"]]
        audio = render_performance(grids, ds)
        wav = os.path.join(WAVS, ds["id"] + ".wav"); write_wav(wav, audio)
        if shutil.which("ffmpeg"):
            ext = "mp3"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "128k", os.path.join(AUDIO, ds["id"] + ".mp3")], check=True)
        else:                                   # no ffmpeg installed: ship the WAV (bigger, but works everywhere)
            ext = "wav"
            shutil.copy(wav, os.path.join(AUDIO, ds["id"] + ".wav"))
        mp3 = os.path.join(AUDIO, f"{ds['id']}.{ext}")
        ds["audio"] = dict(file=f"audio/{ds['id']}.{ext}", seconds=round(len(audio) / 44100, 1), description=describe(ds, grids))
        print(f"{ds['id']:32s} {ds['audio']['seconds']:5.1f}s  {os.path.getsize(mp3) // 1024} KB")
    json.dump(idx, open(os.path.join(DATA, "index.json"), "w", encoding="utf-8"), indent=1)
    # one zip with every track + a text file describing each (the "playlist" deliverable)
    zp = os.path.join(AUDIO, "earth-jukebox-playlist.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
        notes = ["Earth, by ear: playlist. Audio generated from NASA Scientific Visualization Studio animations.\n"]
        for ds in idx["datasets"]:
            z.write(os.path.join(AUDIO, os.path.basename(ds["audio"]["file"])), os.path.basename(ds["audio"]["file"]))
            notes.append(f"{os.path.basename(ds['audio']['file'])}  ({ds['audio']['seconds']} s)\n{ds['title']}\n{ds['audio']['description']}\nSource: {ds.get('sourcePage', '')}\n")
        z.writestr("PLAYLIST.txt", "\n".join(notes))
    if not shutil.which("ffmpeg"):
        print("NOTE: ffmpeg not found, so tracks are WAV files (larger). Install ffmpeg and rerun for small MP3s.")
    print("playlist zip:", os.path.getsize(zp) // 1024, "KB")
