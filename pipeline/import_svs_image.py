"""Import a still NASA SVS image into Earth Jukebox as one visual-feature frame."""
import argparse,json
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"app"/"static"/"data"
PALETTES={
"night":["#03001c","#160b3b","#3b0f70","#721f81","#b63679","#e65c4f","#fca636","#fcfdbf"],
"ocean":["#081d58","#225ea8","#41b6c4","#a1dab4","#ffffcc"],
"viridis":["#440154","#482878","#3e4989","#31688e","#26828e","#1f9e89","#35b779","#6ece58","#b5de2b","#fde725"],
"plasma":["#0d0887","#6a00a8","#b12a90","#e16462","#fca636","#f0f921"]}
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--image",required=True);p.add_argument("--id",required=True);p.add_argument("--title")
 p.add_argument("--unit",default="relative brightness");p.add_argument("--crop",default="0,0,1,1")
 p.add_argument("--rows",type=int,default=45);p.add_argument("--cols",type=int,default=90)
 p.add_argument("--palette",choices=PALETTES,default="viridis");p.add_argument("--colorbar",help="Optional NASA colorbar image path (saved as provenance/reference; not auto-calibrated)")
 a=p.parse_args()
 vals=[float(x) for x in a.crop.split(",")]
 if len(vals)!=4 or vals[2]<=0 or vals[3]<=0 or min(vals)<0 or max(vals)>1 or vals[0]+vals[2]>1 or vals[1]+vals[3]>1: raise ValueError("crop x,y,w,h normalized 0..1")
 img=cv2.imread(a.image)
 if img is None: raise RuntimeError("Cannot read image")
 H,W=img.shape[:2];x,y,w,h=vals; roi=img[int(y*H):int((y+h)*H),int(x*W):int((x+w)*W)]
 gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY);grid=cv2.resize(gray,(a.cols,a.rows),interpolation=cv2.INTER_AREA).astype(float)/255*100
 out=DATA/a.id;out.mkdir(parents=True,exist_ok=True)
 payload={"rows":a.rows,"cols":a.cols,"data":[round(float(v),2) for v in grid.ravel()]}
 (out/"00.json").write_text(json.dumps(payload,separators=(",",":")),encoding="utf-8")
 preview=cv2.resize(roi,(720,360),interpolation=cv2.INTER_AREA);cv2.imwrite(str(out/"00.jpg"),preview)
 catalog=json.loads((ROOT/"datasets/real/nasa_svs_catalog.json").read_text(encoding="utf-8"))
 source=next((r for r in catalog["resources"] if r["id"]==a.id),None)
 if source is None: raise ValueError("id not found in NASA catalog")
 idxp=DATA/"index.json";idx=json.loads(idxp.read_text(encoding="utf-8"));idx["datasets"]=[d for d in idx["datasets"] if d["id"]!=a.id]
 idx["datasets"].append({"id":a.id,"title":a.title or source["title"],"unit":a.unit,"description":source["provenance"]+" One still-image frame; grayscale relative visual intensity 0–100, not calibrated science values.","range":{"vmin":0,"vmax":100,"center":None,"scale":"linear"},"palette":PALETTES[a.palette],"sonification":{"scale":"majorPent","root":"C3","spanOctaves":3,"tension":"high","positiveWord":"brighter","negativeWord":"darker"},"story":{"intro":"This sound is derived from image brightness, not calibrated numerical science data.","outro":"Brightness is mapped to relative pitch and intensity."},"credit":{"text":"NASA SVS/GMAO; see source page for credits and data acknowledgements.","url":source["url"]},"extent":{"west":-180,"south":-90,"east":180,"north":90},"frames":[{"label":"NASA still","url":a.id+"/00.json","image":a.id+"/00.jpg"}],"visualSonification":True,"sourcePage":source["url"],"diagnostics":[{"label":"NASA still","grid_valid":1.0,"warnings":["Visual intensity, not physical units"]}]})
 idxp.write_text(json.dumps(idx,indent=2),encoding="utf-8")
 print("Imported one image frame:",a.id)
 if a.colorbar: print("Colorbar file retained for future calibration:",a.colorbar)
if __name__=="__main__":main()
