"""Python mirror of app/static/js/mapping.js + an offline stereo WAV renderer.

The renderer is the INSURANCE deliverable: if the live app breaks on demo day, you
still submit curated audio files. A cross-language test keeps the note/voicing
logic identical to the browser version. The offline synth is simpler than the
browser one (additive partials, no reverb), so it approximates the live sound.
"""
from __future__ import annotations

import math
import wave

import numpy as np

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11], "lydian": [0, 2, 4, 6, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10], "majorPent": [0, 2, 4, 7, 9],
    "minorPent": [0, 3, 5, 7, 10], "wholeTone": [0, 2, 4, 6, 8, 10],
}
_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SR = 44100


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def note_to_midi(name: str) -> int:
    base, acc, octv = name[0], 0, name[1:]
    if octv and octv[0] in "#b":
        acc = 1 if octv[0] == "#" else -1
        octv = octv[1:]
    return 12 * (int(octv) + 1) + _NOTE[base] + acc


def midi_to_freq(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def normalise(v: float, rng: dict):
    tr = math.log10 if rng.get("scale") == "log" else (lambda x: x)
    a, b, x = tr(rng["vmin"]), tr(rng["vmax"]), tr(v)
    n = clamp((x - a) / (b - a), 0, 1)
    if rng.get("center") is None:
        return n, None
    c = tr(rng["center"])
    if x >= c:
        s = (x - c) / (b - c) if b > c else 0.0
    else:
        s = -((c - x) / (c - a)) if c > a else 0.0
    return n, clamp(s, -1, 1)


def js_round(x: float) -> int:
    """JavaScript Math.round (halves round up), unlike Python's banker's rounding."""
    return math.floor(x + 0.5)


def degree_for(n, s, son: dict) -> int:
    L = len(SCALES[son["scale"]])
    span = son.get("spanOctaves", 3)
    if s is not None:
        return js_round(s * (span / 2) * L)
    return js_round(n * span * L)


def degree_to_midi(deg: int, scale: str, root: int) -> int:
    sc = SCALES[scale]
    L = len(sc)
    return root + 12 * (deg // L) + sc[deg % L]


def tension_of(n, s, mode: str) -> float:
    x = 0.0
    if mode == "anomaly":
        x = 0.0 if s is None else abs(s)
    elif mode == "high":
        x = n
    elif mode == "low":
        x = 1 - n
    return clamp((x - 0.4) / 0.6, 0, 1)


def voicing(midi: int, tension: float):
    parts = [(0, 1.0), (12, 0.35), (7, 0.55 * (1 - 0.6 * tension))]
    if tension > 0.15:
        parts.append((6, 0.5 * tension))
    if tension > 0.6:
        parts.append((1, 0.55 * (tension - 0.6) / 0.4))
    return [dict(midi=midi + s, freq=midi_to_freq(midi + s), gain=g) for s, g in parts]


def cutoff_for(tension: float, lat01: float) -> float:
    return 500 * 2 ** (clamp(0.2 + 0.5 * tension + 0.3 * lat01, 0, 1) * 4.5)


def value_sound(v: float, ds: dict, pan: float = 0.0, lat01: float = 0.5, roughness: float = 0.0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return dict(silent=True, pan=pan)
    son = ds["sonification"]
    n, s = normalise(v, ds["range"])
    midi = degree_to_midi(degree_for(n, s, son), son["scale"], note_to_midi(son["root"]))
    t = tension_of(n, s, son["tension"])
    return dict(silent=False, midi=midi, pan=pan, tension=t, roughness=roughness,
                cutoff=cutoff_for(t, lat01), partials=voicing(midi, t))


# --------------------------------------------------------------------------
# The planet's chord (mirror of planetChord in mapping.js)
# --------------------------------------------------------------------------
CHORD_PERCENTILES = [0.1, 0.3, 0.5, 0.7, 0.9]
CHORD_GAINS = [0.6, 0.8, 1.0, 0.8, 0.6]


def percentile(sorted_vals, p: float) -> float:
    """Linear-interpolated percentile of an ASCENDING list (same rule as the JS and numpy)."""
    if not len(sorted_vals):
        return float("nan")
    idx = p * (len(sorted_vals) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def planet_chord(values, ds: dict):
    """values: iterable of floats (NaN/None ignored). Returns a sound dict or None (too little data)."""
    vals = sorted(float(v) for v in values if v is not None and not math.isnan(float(v)))
    if len(vals) < 10:
        return None
    rng, son = ds["range"], ds["sonification"]
    root = note_to_midi(son["root"])
    percs = [percentile(vals, p) for p in CHORD_PERCENTILES]
    norms = [normalise(v, rng) for v in percs]
    midis = [degree_to_midi(degree_for(n, s, son), son["scale"], root) for n, s in norms]
    tension = max(tension_of(n, s, son["tension"]) for n, s in norms)
    spread = clamp(norms[4][0] - norms[0][0], 0, 1)
    merged = {}
    for m, g in zip(midis, CHORD_GAINS):
        merged[m] = merged.get(m, 0.0) + g
    partials = [dict(midi=m, freq=midi_to_freq(m), gain=min(g, 1.4)) for m, g in sorted(merged.items())]
    if tension > 0.6:
        top = partials[-1]["midi"] + 1
        partials.append(dict(midi=top, freq=midi_to_freq(top), gain=0.5 * (tension - 0.6) / 0.4))
    return dict(silent=False, kind="chord", pan=0.0, midi=midis[2], midis=midis, percentiles=percs,
                tension=tension, spread=spread, roughness=clamp((spread - 0.15) / 0.6, 0, 1),
                cutoff=cutoff_for(tension, 0.5), partials=partials, attack=0.35, sustain=True)


# --------------------------------------------------------------------------
# Offline renderer
# --------------------------------------------------------------------------
def _note(sound: dict, dur: float, level: float = 0.35) -> np.ndarray:
    """Mono note: additive triangle-ish partials, soft attack, exponential decay."""
    t = np.arange(int(dur * SR)) / SR
    if sound["silent"]:
        thump = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 35) * 0.18
        return thump
    # brightness from the same cutoff the browser uses: more harmonics when open
    harmonics = int(clamp(math.log2(sound["cutoff"] / 500) * 1.2 + 1, 1, 6))
    sig = np.zeros_like(t)
    total = sum(p["gain"] for p in sound["partials"])
    for p in sound["partials"]:
        w = 2 * np.pi * p["freq"]
        for k in range(1, harmonics + 1, 2):
            sig += (p["gain"] / total) * np.sin(k * w * t) / (k * k)
    sig += 0.25 * np.sin(2 * np.pi * midi_to_freq(sound["midi"] - 12) * t)
    if sound["roughness"] > 0:
        depth = 0.5 * sound["roughness"]
        rate = 14 + 18 * sound["roughness"]
        sig *= (1 - depth / 2) + (depth / 2) * np.sin(2 * np.pi * rate * t)
    att = sound.get("attack", 0.012)
    attack = np.minimum(t / att, 1.0)
    if sound.get("sustain"):                       # pad: hold, then release over the last 30%
        release = np.where(t < dur * 0.7, 1.0, np.exp(-(t - dur * 0.7) * (6.0 / dur) * 3.3))
        return sig * attack * release * level
    return sig * attack * np.exp(-t * (3.0 / dur)) * level


def _place(buf: np.ndarray, mono: np.ndarray, start: int, pan: float):
    end = min(len(buf), start + len(mono))
    if end <= start:
        return
    m = mono[: end - start]
    ang = (pan + 1) * math.pi / 4          # equal-power pan
    buf[start:end, 0] += m * math.cos(ang)
    buf[start:end, 1] += m * math.sin(ang)


def render_scan(values_a, ds: dict, values_b=None, step: float = 0.16, lat01: float = 0.5,
                pan_sweep: bool = True) -> np.ndarray:
    """Scan a row/profile. With values_b, A plays hard-left and B hard-right (Duet)."""
    n = len(values_a)
    dur = min(0.7, step * 2.4)
    buf = np.zeros((int((n * step + dur + 0.5) * SR), 2), np.float64)
    for i, va in enumerate(values_a):
        start = int(i * step * SR)
        base_pan = (i / max(n - 1, 1) * 2 - 1) * 0.9 if pan_sweep else 0.0
        if values_b is None:
            _place(buf, _note(value_sound(va, ds, base_pan, lat01), dur), start, base_pan)
        else:
            _place(buf, _note(value_sound(va, ds, -0.9, lat01), dur), start, -0.9)
            _place(buf, _note(value_sound(values_b[i], ds, 0.9, lat01), dur), start, 0.9)
    peak = np.abs(buf).max()
    if peak > 0:
        buf = buf / peak * 0.85
    return buf


def render_chords(chords, step: float = 2.4, note_dur: float = 3.4) -> np.ndarray:
    """The planet's chord time-lapse: one overlapping pad per year, centred in the stereo field."""
    buf = np.zeros((int((len(chords) * step + note_dur + 0.5) * SR), 2), np.float64)
    for i, c in enumerate(chords):
        _place(buf, _note(c, note_dur, level=0.3), int(i * step * SR), 0.0)
    peak = np.abs(buf).max()
    return buf / peak * 0.85 if peak > 0 else buf


def write_wav(path: str, stereo: np.ndarray) -> None:
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------
# The jukebox score: mirror of composeBar / stretchOf in mapping.js, plus a full-piece renderer
# --------------------------------------------------------------------------
def stretch_of(grids):
    vals = sorted(float(v) for g in grids for v in np.asarray(g, dtype=float).ravel() if not math.isnan(v))
    return None if len(vals) < 10 else (percentile(vals, 0.05), percentile(vals, 0.95))


def data_extent(grid, min_frac: float = 0.1):
    """First and last column holding data (>= 10% of rows). Mirrors dataExtent() in mapping.js."""
    rows, cols = grid.shape
    ok = np.where((~np.isnan(grid)).sum(axis=0) >= rows * min_frac)[0]
    return (int(ok[0]), int(ok[-1])) if len(ok) else (0, cols - 1)


def slice_cols(ext, s: int, steps: int):
    """Mirrors sliceCols() in mapping.js: columns [from, to) of sweep step s."""
    width = ext[1] - ext[0] + 1
    frm = ext[0] + int(math.floor(s / steps * width))
    return frm, max(frm + 1, ext[0] + int(math.floor((s + 1) / steps * width)))


def compose_bar(grid, ds: dict, steps: int = 16, stretch=None) -> dict:
    """grid: 2-D float array (NaN = nodata). Returns pad / melody / sparkle lists of sound dicts (rest -> dict(rest=True))."""
    rows, cols = grid.shape
    wave = ds["sonification"].get("wave", "triangle")
    vmin, vmax = ds["range"]["vmin"], ds["range"]["vmax"]
    melody, sparkle = [], []
    ext = data_extent(grid)
    for s in range(steps):
        c0, c1 = slice_cols(ext, s, steps)
        sl = grid[:, c0:c1].ravel()
        vals = sorted(float(v) for v in sl if not math.isnan(v))
        if len(vals) < sl.size * 0.2:
            melody.append(dict(rest=True)); sparkle.append(dict(rest=True)); continue
        pan = (s / (steps - 1) * 2 - 1) * 0.8
        mean = sum(vals) / len(vals)
        lo = normalise(percentile(vals, 0.1), ds["range"])[0]
        hi = normalise(percentile(vals, 0.9), ds["range"])[0]
        spread = clamp((hi - lo) / 0.5, 0, 1)
        if stretch and stretch[1] > stretch[0]:
            mean = clamp(vmin + (mean - stretch[0]) / (stretch[1] - stretch[0]) * (vmax - vmin), vmin, vmax)
        if s % 4 == 0 or spread > 0.15:
            melody.append({**value_sound(mean, ds, pan), "wave": wave})
        else:
            melody.append(dict(rest=True))
        if spread > 0.25 and s % 2 == 1:
            top = value_sound(percentile(vals, 0.9), ds, pan, 0.9)
            midi = top["midi"] + 12
            sparkle.append({**top, "midi": midi, "wave": wave, "partials": voicing(midi, top["tension"])})
        else:
            sparkle.append(dict(rest=True))
    pad = planet_chord(grid.ravel(), ds)
    return dict(pad={**pad, "wave": wave} if pad else dict(rest=True), melody=melody, sparkle=sparkle)


def _wave_note(sound: dict, dur: float, level: float) -> np.ndarray:
    """Like _note, but honours sound['wave']: sine = pure, triangle = odd 1/k^2, sawtooth = all 1/k."""
    wave = sound.get("wave", "triangle")
    if wave == "triangle":
        return _note(sound, dur, level)
    t = np.arange(int(dur * SR)) / SR
    harmonics = int(clamp(math.log2(sound["cutoff"] / 500) * 2 + 2, 1, 10)) if wave == "sawtooth" else 1
    sig = np.zeros_like(t)
    total = sum(p["gain"] for p in sound["partials"])
    for p in sound["partials"]:
        for k in range(1, harmonics + 1):
            sig += (p["gain"] / total) * np.sin(2 * np.pi * k * p["freq"] * t) / k
    sig += 0.25 * np.sin(2 * np.pi * midi_to_freq(sound["midi"] - 12) * t)
    if sound.get("roughness", 0) > 0:
        d = 0.5 * sound["roughness"]
        sig *= (1 - d / 2) + (d / 2) * np.sin(2 * np.pi * (14 + 18 * sound["roughness"]) * t)
    attack = np.minimum(t / sound.get("attack", 0.012), 1.0)
    if sound.get("sustain"):
        rel = np.where(t < dur * 0.7, 1.0, np.exp(-(t - dur * 0.7) * (6.0 / dur) * 3.3))
        return sig * attack * rel * level
    return sig * attack * np.exp(-t * (3.0 / dur)) * level


def render_performance(grids, ds: dict, bar_s: float = 4.0, steps: int = 16, reverb: bool = True) -> np.ndarray:
    """The whole 'Play this visualization' piece as stereo audio. One bar per frame; a single still loops 4 bars."""
    seq = list(grids) if len(grids) > 1 else [grids[0]] * 4
    stretch = stretch_of(seq)
    bars = [compose_bar(g, ds, steps, stretch) for g in seq]
    step = bar_s / steps
    buf = np.zeros((int((len(bars) * bar_s + bar_s + 1.5) * SR), 2), np.float64)
    for i, b in enumerate(bars):
        t0 = i * bar_s
        if not b["pad"].get("rest"):
            _place(buf, _wave_note(b["pad"], bar_s + 0.8, 0.3), int(t0 * SR), 0.0)
        for s in range(steps):
            for voice, dur, lvl in (("melody", 0.45, 0.34), ("sparkle", 0.25, 0.15)):
                snd = b[voice][s]
                if snd.get("rest") or snd.get("silent"):
                    continue
                _place(buf, _wave_note(snd, dur, lvl), int((t0 + s * step) * SR), snd["pan"])
    if reverb:
        from scipy.signal import fftconvolve
        n = int(SR * 2.0)
        rng = np.random.default_rng(7)                     # fixed seed: renders are reproducible
        ir = (rng.random((n, 2)) * 2 - 1) * (1 - np.arange(n) / n)[:, None] ** 2.6
        wet = np.stack([fftconvolve(buf[:, k], ir[:, k])[: len(buf)] for k in range(2)], axis=1)
        buf = buf + 0.22 * wet
    peak = np.abs(buf).max()
    return buf / peak * 0.85 if peak > 0 else buf
