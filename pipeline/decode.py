"""Turn pixels back into physical values using the legend LUT.

Steps per pixel:
  1. nearest LUT colour in CIELAB (perceptual, so JPEG/antialias noise is small),
  2. project onto the neighbouring LUT segments for sub-bin precision,
  3. bar fraction (0..1) -> value through the tick table (handles log and
     asymmetric / piecewise colorbars),
  4. pixels farther than `max_de` from ANY legend colour are NODATA (text,
     coastlines, gray land, white background).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .legend import to_lab


def frac_to_value(frac: np.ndarray, ticks, scale: str = "linear") -> np.ndarray:
    """Map bar fraction -> value with a piecewise-linear tick table.

    ticks: [(bar_fraction, value), ...]. `scale='log'` interpolates log10(value).
    """
    ticks = sorted((float(f), float(v)) for f, v in ticks)
    fs = np.array([t[0] for t in ticks])
    vs = np.array([t[1] for t in ticks])
    if scale == "log":
        if (vs <= 0).any():
            raise ValueError("log scale needs positive tick values")
        vs = np.log10(vs)
    out = np.interp(frac, fs, vs)
    if scale == "log":
        out = 10 ** out
    return out


def decode_fraction(img_rgb: np.ndarray, lut_rgb: np.ndarray, max_de: float = 10.0,
                    chunk_rows: int = 128):
    """Return (frac, dist): bar fraction per pixel (NaN = nodata) and the ΔE distance."""
    lut_lab = to_lab(lut_rgb[None])[0].astype(np.float64)
    n = len(lut_lab)
    if n < 8:
        raise ValueError(f"LUT too short ({n} entries); legend detection probably failed")
    tree = cKDTree(lut_lab)
    seg_a = lut_lab[:-1]
    seg_d = lut_lab[1:] - lut_lab[:-1]
    seg_len2 = (seg_d ** 2).sum(1) + 1e-9

    H, W, _ = img_rgb.shape
    frac = np.full((H, W), np.nan, np.float32)
    dist = np.full((H, W), np.inf, np.float32)
    for r0 in range(0, H, chunk_rows):
        lab = to_lab(img_rgb[r0:r0 + chunk_rows]).reshape(-1, 3).astype(np.float64)
        d, idx = tree.query(lab)
        best_pos = idx.astype(np.float64)
        best_d = d.copy()

        # segment (idx, idx+1)
        ok = idx < n - 1
        i = np.where(ok, idx, 0)
        t = np.clip(((lab - seg_a[i]) * seg_d[i]).sum(1) / seg_len2[i], 0, 1)
        dd = np.linalg.norm(lab - (seg_a[i] + t[:, None] * seg_d[i]), axis=1)
        upd = ok & (dd <= best_d + 1e-9)
        best_pos = np.where(upd, i + t, best_pos)
        best_d = np.where(upd, dd, best_d)

        # segment (idx-1, idx)
        ok2 = idx > 0
        j = np.where(ok2, idx - 1, 0)
        t2 = np.clip(((lab - seg_a[j]) * seg_d[j]).sum(1) / seg_len2[j], 0, 1)
        dd2 = np.linalg.norm(lab - (seg_a[j] + t2[:, None] * seg_d[j]), axis=1)
        upd2 = ok2 & (dd2 < best_d - 1e-9)
        best_pos = np.where(upd2, j + t2, best_pos)
        best_d = np.where(upd2, dd2, best_d)

        f = (best_pos / (n - 1)).astype(np.float32)
        f[best_d > max_de] = np.nan
        rows = min(chunk_rows, H - r0)
        frac[r0:r0 + rows] = f.reshape(rows, W)
        dist[r0:r0 + rows] = best_d.astype(np.float32).reshape(rows, W)
    return frac, dist


def decode_values(img_rgb, lut_rgb, ticks, scale="linear", max_de=10.0):
    frac, dist = decode_fraction(img_rgb, lut_rgb, max_de)
    return frac_to_value(frac, ticks, scale).astype(np.float32), dist
