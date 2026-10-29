/**
 * Archival WebAudio Synthesizer for The Ghost Maintainer.
 * 
 * Synthesizes acoustic and eerie feedback purely using WebAudio oscillators,
 * biquad filters, and envelope curves. Zero external audio file downloads required.
 * Muted by default to respect quiet environments and Apple HIG guidelines.
 */

let audioCtx: AudioContext | null = null;
let soundEnabled = false;

// Check localStorage if available
try {
  soundEnabled = localStorage.getItem('ghost_sound_enabled') === 'true';
} catch {
  soundEnabled = false;
}

export function isSoundEnabled(): boolean {
  return soundEnabled;
}

export function setSoundEnabled(enabled: boolean): void {
  soundEnabled = enabled;
  try {
    localStorage.setItem('ghost_sound_enabled', enabled ? 'true' : 'false');
  } catch {
    // ignore storage restrictions
  }
}

function getAudioContext(): AudioContext | null {
  if (!soundEnabled) return null;
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

/**
 * Soft warm candle flame whoosh on summon or transition.
 */
export function playFlameWhoosh(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const bufferSize = ctx.sampleRate * 0.4;
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = Math.random() * 2 - 1;
  }

  const noise = ctx.createBufferSource();
  noise.buffer = buffer;

  const filter = ctx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.setValueAtTime(180, ctx.currentTime);
  filter.frequency.exponentialRampToValueAtTime(750, ctx.currentTime + 0.18);
  filter.frequency.exponentialRampToValueAtTime(120, ctx.currentTime + 0.38);

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.001, ctx.currentTime);
  gain.gain.linearRampToValueAtTime(0.18, ctx.currentTime + 0.12);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.39);

  noise.connect(filter);
  filter.connect(gain);
  gain.connect(ctx.destination);

  noise.start();
  noise.stop(ctx.currentTime + 0.4);
}

/**
 * High pure sine bell tick when a citation chip verifies against git object storage.
 */
export function playGlassTick(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const osc = ctx.createOscillator();
  const gain = ctx.createGain();

  osc.type = 'sine';
  osc.frequency.setValueAtTime(1480, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.04);

  gain.gain.setValueAtTime(0.12, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.14);

  osc.connect(gain);
  gain.connect(ctx.destination);

  osc.start();
  osc.stop(ctx.currentTime + 0.15);
}

/**
 * Low muted sub-thud when a fabricated citation is caught and struck through.
 */
export function playLieThud(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const osc = ctx.createOscillator();
  const gain = ctx.createGain();

  osc.type = 'triangle';
  osc.frequency.setValueAtTime(110, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(42, ctx.currentTime + 0.22);

  gain.gain.setValueAtTime(0.24, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.24);

  osc.connect(gain);
  gain.connect(ctx.destination);

  osc.start();
  osc.stop(ctx.currentTime + 0.25);
}

/**
 * Soft twin ethereal harmonic chime when the ghost enters the séance.
 */
export function playEerieChime(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const freqs = [329.63, 493.88, 659.25]; // E major triad
  freqs.forEach((freq, idx) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, ctx.currentTime + idx * 0.06);

    gain.gain.setValueAtTime(0.001, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0.07, ctx.currentTime + 0.08 + idx * 0.06);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.65);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(ctx.currentTime + idx * 0.06);
    osc.stop(ctx.currentTime + 0.7);
  });
}

/**
 * Easter Egg: Ghost choir chord progression (Konami code).
 */
export function playGhostChoir(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const chords = [
    [220, 261.63, 329.63], // A minor
    [196, 246.94, 293.66], // G major
    [174.61, 220, 261.63], // F major
    [164.81, 207.65, 246.94], // E major
  ];

  chords.forEach((chord, step) => {
    const stepTime = ctx.currentTime + step * 0.35;
    chord.forEach((f) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(f, stepTime);
      gain.gain.setValueAtTime(0.001, stepTime);
      gain.gain.linearRampToValueAtTime(0.06, stepTime + 0.1);
      gain.gain.exponentialRampToValueAtTime(0.0001, stepTime + 0.45);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(stepTime);
      osc.stop(stepTime + 0.5);
    });
  });
}

