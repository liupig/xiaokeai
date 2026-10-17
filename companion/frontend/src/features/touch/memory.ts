import type { TouchZone } from '../../engine/types';

export interface ZoneMem {
  heat: number;
  streak: number;
  lastAt: number;
}

export interface TouchMem {
  bond: number;
  knownSince: number;
  muteUntil: number;
  speechAt: number[];
  lastSpoken: string;
  recentPoses: string[];
  lastTouchAt: number;
  zones: Record<TouchZone, ZoneMem>;
}

const ZONES: TouchZone[] = ['head', 'face', 'chest', 'waist', 'hand'];

const HALF_MS: Record<TouchZone, number> = {
  head: 42000,
  face: 55000,
  hand: 36000,
  waist: 50000,
  chest: 80000,
};

const STREAK_GAP = 14000;
const SPEECH_WINDOW = 120000;

function blankZone(): ZoneMem {
  return { heat: 0, streak: 0, lastAt: 0 };
}

export function emptyTouch(now: number, bond = 0.35): TouchMem {
  const zones = {} as Record<TouchZone, ZoneMem>;
  for (const z of ZONES) zones[z] = blankZone();
  return {
    bond,
    knownSince: now,
    muteUntil: 0,
    speechAt: [],
    lastSpoken: '',
    recentPoses: [],
    lastTouchAt: 0,
    zones,
  };
}

function keyOf(id: number) {
  return `companion.touch.${id}`;
}

export function loadTouch(id: number, now: number, seedBond = 0.35): TouchMem {
  const fresh = emptyTouch(now, seedBond);
  if (!id) return fresh;
  try {
    const raw = localStorage.getItem(keyOf(id));
    if (!raw) return fresh;
    const parsed = JSON.parse(raw) as Partial<TouchMem>;
    const zones = { ...fresh.zones };
    for (const z of ZONES) {
      const row = parsed.zones?.[z];
      if (!row) continue;
      zones[z] = {
        heat: Number(row.heat) || 0,
        streak: Number(row.streak) || 0,
        lastAt: Number(row.lastAt) || 0,
      };
    }
    return {
      bond: clamp(Number(parsed.bond) || seedBond, 0.08, 0.96),
      knownSince: Number(parsed.knownSince) || now,
      muteUntil: Number(parsed.muteUntil) || 0,
      speechAt: Array.isArray(parsed.speechAt) ? parsed.speechAt.map(Number).filter((n) => n > 0) : [],
      lastSpoken: String(parsed.lastSpoken || ''),
      recentPoses: Array.isArray(parsed.recentPoses) ? parsed.recentPoses.map(String).slice(-4) : [],
      lastTouchAt: Number(parsed.lastTouchAt) || 0,
      zones,
    };
  } catch {
    return fresh;
  }
}

export function saveTouch(id: number, mem: TouchMem) {
  if (!id) return;
  try { localStorage.setItem(keyOf(id), JSON.stringify(mem)); } catch { /* 隐私模式 */ }
}

export function liveZone(z: ZoneMem, zone: TouchZone, now: number) {
  const dt = Math.max(0, now - (z.lastAt || 0));
  const heat = (z.heat || 0) * Math.exp(-dt / HALF_MS[zone]);
  const streak = dt > STREAK_GAP ? 0 : (z.streak || 0);
  return { heat, streak };
}

export function recentSpeech(mem: TouchMem, now: number) {
  return mem.speechAt.filter((t) => now - t < SPEECH_WINDOW).length;
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

export function commitTouch(
  mem: TouchMem,
  zone: TouchZone,
  now: number,
  patch: { heatAdd: number; bondDelta: number; muteMs: number; pose: string | null; spoken: string },
) {
  const live = liveZone(mem.zones[zone], zone, now);
  mem.zones[zone] = {
    heat: Math.min(1, live.heat + patch.heatAdd),
    streak: live.streak + 1,
    lastAt: now,
  };
  mem.bond = clamp(mem.bond + patch.bondDelta, 0.08, 0.96);
  mem.lastTouchAt = now;
  mem.speechAt = mem.speechAt.filter((t) => now - t < SPEECH_WINDOW);
  if (patch.spoken) {
    mem.speechAt.push(now);
    mem.lastSpoken = patch.spoken;
  }
  if (patch.muteMs > 0) mem.muteUntil = now + patch.muteMs;
  if (patch.pose) {
    mem.recentPoses = [...mem.recentPoses, patch.pose].slice(-4);
  }
  return mem;
}
