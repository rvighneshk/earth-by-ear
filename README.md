# Earth, by ear — NASA Space Apps 2026 · Earth Information Jukebox

Pick a NASA Earth Information Center visualization and **hear it**. Press *Play this visualization* and the whole
animation is performed as a short piece of music, with the picture changing on screen in time. Or explore by
hand: move over the map with a mouse, touch or arrow keys and each place plays its own note.

Built for blind and low-vision users first: every sound has a spoken/text twin, the whole app works from the keyboard,
and every track has a written description.

## Run it
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000
```
No server? `python -m pipeline.build static` writes a self-contained site to `docs/` (GitHub Pages: deploy the `/docs` folder).

## How the music is made
| Picture | Sound |
|---|---|
| Brightness of a region (or colour-ramp position for ocean temperature) | Pitch, snapped to a scale so it stays musical |
| How extreme the value is | Tension: calm = fifth + octave, extreme = tritone + minor second, brighter tone |
| Local roughness | Flutter |
| West → east | Left → right in the stereo field, and the playhead |
| Busy slice (wide spread) | More melody notes and an octave-up sparkle voice |
| No data / globe background | Silence |
| Each dataset | Its own scale, home note and waveform (`pipeline/voices.py`) |

*Play this visualization*: one frame = one four-second bar; a pad (the map's chord), a melody (16 slices, west → east) and a
sparkle voice. The melody is stretched across all frames of a dataset so quiet structure is audible while change over time is kept.
*Duet*: two years, one in each ear. *Guided tour*: finds the biggest increase, decrease and extreme, with captions made only from the data.

## Honest limits
- Values come from **image brightness** in NASA SVS animations, not calibrated science files. Sea-surface temperature instead uses each pixel's **hue along the blue→red ramp** (tropics read ~89, poles ~13), which suits a rainbow colour map better. Both are relative values; the app says so in its readouts and on the How it works page.
- CO2, air quality and forest height are globe views and ISS lightning is a camera view: they are flagged `geometry: view`, background is silent, and positions are reported in the frame ("upper left of the view"), never as invented latitude/longitude.
- The legend-decoding pipeline (`pipeline/extract.py`, CIELAB colour match) is included for sources that ship a colorbar; the shipped datasets do not use it.

## Adding all 9 sources (start here): see **SETUP_AND_TEST.md**
`python -m pipeline.import_all --list` then `python -m pipeline.import_all`. It matches files to datasets, imports, finishes and checks.

## Adding a single NASA video (any SVS download)
```bash
# 0. put the downloaded video in datasets/real/media/ and look at it first (saves a contact sheet with a grid)
python -m pipeline.preview_video --video datasets/real/media/atmos-river.mp4
# 1. import (ids: eic-atmospheric-river, eic-perpetual-ocean; see datasets/real/nasa_svs_catalog.json)
python -m pipeline.import_svs_media --video datasets/real/media/atmos-river.mp4 --id eic-atmospheric-river
python -m pipeline.finish          # geometry, colour values, voices, time labels, audio playlist, website
```
- **Codec problems fix themselves.** If OpenCV cannot decode a file, the importer converts it to a small H.264 copy
  (needs ffmpeg once: Windows `winget install Gyan.FFmpeg`, then open a new terminal). Add `--proxy` to force this for huge files.
- Choose frames with `--times 5,60,120` (seconds) and exclude labels/legends with `--crop x,y,w,h` (0..1).
- The id must exist in `datasets/real/nasa_svs_catalog.json`.
- `finish` prints how it classified each dataset (flat map / globe / camera view). Wrong? Edit `datasets/real/geometry.json`.
- Real dates for the frame menus: `datasets/real/dates.json`. No entry means "Frame 3 of 6".
- A new dataset automatically gets its own scale, home note and waveform (`pipeline/voices.py`).
- Without ffmpeg the playlist is rendered as WAV instead of MP3 (bigger, same sound).

## Why the downloads and the live jukebox sound the same
*Play this visualization* does not use the live synthesiser. The browser builds the whole performance from the map data
(`app/static/js/synth.js`) with the same note recipe, mix and room reverb as the Python renderer, then plays it. A test
(`tests/test_score.py`) checks that browser and Python produce the same audio sample for sample. It takes about a second to
prepare (the button says "Preparing..."), and the MP3s are the same piece. Exploring by hand uses the live synthesiser and
stays dry on purpose, so single pitches are easy to tell apart.
The melody sweeps only across the part of the picture that has data, so a globe's empty sky never causes silence.

## Downloads
Every dataset has *Download this track* on the main page, and the *Playlist* section of the How it works page has a player,
a download link and a written description per track, plus one ZIP of everything (`earth-jukebox-playlist.zip`, with `PLAYLIST.txt`).

## Tests
```bash
python tests/run_all.py      # automated checks (works on Windows); then SETUP_AND_TEST.md Part B
```

## 3-minute demo script
1. (0:00) Eyes closed, keyboard only: Turn on sound, pick Ocean, arrow across the map. Say what you hear.
2. (0:40) *Play this visualization* on Night Lights, then Lightning. Same button, clearly different music.
3. (1:20) Duet across years on Air Quality: left ear then right ear; *Jump to biggest change*.
4. (2:00) Show the How it works page: the rules, the Playlist with text descriptions, the Limits section.
5. (2:30) Close: why a sound twin of NASA's visuals matters for access to Earth science.

Credits: NASA Scientific Visualization Studio and Earth Information Center (links in each dataset card). Poppins font (OFL).
