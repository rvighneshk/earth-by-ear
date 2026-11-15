"""Pull still frames out of a downloaded video (SVS offers MP4s of 7-150 MB; the frame sets are
thousands of files). Uses OpenCV only, no ffmpeg needed.

  python -m pipeline.build frames video.mp4 --times 0,50%,99% --out datasets/real --prefix nightlights
"""
from __future__ import annotations

import os

import cv2


def parse_times(spec: str) -> list[str]:
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ValueError("no times given")
    for p in parts:
        float(p[:-1] if p.endswith("%") else p)       # raises ValueError on junk
    return parts


def video_info(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(
            f"cannot open video: {path}. Check the path. If the file exists, your OpenCV build may not "
            "decode this codec (SVS MP4s are H.265). Use ffmpeg instead: "
            "ffmpeg -i video.mp4 -vf fps=1/5 -q:v 2 datasets/real/still_%03d.png")
    info = dict(fps=cap.get(cv2.CAP_PROP_FPS), frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    info["seconds"] = info["frames"] / info["fps"] if info["fps"] else 0.0
    cap.release()
    return info


def extract_frames(video: str, times: list[str], out_dir: str, prefix: str = "frame",
                   scale: float = 1.0) -> list[str]:
    """times: seconds ('12.5') or percentages of the video ('50%'). Returns written PNG paths.
    scale < 1 shrinks each still (0.5 halves width and height): faster, lighter, plenty for a
    180-column grid. All coordinates you use later refer to the SAVED (scaled) stills."""
    info = video_info(video)
    if info["frames"] <= 0:
        raise ValueError("video reports zero frames")
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video)
    written = []
    for t in times:
        if t.endswith("%"):
            idx = round(float(t[:-1]) / 100 * (info["frames"] - 1))
            label = f"p{float(t[:-1]):g}"
        else:
            idx = round(float(t) * info["fps"])
            label = f"t{float(t):g}s"
        idx = max(0, min(info["frames"] - 1, idx))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"could not read frame {idx} at {t}")
        if scale != 1.0:
            frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        path = os.path.join(out_dir, f"{prefix}_{label}.png")
        cv2.imwrite(path, frame)
        written.append(path)
    cap.release()
    return written


def contact_sheet(paths: list[str], out_path: str, thumb_w: int = 760, cols: int = 2) -> str:
    """One picture showing every still (with its file name), so you can see the whole video at a glance."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=22)
    thumbs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im = im.resize((thumb_w, max(1, round(im.height * thumb_w / im.width))), Image.LANCZOS)
        thumbs.append((os.path.basename(p), im))
    cell_h = max(im.height for _, im in thumbs) + 34
    rows = -(-len(thumbs) // cols)
    sheet = Image.new("RGB", (cols * (thumb_w + 12) + 12, rows * (cell_h + 12) + 12), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(thumbs):
        x, y = 12 + (i % cols) * (thumb_w + 12), 12 + (i // cols) * (cell_h + 12)
        d.text((x, y), name, fill=(255, 255, 255), font=font)
        sheet.paste(im, (x, y + 32))
    sheet.save(out_path)
    return out_path


def ruler(image_path: str, out_path: str, step: int = 200, max_w: int = 1900) -> dict:
    """Draw a labelled coordinate grid (in ORIGINAL pixels) so you can read off the map and legend
    boxes with your eyes. Returns the downscale factor used for the picture."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(image_path).convert("RGB")
    k = min(1.0, max_w / im.width)
    view = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    d = ImageDraw.Draw(view)
    font = ImageFont.load_default(size=16)
    for x in range(0, im.width, step):
        X = round(x * k)
        d.line([(X, 0), (X, view.height)], fill=(255, 255, 0), width=1)
        d.text((X + 3, 3), str(x), fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    for y in range(0, im.height, step):
        Y = round(y * k)
        d.line([(0, Y), (view.width, Y)], fill=(0, 255, 255), width=1)
        d.text((3, Y + 3), str(y), fill=(0, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    view.save(out_path)
    return dict(original=(im.width, im.height), shown=view.size, scale=k, step=step)
