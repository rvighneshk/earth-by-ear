// Drives the real Engine + composer with a mock Web Audio API. Fails on any exception or empty schedule.
import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
const here = path.dirname(fileURLToPath(import.meta.url));
let oscillators = 0; const waves = new Set();
const param = () => ({ value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {}, setTargetAtTime() {} });
const node = () => { const n = { connect(x) { return x ?? n; }, disconnect() {}, start() {}, stop() {}, gain: param(), pan: param(), frequency: param(), Q: param() }; return n; };
globalThis.window = { AudioContext: class {
  constructor() { this.currentTime = 0; this.sampleRate = 8000; this.state = 'running'; this.destination = node(); }
  resume() { return Promise.resolve(); }
  createGain() { return node(); } createDynamicsCompressor() { return { ...node(), threshold: param(), ratio: param(), knee: param() }; }
  createBufferSource() { return { ...node(), buffer: null, onended: null }; }
  createConvolver() { return node(); } createStereoPanner() { return node(); } createBiquadFilter() { return node(); }
  createBuffer(c, l) { return { getChannelData: () => new Float32Array(l) }; }
  createOscillator() { oscillators++; const o = node(); Object.defineProperty(o, 'type', { set: (v) => waves.add(v), get: () => 'sine' }); return o; }
} };
globalThis.performance = performance;
const { Engine } = await import(path.join(here, '../app/static/js/engine.js'));
const M = await import(path.join(here, '../app/static/js/mapping.js'));
const base = path.join(here, '../app/static/data/');
const idx = JSON.parse(fs.readFileSync(base + 'index.json'));
const e = new Engine(); await e.start();
for (const ds of idx.datasets) {
  const grids = ds.frames.map((f) => { const j = JSON.parse(fs.readFileSync(base + f.url));
    return { rows: j.rows, cols: j.cols, extent: ds.extent, geometry: ds.geometry, data: Float32Array.from(j.data, (v) => (v === null ? NaN : v)) }; });
  const seq = grids.length > 1 ? grids : Array(4).fill(grids[0]);
  const st = M.stretchOf(seq); const bars = seq.map((g) => M.composeBar(g, ds, 16, st));
  const before = oscillators;
  e.scan(bars.map((b) => b.pad), { stepMs: 4000, noteDur: 4.8, level: 0.3 });
  e.scan(bars.flatMap((b) => b.melody), { stepMs: 250, noteDur: 0.45, level: 0.34 });
  e.scan(bars.flatMap((b) => b.sparkle), { stepMs: 250, noteDur: 0.25, level: 0.15 });
  if (oscillators === before) throw new Error('nothing scheduled for ' + ds.id);
  // every cell of the explore mode too (no NaN pitch / frequency)
  const g = grids[0];
  for (let r = 0; r < g.rows; r += 7) for (let c = 0; c < g.cols; c += 7) {
    const s = M.cellSound(g, r, c, ds);
    if (!s.silent && !(s.partials.every((p) => Number.isFinite(p.freq)) && Number.isFinite(s.cutoff))) throw new Error(`bad sound ${ds.id} ${r},${c}`);
    e.play(s, { dur: 0.5 });
  }
}
e.playRendered({ duration: 1 }, 0.5);                       // rendered performance starts...
if (!e._rendered) throw new Error('rendered playback did not start');
e.stopAll();                                                // ...and stopAll silences it
if (e._rendered) throw new Error('stopAll left the rendered performance playing');
console.log('engine ok; oscillators:', oscillators, 'waveforms used:', [...waves].sort().join(','));
