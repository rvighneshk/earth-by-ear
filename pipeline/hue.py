"""Colour-ramp values for datasets whose colour IS the data (sea-surface temperature: blue = cold ... red = warm).

Grayscale brightness is a poor stand-in for a rainbow colour map (yellow is brighter than red, so 'brighter' does not mean
'warmer'). Here each coloured pixel's HUE is placed along the blue -> red ramp (0 = coldest colour, 100 = warmest colour).
Grey land, black background and white streamline highlights have no hue and become silence.
Still a RELATIVE value read from a picture, not degrees Celsius.   Run:  python -m pipeline.hue
"""
import json, os
import cv2
import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "data")
RAMP = ["#08306b", "#2171b5", "#41b6c4", "#7fcdbb", "#addd8e", "#ffeda0", "#fd8d3c", "#e31a1c"]
HUE_DATASETS = ("eic-ocean-current-temperature",)


def hue_values(bgr, min_sat=70, min_val=60):
    """BGR image -> float array, 0 (blue) .. 100 (red), NaN where there is no clear colour."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    deg = hsv[..., 0].astype(np.float32) * 2.0
    ok = (hsv[..., 1] >= min_sat) & (hsv[..., 2] >= min_val) & (deg <= 250)
    return np.where(ok, (250.0 - deg) / 250.0 * 100.0, np.nan)


def to_grid(vals, rows, cols, min_frac=0.12):
    """Mean of coloured pixels per cell; cells that are mostly colourless become NaN."""
    z = np.nan_to_num(vals, nan=0.0).astype(np.float32)
    m = (~np.isnan(vals)).astype(np.float32)
    s = cv2.resize(z, (cols, rows), interpolation=cv2.INTER_AREA)
    f = cv2.resize(m, (cols, rows), interpolation=cv2.INTER_AREA)
    return np.where(f >= min_frac, s / np.maximum(f, 1e-6), np.nan)


def apply(ds):
    for k, fr in enumerate(ds["frames"]):
        p = os.path.join(DATA, fr["url"])
        g = json.load(open(p))
        grid = to_grid(hue_values(cv2.imread(os.path.join(DATA, fr["image"]))), g["rows"], g["cols"])
        g["data"] = [None if np.isnan(v) else round(float(v), 2) for v in grid.ravel()]
        json.dump(g, open(p, "w"), separators=(",", ":"))
        ds["diagnostics"][k].update(grid_valid=round(float((~np.isnan(grid)).mean()), 3),
                                    warnings=["Relative position along the blue-to-red colour ramp; not calibrated degrees."])
    ds.update(unit="% along cold-to-warm ramp", palette=RAMP, valueSource="hue")
    ds["sonification"].update(positiveWord="warmer", negativeWord="cooler")
    ds["description"] = (ds["description"].split(" Visual sonification:")[0]
                         + " Visual sonification: each pixel's hue is placed along the blue-to-red temperature colour ramp "
                           "(0 = coldest colour, 100 = warmest). Grey land is silent. Relative, not calibrated degrees.")


if __name__ == "__main__":
    ip = os.path.join(DATA, "index.json")
    idx = json.load(open(ip, encoding="utf-8"))
    for ds in idx["datasets"]:
        if ds["id"] in HUE_DATASETS and ds.get("valueSource") != "hue":
            apply(ds)
            print("hue values applied to", ds["id"])
    json.dump(idx, open(ip, "w", encoding="utf-8"), indent=1)
