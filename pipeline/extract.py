"""End-to-end: image file -> legend -> physical values -> analysis grid.

The diagnostics are the important part for REAL frames, where there is no
answer key: they tell you, without ground truth, whether the extraction can
be trusted (how well do decoded values re-explain the original colours?).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .decode import decode_values, frac_to_value
from .grid import fill_thin_gaps, to_grid
from .legend import Legend, detect_legend, legend_from_bbox, to_lab


@dataclass
class ExtractConfig:
    vmin: float
    vmax: float
    ticks: list | None = None                 # [(bar_fraction, value)]; default linear vmin..vmax
    scale: str = "linear"                     # 'linear' | 'log'
    grid_cols: int = 180
    grid_rows: int | None = None              # default: from map aspect ratio
    legend_image: str | None = None           # path to a SEPARATE colorbar image (SVS often ships one);
                                              # legend_bbox/orientation then refer to THAT image
    legend_bbox: tuple | None = None          # manual override (x0,y0,x1,y1) of colour band
    legend_orientation: str | None = None     # 'h' | 'v' (auto if None)
    reverse_legend: bool = False              # True if the bar runs high -> low
    map_bbox: tuple | None = None             # manual override of the data area
    locked_map_bbox: tuple | None = None      # set by the builder: first frame's box, reused for the rest
    lock_tolerance: int = 3                   # px of jitter allowed before a layout change is an error
    max_de: float = 10.0                      # ΔE beyond which a pixel is NODATA
    fill_gap_px: int = 3
    # Pixels to blank around an OVERLAPPING legend, beyond the colour band: (left, top, right, bottom).
    # Covers tick labels and a background panel. Default: labels sit below an 'h' bar / right of a 'v' bar.
    legend_blank: tuple | None = None
    min_valid: float = 0.5
    extent: tuple = (-180.0, -90.0, 180.0, 90.0)   # west, south, east, north

    def tick_table(self):
        return self.ticks or [(0.0, self.vmin), (1.0, self.vmax)]


@dataclass
class ExtractResult:
    grid: np.ndarray
    legend: Legend
    map_bbox: tuple
    diagnostics: dict = field(default_factory=dict)
    pixel_values: np.ndarray | None = None


def load_image(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def _longest_run(mask: np.ndarray, max_gap: int = 3) -> tuple[int, int]:
    """Longest run of True in a 1-D mask, bridging gaps of <= max_gap."""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return 0, len(mask)
    best = (idx[0], idx[0] + 1)
    start = prev = idx[0]
    for i in idx[1:]:
        if i - prev > max_gap + 1:
            if prev + 1 - start > best[1] - best[0]:
                best = (start, prev + 1)
            start = i
        prev = i
    if prev + 1 - start > best[1] - best[0]:
        best = (start, prev + 1)
    return int(best[0]), int(best[1])


def find_map_region(img_rgb: np.ndarray, legend: Legend | None, min_frac: float = 0.25,
                    pad: int = 1) -> tuple:
    """Data area = longest run of rows, then columns, that are mostly non-background.

    The page colour is sampled from the image border (not assumed white), because
    diverging colormaps (RdBu, coolwarm) have a near-white midpoint that must not be
    mistaken for page. Row/column occupancy tolerates partly-white edges.
    If the border is not a uniform colour (full-bleed frame) the whole image is used;
    in that case, or if results look shifted, pass `map_bbox` manually.
    """
    lab = to_lab(img_rgb)
    H, W = lab.shape[:2]
    sides = [lab[0], lab[-1], lab[:, 0], lab[:, -1]]
    page = np.median(np.concatenate(sides), axis=0)
    # A real page margin surrounds ALL FOUR sides, so every side must be uniform on its own.
    # (Pooling the sides is fooled by full-bleed maps whose polar rows are near-white.)
    uniform_each = [(np.linalg.norm(sd - page, axis=1) < 1.5).mean() for sd in sides]
    if min(uniform_each) < 0.97:
        # Full-bleed frame: no page margin to peel off. Whole image is the map.
        return (0, 0, W, H)
    bg = np.linalg.norm(lab - page, axis=-1) < 1.5
    fg = ~bg
    if legend is not None:                       # no in-frame legend when a separate colorbar image is used
        x0, y0, x1, y1 = legend.bbox
        fg[max(y0 - 4, 0): y1 + 4, max(x0 - 4, 0): x1 + 4] = False
    r0, r1 = _longest_run(fg.mean(axis=1) > min_frac)
    c0, c1 = _longest_run(fg[r0:r1].mean(axis=0) > min_frac)
    r0b, r1b = _longest_run(fg[:, c0:c1].mean(axis=1) > min_frac)   # refine rows with cols known
    return (c0 + pad, r0b + pad, c1 - pad, r1b - pad)


def extract(img_rgb: np.ndarray, cfg: ExtractConfig, keep_pixels: bool = False) -> ExtractResult:
    # Where to read the colorbar from: the frame itself, or a separate colorbar image.
    src = load_image(cfg.legend_image) if cfg.legend_image else img_rgb
    in_frame = not cfg.legend_image
    if cfg.legend_bbox:
        if not cfg.legend_orientation:
            raise ValueError("manual legend_bbox needs legend_orientation 'h' or 'v'")
        legend = legend_from_bbox(src, cfg.legend_bbox, cfg.legend_orientation, cfg.reverse_legend)
    else:
        # a dedicated colorbar image is mostly colorbar, so the in-frame "thin bar" safeguard is lifted
        legend = detect_legend(src, cfg.legend_orientation, reverse=cfg.reverse_legend,
                               max_thick_frac=1.0 if cfg.legend_image else 0.15)
        if legend is None:
            raise RuntimeError("No colorbar found" + (" in the legend image" if cfg.legend_image else "")
                               + ". Pass legend_bbox + legend_orientation manually.")

    mx0, my0, mx1, my1 = cfg.map_bbox or find_map_region(img_rgb, legend if in_frame else None)
    if cfg.locked_map_bbox and not cfg.map_bbox:
        # Frames of one dataset share a layout. Compression can nudge the auto-detected box by a
        # pixel or two, which would change the grid size, so reuse the first frame's box. But a
        # box that is genuinely different means a different crop: refuse rather than guess.
        if max(abs(a - b) for a, b in zip((mx0, my0, mx1, my1), cfg.locked_map_bbox)) > cfg.lock_tolerance:
            raise RuntimeError(f"Map area {(mx0, my0, mx1, my1)} differs from the first frame's "
                               f"{tuple(cfg.locked_map_bbox)}. Frames of one dataset must share crop and size; "
                               "set map_bbox explicitly.")
        mx0, my0, mx1, my1 = cfg.locked_map_bbox
    crop = img_rgb[my0:my1, mx0:mx1]

    values, dist = decode_values(crop, legend.lut_rgb, cfg.tick_table(), cfg.scale, cfg.max_de)

    # Legend overlapping the map (common in EIC frames): blank it out, labels and panel included.
    lx0, ly0, lx1, ly1 = legend.bbox
    bl, bt, br, bb = cfg.legend_blank or ((14, 8, 14, 56) if legend.orientation == "h" else (8, 14, 72, 14))
    ox0, oy0 = max(lx0 - bl - mx0, 0), max(ly0 - bt - my0, 0)
    ox1, oy1 = min(lx1 + br - mx0, crop.shape[1]), min(ly1 + bb - my0, crop.shape[0])
    overlapped = in_frame and (lx1 > mx0 and lx0 < mx1 and ly1 > my0 and ly0 < my1)
    if overlapped and ox1 > ox0 and oy1 > oy0:
        values[oy0:oy1, ox0:ox1] = np.nan

    raw_valid = float((~np.isnan(values)).mean())
    values = fill_thin_gaps(values, cfg.fill_gap_px)

    h, w = values.shape
    rows = cfg.grid_rows or max(1, round(cfg.grid_cols * h / w))
    grid = to_grid(values, rows, cfg.grid_cols, cfg.min_valid)

    ok = dist < cfg.max_de
    diag = dict(
        legend_bbox=legend.bbox,
        legend_overlaps_map=bool(overlapped),
        legend_from_separate_image=not in_frame,
        legend_orientation=legend.orientation,
        lut=legend.stats(),
        map_bbox=(mx0, my0, mx1, my1),
        pixel_valid_fraction=raw_valid,
        grid_valid_fraction=float((~np.isnan(grid)).mean()),
        mean_de=float(dist[ok].mean()) if ok.any() else float("nan"),
        p95_de=float(np.percentile(dist[ok], 95)) if ok.any() else float("nan"),
        grid_shape=grid.shape,
        value_range=(float(np.nanmin(grid)), float(np.nanmax(grid))) if (~np.isnan(grid)).any()
        else (float("nan"), float("nan")),
    )
    diag["warnings"] = _warnings(diag, cfg)
    return ExtractResult(grid, legend, (mx0, my0, mx1, my1), diag, values if keep_pixels else None)


def _warnings(d, cfg) -> list[str]:
    w = []
    if d.get("legend_overlaps_map"):
        w.append("Legend overlaps the map; its box (with labels) was blanked. Check the debug overlay: if "
                 "a legend background panel is still visible, widen it with legend_blank=(l,t,r,b) pixels.")
    if d["lut"]["max_step_de"] > 12:
        w.append("Legend has a big colour jump (banded legend, or a tick/label inside the bar). "
                 "Check the debug overlay; consider a manual legend_bbox.")
    if d["mean_de"] > 4:
        w.append("Decoded colours are far from the legend on average (mean ΔE>4): wrong legend "
                 "region, heavy compression, or the map uses a different palette than the legend.")
    mx0, my0, mx1, my1 = d["map_bbox"]
    e = cfg.extent
    want = (e[2] - e[0]) / (e[3] - e[1])
    got = (mx1 - mx0) / max(my1 - my0, 1)
    if abs(got / want - 1) > 0.2:
        w.append(f"Detected map is {got:.2f}:1 but extent {tuple(e)} implies {want:.2f}:1. Probably a wrong "
                 "crop (or the map is not equirectangular). Check the debug overlay and pass map_bbox.")
    if d["pixel_valid_fraction"] < 0.35:
        w.append("Under 35% of map pixels matched the legend. Raise max_de or check legend/map boxes.")
    lo, hi = d["value_range"]
    if np.isfinite(lo) and (lo < cfg.vmin - 0.05 * abs(cfg.vmax - cfg.vmin)
                            or hi > cfg.vmax + 0.05 * abs(cfg.vmax - cfg.vmin)):
        w.append("Decoded values fall outside vmin/vmax: legend orientation may be reversed "
                 "(try reverse_legend=True) or ticks are wrong.")
    return w


# --------------------------------------------------------------------------
def debug_overlay(img_rgb: np.ndarray, res: ExtractResult, path: str) -> None:
    """Save the frame with legend (magenta) and map (cyan) boxes + decoded preview side by side."""
    im = Image.fromarray(img_rgb).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle(res.legend.bbox, outline=(255, 0, 255), width=3)
    d.rectangle(res.map_bbox, outline=(0, 200, 255), width=3)
    # re-encode the decoded grid with the legend LUT as a visual round trip
    lut = res.legend.lut_rgb
    g = res.grid
    lo, hi = np.nanmin(g), np.nanmax(g)
    # grid -> colours via LUT using the same fraction logic is approximate: use min/max span
    idx = np.clip(((g - lo) / max(hi - lo, 1e-9) * (len(lut) - 1)), 0, len(lut) - 1)
    prev = np.where(np.isnan(g)[..., None], 128, lut[np.nan_to_num(idx).astype(int)]).astype(np.uint8)
    prev_im = Image.fromarray(prev).resize((im.width // 2, int(im.width // 2 * g.shape[0] / g.shape[1])),
                                           Image.NEAREST)
    canvas = Image.new("RGB", (im.width + prev_im.width + 10, max(im.height, prev_im.height)), "white")
    canvas.paste(im, (0, 0))
    canvas.paste(prev_im, (im.width + 10, 0))
    canvas.save(path)
