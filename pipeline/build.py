"""Command line for the whole pipeline.

  python -m pipeline.build demo                 # make stand-in frames + manifest
  python -m pipeline.build build                # manifest -> app/static/data
  python -m pipeline.build build --manifest datasets/real/datasets.json
  python -m pipeline.build detect frame.png     # where does it see legend & map?
  python -m pipeline.build selftest             # accuracy table on synthetic frames
  python -m pipeline.build audio                # render WAV fallback files into out/audio
  python -m pipeline.build frames video.mp4 --times 0,50%,99% --prefix name [--scale 0.5]   # stills + contact sheet
  python -m pipeline.build ruler still.png      # coordinate grid to read map/legend boxes by eye
  python -m pipeline.build static               # self-contained site in docs/ (public hosting)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

import numpy as np

from .extract import ExtractConfig, debug_overlay, extract, load_image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(ROOT, "datasets", "real", "datasets.json")
OUT_DATA = os.path.join(ROOT, "app", "static", "data")


# --------------------------------------------------------------------------
def build(manifest_path: str = DEFAULT_MANIFEST, out_dir: str = OUT_DATA, verbose: bool = True) -> dict:
    with open(manifest_path) as f:
        manifest = json.load(f)
    os.makedirs(out_dir, exist_ok=True)
    index = {"datasets": []}
    for ds in manifest["datasets"]:
        ex = dict(ds["extract"])
        ex["ticks"] = [tuple(t) for t in ex["ticks"]] if ex.get("ticks") else None
        if ex.get("legend_image") and not os.path.isabs(ex["legend_image"]):
            ex["legend_image"] = os.path.join(ROOT, ex["legend_image"])
        for k in ("legend_bbox", "map_bbox", "extent"):
            if ex.get(k):
                ex[k] = tuple(ex[k])
        cfg = ExtractConfig(**ex)
        ds_dir = os.path.join(out_dir, ds["id"])
        os.makedirs(ds_dir, exist_ok=True)
        frames_out, diags, shape, palette = [], [], None, None
        locked = None
        for fr in ds["frames"]:
            img_path = fr["image"] if os.path.isabs(fr["image"]) else os.path.join(ROOT, fr["image"])
            img = load_image(img_path)
            res = extract(img, dataclasses.replace(cfg, locked_map_bbox=locked) if locked else cfg)
            locked = locked or res.map_bbox
            if shape is None:
                shape, palette = res.grid.shape, _hex_palette(res.legend.lut_rgb)
            elif res.grid.shape != shape:
                raise RuntimeError(f"{ds['id']}/{fr['label']}: grid {res.grid.shape} != {shape}. "
                                   "Frames of one dataset must share crop and size; set map_bbox.")
            with open(os.path.join(ds_dir, f"{fr['label']}.json"), "w") as f:
                json.dump(_grid_json(res.grid), f, separators=(",", ":"))
            _save_crop(img, res.map_bbox, os.path.join(ds_dir, f"{fr['label']}.png"))
            frames_out.append(dict(label=fr["label"], url=f"{ds['id']}/{fr['label']}.json",
                                   image=f"{ds['id']}/{fr['label']}.png"))
            d = res.diagnostics
            diags.append(dict(label=fr["label"], mean_de=round(d["mean_de"], 2),
                              p95_de=round(d["p95_de"], 2),
                              grid_valid=round(d["grid_valid_fraction"], 3),
                              warnings=d["warnings"]))
            if verbose:
                print(f"  {ds['id']:14s} {fr['label']:>6s}  grid={res.grid.shape}  "
                      f"valid={d['grid_valid_fraction']:.2f}  meanΔE={d['mean_de']:.2f}"
                      + ("  WARN: " + "; ".join(d["warnings"]) if d["warnings"] else ""))
        e = cfg.extent
        index["datasets"].append(dict(
            id=ds["id"], title=ds["title"], unit=ds["unit"], description=ds["description"],
            range=dict(vmin=cfg.vmin, vmax=cfg.vmax, center=ds.get("center"), scale=cfg.scale),
            sonification=ds["sonification"], story=ds.get("story"), credit=ds.get("credit"), palette=palette,
            extent=dict(west=e[0], south=e[1], east=e[2], north=e[3]),
            frames=frames_out, diagnostics=diags))
    with open(os.path.join(out_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
    return index


def export_static(out_dir: str = os.path.join(ROOT, "docs")) -> list[str]:
    """Write a self-contained static site (works on GitHub Pages / Netlify / any file host).

    All URLs are relative, so it works at a site root OR under /repo-name/. No server needed:
    the sound engine and everything else run in the visitor's browser.
    """
    import shutil

    import jinja2
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(ROOT, "app", "templates")),
                             autoescape=True, undefined=jinja2.StrictUndefined)
    urls = dict(assets="static", home="index.html", story="story.html")
    with open(os.path.join(OUT_DATA, "index.json"), encoding="utf-8") as f:
        datasets = json.load(f)["datasets"]
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    shutil.copytree(os.path.join(ROOT, "app", "static"), os.path.join(out_dir, "static"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    written = []
    for name, tpl, ctx in (("index.html", "index.html", dict(page="home")),
                           ("story.html", "story.html", dict(page="story", datasets=datasets))):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(env.get_template(tpl).render(**ctx, **urls))
        written.append(path)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()   # tell GitHub Pages not to run Jekyll
    return written


def render_audio(out_dir: str = os.path.join(ROOT, "out", "audio")) -> list[str]:
    from .sonify import planet_chord, render_chords, render_scan, write_wav
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(OUT_DATA, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    written = []
    for ds in index["datasets"]:
        grids = []
        for fr in ds["frames"]:
            with open(os.path.join(OUT_DATA, fr["url"])) as f:
                g = json.load(f)
            arr = np.array([np.nan if v is None else v for v in g["data"]], float).reshape(g["rows"], g["cols"])
            grids.append(arr)
        e = ds["extent"]
        first, last = grids[0], grids[-1]
        # 1. equator-ish row scan of the latest frame
        row = first.shape[0] // 2
        p = os.path.join(out_dir, f"{ds['id']}_equator_scan.wav")
        write_wav(p, render_scan(list(last[row]), ds, lat01=0.5)); written.append(p)
        # 2. north -> south zonal profile
        with np.errstate(all="ignore"):
            zonal = [np.nanmean(r) if np.isfinite(r).mean() >= 0.2 else np.nan for r in last]
        p = os.path.join(out_dir, f"{ds['id']}_pole_to_pole.wav")
        write_wav(p, render_scan(zonal, ds, step=0.12, pan_sweep=False)); written.append(p)
        # 3. the planet's chord, every year (needs >= 3 frames)
        if len(grids) >= 3:
            chords = [planet_chord(g.ravel(), ds) for g in grids]
            if all(c is not None for c in chords):
                p = os.path.join(out_dir, f"{ds['id']}_planet_chord_timelapse.wav")
                write_wav(p, render_chords(chords)); written.append(p)
        # 4. duet: first frame left ear, last frame right ear, same row
        p = os.path.join(out_dir, f"{ds['id']}_duet_{ds['frames'][0]['label']}_vs_{ds['frames'][-1]['label']}.wav")
        write_wav(p, render_scan(list(first[row]), ds, list(last[row]), lat01=0.5)); written.append(p)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline.build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    b = sub.add_parser("build"); b.add_argument("--manifest", default=DEFAULT_MANIFEST)
    d = sub.add_parser("detect"); d.add_argument("image"); d.add_argument("--vmin", type=float, default=0)
    d.add_argument("--vmax", type=float, default=1); d.add_argument("--out", default="debug_overlay.png")
    sub.add_parser("selftest")
    sub.add_parser("audio")
    fr = sub.add_parser("frames"); fr.add_argument("video"); fr.add_argument("--times", default="0,50%,99%")
    fr.add_argument("--out", default=os.path.join(ROOT, "datasets", "real")); fr.add_argument("--prefix", default="frame")
    fr.add_argument("--scale", type=float, default=1.0, help="e.g. 0.5 halves the stills (recommended for 7680-wide video)")
    rl = sub.add_parser("ruler"); rl.add_argument("image"); rl.add_argument("--out", default="out/ruler.png")
    rl.add_argument("--step", type=int, default=200)
    st = sub.add_parser("static"); st.add_argument("--out", default=os.path.join(ROOT, "docs"))
    a = ap.parse_args(argv)

    if a.cmd == "demo":
        print("manifest:", make_demo())
    elif a.cmd == "build":
        build(a.manifest)
        print("built ->", OUT_DATA)
    elif a.cmd == "detect":
        img = load_image(a.image)
        res = extract(img, ExtractConfig(vmin=a.vmin, vmax=a.vmax))
        debug_overlay(img, res, a.out)
        print(json.dumps({k: v for k, v in res.diagnostics.items()}, indent=2, default=str))
        print("overlay ->", a.out)
    elif a.cmd == "selftest":
        from .evaluate import format_table, run_suite
        r = run_suite()
        print(format_table(r))
        sys.exit(0 if all(x["passed"] for x in r) else 1)
    elif a.cmd == "frames":
        from .frames import contact_sheet, extract_frames, parse_times, video_info
        info = video_info(a.video)
        print(f"video: {info['width']}x{info['height']}, {info['frames']} frames, {info['seconds']:.1f}s, {info['fps']:.1f} fps")
        paths = extract_frames(a.video, parse_times(a.times), a.out, a.prefix, a.scale)
        for p in paths:
            print(p)
        sheet = contact_sheet(paths, os.path.join(a.out, f"{a.prefix}_contact_sheet.jpg"))
        print("contact sheet (open this one first):", sheet)
    elif a.cmd == "ruler":
        from .frames import ruler
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        print(ruler(a.image, a.out, a.step))
        print("ruler picture ->", a.out)
    elif a.cmd == "static":
        for p in export_static(a.out):
            print(p)
        print("deploy this folder (GitHub Pages: Settings > Pages > Deploy from branch > /docs)")
    elif a.cmd == "audio":
        for p in render_audio():
            print(p)


if __name__ == "__main__":
    main()
