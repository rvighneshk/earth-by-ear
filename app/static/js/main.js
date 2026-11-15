import * as M from './mapping.js';
import * as Synth from './synth.js';
import { Engine } from './engine.js';
import { findStops, findStillStops, tourIntro, tourOutro, tourIntroStill, tourOutroStill, biggestChange, hasChange } from './tour.js';

const engine = new Engine();
const $ = (id) => document.getElementById(id);
const el = {
  start: $('start'), status: $('status'), datasets: $('datasets'), desc: $('ds-desc'),
  map: $('map'), canvas: $('canvas'), cursor: $('cursor'), readout: $('readout'),
  frameA: $('frame-a'), frameB: $('frame-b'), lblA: $('lbl-a'), lblBDuet: $('lbl-b-duet'),
  slider: $('legend-slider'), strip: $('strip'), endLow: $('end-low'), endHigh: $('end-high'),
  volume: $('volume'), speak: $('speak'),
  credit: $('ds-credit'), creditRow: $('credit-row'),
  timelapse: $('timelapse'), jukebox: $('jukebox'), sweep: $('sweep'), chord: $('now-chord'), vibrate: $('vibrate'),
  orig: $('orig'), showOrig: $('show-orig'), tour: $('tour'), tourNav: $('tour-nav'), tourDots: $('tour-dots'),
  where: $('now-where'), delta: $('now-delta'), tension: $('now-tension'),
  chipA: chipEls('a'), chipB: chipEls('b'),
};
function chipEls(k) {
  return {
    box: $(`now-${k}`), ear: $(`now-${k}-ear`), label: $(`now-${k}-label`),
    sw: $(`now-${k}-sw`), val: $(`now-${k}-value`), note: $(`now-${k}-note`),
  };
}

const state = {
  index: null, ds: null, gridA: null, gridB: null, mode: 'explore',
  cur: { r: 0, c: 0 }, speak: false, scan: null, scanTimer: null, lastCell: '', readoutTimer: null,
  tour: { active: false, stops: [], i: -1, timer: null },
  lapse: { active: false, timers: [], grids: [], prevB: null }, vibrate: false,
};
const gridCache = new Map();
// All data URLs are resolved relative to this file, so the app works at any path
// (site root, a GitHub Pages /repo-name/ subpath, a file server...).
const DATA_BASE = new URL('../data/', import.meta.url);
const dataUrl = (rel) => new URL(rel, DATA_BASE).href;

// ---------- loading ----------
async function loadGrid(ds, frame) {
  if (gridCache.has(frame.url)) return gridCache.get(frame.url);
  const res = await fetch(dataUrl(frame.url));
  if (!res.ok) throw new Error(`Could not load ${frame.url}`);
  const j = await res.json();
  const g = {
    rows: j.rows, cols: j.cols, extent: ds.extent, geometry: ds.geometry,
    data: Float32Array.from(j.data, (v) => (v === null ? NaN : v)),
  };
  gridCache.set(frame.url, g);
  return g;
}

async function init() {
  try {
    const res = await fetch(dataUrl('index.json'));
    state.index = await res.json();
  } catch (e) {
    say('Could not load the data. Run the pipeline build step first.');
    return;
  }
  el.datasets.innerHTML = '';
  state.index.datasets.forEach((ds, i) => {
    const label = document.createElement('label');
    const palette = ds.palette || ['#111827','#374151','#6b7280','#9ca3af','#d1d5db','#f9fafb'];
    const grad = `linear-gradient(90deg, ${palette.filter((_, k) => k % 6 === 0).join(',')})`;
    label.innerHTML = `<input type="radio" name="dataset" value="${ds.id}"><i class="sw" style="background:${grad}"></i><span class="t"></span>`;
    label.querySelector('span').textContent = ds.title.replace(/ \(stand-in\)/, '');
    label.querySelector('input').addEventListener('change', () => selectDataset(i));
    el.datasets.append(label);
  });
  if (!state.index.datasets.length) {
    el.start.disabled = true;
    say('No NASA visualization imported yet. Follow README.md → download an SVS media file → run pipeline.import_svs_media.');
    el.desc.textContent = 'This clean build contains no synthetic sample datasets. Import a challenge-listed NASA SVS resource to begin';
    return;
  }
  document.querySelectorAll('[data-quick]').forEach((b) => { b.hidden = !state.index.datasets.some((d) => d.id === b.dataset.quick); });
  await selectDataset(0);
}

/** One click from the front page: turn the sound on, pick the dataset and perform it. */
async function quickPlay(id) {
  const i = state.index?.datasets.findIndex((d) => d.id === id);
  if (i === undefined || i < 0) return;
  if (!engine.ready) {
    const ok = await engine.start();
    el.status.textContent = ok ? 'Sound is on.' : 'Your browser blocked sound. Try again.';
    el.start.textContent = ok ? 'Sound on' : 'Turn on sound';
    if (!ok) return;
    el.status.classList.add('on');
  }
  await selectDataset(i);
  document.querySelector('.stage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });   // so the sweep is on screen
  startJukebox();
}
document.querySelectorAll('[data-quick]').forEach((b) => b.addEventListener('click', () => quickPlay(b.dataset.quick)));

async function selectDataset(i) {
  stopPlaying();
  const ds = state.index.datasets[i];
  state.ds = ds;
  el.datasets.querySelectorAll('input')[i].checked = true;
  for (const sel of [el.frameA, el.frameB]) {
    sel.innerHTML = '';
    ds.frames.forEach((f, k) => sel.append(new Option(f.label, String(k))));
  }
  el.frameA.value = '0';
  el.frameB.value = String(ds.frames.length - 1);
  el.desc.textContent = ds.description;
  // downloads: this dataset's track, and the whole playlist
  const dl = $('dl-track'); const dlAll = $('dl-all');
  dl.hidden = dlAll.hidden = !ds.audio;
  if (ds.audio) {
    dl.href = new URL(`../${ds.audio.file}`, import.meta.url).href;
    dl.setAttribute('download', ds.audio.file.split('/').pop());
    dl.textContent = `Download this track (${ds.audio.file.split('.').pop().toUpperCase()}, ${Math.round(ds.audio.seconds)} s)`;
    dlAll.href = new URL('../audio/earth-jukebox-playlist.zip', import.meta.url).href;
  }
  $('scan-pole').textContent = ds.geometry === 'view' ? 'Top to bottom' : 'Pole to pole';
  el.creditRow.hidden = !ds.credit;
  if (ds.credit) {
    el.credit.textContent = ds.credit.text;
    el.credit.setAttribute('href', ds.credit.url || '#');
  }
  el.endLow.textContent = `${ds.range.vmin} ${ds.unit}`;
  el.endHigh.textContent = `${ds.range.vmax} ${ds.unit}`;
  const stops = (ds.palette || ['#111827','#374151','#6b7280','#9ca3af','#d1d5db','#f9fafb']).join(',');
  el.strip.style.background = `linear-gradient(to right, ${stops})`;
  await loadFrames();
  state.cur = { r: Math.floor(state.gridB.rows / 2), c: Math.floor(state.gridB.cols / 2) };
  draw();
  placeCursor();
  say(`${ds.title}. ${state.gridB.cols} by ${state.gridB.rows} cells. Use the arrow keys on the map.`);
}

async function loadFrames() {
  const ds = state.ds;
  state.gridA = await loadGrid(ds, ds.frames[+el.frameA.value]);
  state.gridB = await loadGrid(ds, ds.frames[+el.frameB.value]);
  updateOriginal();
}
state.frameSame = () => el.frameA.value === el.frameB.value;

function updateOriginal() {
  const on = el.showOrig.checked;
  const f = state.ds.frames[+el.frameB.value];
  el.orig.hidden = !on || !f.image;
  el.canvas.hidden = on && !!f.image;
  if (on && f.image) el.orig.src = dataUrl(f.image);
}

// ---------- drawing ----------
function hexToRgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}

function draw() {
  const g = state.gridB;
  const pal = state.ds.palette.map(hexToRgb);
  el.canvas.width = g.cols;
  el.canvas.height = g.rows;
  const ctx = el.canvas.getContext('2d');
  const img = ctx.createImageData(g.cols, g.rows);
  for (let i = 0; i < g.data.length; i++) {
    const v = g.data[i];
    const o = i * 4;
    if (Number.isNaN(v)) {
      img.data.set([150, 150, 150, 255], o);
    } else {
      const n = M.normalise(v, state.ds.range).n;
      img.data.set([...pal[Math.round(n * (pal.length - 1))], 255], o);
    }
  }
  ctx.putImageData(img, 0, 0);
  el.canvas.setAttribute('aria-hidden', 'true');
}

function placeCursor() {
  const g = state.gridB;
  el.cursor.style.left = `${((state.cur.c + 0.5) / g.cols) * 100}%`;
  el.cursor.style.top = `${((state.cur.r + 0.5) / g.rows) * 100}%`;
  // sonar ripple: restart the CSS animation on every move
  el.cursor.classList.remove('ping');
  void el.cursor.offsetWidth;
  el.cursor.classList.add('ping');
  updateNow();
}

// ---------- "Now playing" card: swatch -> number -> note ----------
function swatchFor(v) {
  if (Number.isNaN(v)) return '#8a8a8a';
  const pal = state.ds.palette;
  return pal[Math.round(M.normalise(v, state.ds.range).n * (pal.length - 1))];
}

function fillChip(chip, grid, label, ear) {
  const { r, c } = state.cur;
  const s = M.cellSound(grid, r, c, state.ds);
  chip.label.textContent = label;
  chip.ear.textContent = ear;
  if (s.silent) {
    chip.val.textContent = 'No data';
    chip.note.textContent = 'silence';
    chip.sw.style.background = swatchFor(NaN);
    return s;
  }
  chip.val.textContent = M.formatValue(s.value, state.ds);
  chip.note.textContent = M.midiToName(s.midi);
  chip.sw.style.background = swatchFor(s.value);
  return s;
}

function updateNow() {
  if (!state.gridB || !state.ds) return;
  const { r, c } = state.cur;
  const ds = state.ds;
  const duet = state.mode === 'duet';
  const la = ds.frames[+el.frameA.value].label;
  const lb = ds.frames[+el.frameB.value].label;
  el.chipA.box.hidden = !duet;
  const sB = fillChip(el.chipB, state.gridB, lb, duet ? 'Right ear' : 'You hear');
  const sA = duet ? fillChip(el.chipA, state.gridA, la, 'Left ear') : null;
  const a = M.cellValue(state.gridA, r, c);
  const b = M.cellValue(state.gridB, r, c);
  if (duet && !Number.isNaN(a) && !Number.isNaN(b)) {
    const d = b - a;
    const span = ds.range.vmax - ds.range.vmin;
    const digits = Math.abs(span) >= 20 ? 0 : 1;
    el.delta.textContent = Math.abs(d) < span * 0.01
      ? 'Same in both ears: no change'
      : `Change ${d > 0 ? '+' : ''}${d.toFixed(digits)} ${ds.unit}`;
    el.delta.hidden = false;
  } else {
    el.delta.hidden = true;
  }
  const t = Math.max(sB.silent ? 0 : sB.tension, sA && !sA.silent ? sA.tension : 0);
  el.tension.style.clipPath = `inset(0 ${100 - Math.round(t * 100)}% 0 0)`;
  el.where.textContent = M.whereLabel(state.gridB, r, c);
}

// ---------- speech / readout ----------
function say(text) {
  clearTimeout(state.readoutTimer);
  state.readoutTimer = setTimeout(() => {
    el.readout.textContent = text; // aria-live region: screen readers announce this
    if (state.speak && 'speechSynthesis' in window) {
      speechSynthesis.cancel();
      speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    }
  }, 120);
}

function describe(r, c) {
  const ds = state.ds;
  if (state.mode === 'duet') {
    const a = M.cellValue(state.gridA, r, c);
    const b = M.cellValue(state.gridB, r, c);
    const where = M.whereLabel(state.gridB, r, c);
    const la = ds.frames[+el.frameA.value].label;
    const lb = ds.frames[+el.frameB.value].label;
    if (Number.isNaN(a) || Number.isNaN(b)) return `${where}: no data in one of the two times`;
    const d = b - a;
    const sign = d > 0 ? '+' : '';
    const digits = Math.abs(ds.range.vmax - ds.range.vmin) >= 20 ? 0 : 1;
    const dir = Math.abs(d) < (ds.range.vmax - ds.range.vmin) * 0.01 ? 'no real change' : `change ${sign}${d.toFixed(digits)} ${ds.unit}`;
    return `${where}: ${la} ${M.formatValue(a, ds)}, ${lb} ${M.formatValue(b, ds)}, ${dir}`;
  }
  return M.describeCell(state.gridB, r, c, ds);
}

// ---------- playing ----------
function ensureAudio() {
  if (engine.ready) return true;
  say('Sound is off. Press the Turn on sound button first.');
  return false;
}

function soundsAt(r, c) {
  return { a: M.cellSound(state.gridA, r, c, state.ds), b: M.cellSound(state.gridB, r, c, state.ds) };
}

function playCell(r, c, { force = false } = {}) {
  if (!engine.ready) return;
  if (!force && !engine.allow(60)) return;
  const s = soundsAt(r, c);
  if (state.mode === 'duet') engine.playDuet(s.a, s.b, { dur: 0.55 });
  else engine.play(s.b, { dur: 0.55 });
  haptic(Math.max(s.b.silent ? 0 : s.b.tension, state.mode === 'duet' && !s.a.silent ? s.a.tension : 0), s.b.silent);
}

// Tactile feedback (brief: "tactile feedback"). Stronger buzz = more tension; a short tick = no data.
// Works on Android browsers; iOS Safari does not support vibration.
function haptic(tension, silent) {
  if (!state.vibrate || typeof navigator === 'undefined' || !navigator.vibrate) return;
  navigator.vibrate(silent ? 8 : Math.round(15 + 70 * tension));
}

function moveTo(r, c, { announce = true, force = false, keepTour = false } = {}) {
  const g = state.gridB;
  r = M.clamp(r, 0, g.rows - 1);
  c = M.clamp(c, 0, g.cols - 1);
  const key = `${r},${c}`;
  if (key === state.lastCell && !force) return;
  state.lastCell = key;
  state.cur = { r, c };
  placeCursor();
  stopPlaying({ keepTour });
  playCell(r, c, { force: true });
  if (announce) {
    let text = describe(r, c);
    if (!engine.ready && !state.hintedSound) {
      state.hintedSound = true;
      text += ' Sound is off. Press the Turn on sound button to hear it.';
    }
    say(text);
  }
}

function stopPlaying({ keepTour = false } = {}) {
  engine.stopAll();
  clearInterval(state.scanTimer);
  state.scan = null;
  if (!keepTour) { endTour(); endTimelapse(); }
}

// ---------- duet helpers, jump, guided tour ----------
function datasetWithLabels() {
  const ds = state.ds;
  return { ...ds, labelA: ds.frames[+el.frameA.value].label, labelB: ds.frames[+el.frameB.value].label };
}

function jumpToBiggestChange() {
  if (!ensureAudio()) return;
  if (state.mode !== 'duet') setMode('duet', { quiet: true });
  const big = biggestChange(state.gridA, state.gridB, state.ds.range);
  if (!big) { say('There is no place with data in both times.'); return; }
  moveTo(big.r, big.c, { force: true });
}

function renderDots(cur) {
  const n = state.tour.stops.length;
  el.tourDots.innerHTML = state.tour.active
    ? Array.from({ length: n }, (_, i) => `<span class="dot${i === cur ? ' on' : i < cur ? ' done' : ''}"></span>`).join('')
    : '';
}

function endTour() {
  clearTimeout(state.tour.timer);
  state.tour.active = false;
  renderDots(-1);
  el.tour.textContent = 'Take the guided tour';
  el.tourNav.hidden = true;
}

function startStillTour() {
  setMode('explore', { quiet: true });
  const ds = state.ds;
  const stops = findStillStops(state.gridB, ds);
  if (!stops.length) { say('There is not enough data in this picture for a tour.'); return; }
  state.tour = { active: true, stops, i: -1, timer: null, still: true };
  el.tour.textContent = 'Stop the tour';
  el.tourNav.hidden = false;
  renderDots(-1);
  say(tourIntroStill(ds, stops));
  state.tour.timer = setTimeout(() => goToStop(0), 5500);
}

async function startTour() {
  if (state.tour.active) { stopPlaying(); say('Tour stopped.'); return; }
  if (!ensureAudio()) return;
  stopPlaying();
  const n = state.ds.frames.length;
  if (n < 2) { startStillTour(); return; }                       // one picture: tour the places inside it
  if (state.frameSame()) {                                       // one press is enough: first frame against the last
    el.frameA.value = '0';
    el.frameB.value = String(n - 1);
    await loadFrames();
  }
  setMode('duet', { quiet: true });
  const ds = datasetWithLabels();
  const stops = findStops(state.gridA, state.gridB, ds);
  if (!stops.length) { say('These two times look almost identical. Pick times further apart.'); return; }
  state.tour = { active: true, stops, i: -1, timer: null };
  el.tour.textContent = 'Stop the tour';
  el.tourNav.hidden = false;
  renderDots(-1);
  say(tourIntro(ds, stops));
  state.tour.timer = setTimeout(() => goToStop(0), 6500);
}

function goToStop(i) {
  const t = state.tour;
  if (!t.active) return;
  clearTimeout(t.timer);
  if (i < 0) i = 0;
  if (i >= t.stops.length) {
    say(t.still ? tourOutroStill() : tourOutro(datasetWithLabels()));
    endTour();
    return;
  }
  t.i = i;
  renderDots(i);
  const s = t.stops[i];
  moveTo(s.r, s.c, { announce: false, force: true, keepTour: true });
  say(`Stop ${i + 1} of ${t.stops.length}. ${s.text}`);
  // replay the pair of notes so the contrast between ears sinks in
  setTimeout(() => t.active && t.i === i && playCell(s.r, s.c, { force: true }), 1800);
  setTimeout(() => t.active && t.i === i && playCell(s.r, s.c, { force: true }), 3600);
  t.timer = setTimeout(() => goToStop(i + 1), 11000);
}

function runScan(kind) {
  if (!ensureAudio()) return;
  stopPlaying();
  const { gridA, gridB, ds, mode } = state;
  const { r, c } = state.cur;
  const duet = mode === 'duet';
  const view = gridB.geometry === 'view';
  let n; let at; let stepMs; let label;
  if (kind === 'row') {
    n = gridB.cols; stepMs = 130; at = (i) => [r, i];
    label = view ? 'Scanning across the view, left to right.' : `Scanning ${M.formatLatLon(M.cellLatLon(gridB, r, 0)).split(',')[0]}, west to east.`;
  } else if (kind === 'col') {
    n = gridB.rows; stepMs = 110; at = (i) => [i, c];
    label = view ? 'Scanning down the view, top to bottom.' : `Scanning ${M.formatLatLon(M.cellLatLon(gridB, 0, c)).split(', ')[1]}, north to south.`;
  } else {
    n = gridB.rows; stepMs = 110; at = (i) => [i, -1];
    label = view ? 'Top to bottom: average of each row.' : 'Pole to pole: average of each latitude, north to south.';
  }
  let sounds;
  if (kind === 'pole') {
    const zA = M.zonalMean(gridA); const zB = M.zonalMean(gridB);
    const mk = (z, i) => M.valueSound(z[i], ds, { pan: 0, lat01: M.clamp01(1 - i / (n - 1)) });
    sounds = Array.from({ length: n }, (_, i) => (duet ? [mk(zA, i), mk(zB, i)] : mk(zB, i)));
  } else {
    sounds = Array.from({ length: n }, (_, i) => {
      const [rr, cc] = at(i);
      return duet ? [M.cellSound(gridA, rr, cc, ds), M.cellSound(gridB, rr, cc, ds)] : M.cellSound(gridB, rr, cc, ds);
    });
  }
  if (duet && kind !== 'pole') {
    const pairs = Array.from({ length: n }, (_, i) => { const [rr, cc] = at(i); return [M.cellValue(gridA, rr, cc), M.cellValue(gridB, rr, cc)]; });
    if (!hasChange(pairs, ds.range)) {
      label += ' Both times are the same along this line, so you will hear one voice in the middle. Try Jump to biggest change.';
    }
  }
  say(label);
  const handle = engine.scan(sounds, { stepMs });
  state.scan = handle;
  let i = 0;
  state.scanTimer = setInterval(() => {
    if (i >= n) { clearInterval(state.scanTimer); say('Scan finished.'); return; }
    if (kind !== 'pole') { const [rr, cc] = at(i); state.cur = { r: rr, c: cc }; placeCursor(); }
    i++;
  }, stepMs);
}

function playColorbar() {
  if (!ensureAudio()) return;
  stopPlaying();
  const ds = state.ds;
  const sounds = Array.from({ length: 24 }, (_, i) => M.valueSound(valueAt(i / 23), ds, { pan: 0 }));
  say(`Colorbar from ${ds.range.vmin} to ${ds.range.vmax} ${ds.unit}, low to high.`);
  state.scan = engine.scan(sounds, { stepMs: 170 });
}

function valueAt(t) {
  const { vmin, vmax, scale } = state.ds.range;
  return scale === 'log' ? vmin * Math.pow(vmax / vmin, t) : vmin + (vmax - vmin) * t;
}

// ---------- the planet's chord: every frame as one chord ----------
const LAPSE_STEP_MS = 2400;

function showLapseYear(i) {
  const L = state.lapse;
  if (!L.active) return;
  const ds = state.ds;
  el.frameB.value = String(i);
  state.gridB = L.grids[i];
  draw();
  updateOriginal();
  updateNow();
  const label = ds.frames[i].label;
  const text = M.describeChord(L.chords[i], ds, label);
  const [p10, , p50, , p90] = L.chords[i].percentiles;
  el.chord.textContent = `${label} · low ${M.formatValue(p10, ds)} · mid ${M.formatValue(p50, ds)} · high ${M.formatValue(p90, ds)}`;
  el.chord.hidden = false;
  el.tourDots.innerHTML = L.grids.map((_, k) => `<span class="dot${k === i ? ' on' : k < i ? ' done' : ''}"></span>`).join('');
  say(text);
}

async function startTimelapse() {
  if (state.lapse.active) { stopPlaying(); say('Time-lapse stopped.'); return; }
  if (!ensureAudio()) return;
  const ds = state.ds;
  stopPlaying();
  if (ds.frames.length < 2) {                                    // one picture: play its chord once
    const g = await loadGrid(ds, ds.frames[0]);
    const chord = M.planetChord(g, ds);
    if (!chord) { say('There is not enough data in this picture to build a chord.'); return; }
    state.scan = engine.scan([chord], { stepMs: 3600, noteDur: 3.4, level: 0.3 });
    say(`The planet's chord. The whole picture as one chord. ${M.describeChord(chord, ds, ds.frames[0].label)}`);
    return;
  }
  const grids = await Promise.all(ds.frames.map((f) => loadGrid(ds, f)));
  const chords = grids.map((g) => M.planetChord(g, ds));
  if (chords.some((c) => !c)) { say('There is not enough data in every frame to build a chord.'); return; }
  if (state.mode !== 'explore') setMode('explore', { quiet: true });
  state.lapse = { active: true, timers: [], grids, chords, prevB: el.frameB.value, prevGrid: state.gridB };
  el.timelapse.textContent = 'Stop the time-lapse';
  say(`The planet's chord. Each frame's whole map becomes one chord. Listen for it to move.`);
  state.scan = engine.scan(chords, { stepMs: LAPSE_STEP_MS, noteDur: 3.4, level: 0.3 });
  chords.forEach((_, i) => state.lapse.timers.push(setTimeout(() => showLapseYear(i), 60 + i * LAPSE_STEP_MS)));
  state.lapse.timers.push(setTimeout(() => finishTimelapse(), 60 + chords.length * LAPSE_STEP_MS + 2200));
}

function finishTimelapse() {
  const L = state.lapse;
  if (!L.active) return;
  const ds = state.ds;
  const first = L.chords[0].percentiles[2];
  const last = L.chords[L.chords.length - 1].percentiles[2];
  const a = ds.frames[0].label; const b = ds.frames[ds.frames.length - 1].label;
  endTimelapse();
  say(`That was the planet's chord. The middle of the map moved from ${M.formatValue(first, ds)} in ${a} to ${M.formatValue(last, ds)} in ${b}.`);
}

function endTimelapse() {
  const L = state.lapse;
  if (!L.active) return;
  L.timers.forEach(clearTimeout);
  L.active = false;
  el.timelapse.textContent = "Play the planet's chord";
  el.jukebox.textContent = 'Play this visualization';
  engine.stopRendered();
  el.cursor.style.visibility = '';
  el.sweep.classList.remove('on');
  el.chord.hidden = true;
  el.tourDots.innerHTML = '';
  el.frameB.value = L.prevB;           // put the map back to what the person had selected
  state.gridB = L.prevGrid;
  draw();
  updateOriginal();
  updateNow();
}

// ---------- the jukebox: a composed performance of the whole visualization ----------
const BAR_MS = 4000;
const STEPS = 16;
let jukeToken = 0;

/** Build the whole performance in the browser: same synthesis, mix and room reverb as the downloadable tracks. */
async function renderPerformance(bars) {
  const sr = engine.ctx.sampleRate;
  const { L, R } = Synth.mixPerformance(bars, { sr, barSec: BAR_MS / 1000, steps: STEPS });
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const off = new Offline(2, L.length, sr);
  const dry = off.createBuffer(2, L.length, sr);
  dry.copyToChannel(L, 0);
  dry.copyToChannel(R, 1);
  const ir = off.createBuffer(2, Math.floor(sr * 2), sr);
  Synth.makeImpulse(sr).forEach((d, ch) => ir.copyToChannel(d, ch));
  const src = off.createBufferSource();
  src.buffer = dry;
  const room = off.createConvolver();
  room.normalize = false;            // keep the reverb's real energy (the browser's default shrinks it ~46 dB)
  room.buffer = ir;
  const wet = off.createGain();
  wet.gain.value = 0.22;
  src.connect(off.destination);
  src.connect(room).connect(wet).connect(off.destination);
  src.start();
  const buffer = await off.startRendering();
  let peak = 0;
  for (let ch = 0; ch < 2; ch++) for (const v of buffer.getChannelData(ch)) if (Math.abs(v) > peak) peak = Math.abs(v);
  return { buffer, gain: peak > 0 ? 0.85 / peak : 1 };
}

function sweepBand(g, s) {
  const [from, to] = M.sliceCols(M.dataExtent(g), s, STEPS);
  el.sweep.style.left = `${(from / g.cols) * 100}%`;
  el.sweep.style.width = `${((to - from) / g.cols) * 100}%`;
  state.cur = { r: Math.floor(g.rows / 2), c: Math.floor((from + to - 1) / 2) };
  placeCursor();
}

async function startJukebox() {
  if (state.lapse.active || state.preparing) { jukeToken++; state.preparing = false; stopPlaying(); say('Jukebox stopped.'); return; }
  if (!ensureAudio()) return;
  stopPlaying();
  const token = ++jukeToken;
  const ds = state.ds;
  state.preparing = true;
  el.jukebox.textContent = 'Preparing the performance...';
  say('Preparing the performance.');
  const loaded = await Promise.all(ds.frames.map((f) => loadGrid(ds, f)));
  const grids = loaded.length > 1 ? loaded : Array(4).fill(loaded[0]); // a single still loops four bars
  const stretch = M.stretchOf(grids);
  const bars = grids.map((g) => M.composeBar(g, ds, STEPS, stretch));
  await new Promise((r) => setTimeout(r, 30));                         // let the screen update before the heavy part
  const { buffer, gain } = await renderPerformance(bars);
  if (token !== jukeToken || state.ds !== ds) { state.preparing = false; el.jukebox.textContent = 'Play this visualization'; return; }
  state.preparing = false;
  if (state.mode !== 'explore') setMode('explore', { quiet: true });
  state.lapse = { active: true, timers: [], grids, chords: [], prevB: el.frameB.value, prevGrid: state.gridB };
  el.jukebox.textContent = 'Stop the music';
  el.cursor.style.visibility = 'hidden';
  el.sweep.classList.add('on');
  engine.playRendered(buffer, gain);
  const stepMs = BAR_MS / STEPS;
  const at = (ms, fn) => state.lapse.timers.push(setTimeout(fn, ms));
  grids.forEach((g, i) => {
    at(i * BAR_MS, () => {
      el.frameB.value = String(Math.min(i, ds.frames.length - 1));
      state.gridB = g; draw(); updateOriginal();
      const chord = bars[i].pad.rest ? null : M.planetChord(g, ds);
      const label = ds.frames[Math.min(i, ds.frames.length - 1)].label;
      say(chord ? `Movement ${i + 1} of ${grids.length}. ${M.describeChord(chord, ds, label)}` : `Movement ${i + 1} of ${grids.length}.`);
    });
    for (let s = 0; s < STEPS; s++) at(i * BAR_MS + s * stepMs, () => sweepBand(g, s));
  });
  at(buffer.duration * 1000, () => { endTimelapse(); say('The performance is over.'); });
}

// ---------- events ----------
el.start.addEventListener('click', async () => {
  const ok = await engine.start();
  el.status.textContent = ok ? 'Sound is on.' : 'Your browser blocked sound. Try again.';
  el.start.textContent = ok ? 'Sound on' : 'Turn on sound';
  if (ok) el.status.classList.add('on');
  if (ok) { el.map.focus(); playCell(state.cur.r, state.cur.c, { force: true }); }
});

document.querySelectorAll('input[name=mode]').forEach((r) => r.addEventListener('change', () => setMode(r.value)));
function setMode(mode, { quiet = false } = {}) {
  state.mode = mode;
  document.querySelector(`input[name=mode][value=${mode}]`).checked = true;
  el.lblA.hidden = mode !== 'duet';
  el.lblBDuet.hidden = mode !== 'duet';
  updateNow();
  if (quiet) return;
  say(mode === 'duet'
    ? `Duet. ${state.ds.frames[+el.frameA.value].label} in your left ear, ${state.ds.frames[+el.frameB.value].label} in your right.`
    : 'Explore one map.');
}
for (const sel of [el.frameA, el.frameB]) {
  sel.addEventListener('change', async () => { endTour(); await loadFrames(); draw(); updateNow(); say(describe(state.cur.r, state.cur.c)); });
}

el.map.addEventListener('keydown', (e) => {
  const { r, c } = state.cur;
  const big = e.shiftKey ? 10 : 1;
  const handled = {
    ArrowUp: () => moveTo(r - big, c), ArrowDown: () => moveTo(r + big, c),
    ArrowLeft: () => moveTo(r, c - big), ArrowRight: () => moveTo(r, c + big),
    Home: () => moveTo(r, 0), End: () => moveTo(r, state.gridB.cols - 1),
    PageUp: () => moveTo(r - 15, c), PageDown: () => moveTo(r + 15, c),
    ' ': () => { if (ensureAudio()) { stopPlaying(); playCell(r, c, { force: true }); say(describe(r, c)); } },
    Enter: () => { if (ensureAudio()) { stopPlaying(); playCell(r, c, { force: true }); say(describe(r, c)); } },
    r: () => runScan('row'), c: () => runScan('col'), p: () => runScan('pole'),
    d: () => setMode(state.mode === 'explore' ? 'duet' : 'explore'),
    t: startTour, n: () => state.tour.active && goToStop(state.tour.i + 1), b: () => state.tour.active && goToStop(state.tour.i - 1),
    g: jumpToBiggestChange, l: startTimelapse, j: startJukebox,
    s: toggleSpeech, Escape: stopPlaying,
    '?': () => { $('keys').open = true; $('keys').scrollIntoView({ block: 'nearest' }); },
  }[e.key];
  const digit = /^[1-9]$/.test(e.key) ? () => { const i = +e.key - 1; if (state.index.datasets[i]) selectDataset(i); } : null;
  const fn = handled || digit;
  if (!fn) return;
  e.preventDefault();
  if (!engine.ready && /^Arrow|^Home|^End|^Page/.test(e.key)) ensureAudio();
  fn();
});

function cellFromPointer(e) {
  const b = el.map.getBoundingClientRect();
  const g = state.gridB;
  return [
    Math.floor(((e.clientY - b.top) / b.height) * g.rows),
    Math.floor(((e.clientX - b.left) / b.width) * g.cols),
  ];
}
el.map.addEventListener('pointerdown', (e) => { el.map.setPointerCapture(e.pointerId); el.map.focus(); const [r, c] = cellFromPointer(e); moveTo(r, c, { force: true }); });
el.map.addEventListener('pointermove', (e) => {
  if (!engine.ready) return;
  const [r, c] = cellFromPointer(e);
  moveTo(r, c);
});

el.slider.addEventListener('input', () => {
  const ds = state.ds; const v = valueAt(el.slider.value / 100);
  const txt = M.formatValue(v, ds);
  el.slider.setAttribute('aria-valuetext', txt);
  if (engine.ready && engine.allow(70)) engine.play(M.valueSound(v, ds, { pan: 0 }), { dur: 0.45 });
  say(txt);
});

$('scan-row').addEventListener('click', () => runScan('row'));
$('scan-col').addEventListener('click', () => runScan('col'));
$('scan-pole').addEventListener('click', () => runScan('pole'));
$('play-bar').addEventListener('click', playColorbar);
$('stop').addEventListener('click', () => stopPlaying());
$('jump-change').addEventListener('click', jumpToBiggestChange);
el.tour.addEventListener('click', startTour);
el.timelapse.addEventListener('click', startTimelapse);
el.jukebox.addEventListener('click', startJukebox);
el.vibrate.addEventListener('change', () => {
  state.vibrate = el.vibrate.checked;
  if (state.vibrate && !(typeof navigator !== 'undefined' && navigator.vibrate)) {
    state.vibrate = false;
    el.vibrate.checked = false;
    say('This browser does not support vibration. Android Chrome does; iPhones do not.');
  } else if (state.vibrate) {
    navigator.vibrate(60);
  }
});
$('tour-next').addEventListener('click', () => goToStop(state.tour.i + 1));
$('tour-prev').addEventListener('click', () => goToStop(state.tour.i - 1));
el.showOrig.addEventListener('change', updateOriginal);
el.volume.addEventListener('input', () => engine.setVolume(el.volume.value / 100));
function toggleSpeech() { state.speak = !state.speak; el.speak.checked = state.speak; say(state.speak ? 'Spoken readouts on.' : 'Spoken readouts off.'); }
el.speak.addEventListener('change', () => { state.speak = el.speak.checked; });

init();
