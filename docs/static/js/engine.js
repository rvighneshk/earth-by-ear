// engine.js - Web Audio only, no libraries (nothing to vendor, works offline).
// Takes the parameter objects from mapping.js and makes them audible.

export class Engine {
  constructor() {
    this.ctx = null;
    this.lastTrigger = 0;
    this.buses = new Set();
  }

  async start() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC();
      const c = this.ctx;
      this.master = c.createGain();
      this.master.gain.value = 0.8;
      const comp = (this.comp = c.createDynamicsCompressor());
      comp.threshold.value = -16;
      comp.ratio.value = 4;
      this.master.connect(comp).connect(c.destination);
      // Small generated room reverb: gives notes a place to live.
      this.reverb = c.createConvolver();
      this.reverb.buffer = this._impulse(2.2, 2.6);
      this.wet = c.createGain();
      this.wet.gain.value = 0.22;
      this.reverb.connect(this.wet).connect(this.master);
      this.dry = c.createGain();
      this.dry.connect(this.master);
      this.dry.connect(this.reverb);
      // Pre-rendered performances ("Play this visualization") skip the live compressor so they keep the file's dynamics.
      this.renderBus = c.createGain();
      this.renderBus.gain.value = 0.8;
      this.renderBus.connect(c.destination);
    }
    if (this.ctx.state !== 'running') await this.ctx.resume();
    return this.ctx.state === 'running';
  }

  get ready() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  setVolume(v) {
    if (this.master) this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.02);
    if (this.renderBus) this.renderBus.gain.setTargetAtTime(v, this.ctx.currentTime, 0.02);
  }

  /** Play a finished stereo AudioBuffer (the studio render). `gain` brings its peak to 0.85, like the downloadable file. */
  playRendered(buffer, gain, onended) {
    this.stopRendered();
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    const g = this.ctx.createGain();
    g.gain.value = gain;
    src.connect(g).connect(this.renderBus);
    src.onended = onended ?? null;
    src.start();
    this._rendered = { src, g };
  }

  stopRendered() {
    if (!this._rendered) return;
    const { src, g } = this._rendered;
    this._rendered = null;
    src.onended = null;
    g.gain.setTargetAtTime(0, this.ctx.currentTime, 0.02);
    try { src.stop(this.ctx.currentTime + 0.12); } catch { /* already stopped */ }
  }

  _impulse(seconds, decay) {
    const c = this.ctx;
    const len = Math.floor(c.sampleRate * seconds);
    const buf = c.createBuffer(2, len, c.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
    }
    return buf;
  }

  /** Rate limiter so dragging a finger does not fire hundreds of notes. */
  allow(minMs = 60) {
    const now = performance.now();
    if (now - this.lastTrigger < minMs) return false;
    this.lastTrigger = now;
    return true;
  }

  /** One note. `sound` comes from mapping.js (cellSound / valueSound). */
  play(sound, { when = null, dur = 0.5, level = 0.5, dest = null } = {}) {
    if (!this.ready) return;
    const c = this.ctx;
    const t0 = when ?? c.currentTime;
    const out = dest ?? this.dry;
    if (sound.rest) return;
    if (sound.silent) return this._thump(t0, sound.pan ?? 0, out);

    const env = c.createGain();
    const attack = sound.attack ?? 0.012; // chords use a slow swell, single notes a quick pluck
    env.gain.setValueAtTime(0.0001, t0);
    env.gain.exponentialRampToValueAtTime(level, t0 + attack);
    if (sound.sustain) env.gain.setValueAtTime(level, t0 + dur * 0.7); // hold, then release
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

    const pan = c.createStereoPanner();
    pan.pan.value = sound.pan ?? 0;

    const amp = c.createGain();
    const depth = 0.5 * (sound.roughness ?? 0);
    amp.gain.value = 1 - depth / 2;
    const stops = [];
    if (depth > 0.02) {
      // Spatial roughness -> amplitude flutter. Calm data = steady tone.
      const lfo = c.createOscillator();
      lfo.frequency.value = 14 + 18 * sound.roughness;
      const lg = c.createGain();
      lg.gain.value = depth / 2;
      lfo.connect(lg).connect(amp.gain);
      lfo.start(t0);
      stops.push(lfo);
    }

    const filter = c.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = sound.cutoff ?? 4000;
    filter.Q.value = 0.8;

    const total = sound.partials.reduce((a, p) => a + p.gain, 0) || 1;
    sound.partials.forEach((p, i) => {
      const o = c.createOscillator();
      o.type = sound.wave ?? 'triangle';
      o.frequency.value = p.freq;
      const g = c.createGain();
      g.gain.value = p.gain / total;
      o.connect(g).connect(filter);
      o.start(t0);
      stops.push(o);
      if (i === 0) {
        const sub = c.createOscillator(); // body: sine an octave under the main note
        sub.frequency.value = p.freq / 2;
        const sg = c.createGain();
        sg.gain.value = 0.25;
        sub.connect(sg).connect(filter);
        sub.start(t0);
        stops.push(sub);
      }
    });
    filter.connect(amp).connect(env).connect(pan).connect(out);
    const end = t0 + dur + 0.05;
    stops.forEach((o) => o.stop(end));
    stops[stops.length - 1].onended = () => {
      env.disconnect();
      pan.disconnect();
    };
  }

  _thump(t0, pan, out) {
    // NODATA cue: soft low tick, distinct from any pitched note.
    const c = this.ctx;
    const o = c.createOscillator();
    o.frequency.setValueAtTime(90, t0);
    o.frequency.exponentialRampToValueAtTime(45, t0 + 0.12);
    const g = c.createGain();
    g.gain.setValueAtTime(0.22, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.14);
    const p = c.createStereoPanner();
    p.pan.value = pan;
    o.connect(g).connect(p).connect(out);
    o.start(t0);
    o.stop(t0 + 0.16);
  }

  /** Duet: A in the left ear, B in the right, same moment. */
  playDuet(soundA, soundB, opts = {}) {
    this.play({ ...soundA, pan: -0.9 }, opts);
    this.play({ ...soundB, pan: 0.9 }, opts);
  }

  /**
   * Schedule a list of sounds one after another. Returns {durationMs, cancel}.
   * `sounds` is an array of sound objects (or pairs [a, b] for duet scans).
   */
  scan(sounds, { stepMs = 150, level = 0.42, noteDur = null } = {}) {
    if (!this.ready) return { durationMs: 0, cancel() {} };
    const c = this.ctx;
    const bus = c.createGain();
    bus.connect(this.dry);
    this.buses.add(bus);
    const step = stepMs / 1000;
    const dur = noteDur ?? Math.min(0.7, step * 2.4);
    const t0 = c.currentTime + 0.05;
    sounds.forEach((s, i) => {
      const when = t0 + i * step;
      if (Array.isArray(s)) {
        this.play({ ...s[0], pan: -0.9 }, { when, dur, level, dest: bus });
        this.play({ ...s[1], pan: 0.9 }, { when, dur, level, dest: bus });
      } else {
        this.play(s, { when, dur, level, dest: bus });
      }
    });
    const durationMs = sounds.length * stepMs + (noteDur ? noteDur * 1000 : 300);
    const cancel = () => {
      if (!this.buses.has(bus)) return;
      bus.gain.setTargetAtTime(0, c.currentTime, 0.015);
      setTimeout(() => bus.disconnect(), 200);
      this.buses.delete(bus);
    };
    setTimeout(() => this.buses.delete(bus), durationMs + 400);
    return { durationMs, cancel };
  }

  stopAll() {
    if (!this.ctx) return;
    this.stopRendered();
    for (const bus of [...this.buses]) {
      bus.gain.setTargetAtTime(0, this.ctx.currentTime, 0.015);
      setTimeout(() => bus.disconnect(), 200);
      this.buses.delete(bus);
    }
  }
}
