"""Score the extractor against synthetic ground truth.

Error is measured in *normalised legend units*: |Δvalue| / (vmax - vmin) for
linear bars, |Δlog10| / log10(vmax/vmin) for log bars. So "1.0%" means the same
thing for every dataset: one percent of the colorbar's span.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import synth
from .extract import ExtractConfig, extract


@dataclass
class Scenario:
    name: str
    kind: str = "anomaly"
    cmap: str = "RdBu_r"
    norm: str = "linear"
    orientation: str = "h"
    interpolation: str = "nearest"
    jpeg: int | None = None
    map_px: tuple = (900, 450)
    coastlines: bool = True
    text: bool = True
    graticule: bool = True
    max_mae: float = 0.015       # pass thresholds (fraction of colorbar span)
    max_p95: float = 0.06
    min_coverage: float = 0.93


def resample_truth(truth: np.ndarray, rows: int, cols: int, scale: str):
    """Block-average truth to the decoded grid; also return a 'pure cell' mask
    (cells whose block is entirely valid) so coastline-mixed cells are not scored."""
    t = np.log10(truth) if scale == "log" else truth
    valid = (~np.isnan(t)).astype(np.float32)
    filled = np.where(np.isnan(t), 0, t).astype(np.float32)
    num = cv2.resize(filled, (cols, rows), interpolation=cv2.INTER_AREA)
    den = cv2.resize(valid, (cols, rows), interpolation=cv2.INTER_AREA)
    pure = den > 0.999
    mixed = den < 0.001                       # entirely nodata
    out = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
    return out, pure, mixed


def score(frame: synth.SynthFrame, grid: np.ndarray) -> dict:
    rows, cols = grid.shape
    tr, pure, nodata = resample_truth(frame.truth, rows, cols, frame.scale)
    est = np.log10(grid) if frame.scale == "log" else grid
    span = (np.log10(frame.vmax / frame.vmin) if frame.scale == "log" else frame.vmax - frame.vmin)

    # shrink 'pure' by one cell so cells touching a coastline are excluded
    pure_eroded = cv2.erode(pure.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    both = pure_eroded & ~np.isnan(est)
    err = np.abs(est[both] - tr[both]) / span
    covered = float((~np.isnan(est[pure_eroded])).mean()) if pure_eroded.any() else 0.0
    false_valid = float((~np.isnan(est[nodata])).mean()) if nodata.any() else 0.0
    return dict(
        mae=float(err.mean()), p95=float(np.percentile(err, 95)), max=float(err.max()),
        coverage=covered, false_valid=false_valid, n=int(both.sum()),
    )


def run_scenario(sc: Scenario, grid_cols: int | None = None) -> dict:
    truth, vmin, vmax = synth.make_field(sc.kind)
    frame = synth.render_frame(
        truth, vmin=vmin, vmax=vmax, cmap=sc.cmap, norm=sc.norm, orientation=sc.orientation,
        interpolation=sc.interpolation, jpeg_quality=sc.jpeg, map_px=sc.map_px,
        coastlines=sc.coastlines, text=sc.text, graticule=sc.graticule)
    cfg = ExtractConfig(vmin=vmin, vmax=vmax, ticks=frame.ticks, scale=frame.scale,
                        grid_cols=grid_cols or truth.shape[1] // 2)
    t0 = time.time()
    res = extract(frame.image, cfg)
    dt = time.time() - t0
    m = score(frame, res.grid)
    m.update(name=sc.name, seconds=dt, warnings=res.diagnostics["warnings"],
             mean_de=res.diagnostics["mean_de"])
    m["passed"] = (m["mae"] <= sc.max_mae and m["p95"] <= sc.max_p95
                   and m["coverage"] >= sc.min_coverage and m["false_valid"] <= 0.10)
    return m


def default_scenarios() -> list[Scenario]:
    return [
        Scenario("baseline RdBu horizontal"),
        Scenario("vertical bar", orientation="v"),
        Scenario("viridis", cmap="viridis"),
        Scenario("jet (rainbow)", cmap="jet"),
        Scenario("turbo", cmap="turbo"),
        Scenario("bilinear antialiasing", interpolation="bilinear", map_px=(877, 433)),
        Scenario("JPEG q=85", jpeg=85),
        Scenario("JPEG q=60", jpeg=60, max_mae=0.02, max_p95=0.08),
        Scenario("asymmetric bar (TwoSlope)", norm="twoslope", cmap="RdBu_r"),
        Scenario("log colourbar", kind="lognormal", cmap="viridis", norm="log"),
        Scenario("sea ice + gray land", kind="fraction", cmap="Blues_r"),
        Scenario("no overlays (clean)", coastlines=False, text=False, graticule=False,
                 max_mae=0.01),
        Scenario("coolwarm vertical + JPEG", cmap="coolwarm", orientation="v", jpeg=80),
    ]


def format_table(results: list[dict]) -> str:
    head = f"{'scenario':32s} {'MAE%':>6s} {'P95%':>6s} {'cover':>6s} {'falseV':>6s} {'ΔE':>5s} {'sec':>5s}  ok"
    lines = [head, "-" * len(head)]
    for r in results:
        lines.append(f"{r['name']:32s} {100*r['mae']:6.2f} {100*r['p95']:6.2f} {r['coverage']:6.2f} "
                     f"{r['false_valid']:6.2f} {r['mean_de']:5.1f} {r['seconds']:5.1f}  "
                     f"{'PASS' if r['passed'] else 'FAIL'}")
    return "\n".join(lines)


def run_suite(scenarios=None) -> list[dict]:
    return [run_scenario(s) for s in (scenarios or default_scenarios())]


if __name__ == "__main__":
    res = run_suite()
    print(format_table(res))
