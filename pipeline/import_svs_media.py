"""Ingest a NASA SVS video as a visual-feature sonification dataset.

This intentionally maps sampled image luminance to relative sound; it does NOT claim
pixels are calibrated scientific measurements. Use a legend/raw numerical source for
physical-unit sonification.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"app"/"static"/"data"
MEDIA=ROOT/"datasets"/"real"/"media"
CATALOG=ROOT/"datasets"/"real"/"nasa_svs_catalog.json"

def parse_crop(s):
    vals=[float(x) for x in s.split(",")]
    if len(vals)!=4 or any(v<0 or v>1 for v in vals) or vals[2]<=0 or vals[3]<=0 or vals[0]+vals[2]>1 or vals[1]+vals[3]>1:
        raise argparse.ArgumentTypeError("crop must be normalized x,y,width,height (0..1)")
    return vals

PALETTES={
 "night":["#03001c","#160b3b","#3b0f70","#721f81","#b63679","#e65c4f","#fca636","#fcfdbf"],
 "ocean":["#081d58","#225ea8","#41b6c4","#a1dab4","#ffffcc"],
 "viridis":["#440154","#482878","#3e4989","#31688e","#26828e","#1f9e89","#35b779","#6ece58","#b5de2b","#fde725"],
 "plasma":["#0d0887","#6a00a8","#b12a90","#e16462","#fca636","#f0f921"],
}
def make_proxy(video,requested=False):
    """Re-encode to a small, universally decodable H.264 copy (cached in datasets/real/media/_proxy)."""
    ff=shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError(f"OpenCV cannot decode {video.name} and ffmpeg is not installed, so it cannot be converted. "
                           "Install ffmpeg (Windows: winget install Gyan.FFmpeg, then open a NEW terminal; macOS: brew install ffmpeg), "
                           "or re-encode the video to H.264 MP4 yourself and import that.")
    out=MEDIA/"_proxy"/(video.stem+".h264.mp4"); out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and out.stat().st_mtime>=video.stat().st_mtime and out.stat().st_size>0: return out
    print(f"{'Converting' if requested else 'OpenCV cannot decode'} {video.name}{'' if requested else ';'} making a small H.264 copy first (one time, can take a few minutes)...")
    subprocess.run([ff,"-y","-loglevel","error","-stats","-i",str(video),"-an","-vf","scale='min(1280,iw)':-2",
                    "-c:v","libx264","-preset","veryfast","-crf","26","-pix_fmt","yuv420p",str(out)],check=True)
    return out

IMAGE_EXT={".jpg",".jpeg",".png",".tif",".tiff",".webp",".bmp"}

class StillCapture:
    """A single image behaves like a one-frame video (e.g. the GEOS Aerosols still)."""
    def __init__(self,path): self.im=cv2.imdecode(np.fromfile(str(path),np.uint8),cv2.IMREAD_COLOR)
    def isOpened(self): return self.im is not None
    def get(self,prop): return {cv2.CAP_PROP_FRAME_COUNT:1,cv2.CAP_PROP_FPS:1}.get(prop,0)
    def set(self,*a): return True
    def read(self): return True,self.im.copy()
    def release(self): pass

def open_video(video,force_proxy=False):
    """Open with OpenCV; if the codec is unsupported (or the first frame will not decode), fall back to a proxy copy."""
    video=Path(video)
    if not video.exists():
        have=", ".join(p.name for p in sorted(video.parent.glob("*"))[:12]) if video.parent.exists() else "(folder missing)"
        raise FileNotFoundError(f"{video} not found. Files in {video.parent}: {have}")
    if video.suffix.lower() in IMAGE_EXT:
        cap=StillCapture(video)
        if not cap.isOpened(): raise RuntimeError(f"Cannot read image {video}")
        return cap
    if not force_proxy:
        cap=cv2.VideoCapture(str(video))
        ok=cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT)>0 and cap.read()[0]
        if ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES,0); return cap
        cap.release()
    cap=cv2.VideoCapture(str(make_proxy(video,force_proxy)))
    if not cap.isOpened(): raise RuntimeError("Even the converted copy will not open. Try updating opencv-python, or re-encode manually.")
    return cap

def is_blank(bgr):
    """A frame with (almost) no picture: solid black/white/colour, or a fade. Title cards and logos still have detail, so skip those with skip_start."""
    return float(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY).std())<3.0

def read_good(cap,sec,crop,max_nudge=6.0,step=0.5):
    """Frame at `sec`; if it is blank, look a little later (up to 6 s). Returns (time, region) or None."""
    x,y,w,h=crop; t=sec
    while t<=sec+max_nudge+1e-9:
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000); ok,bgr=cap.read()
        if not ok: return None
        H,W=bgr.shape[:2]; region=bgr[int(y*H):int((y+h)*H),int(x*W):int((x+w)*W)]
        if region.size==0: raise ValueError("Crop is empty")
        if not is_blank(region): return t,region
        t+=step
    return None

def ingest(video, dsid, title, unit, times, crop, rows, cols, palette_name, force_proxy=False, skip_start=0.0, skip_end=0.0):
    if not any(r["id"]==dsid for r in json.loads(CATALOG.read_text(encoding="utf-8"))["resources"]):
        raise ValueError(f"Unknown ID {dsid}; see datasets/real/nasa_svs_catalog.json")
    cap=open_video(video,force_proxy)
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps=cap.get(cv2.CAP_PROP_FPS) or 30
    duration=total/fps if total else 0
    if total>1:
        start=skip_start if skip_start else min(5.0,0.1*duration)          # most videos open with a title or logo
        end=max(start+1,duration*0.97-skip_end)
    if not times: times=[0.0] if total<=1 else [start+(end-start)*i/5 for i in range(6)]
    else:
        times=[t for t in times if t>=skip_start and (not skip_end or t<=duration-skip_end)]
        if not times: raise ValueError("skip_start / skip_end removed every requested time")
    out=DATA/dsid; out.mkdir(parents=True,exist_ok=True)
    for old in out.glob("*"): old.unlink()                                # no stale frames from an earlier import
    frames=[]; arrays=[]; last=-9.0
    x,y,w,h=crop
    for sec in times:
        got=read_good(cap,sec,crop)
        if got is None: print(f"Skip {sec:.1f}s (no usable frame)"); continue
        t,region=got
        if abs(t-last)<0.25: print(f"Skip {sec:.1f}s (same frame as the one before)"); continue
        last=t; k=len(frames)
        if t!=sec: print(f"  {sec:.1f}s was blank, using {t:.1f}s")
        gray=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)
        grid=cv2.resize(gray,(cols,rows),interpolation=cv2.INTER_AREA).astype(np.float32)/255
        values=np.round(grid*100,2)                                       # relative brightness 0-100
        arrays.append(values)
        rel=f"{dsid}/{k:02d}.json"
        payload={"rows":rows,"cols":cols,"data":[round(float(v),2) for v in values.ravel()]}
        (DATA/rel).write_text(json.dumps(payload,separators=(",",":")),encoding="utf-8")
        thumb=cv2.resize(region,(720,360),interpolation=cv2.INTER_AREA)
        imgrel=f"{dsid}/{k:02d}.jpg"; cv2.imwrite(str(DATA/imgrel),thumb,[int(cv2.IMWRITE_JPEG_QUALITY),88])
        frames.append({"label":f"{t:.1f} s","seconds":round(t,2),"url":rel,"image":imgrel})
        print(f"Frame {k+1} at {t:.1f}s -> {rel}")
    cap.release()
    if not frames: raise RuntimeError("No frames extracted.")
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    source=next((r for r in catalog["resources"] if r["id"]==dsid),None)
    if source is None: raise ValueError(f"Unknown ID {dsid}; see datasets/real/nasa_svs_catalog.json")
    idxp=DATA/"index.json"
    idx=json.loads(idxp.read_text(encoding="utf-8")) if idxp.exists() else {"datasets":[]}
    idx.setdefault("datasets",[])
    idx["datasets"]=[d for d in idx["datasets"] if d["id"]!=dsid]
    idx["datasets"].append({
      "id":dsid,"title":title or source["title"],"unit":unit,
      "description":source["provenance"]+" Visual sonification: normalized grayscale brightness 0–100 sampled from selected video frames and crop.",
      "range":{"vmin":0,"vmax":100,"center":None,"scale":"linear"},
      "palette":PALETTES[palette_name],
      "sonification":{"scale":"majorPent","root":"C3","spanOctaves":3,"tension":"high","positiveWord":"brighter","negativeWord":"darker"},
      "story":{"intro":"This sound is derived from visual brightness in a NASA Scientific Visualization Studio animation—not directly from calibrated pixel-level scientific measurements.","outro":"Brighter sampled pixels rise in pitch and intensity. The pattern you heard follows the selected visualization frames."},
      "credit":{"text":"NASA Scientific Visualization Studio; see source page for full credits and dataset acknowledgements.","url":source["url"]},
      "extent":{"west":-180,"south":-90,"east":180,"north":90},
      "frames":frames,"visualSonification":True,"sourcePage":source["url"],"cropNormalized":crop,
      "diagnostics":[{"label":f["label"],"grid_valid":1.0,"warnings":["Relative image brightness; not calibrated science units"]} for f in frames]
    })
    idxp.write_text(json.dumps(idx,indent=2),encoding="utf-8")
    print(f"Registered {dsid} in {idxp}")
    print("IMPORTANT: visual brightness is not a physical unit. Confirm the crop excludes labels, legends, titles and overlays.")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video",required=True,help="Downloaded NASA SVS MP4/WEBM")
    p.add_argument("--id",required=True,help="Resource id from nasa_svs_catalog.json")
    p.add_argument("--title"); p.add_argument("--unit",default="relative brightness")
    p.add_argument("--times",default="",help="Comma-separated seconds; default 6 evenly spaced frames")
    p.add_argument("--crop",type=parse_crop,default=(0,0,1,1),help="Normalized x,y,width,height (e.g. 0.05,0.12,0.9,0.75)")
    p.add_argument("--rows",type=int,default=45); p.add_argument("--cols",type=int,default=90)
    p.add_argument("--skip-start",type=float,default=0.0,help="seconds to ignore at the start (titles, logos)")
    p.add_argument("--skip-end",type=float,default=0.0,help="seconds to ignore at the end (credits)")
    p.add_argument("--proxy",action="store_true",help="Always convert to a small H.264 copy first (huge or odd-codec files)")
    p.add_argument("--palette",choices=PALETTES,default="viridis",help="Color rendering palette; visual colors, not data calibration")
    a=p.parse_args()
    times=[float(x) for x in a.times.split(",") if x.strip()] if a.times else None
    palette=a.palette
    if a.id=="eic-night-lights" and palette=="viridis": palette="night"
    if "ocean" in a.id and palette=="viridis": palette="ocean"
    ingest(Path(a.video),a.id,a.title,a.unit,times,a.crop,a.rows,a.cols,palette,a.proxy,a.skip_start,a.skip_end)
    print("NEXT: python -m pipeline.finish   (voices, geometry, colour values, dates, audio, website)")
if __name__=="__main__": main()
