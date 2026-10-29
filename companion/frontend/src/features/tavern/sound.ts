/** 酒馆里的短音。仪式是转轮手枪：空膛是击针打在空仓上，实弹是近处的一声枪响。 */

let ctx: AudioContext | null = null;
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
  void primeShot();
  void primeApplause();
  void primeCollapse();
}

function noise(audio: AudioContext, seconds: number) {
  const samples = Math.max(1, Math.floor(audio.sampleRate * seconds));
  const buffer = audio.createBuffer(1, samples, audio.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < samples; i += 1) data[i] = Math.random() * 2 - 1;
  const src = audio.createBufferSource();
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
  gain.connect(audio.destination);
  src.start(now);
  src.stop(now + seconds + 0.02);
}

function tone(freq: number, seconds: number, peak: number, slideTo?: number) {
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  const osc = audio.createOscillator();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freq, now);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(Math.max(30, slideTo), now + seconds);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
  osc.connect(gain);
  gain.connect(audio.destination);
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
  drone.gain.gain.linearRampToValueAtTime(0.0001, now + 0.35);
  drone.osc.stop(now + 0.4);
  drone = null;
}

export function pulse(on: boolean) {
  if (heart) window.clearInterval(heart);
  if (dub) window.clearTimeout(dub);
  heart = 0;
  dub = 0;
  if (!on) {
    stopDrone();
    return;
  }
  const audio = ac();
  if (audio && !drone) {
    const osc = audio.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(46, audio.currentTime);
    osc.frequency.linearRampToValueAtTime(62, audio.currentTime + 4.2);
    const gain = audio.createGain();
    gain.gain.setValueAtTime(0.0001, audio.currentTime);
    gain.gain.linearRampToValueAtTime(0.14, audio.currentTime + 1.8);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start();
    drone = { osc, gain };
  }
  const beat = () => {
    thump(48, 0.46);
    dub = window.setTimeout(() => thump(64, 0.28), 160);
  };
  beat();
  heart = window.setInterval(beat, 780);
}

export function cock() {
  burst(0.22, 0.045, 1700, 'highpass');
  tone(410, 0.1, 0.07, 150);
}

export function cylinder() {
  burst(0.14, 0.02, 1400, 'bandpass');
  tone(880, 0.03, 0.04, 420);
}

function shaped(peak: number, seconds: number, freq: number, type: BiquadFilterType, attack: number, at: number) {
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
  gain.connect(audio.destination);
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

/** 扣扳机之前。两个不和谐的音往上爬，滴答越来越密。 */
export function dread() {
  stopDread();
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  const low = audio.createBiquadFilter();
  low.type = 'lowpass';
  low.frequency.setValueAtTime(240, now);
  low.frequency.exponentialRampToValueAtTime(1600, now + 4.2);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.linearRampToValueAtTime(0.26, now + 3.5);
  gain.gain.linearRampToValueAtTime(0.0001, now + 4.5);
  low.connect(gain);
  gain.connect(audio.destination);
  for (const start of [70, 74]) {
    const osc = audio.createOscillator();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(start, now);
    osc.frequency.exponentialRampToValueAtTime(start * 3.1, now + 4.3);
    osc.connect(low);
    osc.start(now);
    osc.stop(now + 4.6);
    dreadOsc.push(osc);
  }
  let wait = 480;
  let gone = 0;
  const tick = () => {
    if (gone > 4300) return;
    burst(0.12 + gone / 9000, 0.018, 2200, 'highpass');
    gone += wait;
    wait = Math.max(64, Math.floor(wait * 0.76));
    dreadTimers.push(window.setTimeout(tick, wait));
  };
  tick();
}

function chime(freq: number, at: number, peak: number) {
  const audio = ac();
  if (!audio) return;
  const osc = audio.createOscillator();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freq, at);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), at + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.28);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(at);
  osc.stop(at + 0.3);
}

/** 空膛。先是一声轻的金属响，再接一段明快的三音，然后两声往下掉的嘲讽。 */
export function relieved() {
  pulse(false);
  stopDread();
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  shaped(0.22, 0.04, 3400, 'highpass', 0.002, now);
  chime(784, now + 0.06, 0.16);
  chime(988, now + 0.12, 0.14);
  chime(1318, now + 0.18, 0.12);
  const scoffAt = now + 0.34;
  voiced(340, 150, scoffAt, 0.22);
  voiced(260, 100, scoffAt + 0.16, 0.18);
  shaped(0.2, 0.09, 1200, 'bandpass', 0.008, scoffAt);
  shaped(0.16, 0.1, 680, 'bandpass', 0.008, scoffAt + 0.16);
}

function voiced(from: number, to: number, at: number, peak: number) {
  const audio = ac();
  if (!audio) return;
  const osc = audio.createOscillator();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(from, at);
  osc.frequency.exponentialRampToValueAtTime(Math.max(40, to), at + 0.15);
  const filter = audio.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.setValueAtTime(900, at);
  filter.Q.value = 4;
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(peak, at + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
  osc.connect(filter);
  filter.connect(gain);
  gain.connect(audio.destination);
  osc.start(at);
  osc.stop(at + 0.18);
}

let shotBuffer: AudioBuffer | null = null;
let shotLoading: Promise<AudioBuffer | null> | null = null;
let shotNode: AudioBufferSourceNode | null = null;

/** 进仪式就先把枪声读进内存，扣下扳机时不再等。 */
export function primeShot() {
  const audio = ac();
  if (!audio) return Promise.resolve(null);
  if (shotBuffer) return Promise.resolve(shotBuffer);
  if (shotLoading) return shotLoading;
  shotLoading = fetch('/assets/tavern/killshot.wav')
    .then((res) => res.arrayBuffer())
    .then((raw) => audio.decodeAudioData(raw.slice(0)))
    .then((buf) => {
      shotBuffer = buf;
      return buf;
    })
    .catch(() => null);
  return shotLoading;
}

function playShot(audio: AudioContext, buf: AudioBuffer) {
  if (shotNode) {
    try { shotNode.stop(); } catch { /* already ended */ }
  }
  const src = audio.createBufferSource();
  src.buffer = buf;
  const gain = audio.createGain();
  gain.gain.value = 1;
  src.connect(gain);
  gain.connect(audio.destination);
  src.start();
  shotNode = src;
}

/** 实弹。枪声和坍塌叠在一起，满响度，不经过压缩。 */
export function killshot() {
  pulse(false);
  stopDread();
  const audio = ac();
  if (!audio) return;
  if (shotBuffer) playShot(audio, shotBuffer);
  else {
    void primeShot().then((buf) => {
      if (buf) playShot(audio, buf);
      else brutalFallback();
    });
  }
  if (collapseBuffer) playClip(collapseBuffer);
  else void primeCollapse().then((buf) => { if (buf) playClip(buf); });
}

function brutalFallback() {
  const audio = ac();
  if (!audio) return;
  const now = audio.currentTime;
  const crack = noise(audio, 0.2);
  const high = audio.createBiquadFilter();
  high.type = 'highpass';
  high.frequency.setValueAtTime(900, now);
  const gain = audio.createGain();
  gain.gain.setValueAtTime(1, now);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
  crack.connect(high);
  high.connect(gain);
  gain.connect(audio.destination);
  crack.start(now);
  crack.stop(now + 0.22);
  const body = audio.createOscillator();
  body.type = 'sine';
  body.frequency.setValueAtTime(140, now);
  body.frequency.exponentialRampToValueAtTime(32, now + 0.45);
  const bodyGain = audio.createGain();
  bodyGain.gain.setValueAtTime(1, now);
  bodyGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.7);
  body.connect(bodyGain);
  bodyGain.connect(audio.destination);
  body.start(now);
  body.stop(now + 0.75);
}

let applauseBuffer: AudioBuffer | null = null;
let applauseLoading: Promise<AudioBuffer | null> | null = null;
let applauseNode: AudioBufferSourceNode | null = null;
let collapseBuffer: AudioBuffer | null = null;
let collapseLoading: Promise<AudioBuffer | null> | null = null;

function loadWav(url: string, ready: () => AudioBuffer | null, save: (buf: AudioBuffer) => void, pending: () => Promise<AudioBuffer | null> | null, store: (job: Promise<AudioBuffer | null>) => void) {
  const audio = ac();
  if (!audio) return Promise.resolve(null);
  const have = ready();
  if (have) return Promise.resolve(have);
  const job = pending();
  if (job) return job;
  const next = fetch(url)
    .then((res) => res.arrayBuffer())
    .then((raw) => audio.decodeAudioData(raw.slice(0)))
    .then((buf) => {
      save(buf);
      return buf;
    })
    .catch(() => null);
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
  const src = audio.createBufferSource();
  src.buffer = buf;
  const gain = audio.createGain();
  gain.gain.value = 1;
  src.connect(gain);
  gain.connect(audio.destination);
  src.start();
}

/** 出完退场。铜管上行，然后掌声铺满。 */
export function applause() {
  const audio = ac();
  if (!audio) return;
  const start = (buf: AudioBuffer) => {
    if (applauseNode) {
      try { applauseNode.stop(); } catch { /* already ended */ }
    }
    const src = audio.createBufferSource();
    src.buffer = buf;
    const gain = audio.createGain();
    gain.gain.value = 1;
    src.connect(gain);
    gain.connect(audio.destination);
    src.start();
    applauseNode = src;
  };
  if (applauseBuffer) start(applauseBuffer);
  else void primeApplause().then((buf) => { if (buf) start(buf); });
}
