> The full, step-by-step listening protocol is in **SETUP_AND_TEST.md (Part B)**. This file is the short checklist.

# Testing checklist

## Automated (≈10 s)
```bash
python tests/run_all.py
```
Checks: JS and Python scores pick identical notes · globe masks · audio is audible/stereo/unclipped · the real audio engine
schedules every dataset with all waveforms · the static site builds.

## Manual (needs ears, ~15 min). Use Chrome or Edge first, then Safari/Firefox.
Start: `uvicorn app.main:app --reload` → http://127.0.0.1:8000  (or open `docs/` through any static server).

**Sound & basics**
- [ ] Nothing is audible before pressing *Turn on sound*; after pressing it, a note plays.
- [ ] Volume slider works; *Stop* silences everything within ~0.2 s.
- [ ] Each of the 7 datasets loads, shows its picture/colours, and a different scale/timbre is audible between datasets.

**Play this visualization (key J)**
- [ ] Plays pad + melody + sparkle; cursor sweeps left → right each ~4 s; the map changes each bar.
- [ ] Night Lights, Lightning and Forest sound clearly different from each other.
- [ ] Pressing the button again (or Escape) stops it and restores the map you had selected.
- [ ] Aerosols (single still) loops four bars. Switching dataset mid-play stops cleanly.

**Globe/camera datasets (CO2, Air quality, Lightning, Forest)**
- [ ] Moving into the black sky is silent (soft thump), never a pitch.
- [ ] Readout says "upper left of the view", never a latitude/longitude. Button reads "Top to bottom".
- [ ] Flat maps (Night lights, Ocean, Aerosols) still say "° N / ° E" and "Pole to pole".

**Accessibility**
- [ ] Keyboard only: Tab → map, arrows move, Space replays, `?` lists keys, `R/C/P/D/G/L/J/T` work.
- [ ] Screen reader (NVDA / VoiceOver / TalkBack): moving announces value + place; J announces each movement.
- [ ] Duet mode: left ear = first year, right ear = last; *Jump to biggest change* lands somewhere sensible.
- [ ] Phone: touch-drag on the map plays; vibration toggle works on Android.

**Playlist page (/story#playlist)**
- [ ] All 7 players play; durations 20–50 s; the description under each makes sense. Tracks resemble the live jukebox.
- [ ] Nothing in the text claims calibrated science values.

**Tour & chord:** guided tour and planet chord now work on every dataset, including single pictures (see SETUP_AND_TEST.md, Test 7).

**Live vs download**
- [ ] Press J, then play the same dataset's downloaded MP3: loudness and reverb should now feel alike (the file may differ slightly in timbre).
- [ ] Moving over the map by hand (not J) is still dry and clear. After J ends or is stopped, the dry sound returns.

**New in this version**
- [ ] Frame menus show times (CO2 "~14 Jan 2020", Lightning "01 Mar 2017 03:27"), or "Frame 3 of 6" where no date is known.
- [ ] *Download this track* saves a playable file; *Download all tracks (ZIP)* contains every track + PLAYLIST.txt.
- [ ] Ocean temperature: the map is blue (poles) to red (tropics), land is silent, and equatorial notes are higher than polar ones.
- [ ] Importing a video OpenCV cannot read converts it automatically (or says clearly that ffmpeg is needed).

**Known gaps (not bugs):** only the ocean temperature data uses colour; the other datasets use brightness · Air quality and
Aerosols show several variables side by side, so no single colour ramp exists for them · dates are known only for CO2 and Lightning.
