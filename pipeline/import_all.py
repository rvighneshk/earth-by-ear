"""Import all nine sources in one go, then finish (geometry, colour values, voices, dates, audio, website, checks).

  1. Save the NASA downloads in datasets/real/media/  (a still image is fine for GEOS Aerosols)
  2. python -m pipeline.import_all --list        shows which file would be used for which dataset (nothing is changed)
  3. python -m pipeline.import_all               imports everything it can find, then runs `pipeline.finish`
Options: --only eic-air-quality eic-gedi-forest-height   re-import just these
         --no-finish   skip the finishing steps     --proxy   convert every video to a small H.264 copy first
Settings (crop, frame times, palette) are in datasets/real/sources.json.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

from .import_svs_media import CATALOG, MEDIA, IMAGE_EXT, ingest, parse_crop

SOURCES = Path(__file__).resolve().parents[1] / "datasets" / "real" / "sources.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".mpg", ".mpeg"}
norm = lambda s: re.sub(r"[\s_.]+", "-", s.lower())


def find_media():
    return sorted(p for p in MEDIA.glob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT) if MEDIA.exists() else []


def match(sources, files):
    """Best unique file per source: exact name (id or id without 'eic-') beats keyword hits. A file is used once."""
    scores = []
    for s in sources:
        for f in files:
            stem = norm(f.stem)
            sc = sum(k in stem for k in s["keywords"]) + (10 if stem in (s["id"], s["id"].replace("eic-", "")) else 0)
            if sc:
                scores.append((sc, s["id"], f))
    chosen, used = {}, set()
    for sc, sid, f in sorted(scores, key=lambda t: -t[0]):
        if sid not in chosen and f not in used:
            chosen[sid] = f; used.add(f)
    return chosen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true"); ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-finish", action="store_true"); ap.add_argument("--proxy", action="store_true")
    a = ap.parse_args()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    catalog = {r["id"]: r for r in json.loads(CATALOG.read_text(encoding="utf-8"))["resources"]}
    if a.only:
        sources = [s for s in sources if s["id"] in a.only]
    files = find_media()
    chosen = match(sources, files)
    print(f"Media folder: {MEDIA}  ({len(files)} files)\n")
    for s in sources:
        f = chosen.get(s["id"])
        print(f"  {s['id']:32s} {'<- ' + f.name if f else 'MISSING  download: ' + catalog[s['id']]['url'] + '  save as media/' + s['id'] + '.mp4'}")
    unused = [f.name for f in files if f not in chosen.values()]
    if unused:
        print("\n  Files not matched to any source:", ", ".join(unused))
    if a.list:
        return
    done, failed = [], []
    for s in sources:
        f = chosen.get(s["id"])
        if not f:
            continue
        print(f"\n=== {s['id']}")
        times = [float(x) for x in s["times"].split(",")] if s.get("times") else None
        try:
            ingest(f, s["id"], None, "relative brightness", times, parse_crop(s["crop"]) if s.get("crop") else (0, 0, 1, 1),
                   45, 90, s.get("palette", "viridis"), a.proxy or s.get("proxy", False), s.get("skip_start", 0.0), s.get("skip_end", 0.0))
            done.append(s["id"])
        except Exception as e:                                   # keep going; report at the end
            print(f"  FAILED: {e}"); failed.append((s["id"], str(e)))
    print(f"\nImported {len(done)}; failed {len(failed)}; missing {len(sources) - len(chosen)}.")
    for sid, err in failed:
        print(f"  {sid}: {err[:200]}")
    if done and not a.no_finish:
        subprocess.run([sys.executable, "-m", "pipeline.finish"], check=True)


if __name__ == "__main__":
    main()
