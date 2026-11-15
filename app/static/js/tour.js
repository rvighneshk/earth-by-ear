// tour.js - finds the most striking places in the data and writes honest captions.
// Every number in a caption is read from the grid, nothing is invented.
// Pure functions (no DOM, no audio) so they are unit-tested in Node.

import {
  cellValue, whereLabel, formatValue, normalise, tensionOf,
} from './mapping.js';

/** Legend span in the units used for comparing changes (log10 for log legends). */
export function span(range) {
  return range.scale === 'log' ? Math.log10(range.vmax / range.vmin) : range.vmax - range.vmin;
}

/** Change in "legend units" between two values (log10 ratio for log legends). */
export function changeBetween(a, b, range) {
  if (Number.isNaN(a) || Number.isNaN(b)) return NaN;
  return range.scale === 'log' ? Math.log10(b / a) : b - a;
}

/** Per-cell change B - A, smoothed over a (2k+1)^2 window so single noisy cells cannot win. */
export function smoothedChange(gA, gB, range, k = 2) {
  const { rows, cols } = gB;
  const raw = new Float32Array(rows * cols);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      raw[r * cols + c] = changeBetween(cellValue(gA, r, c), cellValue(gB, r, c), range);
    }
  }
  const out = new Float32Array(rows * cols).fill(NaN);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (Number.isNaN(raw[r * cols + c])) continue;
      let s = 0; let n = 0; let total = 0;
      for (let dr = -k; dr <= k; dr++) {
        for (let dc = -k; dc <= k; dc++) {
          const rr = r + dr; const cc = c + dc;
          if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) continue;
          total++;
          const v = raw[rr * cols + cc];
          if (!Number.isNaN(v)) { s += v; n++; }
        }
      }
      if (n >= total * 0.6) out[r * cols + c] = s / n;
    }
  }
  return { rows, cols, data: out };
}

/** Do the two frames differ anywhere along these cells? Used to explain a "silent" duet. */
export function hasChange(cells, range, minFrac = 0.01) {
  const sp = span(range);
  return cells.some(([a, b]) => Math.abs(changeBetween(a, b, range)) >= minFrac * sp);
}

/** The single place where the (smoothed) change is largest in either direction. */
export function biggestChange(gA, gB, range) {
  const ch = smoothedChange(gA, gB, range);
  let best = null;
  for (let r = 0; r < ch.rows; r++) {
    for (let c = 0; c < ch.cols; c++) {
      const v = ch.data[r * ch.cols + c];
      if (!Number.isNaN(v) && (!best || Math.abs(v) > Math.abs(best.change))) best = { r, c, change: v };
    }
  }
  return best;
}

function pickBest(field, score, taken, minSep) {
  let best = null;
  for (let r = 0; r < field.rows; r++) {
    for (let c = 0; c < field.cols; c++) {
      const v = field.data[r * field.cols + c];
      if (Number.isNaN(v)) continue;
      const s = score(v, r, c);
      if (s === null || s === undefined || Number.isNaN(s)) continue;
      if (taken.some(([tr, tc]) => Math.hypot(tr - r, (tc - c) * 0.5) < minSep)) continue;
      if (!best || s > best.s) best = { r, c, s };
    }
  }
  return best;
}

/**
 * Pick up to `max` stops in a story order: calm -> biggest rise -> biggest fall -> most extreme now.
 * Stops that would be uninteresting (change under 2% of the legend) are skipped.
 */
export function findStops(gA, gB, ds, { minSep = 14, minChangeFrac = 0.02 } = {}) {
  const range = ds.range;
  const sp = span(range);
  const ch = smoothedChange(gA, gB, range);
  const taken = [];
  const stops = [];
  const labelA = ds.labelA ?? 'earlier';
  const labelB = ds.labelB ?? 'later';
  const word = (up) => (up ? ds.sonification.positiveWord : ds.sonification.negativeWord);

  const describeStop = (kind, r, c, headline) => {
    const where = whereLabel(gB, r, c);
    const a = cellValue(gA, r, c); const b = cellValue(gB, r, c);
    return {
      kind, r, c, where,
      title: headline,
      text: `${headline}. ${where}. ${labelA}: ${formatValue(a, ds)}. ${labelB}: ${formatValue(b, ds)}.`,
    };
  };

  // Priority order for PICKING (dramatic stops first, so a calm spot can never crowd them out)...
  const rise = pickBest(ch, (v) => (v >= minChangeFrac * sp ? v : null), taken, minSep);
  if (rise) taken.push([rise.r, rise.c]);
  const fall = pickBest(ch, (v) => (v <= -minChangeFrac * sp ? -v : null), taken, minSep);
  if (fall) taken.push([fall.r, fall.c]);

  // most extreme value in the later frame (what the tension rule treats as most alarming)
  const ext = pickBest(
    { rows: gB.rows, cols: gB.cols, data: gB.data },
    (v) => {
      const n = normalise(v, range);
      const t = tensionOf(n, ds.sonification.tension);
      return t > 0 ? t + 1e-6 * (n.s === null ? n.n : Math.abs(n.s)) : null;
    },
    taken, minSep,
  );
  if (ext) taken.push([ext.r, ext.c]);

  // Calm: where change is smallest. If nowhere is truly unchanged (typical for climate data,
  // where almost everywhere moves) it is "the place that changed least", but only when that is
  // clearly smaller than the dramatic stops, otherwise the contrast would be meaningless.
  const dramatic = Math.max(rise ? rise.s : 0, fall ? fall.s : 0);
  const calmLimit = dramatic > 0 ? 0.4 * dramatic : 0.005 * sp;
  const calm = pickBest(ch, (v, r, c) => {
    if (Math.abs(v) > calmLimit) return null;
    const t = tensionOf(normalise(cellValue(gB, r, c), range), ds.sonification.tension);
    return (t === 0 ? 1 : 0) + (1 - Math.abs(v) / sp);
  }, taken, minSep);
  const calmHeadline = calm && Math.abs(ch.data[calm.r * ch.cols + calm.c]) < 0.005 * sp
    ? 'A place that barely changed' : 'The place that changed least';

  // ...but PRESENT them as a story: calm -> rise -> fall -> extreme.
  if (calm) stops.push(describeStop('calm', calm.r, calm.c, calmHeadline));
  if (rise) stops.push(describeStop('rise', rise.r, rise.c, `Biggest increase: ${word(true)}`));
  if (fall) stops.push(describeStop('fall', fall.r, fall.c, `Biggest decrease: ${word(false)}`));
  if (ext) stops.push(describeStop('extreme', ext.r, ext.c, `Most extreme place in ${labelB}`));
  return stops;
}

/** Shown before the first stop: your story intro (if any) + how to listen, built from dataset facts. */
export function tourIntro(ds, stops) {
  const name = ds.title.replace(/ \(stand-in\)/, '');
  const story = ds.story?.intro ? `${ds.story.intro} ` : '';
  return `${story}${name}. ${ds.labelA ?? 'Earlier'} in your left ear, ${ds.labelB ?? 'later'} in your right. ${stops.length} stops. Same note in both ears means nothing changed. A gap between the ears is the change.`;
}

/** Shown after the last stop: your story outro (if any), then how to keep exploring. */
export function tourOutro(ds) {
  const story = ds.story?.outro ? `${ds.story.outro} ` : '';
  return `${story}That is the end of the tour. Explore on your own with the arrow keys.`;
}

// ---- A tour of ONE picture (datasets with a single frame, nothing to compare against) -----------------------------

/** Spread of the values around a cell (5x5 window), as a fraction of the legend. NaN where the neighbourhood is mostly empty. */
function busyness(g, range, k = 2) {
  const { rows, cols } = g;
  const sp = span(range);
  const out = new Float32Array(rows * cols).fill(NaN);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (Number.isNaN(cellValue(g, r, c))) continue;
      let lo = Infinity; let hi = -Infinity; let n = 0; let total = 0;
      for (let dr = -k; dr <= k; dr++) {
        for (let dc = -k; dc <= k; dc++) {
          const rr = r + dr; const cc = c + dc;
          if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) continue;
          total++;
          const v = cellValue(g, rr, cc);
          if (!Number.isNaN(v)) { n++; lo = Math.min(lo, v); hi = Math.max(hi, v); }
        }
      }
      if (n >= total * 0.6) out[r * cols + c] = (hi - lo) / sp;
    }
  }
  return { rows, cols, data: out };
}

/** Up to three stops in one picture, quiet to loud: the lowest part, the busiest part, the highest part. Captions use only the data. */
export function findStillStops(g, ds, { minSep = 12, minBusy = 0.05 } = {}) {
  const field = { rows: g.rows, cols: g.cols, data: g.data };
  const taken = [];
  const hi = pickBest(field, (v) => v, taken, minSep);
  if (hi) taken.push([hi.r, hi.c]);
  const lo = pickBest(field, (v) => -v, taken, minSep);
  if (lo) taken.push([lo.r, lo.c]);
  const bz = pickBest(busyness(g, ds.range), (v) => (v >= minBusy ? v : null), taken, minSep);
  const make = (kind, p, headline) => {
    const where = whereLabel(g, p.r, p.c);
    return { kind, r: p.r, c: p.c, where, title: headline, text: `${headline}. ${where}: ${formatValue(cellValue(g, p.r, p.c), ds)}.` };
  };
  const stops = [];
  if (lo) stops.push(make('low', lo, `The ${ds.sonification.negativeWord} part of this picture`));
  if (bz) stops.push(make('busy', bz, 'Where the picture is busiest'));
  if (hi) stops.push(make('high', hi, `The ${ds.sonification.positiveWord} part of this picture`));
  return stops;
}

export function tourIntroStill(ds, stops) {
  const name = ds.title.replace(/ \(stand-in\)/, '');
  return `${name}. This is one picture, so the tour compares places inside it. ${stops.length} stops, quietest first. Higher notes mean ${ds.sonification.positiveWord}.`;
}

export function tourOutroStill() {
  return 'That is the end of the tour. Explore on your own with the arrow keys, or press the jukebox button to hear the whole picture.';
}
