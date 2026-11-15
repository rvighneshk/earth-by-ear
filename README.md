# Earth, by Ear

**An accessible Earth Jukebox that turns NASA Earth Information Center visualizations into music.**  
*Hear what the map says.*

[**Try the live experience**](https://earth-by-ear.onrender.com) · [How it works](#how-it-works) · [NASA sources](#nasa-visualizations)

Earth, by Ear makes Earth science audible. It pairs NASA Scientific Visualization Studio (SVS) / Earth Information Center (EIC) frames with data-driven sound, letting people explore a map with their ears as well as their eyes. A frame becomes a four-second musical bar: a chord describes the overall data, a melody moves west to east, and a sparkle voice highlights busy regions. Each visualization has its own musical character.

> **Why it matters:** Earth science is often communicated visually. Sonification creates another way to experience and explore it, including for blind and low-vision audiences and people who learn better by listening.

## Experience it

**[Open Earth, by Ear](https://earth-by-ear.onrender.com)**

1. Turn on sound (browsers require a user gesture before audio can play).
2. Choose one of the NASA visualizations.
3. Explore the map with a mouse, touch, or keyboard—or let the jukebox perform it.

## Listen to samples

The repository includes generated audio for all nine visualizations. Open an MP3 sample below, or download the complete playlist ZIP.

| Visualization | Audio sample |
|---|---|
| Night Lights | [Listen (MP3)](app/static/audio/eic-night-lights.mp3) |
| Sea Surface Currents & Temperature | [Listen (MP3)](app/static/audio/eic-ocean-current-temperature.mp3) |
| GEOS Aerosols | [Listen (MP3)](app/static/audio/eic-geos-aerosols.mp3) |
| Air Quality | [Listen (MP3)](app/static/audio/eic-air-quality.mp3) |
| Perpetual Ocean | [Listen (MP3)](app/static/audio/eic-perpetual-ocean.mp3) |
| DYAMOND CO₂ | [Listen (MP3)](app/static/audio/eic-dyamond-co2.mp3) |
| ISS Lightning | [Listen (MP3)](app/static/audio/eic-iss-lightning.mp3) |
| Atmospheric River | [Listen (MP3)](app/static/audio/eic-atmospheric-river.mp3) |
| GEDI Forest Height | [Listen (MP3)](app/static/audio/eic-gedi-forest-height.mp3) |

**[Download the complete audio playlist (ZIP)](app/static/audio/earth-jukebox-playlist.zip)**

> GitHub README does not consistently render embedded audio players, so these are direct links to the audio files. Click a sample to play it in your browser or download it.

## Features

- **Play a visualization:** performs its frames as a short composition, with a four-second bar per frame, a west-to-east melody, an overall chord/pad, and a sparkle voice for dense or varied regions.
- **Explore by touch, mouse, or keyboard:** move across the map to hear local values; scan a row, column, or north-to-south profile; jump to the largest change; or play values along the legend.
- **Duet across time:** compare two frames. The earlier moment is placed in the left ear and the later moment in the right; differences are heard as differences between the notes.
- **Guided tour:** visit data-derived locations such as the largest increase, decrease, and extreme value, with captions generated from the extracted data.
- **The planet's chord:** represent a whole map with a five-note chord based on its 10th, 30th, 50th, 70th, and 90th percentiles. Play frames in sequence to hear the distribution change.
- **Accessible controls and descriptions:** semantic controls, keyboard navigation and shortcuts, live readouts, optional browser speech, and optional vibration on supported Android devices.
- **Listen offline:** download individual MP3 tracks or the complete playlist ZIP, with written track descriptions.
- **Original NASA frames:** optionally display the source frame alongside the sonification.
- **Nine visualizations:** explore night lights, sea-surface temperature and currents, aerosols, air quality, ocean currents, carbon dioxide, lightning, atmospheric rivers, and forest height.

## How it works

Earth, by Ear does not simply assign arbitrary notes to image colours. Its main pipeline uses a visualization's **colour legend as a codebook**:

1. **Find the legend and map region.** Detect or configure the colourbar and the image area containing the data.
2. **Decode image colours.** Match map pixels to legend colours in the perceptual CIELAB colour space, then infer the value represented by the closest colour. Pixels that do not match the legend (such as text, coastlines, or overlays) can become no-data.
3. **Create a compact data grid.** Fill small gaps and aggregate pixels into a grid that the interactive audio engine can explore.
4. **Map values to musical notes.** Normalize values to the dataset's range and snap pitches to a selected musical scale and root note. For anomaly datasets, the legend's centre maps to the home note.
5. **Add musical character.** Extreme values introduce dissonance (a tritone, then a minor second); local variation affects roughness; latitude and tension affect brightness; and longitude maps to stereo position.
6. **Compose and play.** The browser synthesizes notes with the Web Audio API. A separate Python renderer creates downloadable stereo audio using corresponding sonification rules.

### A note on visual sonification

The sound is derived from **NASA visualization frames**, not necessarily from the underlying original science data. It is therefore constrained by image resolution, colour palettes, legends, compression, and overlays. Values should be treated as approximate or relative—not as calibrated scientific measurements unless a dataset explicitly provides source-native values. Sea-surface temperature is decoded from pixel hue along its blue-to-red colour ramp rather than brightness. Globe and camera views use positions within the frame instead of claiming latitude/longitude; no-data areas are silent.

## NASA visualizations

Each item links to its NASA SVS source page. Please consult the source for scientific context, credits, and data details.

| Visualization | NASA SVS source |
|---|---|
| Change in Night Lights between 2012 and 2023 | [SVS 5313](https://svs.gsfc.nasa.gov/5313/) |
| Global Sea Surface Currents and Temperature | [SVS 3912](https://svs.gsfc.nasa.gov/3912/) |
| GEOS Aerosols | [SVS 5669](https://svs.gsfc.nasa.gov/5669/) |
| Air Quality Model Runs | [SVS 5533](https://svs.gsfc.nasa.gov/5533/) |
| Perpetual Ocean 2: Western Boundary Currents | [SVS 5425](https://svs.gsfc.nasa.gov/5425/) |
| DYAMOND Global Carbon Dioxide | [SVS 5196](https://svs.gsfc.nasa.gov/5196/) |
| Lightning Events Detected from the ISS, 2017–2023 | [SVS 5011](https://svs.gsfc.nasa.gov/5011/) |
| A 3D View of an Atmospheric River from an Earth System Model | [SVS 4960](https://svs.gsfc.nasa.gov/4960/) |
| GEDI Forest Height | [SVS 4950](https://svs.gsfc.nasa.gov/4950/) |

## Tech stack

- **Backend / web server:** Python, FastAPI, Uvicorn, Jinja2
- **Data processing:** NumPy, SciPy, scikit-image, OpenCV, Pillow
- **Audio:** JavaScript Web Audio API (custom browser synthesizer); Python offline stereo renderer
- **Frontend:** HTML, CSS, vanilla JavaScript (ES modules; no frontend framework)
- **Media processing:** FFmpeg (for video conversion / compatible media workflows)

## Run locally

### Requirements

- Python 3.10+ recommended
- pip
- A modern browser with Web Audio API support
- FFmpeg for importing or converting some NASA videos (not needed just to run the prebuilt app)

### Setup

Clone or download this repository, then run from its root directory:

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and start the server:

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser. Use the **Turn on sound** button before exploring.

### Useful routes

| Route | Purpose |
|---|---|
| `/` | Interactive jukebox |
| `/story` | Method, dataset details, and downloadable playlist |
| `/api/datasets` | Dataset index and metadata JSON |
| `/healthz` | Health check and dataset count |

## Rebuild or extend the datasets

The repository includes preprocessed frames, data grids, and audio assets, so you can run the app without downloading NASA media again. To import new or refreshed SVS material, use the pipeline from the repository root.

1. Download the appropriate media from its NASA SVS source page and place it in `datasets/real/media/`.
2. Review the source matching and sampling configuration in `datasets/real/sources.json`.
3. Preview which local file will be matched to each source:

   ```bash
   python -m pipeline.import_all --list
   ```

4. Import available sources and run the finishing pipeline:

   ```bash
   python -m pipeline.import_all
   ```

   Import selected datasets only:

   ```bash
   python -m pipeline.import_all --only eic-air-quality eic-gedi-forest-height
   ```

   The finishing steps process geometry, colour/value mapping, voices, dates, audio, static export, and checks. Some videos may require FFmpeg; `--proxy` asks the importer to make compatible H.264 copies.

### Pipeline commands

```bash
python -m pipeline.build selftest                 # run extraction/sonification checks
python -m pipeline.build detect IMAGE --vmin 0 --vmax 1 --out out/debug.png
python -m pipeline.build frames VIDEO --times 0,50%,99%
python -m pipeline.finish                          # full finishing pipeline
python -m pipeline.finish --fast                   # skip audio + static export
python -m pipeline.build static --out docs          # export static website
python -m pipeline.build audio                     # render offline WAV examples
```

The exact `detect` range and extraction settings depend on the visualization legend. Inspect the debug output before trusting a new import.

## Repository layout

```text
app/
  main.py                 FastAPI routes
  templates/              Jinja2 pages (jukebox and methodology)
  static/
    css/                  Interface styles
    js/                   Audio engine, mapping, interaction, guided tour
    data/                 Preprocessed frames, grids, and dataset index
    audio/                MP3 tracks and playlist archive
pipeline/                 Import, decode, grid, sonify, render, and validation tools
datasets/real/
  sources.json            NASA media matching, crops, frame times, palette config
  nasa_svs_catalog.json   NASA SVS source catalog
  media/                  Place downloaded source media here (not included)
out/audio/                Offline WAV renders
requirements.txt           Python dependencies
```

## Accessibility

Accessibility is part of the interaction design, not an add-on. The interface includes keyboard-operable controls and map navigation, semantic labels and landmarks, live text readouts, optional browser speech, and optional vibration feedback. The story/playlist page provides audio controls and written descriptions so tracks can be experienced without navigating the visual map.

**Keyboard shortcuts** (focus the map first where applicable):

| Key | Action |
|---|---|
| Arrow keys | Move one grid cell; hold Shift to move ten |
| Home / End | Move to west / east edge of the row |
| Page Up / Page Down | Move north / south by 15 rows |
| Space / Enter | Hear the current cell again |
| `R` / `C` / `P` | Scan row / column / pole-to-pole |
| `D` | Switch One map / Duet |
| `J` | Play the visualization |
| `L` | Play the planet's chord |
| `T` / `N` / `B` | Guided tour / next stop / previous stop |
| `G` | Jump to the biggest change |
| `1`–`9` | Select a dataset |
| `S` | Toggle spoken readouts |
| `Escape` | Stop playback |
| `?` | Show keyboard help |

## Challenge connection

**NASA Space Apps Challenge 2026 — The Earth Information Jukebox**

Earth, by Ear responds to the challenge by pairing EIC/SVS visual frames with dynamic sonification and a user-facing jukebox. It combines data processing and audio synthesis with an exploratory experience designed to make Earth science accessible beyond sight. The guided tour and downloadable described tracks offer additional ways to encounter the visualizations.

## Credits and acknowledgments

- Earth science visualizations and source material: **NASA Scientific Visualization Studio / Earth Information Center**. See each linked SVS page for source-specific credits and acknowledgments.
- Built with Python, FastAPI, NumPy, SciPy, scikit-image, OpenCV, Pillow, and the browser Web Audio API.
- An AI assistant (Claude) helped with code writing, testing, and documentation; project design and creative direction are reflected in the implementation.
