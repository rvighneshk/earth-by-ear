// Prints the jukebox score (MIDI numbers per step) for every dataset, as JSON. Used by test_crosslang.py.
import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
const here = path.dirname(fileURLToPath(import.meta.url));
const M = await import(path.join(here, '../app/static/js/mapping.js'));
const base = path.join(here, '../app/static/data/');
const idx = JSON.parse(fs.readFileSync(base + 'index.json'));
const out = {};
for (const ds of idx.datasets) {
  const grids = ds.frames.map((f) => {
    const j = JSON.parse(fs.readFileSync(base + f.url));
    return { rows: j.rows, cols: j.cols, extent: ds.extent, geometry: ds.geometry, data: Float32Array.from(j.data, (v) => (v === null ? NaN : v)) };
  });
  const seq = grids.length > 1 ? grids : Array(4).fill(grids[0]);
  const st = M.stretchOf(seq);
  out[ds.id] = seq.map((g) => {
    const b = M.composeBar(g, ds, 16, st);
    const m = (x) => (x.rest || x.silent ? null : x.midi);
    return { pad: b.pad.rest ? null : b.pad.partials.map((p) => p.midi), melody: b.melody.map(m), sparkle: b.sparkle.map(m) };
  });
}
console.log(JSON.stringify(out));
