"""Check the finished project: are all 9 sources in, do they have data, voices, audio? Prints a table, exits 1 on problems.

  python -m pipeline.check
"""
import json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "static", "data")
STATIC = os.path.join(ROOT, "app", "static")


def main():
    cat = json.load(open(os.path.join(ROOT, "datasets", "real", "nasa_svs_catalog.json"), encoding="utf-8"))["resources"]
    expected = [r["id"] for r in cat if r["sonification_type"] != "sonification inspiration"]   # Caldwell 73 is reference only
    idx = {d["id"]: d for d in json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))["datasets"]}
    problems, voices, warns = [], {}, []
    print(f"{'dataset':32s} frames valid%  spread geometry value  voice                      audio")
    for sid in expected:
        d = idx.get(sid)
        if not d:
            print(f"{sid:32s} MISSING"); problems.append(f"{sid}: not imported (python -m pipeline.import_all --list)"); continue
        vals, ok = [], True
        for f in d["frames"]:
            for rel in (f["url"], f["image"]):
                if not os.path.exists(os.path.join(DATA, rel)):
                    problems.append(f"{sid}: missing file {rel}"); ok = False
            if os.path.exists(os.path.join(DATA, f["url"])):
                vals += [v for v in json.load(open(os.path.join(DATA, f["url"])))["data"] if v is not None]
        grids = []
        for f in d["frames"]:
            if os.path.exists(os.path.join(DATA, f["url"])):
                gj = json.load(open(os.path.join(DATA, f["url"])))
                grids.append(np.array([np.nan if v is None else v for v in gj["data"]], float))
        for i, g in enumerate(grids):                                   # a frame with no picture in it
            if np.nanstd(g) < 3 if (~np.isnan(g)).any() else True:
                warns.append(f"{sid}: frame {i} ({d['frames'][i]['label']}) looks blank. Remove it: python -m pipeline.drop_frames --id {sid} --frames {i}")
        if len(grids) >= 5:                                            # a frame unlike all the others (title card, logo)
            dist = [np.nanmean([np.nanmean(np.abs(a - b)) for j, b in enumerate(grids) if j != i]) for i, a in enumerate(grids)]
            med = float(np.median(dist))
            for i, dv in enumerate(dist):
                if med > 0 and dv > 2.5 * med and dv > 8:
                    warns.append(f"{sid}: frame {i} ({d['frames'][i]['label']}) is very different from the rest: a logo or title? Look at app/static/data/{d['frames'][i]['image']}, then python -m pipeline.drop_frames --id {sid} --frames {i}")
        valid = np.array(vals, float)
        n_all = sum(json.load(open(os.path.join(DATA, f["url"])))["rows"] * json.load(open(os.path.join(DATA, f["url"])))["cols"]
                    for f in d["frames"] if os.path.exists(os.path.join(DATA, f["url"]))) or 1
        frac = len(valid) / n_all
        spread = float(np.percentile(valid, 95) - np.percentile(valid, 5)) if len(valid) else 0.0
        s = d["sonification"]; voice = f"{s['scale']}/{s['root']}/{s.get('wave', '-')}"
        a = d.get("audio"); aud = "none"
        if a and os.path.exists(os.path.join(STATIC, a["file"])) and os.path.getsize(os.path.join(STATIC, a["file"])) > 20000:
            aud = f"{a['seconds']:.0f}s"
        else:
            problems.append(f"{sid}: no audio file (run python -m pipeline.finish)")
        if len(d["frames"]) < 5 and sid != "eic-geos-aerosols": problems.append(f"{sid}: only {len(d['frames'])} frames (video shorter than --times? see sources.json)")
        if frac < 0.05: problems.append(f"{sid}: only {frac:.0%} of cells have data; check the crop")
        if spread < 3 and len(vals): problems.append(f"{sid}: values barely vary (spread {spread:.1f}); the crop may cover only background")
        if voice in voices: problems.append(f"{sid}: same voice as {voices[voice]}")
        voices[voice] = sid
        print(f"{sid:32s} {len(d['frames']):6d} {frac*100:5.0f}% {spread:7.1f} {d.get('geometry','?'):8s} {d.get('valueSource','bright'):6s} {voice:26s} {aud}")
    print()
    if warns:
        print("CHECK THESE FRAMES (warnings, not errors):"); [print("  -", w) for w in warns]; print()
    if problems:
        print("PROBLEMS:"); [print("  -", p) for p in problems]; sys.exit(1)
    print(f"All {len(expected)} sources are in and look healthy.")


if __name__ == "__main__":
    main()
