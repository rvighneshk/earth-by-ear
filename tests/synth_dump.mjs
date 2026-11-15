// node tests/synth_dump.mjs <dataset-id> <out.f32>: the browser's dry performance mix (44.1 kHz, interleaved L/R float32).
import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
const here = path.dirname(fileURLToPath(import.meta.url));
const M = await import(path.join(here, '../app/static/js/mapping.js'));
const S = await import(path.join(here, '../app/static/js/synth.js'));
const base = path.join(here, '../app/static/data/');
const ds = JSON.parse(fs.readFileSync(base + 'index.json')).datasets.find((d) => d.id === process.argv[2]);
const grids = ds.frames.map((f) => { const j = JSON.parse(fs.readFileSync(base + f.url));
  return { rows: j.rows, cols: j.cols, extent: ds.extent, geometry: ds.geometry, data: Float32Array.from(j.data, (v) => (v === null ? NaN : v)) }; });
const seq = grids.length > 1 ? grids : Array(4).fill(grids[0]);
const st = M.stretchOf(seq);
const { L, R } = S.mixPerformance(seq.map((g) => M.composeBar(g, ds, 16, st)), { sr: 44100 });
const out = new Float32Array(L.length * 2);
for (let i = 0; i < L.length; i++) { out[2 * i] = L[i]; out[2 * i + 1] = R[i]; }
fs.writeFileSync(process.argv[3], Buffer.from(out.buffer));
