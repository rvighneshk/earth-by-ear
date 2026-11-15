"""Synthetic EIC-style map frames with KNOWN ground truth.

Real NASA frames have no answer key. These do: we generate a field, render it
through a colormap + colorbar exactly the way a visualization would, and then
the extractor has to recover the field from pixels alone. That gives us a
measurable accuracy number for every nasty case (anti-aliasing, JPEG, text,
coastlines, nodata, non-linear colorbars, vertical/horizontal legends).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

NODATA_GRAY = "#9b9b9b"


@dataclass
class SynthFrame:
    image: np.ndarray                 # H,W,3 uint8
    truth: np.ndarray                 # rows x cols, NaN = nodata
    map_bbox: tuple                   # x0,y0,x1,y1 (pixels, x1/y1 exclusive)
    legend_bbox: tuple                # x0,y0,x1,y1 of the colour band
    vmin: float
    vmax: float
    ticks: list                       # [(bar_fraction, value), ...]
    scale: str                        # 'linear' | 'log'
    orientation: str                  # 'h' | 'v'
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Ground-truth fields
# --------------------------------------------------------------------------
def make_land_mask(rows: int, cols: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = ndi.gaussian_filter(rng.normal(size=(rows, cols)), sigma=rows / 10, mode="wrap")
    return noise > np.quantile(noise, 0.62)


def _blobs(rows, cols, seed, k=7):
    rng = np.random.default_rng(seed)
    lat = np.linspace(90, -90, rows)[:, None]
    lon = np.linspace(-180, 180, cols)[None, :]
    f = np.zeros((rows, cols))
    for _ in range(k):
        la0, lo0 = rng.uniform(-70, 70), rng.uniform(-170, 170)
        sl, sn = rng.uniform(12, 30), rng.uniform(25, 60)
        f += rng.uniform(-1, 1) * np.exp(-(((lat - la0) / sl) ** 2) - (((lon - lo0) / sn) ** 2))
    return f, lat, lon


def make_field(kind: str, rows: int = 90, cols: int = 180, seed: int = 1, shift: float = 0.0):
    """Return (truth, vmin, vmax). `shift` simulates later years (warming, ice loss)."""
    f, lat, lon = _blobs(rows, cols, seed)
    land = make_land_mask(rows, cols)
    if kind == "anomaly":                       # diverging, centred on 0
        f = 2.2 * f / np.abs(f).max()
        f = f + shift * (0.6 + 0.9 * (np.abs(lat) / 90) ** 2)
        # a regional cooling patch (like the real North Atlantic 'warming hole') so the
        # demo has both a biggest rise and a biggest fall to find
        f = f - shift * 2.2 * np.exp(-(((lat - 50) / 12) ** 2) - (((lon + 35) / 22) ** 2))
        return np.clip(f, -3.95, 3.95), -4.0, 4.0
    if kind == "fraction":                      # sequential 0..1, land is nodata
        edge = 62 + 9 * shift
        base = np.clip((np.abs(lat) - edge) / 26, 0, 1) ** 0.8
        base = np.clip(base + 0.12 * f, 0, 1)
        base = np.broadcast_to(base, (rows, cols)).copy()
        base[land] = np.nan
        return base, 0.0, 1.0
    if kind == "lognormal":                     # 0.1..10, log colourbar
        z = (f - f.min()) / (f.max() - f.min())
        z = np.clip(z + 0.25 * shift, 0, 1)
        return 10 ** (-1 + 2 * z * 0.98 + 0.01), 0.1, 10.0
    raise ValueError(kind)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_frame(
    truth: np.ndarray,
    *,
    vmin: float,
    vmax: float,
    cmap: str = "RdBu_r",
    norm: str = "linear",          # linear | twoslope | log
    orientation: str = "h",
    map_px: tuple = (900, 450),
    interpolation: str = "nearest",
    coastlines: bool = True,
    text: bool = True,
    graticule: bool = True,
    jpeg_quality: int | None = None,
    page: str = "white",          # white | dark
    title: str = "Synthetic frame",
    label: str = "units",
    seed: int = 3,
) -> SynthFrame:
    mw, mh = map_px
    ml, mr, mt, mb = 30, 30, 60, 30
    if orientation == "h":
        mb += 110
    else:
        mr += 150
    W, H = ml + mw + mr, mt + mh + mb

    bgc = "white" if page == "white" else "#101418"
    fgc = "black" if page == "white" else "white"
    rc = plt.rc_context({"text.color": fgc, "axes.labelcolor": fgc, "xtick.color": fgc,
                         "ytick.color": fgc, "axes.edgecolor": fgc})
    rc.__enter__()
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=bgc)

    def rect(x, y, w, h):
        return [x / W, 1 - (y + h) / H, w / W, h / H]

    ax = fig.add_axes(rect(ml, mt, mw, mh))
    cmap_obj = plt.get_cmap(cmap).with_extremes(bad=NODATA_GRAY)
    if norm == "linear":
        nrm = mcolors.Normalize(vmin, vmax)
        ticks = [(0.0, vmin), (1.0, vmax)]
        scale = "linear"
    elif norm == "twoslope":
        nrm = mcolors.TwoSlopeNorm(vcenter=0.0, vmin=vmin, vmax=vmax)
        ticks = [(0.0, vmin), (0.5, 0.0), (1.0, vmax)]
        scale = "linear"
    elif norm == "log":
        nrm = mcolors.LogNorm(vmin, vmax)
        ticks = [(0.0, vmin), (1.0, vmax)]
        scale = "log"
    else:
        raise ValueError(norm)

    extent = (-180, 180, -90, 90)
    im = ax.imshow(np.ma.masked_invalid(truth), cmap=cmap_obj, norm=nrm, extent=extent,
                   origin="upper", aspect="auto", interpolation=interpolation)
    if graticule:
        for lo in range(-120, 180, 60):
            ax.axvline(lo, color="white", lw=0.6, alpha=0.55)
        for la in (-60, -30, 0, 30, 60):
            ax.axhline(la, color="white", lw=0.6, alpha=0.55)
    if coastlines:
        land = make_land_mask(*truth.shape, seed=seed)
        ax.contour(land.astype(float), levels=[0.5], colors="k", linewidths=0.8,
                   origin="upper", extent=extent)
    if text:
        ax.text(-172, 80, title, color="black", fontsize=15, fontweight="bold")
        ax.text(120, -80, "NASA-style demo", color="black", fontsize=11)
        if page != "white":
            fig.text(0.03, 0.965, title, color=fgc, fontsize=14)
    ax.set_axis_off()

    if orientation == "h":
        cax = fig.add_axes(rect(ml + mw * 0.2, mt + mh + 40, mw * 0.6, 22))
    else:
        cax = fig.add_axes(rect(ml + mw + 45, mt + mh * 0.1, 22, mh * 0.8))
    cb = fig.colorbar(im, cax=cax, orientation="horizontal" if orientation == "h" else "vertical")
    cb.set_label(label, fontsize=11)

    fig.canvas.draw()
    bb = ax.get_window_extent()
    map_bbox = (int(round(bb.x0)), int(round(H - bb.y1)), int(round(bb.x1)), int(round(H - bb.y0)))
    cb_bb = cax.get_window_extent()
    legend_bbox = (int(round(cb_bb.x0)), int(round(H - cb_bb.y1)),
                   int(round(cb_bb.x1)), int(round(H - cb_bb.y0)))

    buf = io.BytesIO()
    fig.savefig(buf, dpi=100, format="png", facecolor=bgc)
    plt.close(fig)
    rc.__exit__(None, None, None)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    # Matplotlib can round figsize*dpi one pixel short/long on some backends.
    # Keep the synthetic frame and all pixel-space bounding boxes on one exact grid.
    if img.size != (W, H):
        img = img.resize((W, H), Image.Resampling.BILINEAR)
    if jpeg_quality:
        jb = io.BytesIO()
        img.save(jb, "JPEG", quality=jpeg_quality)
        jb.seek(0)
        img = Image.open(jb).convert("RGB")
    arr = np.asarray(img)
    assert arr.shape[:2] == (H, W), (arr.shape, H, W)

    return SynthFrame(arr, truth, map_bbox, legend_bbox, vmin, vmax, ticks, scale, orientation,
                      meta=dict(cmap=cmap, norm=norm, interpolation=interpolation,
                                jpeg=jpeg_quality, page=page))


def overlay_legend_full_bleed(frame: SynthFrame, corner: str = "bl", pad: int = 14) -> SynthFrame:
    """Real EIC-style layout: the map fills the whole image and the colorbar (with its labels)
    is pasted ON TOP of it, bottom-left. Returns a new frame with updated geometry."""
    img = frame.image
    mx0, my0, mx1, my1 = frame.map_bbox
    base = img[my0:my1, mx0:mx1].copy()
    lx0, ly0, lx1, ly1 = frame.legend_bbox
    if frame.orientation == "h":
        patch = img[ly0 - 6: ly1 + 52, lx0 - 12: lx1 + 12].copy()
    else:
        patch = img[ly0 - 12: ly1 + 12, lx0 - 6: lx1 + 70].copy()
    ph, pw = patch.shape[:2]
    H, W = base.shape[:2]
    y = H - ph - pad
    x = pad if corner == "bl" else W - pw - pad
    base[y:y + ph, x:x + pw] = patch
    off_y = (ly0 - (ly0 - 6 if frame.orientation == "h" else ly0 - 12))
    off_x = (lx0 - (lx0 - 12 if frame.orientation == "h" else lx0 - 6))
    new_legend = (x + off_x, y + off_y, x + off_x + (lx1 - lx0), y + off_y + (ly1 - ly0))
    return SynthFrame(base, frame.truth, (0, 0, W, H), new_legend, frame.vmin, frame.vmax,
                      frame.ticks, frame.scale, frame.orientation, meta=dict(frame.meta, full_bleed=True))


def save_png(frame: SynthFrame, path: str) -> None:
    Image.fromarray(frame.image).save(path)
