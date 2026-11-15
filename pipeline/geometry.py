"""Decide whether each dataset is a flat map, a globe, or a camera view, and fix the sonification accordingly.

  map    flat lat/lon picture: positions are reported as latitude / longitude.
  globe  round Earth on black: sky, date stamps and colorbars outside the globe become silence;
         positions are reported inside the frame ("upper left of the view").
  view   camera / 3-D scene: positions inside the frame, no masking.

Known datasets are listed in datasets/real/geometry.json. New ones are auto-detected and the decision is printed;
add the id to that file to override.   Run:  python -m pipeline.geometry
"""
import json, os
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "static", "data")
OVERRIDES = os.path.join(ROOT, "datasets", "real", "geometry.json")


def _union_blob(ds):
    """Union over frames of the biggest 'not sky' blob. Returns (mask, (H, W))."""
    acc = None
    for f in ds["frames"]:
        im = cv2.imread(os.path.join(DATA, f["image"]))
        bright = (im.max(axis=2) > 28).astype(np.uint8)
        bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(bright)
        if n < 2:
            continue
        k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        m = (lab == k).astype(np.uint8)
        acc = m if acc is None else np.maximum(acc, m)
    return acc, im.shape[:2]


def classify(ds):
    """Heuristic for datasets not in geometry.json: ellipse-shaped blob on dark sky = globe; dark frame = view; else map."""
    acc, (H, W) = _union_blob(ds)
    if acc is None:
        return "view"
    x, y, w, h = cv2.boundingRect(acc)
    fill = acc.sum() / max(np.pi / 4 * w * h, 1)
    if w < 0.9 * W and 0.75 <= fill <= 1.1 and acc.sum() > 0.12 * H * W:
        return "globe"
    return "map" if acc.sum() > 0.6 * H * W else "view"


def apply_mask(ds):
    acc, (H, W) = _union_blob(ds)
    x, y, w, h = cv2.boundingRect(acc)
    mask = np.zeros((H, W), np.uint8)
    cv2.ellipse(mask, (int(x + w / 2), int(y + h / 2)), (int(w / 2 * 0.97), int(h / 2 * 0.97)), 0, 0, 360, 1, -1)
    for f in ds["frames"]:
        p = os.path.join(DATA, f["url"])
        g = json.load(open(p))
        m = cv2.resize(mask, (g["cols"], g["rows"]), interpolation=cv2.INTER_AREA) > 0.5
        vals = np.array(g["data"], dtype=object).reshape(g["rows"], g["cols"])
        vals[~m] = None
        g["data"] = vals.ravel().tolist()
        json.dump(g, open(p, "w"), separators=(",", ":"))


def kind_of(ds, table):
    for kind in ("map", "globe", "view"):
        if ds["id"] in table.get(kind, []):
            return kind, "listed"
    return classify(ds), "auto-detected"


if __name__ == "__main__":
    table = json.load(open(OVERRIDES, encoding="utf-8")) if os.path.exists(OVERRIDES) else {}
    ip = os.path.join(DATA, "index.json")
    idx = json.load(open(ip, encoding="utf-8"))
    for ds in idx["datasets"]:
        kind, how = kind_of(ds, table)
        ds["geometry"] = "map" if kind == "map" else "view"
        if kind == "globe" and not ds.get("globeMasked"):
            apply_mask(ds)
            ds["globeMasked"] = True
        if ds.get("globeMasked") and "Grey area" not in ds["description"]:
            ds["description"] += " Grey area = outside the globe: no data, so it is silent."
        print(f"  {ds['id']:34s} {kind:6s} ({how})")
    json.dump(idx, open(ip, "w", encoding="utf-8"), indent=1)
