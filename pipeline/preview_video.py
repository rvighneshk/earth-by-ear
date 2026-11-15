"""Look at a video before importing it: saves a contact sheet of evenly spaced frames with a 10% grid and the time of each,
so you can choose --crop (exclude titles, labels, legends) and --times.

  python -m pipeline.preview_video --video datasets/real/media/atmos-river.mp4
  -> datasets/real/preview/atmos-river.jpg   (open it; grid labels are fractions 0.1 ... 0.9 of width / height)
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

from .import_svs_media import ROOT, open_video


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True)
    ap.add_argument("--n", type=int, default=6, help="number of frames to show")
    ap.add_argument("--proxy", action="store_true")
    a = ap.parse_args()
    cap = open_video(Path(a.video), a.proxy)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = total / fps
    tiles = []
    for i in range(a.n):
        sec = dur * 0.99 * i / max(a.n - 1, 1)
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ok, im = cap.read()
        if not ok:
            continue
        im = cv2.resize(im, (640, int(640 * im.shape[0] / im.shape[1])))
        h, w = im.shape[:2]
        for k in range(1, 10):
            x, y = int(w * k / 10), int(h * k / 10)
            cv2.line(im, (x, 0), (x, h), (255, 255, 255), 1); cv2.line(im, (0, y), (w, y), (255, 255, 255), 1)
            cv2.putText(im, f"{k/10:.1f}", (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 255, 255), 1)
            cv2.putText(im, f"{k/10:.1f}", (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 255, 255), 1)
        cv2.putText(im, f"t = {sec:.1f} s", (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
        tiles.append(im)
    if not tiles:
        raise SystemExit("Could not read any frames.")
    h = min(t.shape[0] for t in tiles)
    tiles = [t[:h] for t in tiles]
    while len(tiles) % 2:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]
    out = ROOT / "datasets" / "real" / "preview" / (Path(a.video).stem + ".jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack(rows), [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    print(f"Saved {out}\nVideo: {dur:.1f} s. Pick the rectangle with the Earth data only, e.g. --crop 0.05,0.12,0.9,0.75 (x,y,width,height).")


if __name__ == "__main__":
    main()
