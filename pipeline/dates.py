"""Replace 'seconds into the video' frame labels with real times (datasets/real/dates.json) or 'Frame k of n'.

Run:  python -m pipeline.dates      (safe to repeat; remembers each frame's original seconds)
"""
import json, os, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "static", "data")
DATES = os.path.join(ROOT, "datasets", "real", "dates.json")


def seconds_of(f):
    if "seconds" in f:
        return float(f["seconds"])
    m = re.match(r"\s*([\d.]+)\s*s", f["label"])
    return float(m.group(1)) if m else None


def label_for(frac, entry):
    a, b = datetime.fromisoformat(entry["start"]), datetime.fromisoformat(entry["end"])
    t = a + (b - a) * frac
    return ("~" if entry.get("approx") else "") + t.strftime(entry.get("format", "%d %b %Y"))


def relabel(ds, table):
    secs = [seconds_of(f) for f in ds["frames"]]
    if None in secs:
        return False
    for f, s in zip(ds["frames"], secs):
        f["seconds"] = s
    entry, n = table.get(ds["id"]), len(secs)
    span = (max(secs) - min(secs)) or 1.0
    for i, f in enumerate(ds["frames"]):
        f["label"] = label_for((secs[i] - min(secs)) / span, entry) if entry else f"Frame {i + 1} of {n}"
        if i < len(ds.get("diagnostics", [])):
            ds["diagnostics"][i]["label"] = f["label"]
    return True


if __name__ == "__main__":
    table = json.load(open(DATES, encoding="utf-8")) if os.path.exists(DATES) else {}
    ip = os.path.join(DATA, "index.json")
    idx = json.load(open(ip, encoding="utf-8"))
    for ds in idx["datasets"]:
        if relabel(ds, table):
            print(f"  {ds['id']:34s} {ds['frames'][0]['label']}  ->  {ds['frames'][-1]['label']}")
    json.dump(idx, open(ip, "w", encoding="utf-8"), indent=1)
