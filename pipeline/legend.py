"""Find the colorbar in a visualization and turn it into a lookup table (LUT).

Idea: a colorbar is a long thin rectangle whose colour is CONSTANT across its
short axis and SMOOTHLY VARYING along its long axis. Flat backgrounds are
constant too, but they have no colour variety, so we score candidates by how
far the colour travels (in CIELAB) along the bar.

If auto-detection fails on a real frame, pass a manual bbox (see
`legend_from_bbox`) - that is the escape hatch for the hackathon.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage import color as skcolor


def to_lab(img_rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB (..., 3) -> float32 CIELAB (..., 3)."""
    arr = img_rgb.astype(np.float32) / 255.0
    return skcolor.rgb2lab(arr).astype(np.float32)


def delta_e(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a - b) ** 2).sum(-1))


@dataclass
class Legend:
    x0: int
    y0: int
    x1: int          # exclusive
    y1: int          # exclusive
    orientation: str  # 'h' (low->high = left->right) or 'v' (low->high = bottom->top)
    lut_rgb: np.ndarray  # (N,3) uint8, ordered LOW -> HIGH
    score: float = 0.0

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)

    def stats(self) -> dict:
        lab = to_lab(self.lut_rgb[None])[0]
        steps = delta_e(lab[1:], lab[:-1])
        return dict(n=len(lab), path_de=float(steps.sum()), max_step_de=float(steps.max()),
                    mean_step_de=float(steps.mean()))


# --------------------------------------------------------------------------
def _trim_ends(colors_lab: np.ndarray, max_trim: int = 6, jump: float = 12.0):
    """Drop outline pixels at the ends of the bar. Returns (lo, hi) slice bounds."""
    n = len(colors_lab)
    steps = delta_e(colors_lab[1:], colors_lab[:-1])
    lo, hi = 0, n
    head = steps[:max_trim]
    if len(head) and head.max() > jump:
        lo = int(head.argmax()) + 1
    tail = steps[-max_trim:]
    if len(tail) and tail.max() > jump:
        hi = n - len(tail) + int(tail.argmax())
    return lo, max(hi, lo + 2)


def _bars_horizontal(lab, tol, min_len, min_aspect, min_variety, max_step=20.0, min_thick=8, max_thick=None):
    H, W, _ = lab.shape
    mask = np.zeros((H, W), bool)
    up = delta_e(lab[1:-1], lab[:-2])
    dn = delta_e(lab[1:-1], lab[2:])
    mask[1:-1] = (up < tol) & (dn < tol)
    # Cut at big horizontal colour jumps (outline<->bar, bar<->page) so the bar
    # cannot leak into the page background through its outline columns.
    lr = delta_e(lab[:, 1:], lab[:, :-1])
    smooth_h = np.zeros((H, W), bool)
    smooth_h[:, 1:-1] = (lr[:, :-1] < max_step) & (lr[:, 1:] < max_step)
    mask &= smooth_h
    labels, n = ndi.label(mask)
    out = []
    for i, sl in enumerate(ndi.find_objects(labels), start=1):
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if w < min_len or h < min_thick or w / h < min_aspect:
            continue
        if max_thick is not None and h > max_thick:
            continue
        if (labels[sl] == i).mean() < 0.8:
            continue
        pad = h // 4
        band = lab[ys.start + pad: ys.stop - pad, xs.start: xs.stop]
        colors = np.median(band, axis=0)
        steps = delta_e(colors[1:], colors[:-1])
        variety = float(steps.sum())
        if variety < min_variety:
            continue
        score = variety * (w / h)
        out.append((score, ys.start, ys.stop, xs.start, xs.stop))
    return out


def _lut_from_box(img_rgb, y0, y1, x0, x1, orientation, reverse=False, trim=True):
    """Median colour along the long axis over the central band of the short axis.

    Returns (lut_low_to_high, (lo, hi)) where lo/hi are the kept bounds along the
    long axis in *box order* (left->right or top->bottom), used to tighten the bbox.
    """
    if orientation == "h":
        pad = (y1 - y0) // 4
        band = img_rgb[y0 + pad: max(y1 - pad, y0 + pad + 1), x0:x1]
        lut = np.median(band, axis=0)
    else:
        pad = (x1 - x0) // 4
        band = img_rgb[y0:y1, x0 + pad: max(x1 - pad, x0 + pad + 1)]
        lut = np.median(band, axis=1)
    lut = lut.astype(np.uint8)
    lo, hi = 0, len(lut)
    if trim:
        lo, hi = _trim_ends(to_lab(lut[None])[0])
        lut = lut[lo:hi]
    if orientation == "v":
        lut = lut[::-1]                      # bottom -> top = low -> high
    if reverse:
        lut = lut[::-1]
    return lut, (lo, hi)


def detect_legend(img_rgb: np.ndarray, orientation: str | None = None, *, tol: float = 8.0,
                  min_len: int = 60, min_aspect: float = 6.0, min_variety: float = 30.0,
                  max_step: float = 20.0, min_thick: int = 8, max_thick_frac: float = 0.15,
                  reverse: bool = False) -> Legend | None:
    """Auto-detect the colorbar. Returns None when nothing plausible is found."""
    lab = to_lab(img_rgb)
    best = None
    for ori in ("h", "v") if orientation is None else (orientation,):
        L = lab if ori == "h" else lab.transpose(1, 0, 2)
        max_thick = max(min_thick, int(max_thick_frac * min(lab.shape[:2])))
        for score, ya, yb, xa, xb in _bars_horizontal(L, tol, min_len, min_aspect, min_variety,
                                                      max_step, min_thick, max_thick):
            box = (xa, ya, xb, yb) if ori == "h" else (ya, xa, yb, xb)   # undo transpose
            if best is None or score > best[0]:
                best = (score, ori, box)
    if best is None:
        return None
    score, ori, (x0, y0, x1, y1) = best
    lut, (lo, hi) = _lut_from_box(img_rgb, y0, y1, x0, x1, ori, reverse)
    if ori == "h":
        x0, x1 = x0 + lo, x0 + hi
    else:
        y0, y1 = y0 + lo, y0 + hi
    return Legend(x0, y0, x1, y1, ori, lut, float(score))


def legend_from_bbox(img_rgb, bbox, orientation: str, reverse: bool = False) -> Legend:
    """Manual override: bbox = (x0, y0, x1, y1) of the colour band only (no labels)."""
    x0, y0, x1, y1 = bbox
    lut, _ = _lut_from_box(img_rgb, y0, y1, x0, x1, orientation, reverse, trim=False)
    return Legend(x0, y0, x1, y1, orientation, lut, 0.0)
