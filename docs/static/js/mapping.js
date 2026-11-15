// mapping.js - the "codebook". Pure functions: data value -> musical parameters.
// No DOM, no Web Audio, so everything here is unit-tested in Node and mirrored
// in Python (pipeline/sonify.py) for the offline WAV renderer.
//
// The rules, in one breath:
//   pitch      = WHERE the value sits on the legend, snapped to a musical scale
//   tension    = HOW EXTREME it is (anomaly: far from centre; or high / low end)
//   roughness  = HOW MUCH the data changes between neighbouring cells
//   pan        = WHERE you are (west -> east)
//   brightness = tension + latitude
//   silence    = NODATA (plus a soft thump so you know you hit it)

export const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],
  lydian: [0, 2, 4, 6, 7, 9, 11],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  majorPent: [0, 2, 4, 7, 9],
  minorPent: [0, 3, 5, 7, 10],
  wholeTone: [0, 2, 4, 6, 8, 10],
};

const NOTE_INDEX = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

export const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
export const clamp01 = (x) => clamp(x, 0, 1);

/** 'A3' -> 57, 'C#4' -> 61, 'Bb2' -> 46 */
export function noteToMidi(name) {
  const m = /^([A-G])([#b]?)(-?\d)$/.exec(name);
  if (!m) throw new Error(`bad note name: ${name}`);
  const acc = m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0;
  return 12 * (parseInt(m[3], 10) + 1) + NOTE_INDEX[m[1]] + acc;
}

const NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];
/** 57 -> 'A3', 61 -> 'C♯4' (display only). */
export const midiToName = (m) => `${NAMES[((m % 12) + 12) % 12]}${Math.floor(m / 12) - 1}`;

export const midiToFreq = (m) => 440 * Math.pow(2, (m - 69) / 12);

/**
 * Normalise a value against the legend.
 * range = { vmin, vmax, center (number|null), scale: 'linear'|'log' }
 * Returns { n: 0..1 across the whole legend, s: -1..1 around centre (or null) }.
 * Positive and negative sides are scaled separately, so an asymmetric legend
 * (e.g. -2..+6) still puts "no change" exactly at the tonic.
 */
export function normalise(v, range) {
  const tr = range.scale === 'log' ? Math.log10 : (x) => x;
  const a = tr(range.vmin);
  const b = tr(range.vmax);
  const x = tr(v);
  const n = clamp01((x - a) / (b - a));
  if (range.center === null || range.center === undefined) return { n, s: null };
  const c = tr(range.center);
  let s;
  if (x >= c) s = b > c ? (x - c) / (b - c) : 0;
  else s = c > a ? -((c - x) / (c - a)) : 0;
  return { n, s: clamp(s, -1, 1) };
}

/** Scale degree (integer, can be negative) for a normalised value. */
export function degreeFor(norm, son) {
  const L = SCALES[son.scale].length;
  const span = son.spanOctaves ?? 3;
  if (norm.s !== null) return Math.round(norm.s * (span / 2) * L); // centred on the tonic
  return Math.round(norm.n * span * L); // tonic = bottom of legend
}

export function degreeToMidi(deg, scaleName, rootMidi) {
  const sc = SCALES[scaleName];
  const L = sc.length;
  const oct = Math.floor(deg / L);
  const idx = ((deg % L) + L) % L;
  return rootMidi + 12 * oct + sc[idx];
}

/** 0..1 "how alarming is this value", per dataset rule. */
export function tensionOf(norm, mode) {
  let x = 0;
  if (mode === 'anomaly') x = norm.s === null ? 0 : Math.abs(norm.s);
  else if (mode === 'high') x = norm.n;
  else if (mode === 'low') x = 1 - norm.n;
  // Only the extreme end of the range gets dissonant; the middle stays calm.
  return clamp01((x - 0.4) / 0.6);
}

/** Partials for one cell. Calm = tonic + fifth + octave; tension adds a tritone then a minor second. */
export function voicing(midi, tension) {
  const parts = [
    { semi: 0, gain: 1.0 },
    { semi: 12, gain: 0.35 },
    { semi: 7, gain: 0.55 * (1 - 0.6 * tension) },
  ];
  if (tension > 0.15) parts.push({ semi: 6, gain: 0.5 * tension });
  if (tension > 0.6) parts.push({ semi: 1, gain: (0.55 * (tension - 0.6)) / 0.4 });
  return parts.map((p) => ({ midi: midi + p.semi, freq: midiToFreq(midi + p.semi), gain: p.gain }));
}

/** Filter cutoff in Hz: tension and latitude (0 = south pole .. 1 = north pole) open the filter. */
export function cutoffFor(tension, lat01) {
  const brightness = clamp01(0.2 + 0.5 * tension + 0.3 * lat01);
  return 500 * Math.pow(2, brightness * 4.5);
}

export const panForCol = (c, cols) => (cols <= 1 ? 0 : (c / (cols - 1) * 2 - 1) * 0.9);

// ---- grid helpers ---------------------------------------------------------
// grid = { rows, cols, data: Float32Array|Array (NaN or null = nodata), extent: {west,south,east,north} }
export function cellValue(grid, r, c) {
  if (r < 0 || c < 0 || r >= grid.rows || c >= grid.cols) return NaN;
  const v = grid.data[r * grid.cols + c];
  return v === null || v === undefined ? NaN : v;
}

/** Spatial roughness: std-dev of normalised values in the 3x3 neighbourhood, scaled 0..1. */
export function localRoughness(grid, r, c, range) {
  const xs = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      const v = cellValue(grid, r + dr, c + dc);
      if (!Number.isNaN(v)) xs.push(normalise(v, range).n);
    }
  }
  if (xs.length < 3) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
  return clamp01(sd / 0.12);
}

export function cellLatLon(grid, r, c) {
  const e = grid.extent;
  return {
    lat: e.north - ((r + 0.5) / grid.rows) * (e.north - e.south),
    lon: e.west + ((c + 0.5) / grid.cols) * (e.east - e.west),
  };
}

const fmtDeg = (x, pos, neg) => `${Math.abs(x).toFixed(0)}° ${x >= 0 ? pos : neg}`;
export const formatLatLon = ({ lat, lon }) => `${fmtDeg(lat, 'N', 'S')}, ${fmtDeg(lon, 'E', 'W')}`;

/** Place name for a cell. Flat maps: latitude/longitude. Globes and camera views: a position in the frame only. */
export function whereLabel(grid, r, c) {
  if (grid.geometry !== 'view') return formatLatLon(cellLatLon(grid, r, c));
  const v = r < grid.rows / 3 ? 'upper' : r < (2 * grid.rows) / 3 ? 'middle' : 'lower';
  const h = c < grid.cols / 3 ? 'left' : c < (2 * grid.cols) / 3 ? 'centre' : 'right';
  return `${v} ${h} of the view`;
}

/** Everything the audio engine needs for one cell. */
export function cellSound(grid, r, c, ds) {
  const v = cellValue(grid, r, c);
  const { lat } = cellLatLon(grid, r, c);
  const pan = panForCol(c, grid.cols);
  if (Number.isNaN(v)) return { silent: true, pan };
  const range = ds.range;
  const norm = normalise(v, range);
  const midi = degreeToMidi(degreeFor(norm, ds.sonification), ds.sonification.scale, noteToMidi(ds.sonification.root));
  const tension = tensionOf(norm, ds.sonification.tension);
  const lat01 = grid.geometry === 'view' ? 0.5 : clamp01((lat + 90) / 180);
  return {
    silent: false,
    value: v,
    midi,
    pan,
    tension,
    roughness: localRoughness(grid, r, c, range),
    cutoff: cutoffFor(tension, lat01),
    partials: voicing(midi, tension),
  };
}

export function formatValue(v, ds) {
  const sign = ds.range.center !== null && ds.range.center !== undefined && v > 0 ? '+' : '';
  const digits = Math.abs(ds.range.vmax - ds.range.vmin) >= 20 ? 0 : Math.abs(ds.range.vmax - ds.range.vmin) >= 2 ? 1 : 2;
  return `${sign}${v.toFixed(digits)} ${ds.unit}`.trim();
}

/** Plain-language description for screen readers and captions. */
export function describeCell(grid, r, c, ds) {
  const where = whereLabel(grid, r, c);
  const v = cellValue(grid, r, c);
  if (Number.isNaN(v)) return `${where}: no data`;
  const norm = normalise(v, ds.range);
  let word = '';
  if (norm.s !== null) {
    const m = Math.abs(norm.s);
    const strength = m < 0.1 ? 'near normal' : m < 0.4 ? 'slightly' : m < 0.75 ? 'clearly' : 'extremely';
    if (m < 0.1) word = strength;
    else word = `${strength} ${norm.s > 0 ? ds.sonification.positiveWord : ds.sonification.negativeWord}`;
  } else {
    word = norm.n < 0.2 ? 'very low' : norm.n < 0.45 ? 'low' : norm.n < 0.7 ? 'moderate' : norm.n < 0.9 ? 'high' : 'very high';
  }
  return `${where}: ${formatValue(v, ds)}, ${word}`;
}

// ---- profiles for scans ---------------------------------------------------
export const rowValues = (grid, r) => Array.from({ length: grid.cols }, (_, c) => cellValue(grid, r, c));
export const colValues = (grid, c) => Array.from({ length: grid.rows }, (_, r) => cellValue(grid, r, c));

/** Mean over longitude for each latitude row, ignoring nodata: north -> south profile. */
export function zonalMean(grid) {
  const out = [];
  for (let r = 0; r < grid.rows; r++) {
    let s = 0;
    let n = 0;
    for (let c = 0; c < grid.cols; c++) {
      const v = cellValue(grid, r, c);
      if (!Number.isNaN(v)) {
        s += v;
        n++;
      }
    }
    out.push(n >= grid.cols * 0.2 ? s / n : NaN);
  }
  return out;
}

/** Sound parameters for a bare value (used by scans and the legend slider). */
export function valueSound(v, ds, { pan = 0, lat01 = 0.5, roughness = 0 } = {}) {
  if (Number.isNaN(v)) return { silent: true, pan };
  const norm = normalise(v, ds.range);
  const midi = degreeToMidi(degreeFor(norm, ds.sonification), ds.sonification.scale, noteToMidi(ds.sonification.root));
  const tension = tensionOf(norm, ds.sonification.tension);
  return { silent: false, value: v, midi, pan, tension, roughness, cutoff: cutoffFor(tension, lat01), partials: voicing(midi, tension) };
}

// ---- The planet's chord ----------------------------------------------------
// A whole map becomes ONE chord: the 10/30/50/70/90th percentile values are five notes
// (through the same pitch rule as every other sound). As a distribution climbs, the chord
// climbs; as it widens, the chord spreads; as its extremes get extreme, tension rises.
export const CHORD_PERCENTILES = [0.1, 0.3, 0.5, 0.7, 0.9];
const CHORD_GAINS = [0.6, 0.8, 1.0, 0.8, 0.6];

/** Percentile of an ASCENDING array, linear interpolation (numpy's default rule). */
export function percentile(sorted, p) {
  if (!sorted.length) return NaN;
  const idx = p * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

/** Sound object for a whole grid, or null if there is too little data. Plays like a slow pad. */
export function planetChord(grid, ds) {
  const vals = [];
  for (const v of grid.data) if (v !== null && v !== undefined && !Number.isNaN(v)) vals.push(v);
  if (vals.length < 10) return null;
  vals.sort((a, b) => a - b);
  const range = ds.range;
  const son = ds.sonification;
  const root = noteToMidi(son.root);
  const percs = CHORD_PERCENTILES.map((p) => percentile(vals, p));
  const norms = percs.map((v) => normalise(v, range));
  const midis = norms.map((n) => degreeToMidi(degreeFor(n, son), son.scale, root));
  const tension = Math.max(...norms.map((n) => tensionOf(n, son.tension)));
  const spread = clamp01(norms[4].n - norms[0].n);
  const byMidi = new Map(); // identical pitches merge (a narrow distribution is a narrow chord)
  midis.forEach((m, i) => byMidi.set(m, (byMidi.get(m) || 0) + CHORD_GAINS[i]));
  const partials = [...byMidi.entries()].sort((a, b) => a[0] - b[0])
    .map(([m, g]) => ({ midi: m, freq: midiToFreq(m), gain: Math.min(g, 1.4) }));
  if (tension > 0.6) {
    const top = partials[partials.length - 1].midi + 1;
    partials.push({ midi: top, freq: midiToFreq(top), gain: (0.5 * (tension - 0.6)) / 0.4 });
  }
  return {
    silent: false, kind: 'chord', pan: 0, midi: midis[2], midis, percentiles: percs, tension, spread,
    roughness: clamp01((spread - 0.15) / 0.6), cutoff: cutoffFor(tension, 0.5), partials,
    attack: 0.35, sustain: true,
  };
}

/** One honest sentence: the actual percentile values behind the chord. */
export function describeChord(chord, ds, label) {
  const f = (v) => formatValue(v, ds);
  const [p10, , p50, , p90] = chord.percentiles;
  return `${label}: the middle of the map is ${f(p50)}. Most places range from ${f(p10)} to ${f(p90)}.`;
}

// ---- The jukebox score ------------------------------------------------------
// One map = one 16-step bar, read west -> east like a playhead:
//   melody  = mean value of each column slice, through the usual pitch rule
//   rhythm  = calm maps play 4 beats; busy (high-spread) maps fill in every step
//   sparkle = an octave-up voice that appears only where a slice mixes low and high values
//   pad     = the planet's chord underneath
/** 5th..95th percentile over every frame of a dataset: lets the melody use the full range without losing change over time. */
export function stretchOf(grids) {
  const vals = [];
  for (const g of grids) for (const v of g.data) if (v !== null && v !== undefined && !Number.isNaN(v)) vals.push(v);
  vals.sort((a, b) => a - b);
  return vals.length < 10 ? null : { lo: percentile(vals, 0.05), hi: percentile(vals, 0.95) };
}

/** First and last column that hold data (>= 10% of rows). A globe's empty sky on either side is skipped. */
export function dataExtent(grid, minFrac = 0.1) {
  const { rows, cols } = grid;
  let first = -1;
  let last = -1;
  for (let c = 0; c < cols; c++) {
    let n = 0;
    for (let r = 0; r < rows; r++) if (!Number.isNaN(cellValue(grid, r, c))) n++;
    if (n >= rows * minFrac) { if (first < 0) first = c; last = c; }
  }
  return first < 0 ? { c0: 0, c1: grid.cols - 1 } : { c0: first, c1: last };
}

/** Columns [from, to) of sweep step s, spread across the data extent. Used by the music and by the on-screen band. */
export function sliceCols(ext, s, steps) {
  const width = ext.c1 - ext.c0 + 1;
  const from = ext.c0 + Math.floor((s / steps) * width);
  return [from, Math.max(from + 1, ext.c0 + Math.floor(((s + 1) / steps) * width))];
}

export function composeBar(grid, ds, steps = 16, stretch = null) {
  const { rows, cols } = grid;
  const wave = ds.sonification.wave;
  const melody = [];
  const sparkle = [];
  const ext = dataExtent(grid);
  for (let s = 0; s < steps; s++) {
    const [c0, c1] = sliceCols(ext, s, steps);
    const vals = [];
    let total = 0;
    for (let c = c0; c < c1; c++) {
      for (let r = 0; r < rows; r++) {
        total++;
        const v = cellValue(grid, r, c);
        if (!Number.isNaN(v)) vals.push(v);
      }
    }
    if (vals.length < total * 0.2) { melody.push({ rest: true }); sparkle.push({ rest: true }); continue; }
    vals.sort((a, b) => a - b);
    const pan = (s / (steps - 1) * 2 - 1) * 0.8;
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const lo = normalise(percentile(vals, 0.1), ds.range).n;
    const hi = normalise(percentile(vals, 0.9), ds.range).n;
    const spread = clamp01((hi - lo) / 0.5);
    const { vmin, vmax } = ds.range;
    const melodic = stretch && stretch.hi > stretch.lo
      ? clamp(vmin + ((mean - stretch.lo) / (stretch.hi - stretch.lo)) * (vmax - vmin), vmin, vmax) : mean;
    melody.push(s % 4 === 0 || spread > 0.15 ? { ...valueSound(melodic, ds, { pan }), wave } : { rest: true });
    if (spread > 0.25 && s % 2 === 1) {
      const top = valueSound(percentile(vals, 0.9), ds, { pan, lat01: 0.9 });
      const midi = top.midi + 12;
      sparkle.push({ ...top, midi, wave, partials: voicing(midi, top.tension) });
    } else sparkle.push({ rest: true });
  }
  const pad = planetChord(grid, ds);
  return { pad: pad ? { ...pad, wave } : { rest: true }, melody, sparkle };
}
