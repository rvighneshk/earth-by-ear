"""Give every dataset its own musical voice (scale, home note, waveform) in app/static/data/index.json.

Run after any import:  python -m pipeline.voices
"""
import json, os

INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "data", "index.json")
VOICES = {  # glassy / flowing / hazy / ominous / urban / crackling / woody
    "eic-night-lights":              dict(scale="lydian",    root="D3",  wave="sine"),
    "eic-ocean-current-temperature": dict(scale="dorian",    root="A2",  wave="triangle"),
    "eic-geos-aerosols":             dict(scale="wholeTone", root="E3",  wave="sine"),
    "eic-dyamond-co2":               dict(scale="minorPent", root="C3",  wave="sawtooth"),
    "eic-air-quality":               dict(scale="dorian",    root="F3",  wave="triangle"),
    "eic-iss-lightning":             dict(scale="minorPent", root="F#3", wave="sawtooth"),
    "eic-gedi-forest-height":        dict(scale="majorPent", root="G2",  wave="sine"),
    "eic-atmospheric-river":         dict(scale="lydian",    root="A2",  wave="triangle"),   # moist, sweeping
    "eic-perpetual-ocean":           dict(scale="dorian",    root="D3",  wave="sine"),       # slow, deep currents
}
_SCALES = ["majorPent", "minorPent", "dorian", "lydian", "wholeTone"]
_ROOTS = ["C3", "D3", "E3", "F3", "G2", "A2", "B2"]
_WAVES = ["sine", "triangle", "sawtooth"]


def voice_for(dsid: str) -> dict:
    """Explicit voice if we have one; otherwise a stable pick from the id, so a new import never sounds like another."""
    if dsid in VOICES:
        return VOICES[dsid]
    import zlib
    h = zlib.crc32(dsid.encode())
    return dict(scale=_SCALES[h % 5], root=_ROOTS[(h >> 3) % 7], wave=_WAVES[(h >> 6) % 3])
if __name__ == "__main__":
    with open(INDEX, encoding="utf-8") as f:
        idx = json.load(f)
    for ds in idx["datasets"]:
        ds["sonification"].update(voice_for(ds["id"]))
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=1)
    print("voices applied to", len(idx["datasets"]), "datasets")
