"""Remove bad frames (a logo, a title card, a blank or half-faded frame) from a dataset without re-importing it.

  python -m pipeline.drop_frames --id eic-atmospheric-river --list        # shows each frame: number, time, how much picture it has
  python -m pipeline.drop_frames --id eic-atmospheric-river --frames 0    # drops frame number 0 (numbers as shown by --list)
  python -m pipeline.finish                                               # then rebuild sound, audio and website
Look at app/static/data/<id>/NN.jpg to see what a frame looks like.
"""
import argparse, json, os, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "static", "data")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True); ap.add_argument("--list", action="store_true"); ap.add_argument("--frames", type=int, nargs="*", default=[])
    a = ap.parse_args()
    ip = os.path.join(DATA, "index.json")
    idx = json.load(open(ip, encoding="utf-8"))
    ds = next((d for d in idx["datasets"] if d["id"] == a.id), None)
    if ds is None:
        sys.exit(f"No dataset {a.id}. Have: {', '.join(d['id'] for d in idx['datasets'])}")
    if a.list or not a.frames:
        print(f"{'#':>3} {'label':22s} {'valid':>6} {'detail':>7}  image")
        for i, f in enumerate(ds["frames"]):
            vals = np.array([v for v in json.load(open(os.path.join(DATA, f["url"])))["data"] if v is not None], float)
            print(f"{i:3d} {f['label']:22s} {len(vals) / max(1, len(json.load(open(os.path.join(DATA, f['url'])))['data'])):6.0%} {vals.std() if len(vals) else 0:7.1f}  app/static/data/{f['image']}")
        return
    bad = sorted(set(a.frames))
    if any(i < 0 or i >= len(ds["frames"]) for i in bad):
        sys.exit(f"Frame numbers must be 0..{len(ds['frames']) - 1}")
    if len(bad) >= len(ds["frames"]):
        sys.exit("That would remove every frame.")
    keep = [i for i in range(len(ds["frames"])) if i not in bad]
    for i in bad:
        for k in ("url", "image"):
            p = os.path.join(DATA, ds["frames"][i][k])
            if os.path.exists(p): os.remove(p)
    ds["frames"] = [ds["frames"][i] for i in keep]
    if ds.get("diagnostics"):
        ds["diagnostics"] = [ds["diagnostics"][i] for i in keep if i < len(ds["diagnostics"])]
    json.dump(idx, open(ip, "w", encoding="utf-8"), indent=1)
    print(f"Dropped frame(s) {bad}; {len(ds['frames'])} left. Now run: python -m pipeline.finish")


if __name__ == "__main__":
    main()
