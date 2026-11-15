// synth.js - the "studio" renderer. Pure functions (no Web Audio), so Node can test them against the Python renderer.
// Same note recipe, panning and levels as pipeline/sonify.py (_note / _wave_note / render_performance), so a performance
// rendered live in the browser matches the downloadable track.

const TWO_PI = Math.PI * 2;
const TABLE = 8192;
const tables = new Map();
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const midiToFreq = (m) => 440 * 2 ** ((m - 69) / 12);

/** One cycle of the note's harmonic recipe, so each partial costs one table lookup per sample instead of many sines. */
function cycle(wave, harmonics) {
  const key = `${wave}:${harmonics}`;
  if (tables.has(key)) return tables.get(key);
  const t = new Float64Array(TABLE + 1);
  for (let i = 0; i < TABLE; i++) {
    let s = 0;
    if (wave === 'triangle') for (let k = 1; k <= harmonics; k += 2) s += Math.sin((TWO_PI * k * i) / TABLE) / (k * k);
    else if (wave === 'sawtooth') for (let k = 1; k <= harmonics; k++) s += Math.sin((TWO_PI * k * i) / TABLE) / k;
    else s = Math.sin((TWO_PI * i) / TABLE);
    t[i] = s;
  }
  t[TABLE] = t[0];
  tables.set(key, t);
  return t;
}

function harmonicsFor(wave, cutoff) {
  if (wave === 'sawtooth') return Math.trunc(clamp(Math.log2(cutoff / 500) * 2 + 2, 1, 10));
  if (wave === 'sine') return 1;
  return Math.trunc(clamp(Math.log2(cutoff / 500) * 1.2 + 1, 1, 6));
}

/** One mono note as Float32Array. `sound` is a parameter object from mapping.js. */
export function synthNote(sound, dur, level, sr) {
  const n = Math.floor(dur * sr);
  const out = new Float32Array(n);
  const wave = sound.wave ?? 'triangle';
  const tab = cycle(wave, harmonicsFor(wave, sound.cutoff));
  const total = sound.partials.reduce((a, p) => a + p.gain, 0);
  for (const p of sound.partials) {
    const a = p.gain / total;
    for (let i = 0; i < n; i++) {
      let ph = (p.freq * i) / sr;
      ph -= Math.floor(ph);
      const x = ph * TABLE;
      const j = Math.floor(x);
      out[i] += a * (tab[j] + (tab[j + 1] - tab[j]) * (x - j));
    }
  }
  const sub = midiToFreq(sound.midi - 12);
  const rough = sound.roughness ?? 0;
  const depth = 0.5 * rough;
  const rate = 14 + 18 * rough;
  const att = sound.attack ?? 0.012;
  for (let i = 0; i < n; i++) {
    const t = i / sr;
    let v = out[i] + 0.25 * Math.sin(TWO_PI * sub * t);
    if (rough > 0) v *= 1 - depth / 2 + (depth / 2) * Math.sin(TWO_PI * rate * t);
    const attack = Math.min(t / att, 1);
    const env = sound.sustain
      ? t < dur * 0.7 ? 1 : Math.exp(-(t - dur * 0.7) * (6 / dur) * 3.3)
      : Math.exp(-t * (3 / dur));
    out[i] = v * attack * env * level;
  }
  return out;
}

/** The whole piece, dry, as two Float32Arrays (left, right). `bars` come from composeBar. */
export function mixPerformance(bars, { sr = 44100, barSec = 4, steps = 16 } = {}) {
  const total = Math.floor((bars.length * barSec + barSec + 1.5) * sr);
  const L = new Float32Array(total);
  const R = new Float32Array(total);
  const put = (note, start, pan) => {
    const end = Math.min(total, start + note.length);
    if (end <= start) return;
    const ang = ((pan + 1) * Math.PI) / 4;               // equal-power pan
    const cl = Math.cos(ang);
    const cr = Math.sin(ang);
    for (let i = 0; i < end - start; i++) { L[start + i] += note[i] * cl; R[start + i] += note[i] * cr; }
  };
  const step = barSec / steps;
  bars.forEach((b, i) => {
    const t0 = i * barSec;
    if (!b.pad.rest) put(synthNote(b.pad, barSec + 0.8, 0.3, sr), Math.floor(t0 * sr), 0);
    for (let s = 0; s < steps; s++) {
      for (const [voice, dur, lvl] of [['melody', 0.45, 0.34], ['sparkle', 0.25, 0.15]]) {
        const snd = b[voice][s];
        if (snd.rest || snd.silent) continue;
        put(synthNote(snd, dur, lvl, sr), Math.floor((t0 + s * step) * sr), snd.pan);
      }
    }
  });
  return { L, R };
}

/** Room reverb impulse response (2 s, noise with a steep decay); fixed seed so every run sounds the same. */
export function makeImpulse(sr, seconds = 2.0, decay = 2.6, seed = 7) {
  const n = Math.floor(sr * seconds);
  let a = seed;
  const rnd = () => { a += 0x6d2b79f5; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  return [0, 1].map(() => { const d = new Float32Array(n); for (let i = 0; i < n; i++) d[i] = (rnd() * 2 - 1) * Math.pow(1 - i / n, decay); return d; });
}
