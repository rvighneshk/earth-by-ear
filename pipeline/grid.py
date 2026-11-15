"""Clean decoded pixel values and reduce them to a compact analysis grid."""
from __future__ import annotations

import warnings

import numpy as np
from scipy import ndimage as ndi


def _disk(r: int) -> np.ndarray:
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y) <= r * r


def fill_thin_gaps(values: np.ndarray, max_gap_px: int = 3) -> np.ndarray:
    """Fill NaN features thinner than ~2*max_gap_px (coastlines, graticules, glyph strokes).

    Big NaN regions (gray land, missing data, large text blocks) are left alone.
    """
    nan = np.isnan(values)
    if not nan.any():
        return values
    thick = ndi.binary_opening(nan, structure=_disk(max_gap_px))
    thin = nan & ~thick
    if not thin.any():
        return values
    _, (iy, ix) = ndi.distance_transform_edt(nan, return_indices=True)
    out = values.copy()
    out[thin] = values[iy[thin], ix[thin]]
    return out


def to_grid(values: np.ndarray, rows: int, cols: int, min_valid: float = 0.5) -> np.ndarray:
    """Median of valid pixels in each cell. Cells with < min_valid valid pixels -> NaN.

    Median (not mean) so blended edge pixels between two very different colours
    cannot drag a cell to a value that is not in the data.
    """
    H, W = values.shape
    ys = np.linspace(0, H, rows + 1).astype(int)
    xs = np.linspace(0, W, cols + 1).astype(int)
    out = np.full((rows, cols), np.nan, np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for r in range(rows):
            band = values[ys[r]:ys[r + 1]]
            for c in range(cols):
                cell = band[:, xs[c]:xs[c + 1]]
                if cell.size == 0:
                    continue
                v = cell[~np.isnan(cell)]
                if v.size >= min_valid * cell.size:
                    out[r, c] = np.median(v)
    return out
