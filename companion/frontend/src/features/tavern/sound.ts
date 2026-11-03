/** 酒馆里的短音。仪式是转轮手枪：空膛是击针打在空仓上，实弹是近处的一声枪响。 */

let ctx: AudioContext | null = null;
// 瞬态压缩保留击发力度，限制枪声、倒地声和心跳叠加的峰值。
let effectsBus: DynamicsCompressorNode | null = null;
function output(audio: AudioContext) {
  if (!effectsBus) {
    effectsBus = audio.createDynamicsCompressor();
    effectsBus.threshold.value = -12;
    effectsBus.knee.value = 12;
    effectsBus.ratio.value = 5;
    effectsBus.attack.value = 0.003;
    effectsBus.release.value = 0.18;
    effectsBus.connect(audio.destination);
  }
  return effectsBus;
}
// 击发独立通道：保留大动态，软限幅负责峰值，不被日常 UI 的压缩压扁。
let impactBus: GainNode | null = null;
function impactOutput(audio: AudioContext) {
  if (!impactBus) {
    impactBus = audio.createGain();
    impactBus.gain.value = 1.75;
    const limiter = audio.createWaveShaper();
    const curve = new Float32Array(4096);
    for (let i = 0; i < curve.length; i += 1) {
      const x = i * 2 / (curve.length - 1) - 1;
      curve[i] = Math.tanh(x * 1.6) * 0.94;
    }
    limiter.curve = curve;
    limiter.oversample = '4x';
    // 过采样滤波会产生瞬态过冲，再用无过采样的末级峰值上限兜住。
    const ceiling = audio.createWaveShaper();
    const ceilingCurve = new Float32Array(4096);
    for (let i = 0; i < ceilingCurve.length; i += 1) {
      const x = i * 2 / (ceilingCurve.length - 1) - 1;
      ceilingCurve[i] = Math.max(-0.9, Math.min(0.9, x));
    }
    ceiling.curve = ceilingCurve;
    ceiling.oversample = 'none';
    impactBus.connect(limiter);
    limiter.connect(ceiling);
    ceiling.connect(audio.destination);
  }
  return impactBus;
}
// 录音保留原始波形和尾响，只有超过峰值上限才限幅。
let recordingBus: WaveShaperNode | null = null;
function recordingOutput(audio: AudioContext) {
  if (!recordingBus) {
    recordingBus = audio.createWaveShaper();
    const curve = new Float32Array(4096);
    for (let i = 0; i < curve.length; i += 1) curve[i] = Math.max(-0.96, Math.min(0.96, i * 2 / (curve.length - 1) - 1));
    recordingBus.curve = curve;
    recordingBus.connect(audio.destination);
  }
  return recordingBus;
}
let effectGeneration = 0;
const effectSources = new Set<AudioScheduledSourceNode>();
function track<T extends AudioScheduledSourceNode>(source: T): T {
  effectSources.add(source);
  source.addEventListener('ended', () => effectSources.delete(source), { once: true });
  return source;
}
/** 离场/结束时连同已预约的余响一起停止，避免下一手还在响。 */
export function stopEffects() {
  effectGeneration += 1;
  pulse(false);
  stopDread();
  for (const source of effectSources) {
    try { source.stop(); } catch { /* already stopped */ }
  }
  effectSources.clear();
}
let heart = 0;
let dub = 0;
let drone: { osc: OscillatorNode; gain: GainNode } | null = null;
let dreadTimers: number[] = [];
let dreadOsc: OscillatorNode[] = [];

function ac() {
  const Ctx = window.AudioContext;
  if (!Ctx) return null;
  if (!ctx) ctx = new Ctx();
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
}

export function unlock() {
  ac();
  void primeApplause();
  void primeShot();
  void primeDryFire();
}

function noise(audio: AudioContext, seconds: number) {
  const samples = Math.max(1, Math.floor(audio.sampleRate * seconds));
  const buffer = audio.createBuffer(1, samples, audio.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < samples; i += 1) data[i] = Math.random() * 2 - 1;
  const src = track(audio.createBufferSource());
  src.buffer = buffer;
  return src;
}

function burst(peak: number, seconds: number, freq: number, type: BiquadFilterType) {
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  const src = noise(audio, seconds);
  const filter = audio.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = freq;
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), now + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
  src.connect(filter);
  filter.connect(gain);
  gain.connect(output(audio));
  src.start(now);
  src.stop(now + seconds + 0.02);
}

function tone(freq: number, seconds: number, peak: number, slideTo?: number) {
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  const osc = track(audio.createOscillator());
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freq, now);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(Math.max(30, slideTo), now + seconds);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
  osc.connect(gain);
  gain.connect(output(audio));
  osc.start(now);
  osc.stop(now + seconds + 0.02);
}

export function pick() {
  tone(740, 0.05, 0.035, 1180);
}

export function slide() {
  burst(0.09, 0.07, 1600, 'highpass');
  tone(220, 0.1, 0.05, 110);
  window.setTimeout(() => burst(0.07, 0.06, 700, 'bandpass'), 80);
}

export function turn() {
  burst(0.18, 0.28, 900, 'bandpass');
  tone(520, 0.22, 0.09, 240);
}

function thump(freq: number, peak: number) {
  tone(freq, 0.16, peak, freq * 0.55);
  burst(peak * 0.35, 0.05, 120, 'lowpass');
}

function stopDrone() {
  const audio = ac();
  if (!drone || !audio) {
    drone = null;
    return;
  }
  const now = audio.currentTime;
  drone.gain.gain.cancelScheduledValues(now);
  drone.gain.gain.setValueAtTime(Math.max(0.0002, drone.gain.gain.value), now);
  drone.gain.gain.linearRampToValueAtTime(0.0001, now + 0.08);
  drone.osc.stop(now + 0.1);
  drone = null;
}

export function pulse(on: boolean, chamber = 1) {
  if (heart) window.clearTimeout(heart);
  if (dub) window.clearTimeout(dub);
  heart = 0;
  dub = 0;
  if (!on) {
    stopDrone();
    return;
  }
  const audio = ac();
  if (audio && !drone) {
    const osc = track(audio.createOscillator());
    osc.type = 'sine';
    osc.frequency.setValueAtTime(46, audio.currentTime);
    osc.frequency.linearRampToValueAtTime(62, audio.currentTime + 4.2);
    const gain = audio.createGain();
    gain.gain.setValueAtTime(0.0001, audio.currentTime);
    gain.gain.linearRampToValueAtTime(0.14, audio.currentTime + 1.8);
    osc.connect(gain);
    gain.connect(output(audio));
    osc.start();
    drone = { osc, gain };
  }
  const began = performance.now();
  const beat = () => {
    const pressure = Math.min(1, (performance.now() - began) / 4000);
    thump(48, 0.46 + pressure * 0.18);
    dub = window.setTimeout(() => thump(68, 0.32), 125);
    heart = window.setTimeout(beat, Math.max(330, 800 - chamber * 95 - pressure * 190));
  };
  beat();
}

export function cock() {
  const audio = ac();
  if (!audio) return;
  const at = audio.currentTime;
  shaped(0.2, 0.045, 1800, 'bandpass', 0.002, at);
  shaped(0.14, 0.035, 3200, 'highpass', 0.002, at + 0.095);
  cinematicTone(310, 145, 0.13, 0.07, at + 0.02, 'triangle');
}

export function cylinder() {
  const audio = ac();
  if (!audio) return;
  const at = audio.currentTime;
  shaped(0.13, 0.032, 2300, 'bandpass', 0.001, at);
  shaped(0.065, 0.07, 800, 'bandpass', 0.003, at + 0.025);
}

/** 所有层使用同一个音频时钟，不依赖下载或 setTimeout 对齐击发。 */
function cinematicTone(from: number, to: number, seconds: number, peak: number, at: number, type: OscillatorType = 'sine', destination?: AudioNode) {
  const audio = ac();
  if (!audio) return;
  const osc = track(audio.createOscillator());
  osc.type = type;
  osc.frequency.setValueAtTime(from, at);
  osc.frequency.exponentialRampToValueAtTime(to, at + seconds);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(peak, at + Math.min(0.008, seconds / 4));
  gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
  osc.connect(gain);
  gain.connect(destination || output(audio));
  osc.start(at);
  osc.stop(at + seconds + 0.02);
}

function shaped(peak: number, seconds: number, freq: number, type: BiquadFilterType, attack: number, at: number, destination?: AudioNode) {
  const audio = ac();
  if (!audio) return;
  const src = noise(audio, seconds);
  const filter = audio.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = freq;
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), at + attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
  src.connect(filter);
  filter.connect(gain);
  gain.connect(destination || output(audio));
  src.start(at);
  src.stop(at + seconds + 0.02);
}

export function dryFire() {
  pulse(false);
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  shaped(0.42, 0.028, 2600, 'highpass', 0.002, now);
  shaped(0.28, 0.05, 740, 'bandpass', 0.003, now + 0.022);
  tone(210, 0.07, 0.1, 70);
}

function hushOsc() {
  const audio = ac();
  const at = audio ? audio.currentTime + 0.04 : 0;
  for (const osc of dreadOsc) {
    try { osc.stop(at); } catch { /* 已经停了 */ }
  }
  dreadOsc = [];
}

export function stopDread() {
  for (const id of dreadTimers) window.clearTimeout(id);
  dreadTimers = [];
  hushOsc();
}

/** 扣扳机之前：低频弦鸣缓慢收紧，机械声由转轮动作同步触发。 */
export function dread() {
  stopDread();
  const audio = ac();
  if (!audio) return;
  const at = audio.currentTime;
  // 低沉、不完全和谐的弦鸣；音量让开人物台词。
  for (const freq of [49, 51.2, 97, 391, 407]) {
    const osc = track(audio.createOscillator());
    const gain = audio.createGain();
    osc.type = freq > 300 ? 'sine' : 'triangle';
    const level = freq > 300 ? 0.5 : 1;
    osc.frequency.setValueAtTime(freq, at);
    osc.frequency.exponentialRampToValueAtTime(freq * 1.36, at + 5.5);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.linearRampToValueAtTime(0.055 * level, at + 0.8);
    gain.gain.linearRampToValueAtTime(0.15 * level, at + 3.8);
    gain.gain.linearRampToValueAtTime(0.0001, at + 6.5);
    osc.connect(gain);
    gain.connect(output(audio));
    osc.start(at);
    osc.stop(at + 6.6);
    dreadOsc.push(osc);
  }
}

let dryBuffer: AudioBuffer | null = null;
/** 撞针与弹簧是短促、不谐和的金属振动，不使用滑音和电子提示音。 */
function mechanicalClick(audio: AudioContext) {
  if (dryBuffer && dryBuffer.sampleRate === audio.sampleRate) return dryBuffer;
  const rate = audio.sampleRate;
  const buffer = audio.createBuffer(1, Math.ceil(rate * 0.65), rate);
  const data = buffer.getChannelData(0);
  let seed = 9137;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) | 0; return seed / 2147483648; };
  const strikes = [{ at: 0, strength: 1 }, { at: 0.012, strength: 0.48 }, { at: 0.047, strength: 0.23 }];
  for (let i = 0; i < data.length; i += 1) {
    const time = i / rate;
    let value = 0;
    for (const strike of strikes) {
      const t = time - strike.at;
      if (t < 0) continue;
      const attack = Math.min(1, t / 0.0005);
      const snap = random() * 0.62 * Math.exp(-t / 0.004);
      const body = Math.sin(2 * Math.PI * 185 * t) * 0.24 * Math.exp(-t / 0.015);
      let metal = 0;
      for (const [frequency, decay, level] of [[1373, 0.032, 0.13], [2189, 0.022, 0.1], [3541, 0.014, 0.07], [4877, 0.009, 0.04]]) {
        metal += Math.sin(2 * Math.PI * frequency * t) * level * Math.exp(-t / decay);
      }
      value += (snap + body + metal) * attack * strike.strength;
    }
    data[i] = value;
  }
  // 极短的房间反射给撞针距离感，不拖成铃声。
  const direct = data.slice();
  for (const [seconds, level] of [[0.083, 0.19], [0.139, 0.075]]) {
    const delay = Math.round(seconds * rate);
    for (let i = delay; i < data.length; i += 1) data[i] += direct[i - delay] * level;
  }
  dryBuffer = buffer;
  return buffer;
}

export function relieved() {
  pulse(false);
  stopDread();
  const audio = ac();
  if (!audio) return;
  if (dryRecording) {
    impactClip(audio, dryRecording, audio.currentTime, 1, dryRecording.duration, true);
    return;
  }
  void primeDryFire();
  impactClip(audio, mechanicalClick(audio), audio.currentTime, 1.15, 0.65);
}

/** 缓存素材的播放也使用同一音频时钟，绝不等待下载后补响。 */
function impactClip(audio: AudioContext, buffer: AudioBuffer, at: number, level: number, duration: number, recorded = false) {
  const src = track(audio.createBufferSource());
  const gain = audio.createGain();
  src.buffer = buffer;
  const length = Math.min(duration, buffer.duration);
  gain.gain.setValueAtTime(level, at);
  gain.gain.setValueAtTime(level, at + Math.max(0, length - 0.15));
  gain.gain.linearRampToValueAtTime(0, at + length);
  src.connect(gain);
  gain.connect(recorded ? recordingOutput(audio) : impactOutput(audio));
  src.start(at, 0, length);
}

/** 近场枪响 + 重击 + 尾响；峰值交给独立限幅，而不是压低整个枪声。 */
export function killshot() {
  pulse(false);
  stopDread();
  const audio = ac();
  if (!audio) return;
  const at = audio.currentTime;
  const bus = impactOutput(audio);
  if (shotBuffer) {
    // 增强 WAV 已包含高频起音、耳鸣和回声，按原电平完整播放。
    impactClip(audio, shotBuffer, at, 1, shotBuffer.duration, true);
    return;
  }
  void primeShot();
  {
    shaped(1.05, 0.12, 1900, 'highpass', 0.0007, at, bus);
    shaped(0.8, 0.28, 780, 'bandpass', 0.001, at + 0.004, bus);
  }
  cinematicTone(185, 32, 0.48, 0.85, at, 'sine', bus);
  shaped(0.55, 0.28, 240, 'lowpass', 0.003, at + 0.055, bus);
  if (collapseBuffer) impactClip(audio, collapseBuffer, at + 0.09, 0.72, 1.3);
  cinematicTone(105, 27, 0.65, 0.48, at + 0.06, 'sine', bus);
  shaped(0.42, 0.6, 1100, 'bandpass', 0.006, at + 0.11, bus);
  shaped(0.24, 1.05, 540, 'lowpass', 0.015, at + 0.23, bus);
  cinematicTone(2850, 1700, 1.05, 0.04, at + 0.2);
}

let shotBuffer: AudioBuffer | null = null;
let shotLoading: Promise<AudioBuffer | null> | null = null;
export function primeShot() {
  return loadWav('/assets/tavern/barrett-m82-ringing.wav', () => shotBuffer,
    (buf) => { shotBuffer = buf; }, () => shotLoading, (job) => { shotLoading = job; });
}

let dryRecording: AudioBuffer | null = null;
let dryLoading: Promise<AudioBuffer | null> | null = null;
export function primeDryFire() {
  return loadWav('/assets/tavern/rifle-dryfire-close.wav', () => dryRecording,
    (buf) => { dryRecording = buf; }, () => dryLoading, (job) => { dryLoading = job; });
}

let applauseBuffer: AudioBuffer | null = null;
let applauseLoading: Promise<AudioBuffer | null> | null = null;
let applauseNode: AudioBufferSourceNode | null = null;
let collapseBuffer: AudioBuffer | null = null;
let collapseLoading: Promise<AudioBuffer | null> | null = null;

function loadWav(url: string, ready: () => AudioBuffer | null, save: (buf: AudioBuffer) => void, pending: () => Promise<AudioBuffer | null> | null, store: (job: Promise<AudioBuffer | null> | null) => void) {
  const audio = ac();
  if (!audio) return Promise.resolve(null);
  const have = ready();
  if (have) return Promise.resolve(have);
  const job = pending();
  if (job) return job;
  const next = fetch(url)
    .then((res) => { if (!res.ok) throw new Error(String(res.status)); return res.arrayBuffer(); })
    .then((raw) => audio.decodeAudioData(raw.slice(0)))
    .then((buf) => {
      save(buf);
      return buf;
    })
    .catch(() => null)
    .finally(() => store(null));
  store(next);
  return next;
}

export function primeApplause() {
  return loadWav(
    '/assets/tavern/applause.wav?v=3',
    () => applauseBuffer,
    (buf) => { applauseBuffer = buf; },
    () => applauseLoading,
    (job) => { applauseLoading = job; },
  );
}

export function primeCollapse() {
  return loadWav(
    '/assets/tavern/collapse.wav',
    () => collapseBuffer,
    (buf) => { collapseBuffer = buf; },
    () => collapseLoading,
    (job) => { collapseLoading = job; },
  );
}

function playClip(buf: AudioBuffer) {
  const audio = ac();
  if (!audio) return;
  const src = track(audio.createBufferSource());
  src.buffer = buf;
  const gain = audio.createGain();
  gain.gain.value = 0.75;
  src.connect(gain);
  gain.connect(output(audio));
  src.start();
}

/** 出完退场。铜管上行，然后掌声铺满。 */
export function applause() {
  const generation = effectGeneration;
  const audio = ac();
  if (!audio) return;
  const start = (buf: AudioBuffer) => {
    if (generation !== effectGeneration) return;
    if (applauseNode) {
      try { applauseNode.stop(); } catch { /* already ended */ }
    }
    const src = track(audio.createBufferSource());
    src.buffer = buf;
    const gain = audio.createGain();
    gain.gain.value = 0.75;
    src.connect(gain);
    gain.connect(output(audio));
    src.start();
    applauseNode = src;
  };
  if (applauseBuffer) start(applauseBuffer);
  else void primeApplause().then((buf) => { if (buf) start(buf); });
}
