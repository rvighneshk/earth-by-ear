"""After ANY import, run this one command. Order matters; every step is safe to repeat.

  python -m pipeline.finish            # geometry -> colour values -> voices -> dates -> audio -> website (docs/)
  python -m pipeline.finish --fast     # skip audio rendering and website export
"""
import subprocess, sys

STEPS = ["pipeline.geometry", "pipeline.hue", "pipeline.voices", "pipeline.dates", "pipeline.jukebox_render", "pipeline.build static", "pipeline.check"]

if __name__ == "__main__":
    steps = STEPS[:4] if "--fast" in sys.argv else STEPS
    for st in steps:
        print(f"\n== {st}")
        subprocess.run([sys.executable, "-m", *st.split()], check=(st != "pipeline.check"))   # the check reports problems itself
    print("\nDone. Start the site:  uvicorn app.main:app --reload")
