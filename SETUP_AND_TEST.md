# Add all 9 sources, then test the Jukebox properly

Commands are for Windows PowerShell, run from the project folder (`earth-jukebox`). They work the same on macOS/Linux.

## Part A. Add the 9 sources

**1. One-time setup**
```powershell
pip install -r requirements.txt
winget install Gyan.FFmpeg          # then CLOSE and reopen PowerShell
ffmpeg -version                     # must print a version
```
Without ffmpeg, big or unusual videos cannot be converted and the audio is saved as WAV instead of MP3.

**2. Download the 9 NASA videos** into `datasets\real\media\`. Take the 1080p MP4 (or smaller) from each page.
Keep the SVS number or a keyword in the file name, because that is how files are matched to datasets.

| Dataset | Page | Name must contain |
|---|---|---|
| Night Lights | https://svs.gsfc.nasa.gov/5313/ | `night` or `5313` |
| Sea Surface Currents & Temperature | https://svs.gsfc.nasa.gov/3912/ | `current`, `sst` or `3912` |
| GEOS Aerosols (a still image is fine) | https://svs.gsfc.nasa.gov/5669/ | `aerosol` or `5669` |
| Air Quality | https://svs.gsfc.nasa.gov/5533/ | `air`, `quality` or `5533` |
| Perpetual Ocean 2 | https://svs.gsfc.nasa.gov/5425/ | `perpetual` or `5425` |
| DYAMOND CO2 | https://svs.gsfc.nasa.gov/5196/ | `dyamond`, `co2` or `5196` |
| ISS Lightning | https://svs.gsfc.nasa.gov/5011/ | `lightning`, `iss` or `5011` |
| Atmospheric River | https://svs.gsfc.nasa.gov/4960/ | `atmos`, `river` or `4960` |
| GEDI Forest Height | https://svs.gsfc.nasa.gov/4950/ | `gedi`, `forest` or `4950` |

(Caldwell 73 in the catalog is a reference demo, not Earth data. It is not imported.)
A file over ~1 GB is fine: the importer converts it to a small copy by itself.

**3. Check that every file is matched** (changes nothing)
```powershell
python -m pipeline.import_all --list
```
Every dataset must show `<- filename`. A `MISSING` line tells you which page to download from and what to name the file.

**4. Choose the crop for the two new videos** (the other seven already have their settings)
```powershell
python -m pipeline.preview_video --video datasets\real\media\atmos-river.mp4
python -m pipeline.preview_video --video datasets\real\media\perpetual_ocean_2.mp4
```
Open `datasets\real\preview\<name>.jpg`. The grid lines are labelled 0.1 to 0.9. Find the rectangle that holds only the
Earth picture, with no title, legend or credits. Put it in `datasets\real\sources.json` for that dataset, as
`"crop": "x,y,width,height"` (for example `"0.05,0.12,0.9,0.75"`). Leave `null` if the whole frame is the picture.

**5. Import everything**
```powershell
python -m pipeline.import_all
```
It imports all 9, then runs the finishing steps (geometry, colour values, voices, dates, audio, website) and prints a health
table. The last line must be **`All 9 sources are in and look healthy.`** Converting big videos can take several minutes.

**6. Start and open the site**
```powershell
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 and press **Ctrl+F5** (a hard refresh, so the browser drops its cached data).

**Bad frames: a logo, title card or blank screen.** The importer now skips blank frames and the first seconds of a video
by itself (`skip_start` in `sources.json`; Atmospheric River uses 8 s). The health table at the end also warns about any frame
that looks blank or very different from the others. To remove a frame without re-importing:
```powershell
python -m pipeline.drop_frames --id eic-atmospheric-river --list         # frame numbers, times, picture detail
python -m pipeline.drop_frames --id eic-atmospheric-river --frames 0     # remove frame 0 (the logo)
python -m pipeline.finish
```
Look at `app\static\data\eic-atmospheric-river\00.jpg` (and 01, 02...) to see what each frame is.

**Redo one dataset** (for example after changing a crop):
`python -m pipeline.import_all --only eic-atmospheric-river`

**If something goes wrong**

| You see | Do this |
|---|---|
| `MISSING` | Download from the page shown, save the file with the keyword in its name |
| `FAILED: ... ffmpeg is not installed` | Install ffmpeg (step 1) and open a new terminal |
| `only N frames` | The video is shorter than the frame times in `sources.json`. Lower the times, or set `"times": null` |
| `values barely vary` or `% of cells have data` low | The crop covers only background or a title. Redo step 4 |
| Geometry looks wrong (lat/lon shown on a globe, or silence on a flat map) | Move the id to the right list in `datasets\real\geometry.json`, run `python -m pipeline.finish` |
| The page still shows old datasets | Ctrl+F5 |

## Part B. Test the Jukebox properly

**Set up:** headphones, system volume about half, Chrome or Edge, the site's volume slider left at its default.
Press **F12 → Console** and keep it open: it must stay free of red errors during all tests.
First run `python tests/run_all.py`. All automated checks should pass.

Press **Turn on sound**, pick a dataset, then press **J** (or *Play this visualization*).

**Test 1. Every dataset plays through (all 9).** Expected length is 4 s per frame plus about 3 s for the reverb to fade:
Night Lights ~23 s · Ocean Currents ~27 s · Aerosols (one still, four bars) ~19 s · Air Quality ~47 s · CO2 ~35 s ·
Lightning ~47 s · Forest ~47 s · Perpetual Ocean and Atmospheric River ~27 s each if you import 6 frames.
- [ ] The button says *Preparing the performance...* for about a second (longer on a phone), then the music starts, runs to the end and stops by itself.
- [ ] The button changes to *Stop the music* and back to *Play this visualization* at the end.
- [ ] The map you had selected is restored afterwards.

**Test 2. Picture and sound stay together.**
- [ ] A shaded band sweeps left to right once in every 4-second bar, in time with the melody (panned from left ear to right ear).
  The band is the slice being played: the music is the average of that whole column, top to bottom. On a globe it covers only the globe.
- [ ] On the globe datasets, the grey area around the globe is silent and the sweep never wastes time on it (no dead air at the ends of a bar).
- [ ] The map changes at the start of every bar, and the frame label changes with it.
- [ ] Each bar the screen-reader line reads "Movement N of M".

**Test 3. Live matches the download (this is the quality test).** On one dataset: press J and listen, then play the downloaded
track. Do it for at least Night Lights, Ocean and Lightning.
- [ ] Reverb amount and loudness feel alike. Timbre may differ a little.
- [ ] No crackle, clicks or distortion in the live version, even in the busiest dataset (Ocean, Aerosols).
- The live version is built with the same code as the file, so any difference you hear is worth reporting (tell me the dataset).
  The volume slider reaches the file's full level at its maximum; at its default it is about 2 dB quieter.

**Test 4. The datasets sound different from each other.** Listen to 10 seconds of each. What the score contains:

| Dataset | Melody notes per bar (of 16) | Sparkles per bar | You should hear |
|---|---|---|---|
| Night Lights | ~11 | ~1 | mostly sparse; a few bright glints |
| Ocean Currents | 16 | 8 | continuously busy, flowing |
| Aerosols | 16 | 8 | continuously busy, hazy (whole-tone scale) |
| Air Quality | 8 | 4 | medium |
| CO2 | ~6 | ~2-3 | sparse, tense (sawtooth) |
| Lightning | 7-13, varies | ~3 | uneven, rough |
| Forest | ~7 | ~2 | sparse, soft (sine) |

The pad (the long chord underneath) stays on nearly the same note in most datasets. The change over time is in the melody and
sparkles, so do not expect a dramatic arc.
- [ ] You can tell Night Lights, Ocean and Lightning apart blindfolded.

**Test 5. Starting and stopping is safe.**
- [ ] Press J, then J again after 5 s: music stops at once and the map returns.
- [ ] Press J, then switch dataset mid-play: it stops cleanly, nothing keeps playing.
- [ ] Press J twice quickly: no double music.
- [ ] After J ends, move the cursor over the map by hand: the sound is **dry and clear** (no wash). Then press J: lush again.
- [ ] Press *Stop* during J: all sound ends within a moment, even the reverb.

**Test 6. Other modes and devices**
- [ ] J works in Duet mode, and after the *planet's chord* mode.
- [ ] Phone (Chrome Android or Safari iOS): tap *Turn on sound* first, then play. Check there is no stutter on the 50-second tracks.
- [ ] Keyboard only: Tab to the button, Enter plays; `?` lists the keys.
- [ ] Screen reader (NVDA on Windows): hear the movement announcements without them cutting each other off.

**Test 7. Guided tour and planet chord (all 9, including GEOS Aerosols)**
- [ ] *Guided tour* works with one press on every dataset. With several frames it compares the first and last (left ear, right ear).
  With a single picture (Aerosols) it visits three places in it: quietest, busiest, brightest, and says where and how much.
- [ ] *Play the planet's chord* plays a chord on every dataset (a single picture plays one chord and describes it).
- [ ] Tour captions never name a latitude or longitude on a globe or camera view ("upper left of the view" instead).
- [ ] Pressing the tour button again stops it; Next/Previous move between stops.

**Test 8. The new datasets**
- [ ] Perpetual Ocean and Atmospheric River appear in the dataset list with their own picture and a different voice.
- [ ] The *Download this track* button saves a playable file for each of the 9, and *Download all tracks (ZIP)* holds 9 files.
- [ ] How it works → Playlist lists 9 players with descriptions.

**Report back** like this (it makes problems fast to fix):
`Dataset | pass/fail | what you heard or saw | browser/device`. Any red console message, copy it exactly.
