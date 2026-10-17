import type { TouchPose, TouchZone } from '../../engine/types';

/** 这一下的态度。后面几下会从亲昵滑到腻、麻、不理。 */
export type TouchTone =
  | 'fond' | 'shy' | 'dodge' | 'cover' | 'play'
  | 'bored' | 'numb' | 'ignore' | 'disdain';

export interface TouchRollInput {
  zone: TouchZone;
  hour: number;
  /** 0~1，触碰模块自己记的亲疏，不是商城好感 */
  bond: number;
  /** 第一次见面到现在 */
  knownMs: number;
  /** 距上次说话或触碰 */
  idleMs: number;
  /** 这次坐下来多久 */
  sessionMs: number;
  /** 衰减之后、这一下之前的热度 */
  heat: number;
  /** 短时间里连续摸同一处，间隔一长就归零 */
  streak: number;
  boundary: string;
  /** 两分钟里已经开口几次 */
  speechRecent: number;
  muted: boolean;
  recentPoses: string[];
  rng?: () => number;
}

export interface TouchRoll {
  tone: TouchTone;
  pose: TouchPose | null;
  speak: boolean;
  heatAdd: number;
  bondDelta: number;
  /** 冷淡地说过一次之后，这段时间不再开口 */
  muteMs: number;
}

const HEAT_ADD: Record<TouchZone, number> = {
  head: 0.13,
  face: 0.18,
  hand: 0.11,
  waist: 0.16,
  chest: 0.22,
};

const POSE: Record<string, TouchPose[]> = {
  'head.fond': ['squint', 'fond'],
  'head.shy': ['squint', 'shy'],
  'head.play': ['squint', 'fond', 'shy'],
  'head.dodge': ['shy', 'dodge'],
  'head.bored': ['bored'],
  'head.numb': ['flinch'],
  'head.disdain': ['cold', 'bored'],
  'face.fond': ['shy', 'fond'],
  'face.shy': ['shy', 'dodge'],
  'face.play': ['shy', 'dodge', 'squint'],
  'face.dodge': ['dodge', 'flinch'],
  'face.cover': ['shy', 'dodge'],
  'face.bored': ['bored', 'dodge'],
  'face.numb': ['flinch'],
  'face.disdain': ['cold'],
  'chest.fond': ['shy', 'fond'],
  'chest.shy': ['cover', 'shy'],
  'chest.play': ['shy', 'dodge', 'cover'],
  'chest.dodge': ['dodge', 'cover'],
  'chest.cover': ['cover'],
  'chest.bored': ['bored', 'cold'],
  'chest.numb': ['flinch'],
  'chest.disdain': ['cold'],
  'waist.fond': ['shy'],
  'waist.shy': ['dodge', 'shy'],
  'waist.play': ['dodge', 'shy'],
  'waist.dodge': ['dodge', 'cover'],
  'waist.cover': ['cover', 'dodge'],
  'waist.bored': ['bored'],
  'waist.numb': ['flinch'],
  'waist.disdain': ['cold'],
  'hand.fond': ['fond', 'squint'],
  'hand.shy': ['shy', 'fond'],
  'hand.play': ['fond', 'shy', 'squint'],
  'hand.dodge': ['dodge'],
  'hand.bored': ['bored'],
  'hand.numb': ['flinch'],
  'hand.disdain': ['cold'],
};

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

function pick<T>(pool: T[], rng: () => number, recent: string[], key: (x: T) => string): T {
  const fresh = pool.filter((x) => !recent.includes(key(x)));
  const src = fresh.length ? fresh : pool;
  return src[Math.floor(rng() * src.length)] ?? pool[0];
}

/** 认识越久、好感越高，越熟。刚见面时压得很低。 */
export function closeness(bond: number, knownMs: number) {
  const days = knownMs / 86400000;
  const known = days < 0.5 ? 0.22 : days < 3 ? 0.45 : days < 14 ? 0.68 : days < 45 ? 0.84 : 1;
  return clamp(bond * 0.62 + known * 0.38, 0, 1);
}

function timeMood(hour: number, zone: TouchZone) {
  const late = hour < 5 || hour >= 23;
  const morning = hour >= 6 && hour < 11;
  const evening = hour >= 18 && hour < 23;
  if (zone === 'chest' || zone === 'waist') {
    if (late) return 0.7;
    if (morning) return 0.78;
    if (evening) return 1.02;
    return 0.88;
  }
  if (zone === 'face') {
    if (late) return 0.86;
    if (morning) return 0.95;
    return 1;
  }
  if (morning) return 1.08;
  if (evening) return 1.04;
  if (late) return 0.92;
  return 1;
}

function idleBoost(idleMs: number) {
  if (idleMs > 6 * 3600000) return 1.22;
  if (idleMs > 45 * 60000) return 1.1;
  if (idleMs < 5000) return 0.9;
  return 1;
}

function sessionPatience(sessionMs: number) {
  const min = sessionMs / 60000;
  if (min < 8) return 1;
  if (min < 25) return 0.9;
  if (min < 50) return 0.78;
  return 0.64;
}

const ZONE_BASE: Record<TouchZone, number> = {
  head: 0.84,
  face: 0.6,
  hand: 0.74,
  waist: 0.5,
  chest: 0.36,
};

const HEAT_SENSE: Record<TouchZone, number> = {
  head: 0.8,
  face: 1.05,
  hand: 0.7,
  waist: 1,
  chest: 1.3,
};

function warmthOf(input: TouchRollInput) {
  const close = closeness(input.bond, input.knownMs);
  let w = ZONE_BASE[input.zone]
    * timeMood(input.hour, input.zone)
    * (0.55 + close * 0.7)
    * idleBoost(input.idleMs)
    * sessionPatience(input.sessionMs);
  const heatCut = 1 - Math.min(1, input.heat * HEAT_SENSE[input.zone]);
  w *= heatCut;
  if (input.streak >= 2) w *= Math.max(0.12, 1 - (input.streak - 1) * 0.2);
  if (input.boundary === 'strict' && (input.zone === 'chest' || input.zone === 'waist')) w *= 0.42;
  if (input.boundary === 'warm' && input.zone === 'chest') w *= 0.72;
  return clamp(w, 0, 1.2);
}

function toneFromWarmth(zone: TouchZone, warmth: number, close: number, rng: () => number): TouchTone {
  const r = rng();
  if (zone === 'chest' || zone === 'waist') {
    if (warmth > 0.72 && close > 0.62) {
      if (r < 0.34) return 'fond';
      if (r < 0.7) return 'shy';
      return 'play';
    }
    if (warmth > 0.48) {
      if (r < 0.4) return 'shy';
      if (r < 0.72) return 'cover';
      return 'dodge';
    }
    if (r < 0.55) return 'cover';
    if (r < 0.85) return 'dodge';
    return 'shy';
  }
  if (zone === 'face') {
    if (warmth > 0.75 && r < 0.4) return 'fond';
    if (warmth > 0.5) return r < 0.55 ? 'shy' : r < 0.8 ? 'play' : 'dodge';
    return r < 0.6 ? 'dodge' : 'shy';
  }
  if (warmth > 0.7) return r < 0.55 ? 'fond' : r < 0.85 ? 'play' : 'shy';
  if (warmth > 0.4) return r < 0.5 ? 'shy' : r < 0.8 ? 'play' : 'fond';
  return r < 0.7 ? 'shy' : 'dodge';
}

function pushed(input: TouchRollInput, rng: () => number): TouchTone | null {
  const intimate = input.zone === 'chest' || input.zone === 'face' || input.zone === 'waist';
  if (input.heat > 0.9 || input.streak >= 7) {
    const r = rng();
    if (r < 0.58) return 'ignore';
    if (r < 0.82) return 'numb';
    return intimate ? 'disdain' : 'bored';
  }
  if (input.heat > 0.64 || input.streak >= 4) {
    const r = rng();
    if (r < 0.42) return 'bored';
    if (r < 0.64) return 'numb';
    if (r < 0.84) return intimate ? 'cover' : 'dodge';
    return intimate ? 'disdain' : 'ignore';
  }
  return null;
}

function speakChance(tone: TouchTone, input: TouchRollInput, warmth: number) {
  if (tone === 'ignore' || tone === 'numb') return 0;
  if (input.muted) return 0;
  let p = {
    fond: 0.46,
    shy: 0.3,
    play: 0.36,
    dodge: 0.1,
    cover: 0.16,
    bored: 0.07,
    disdain: 0.42,
    numb: 0,
    ignore: 0,
  }[tone];
  if (input.zone === 'chest' || input.zone === 'waist') p *= warmth < 0.5 ? 0.45 : 0.8;
  if (input.boundary === 'strict' && (input.zone === 'chest' || input.zone === 'waist' || input.zone === 'face')) {
    p *= 0.35;
  }
  if (input.speechRecent >= 4) return 0;
  if (input.speechRecent >= 2) p *= 0.22;
  else if (input.speechRecent === 1) p *= 0.55;
  return p;
}

function bondDelta(tone: TouchTone, zone: TouchZone, heat: number) {
  if (tone === 'disdain') return -0.02;
  if ((zone === 'chest' || zone === 'waist') && heat > 0.45) return -0.01;
  if (tone === 'fond' && (zone === 'head' || zone === 'hand')) return 0.014;
  if (tone === 'fond') return 0.008;
  if (tone === 'shy' && (zone === 'head' || zone === 'face' || zone === 'hand')) return 0.007;
  return 0;
}

/** 这一下做什么。同一处摸多了会推开、腻、最后不理。 */
export function decideTouch(input: TouchRollInput): TouchRoll {
  const rng = input.rng ?? Math.random;
  const close = closeness(input.bond, input.knownMs);
  const warmth = warmthOf(input);
  let tone = pushed(input, rng) ?? toneFromWarmth(input.zone, warmth, close, rng);
  if (input.boundary === 'strict' && tone === 'fond' && input.zone !== 'head' && input.zone !== 'hand') {
    tone = input.zone === 'face' ? 'shy' : 'cover';
  }
  if (input.boundary === 'warm' && tone === 'fond' && input.zone === 'chest' && close < 0.7) {
    tone = 'shy';
  }
  const pose = tone === 'ignore'
    ? null
    : pick(POSE[`${input.zone}.${tone}`] ?? ['flinch'], rng, input.recentPoses, (p) => p);
  const speak = rng() < speakChance(tone, input, warmth);
  return {
    tone,
    pose,
    speak,
    heatAdd: HEAT_ADD[input.zone],
    bondDelta: bondDelta(tone, input.zone, input.heat),
    muteMs: tone === 'disdain' && speak ? 48000 : 0,
  };
}
