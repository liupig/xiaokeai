/**
 * 闲时表演库：闲着也别站桩。
 *
 * 两套闲时：
 *   chat  —— 说话间隙：还在这场对话里，站着、聊天距离、小动作
 *   alone —— goodbye 之后：一个人在场上玩，坐下、出神、走动都可以（只不上舞）
 */
import type { IdleMoveKind } from '../../engine/camera';
import type { CamShotId } from '../../engine/types';
import type { Intent } from './lexicon';

export type { IdleMoveKind };

export type IdleKind = 'chat' | 'alone';

/** 说话间隙：像还在听你说话 */
export const CHAT_IDLE_INTENTS: Intent[] = [
  'idle', 'look', 'think', 'shy', 'talk', 'stretch', 'cute', 'nod', 'shake', 'tease', 'comfort',
];
const CHAT_IDLE_SET = new Set<Intent>(CHAT_IDLE_INTENTS);
const CHAT_BAN = new Set<Intent>(['dance', 'walk', 'sit', 'kiss', 'bow', 'greet', 'clap']);

/** 一个人玩：除了跳舞都可上场，休闲的优先 */
export const ALONE_IDLE_INTENTS: Intent[] = [
  'sit', 'look', 'idle', 'stretch', 'think', 'cute', 'tease', 'comfort',
  'talk', 'shy', 'nod', 'shake', 'heart', 'clap', 'walk', 'greet',
];

export function isIdleSafeIntents(intents: Intent[], kind: IdleKind = 'chat') {
  if (intents.includes('dance')) return false;
  if (kind === 'alone') return intents.length > 0;
  if (intents.some((i) => CHAT_BAN.has(i))) return false;
  return intents.some((i) => CHAT_IDLE_SET.has(i));
}

export const IDLE_SIZES: CamShotId[] = ['bust', 'half', 'threeQ'];
export const IDLE_SIZE_OK = new Set<CamShotId>(['bust', 'half', 'threeQ', 'full']);

export const IDLE_MOVES: { kind: IdleMoveKind; label: string; shot: CamShotId | null }[] = [
  { kind: 'driftL', label: '轻移左', shot: 'yawL45' },
  { kind: 'driftR', label: '轻移右', shot: 'yawR45' },
  { kind: 'push', label: '轻推', shot: null },
  { kind: 'pull', label: '轻拉', shot: null },
  { kind: 'rise', label: '微仰', shot: 'high45' },
  { kind: 'settle', label: '落幅', shot: null },
];

const MOVE_CYCLE: IdleMoveKind[] = ['driftL', 'push', 'driftR', 'rise', 'pull', 'settle'];

export const IDLE_CADENCE = {
  firstCut: 0.85,
  afterSpeak: [1.6, 2.8] as const,
  betweenCuts: [6.2, 10.8] as const,
  /** goodbye 之后拉长，让一个姿势待得住 */
  aloneCuts: [8, 14] as const,
  aloneFirst: 2.4,
  /** 含定格末帧在内，一个动作待这么久才换下一个 */
  alonePoseHold: [24, 40] as const,
};

export function isIdleSize(size: CamShotId) {
  return IDLE_SIZE_OK.has(size);
}

export function idleSizeScore(size: CamShotId, kind: IdleKind = 'chat') {
  if (kind === 'alone') {
    if (size === 'full') return 22;
    if (size === 'threeQ') return 20;
    if (size === 'half') return 12;
    if (size === 'long') return 10;
    if (size === 'bust') return 6;
    if (size === 'close') return -6;
    return 0;
  }
  if (size === 'half') return 24;
  if (size === 'bust' || size === 'threeQ') return 20;
  if (size === 'full') return 4;
  if (size === 'close') return -8;
  if (size === 'long') return -28;
  return 0;
}

export function nextIdleMove(prev: IdleMoveKind | null): IdleMoveKind {
  const pool = MOVE_CYCLE.filter((k) => k !== prev);
  return pool[Math.floor(Math.random() * pool.length)] ?? 'driftL';
}

export function idleMoveToShot(kind: IdleMoveKind): CamShotId | undefined {
  return IDLE_MOVES.find((m) => m.kind === kind)?.shot ?? undefined;
}

export function idleMoveLabel(kind: IdleMoveKind) {
  return IDLE_MOVES.find((m) => m.kind === kind)?.label ?? '落幅';
}

function pickIntent(pool: Intent[]): Intent {
  return pool[Math.floor(Math.random() * pool.length)] ?? 'idle';
}

/** 说话间隙：小动作，像还在这场对话里 */
export function chatIdleIntent(mood: string): Intent | undefined {
  if (mood === 'happy') return Math.random() < 0.5 ? 'cute' : pickIntent(['idle', 'look', 'talk']);
  if (mood === 'sad') return Math.random() < 0.55 ? 'think' : 'look';
  if (mood === 'angry') return pickIntent(['look', 'shake', 'tease']);
  if (mood === 'relaxed') return pickIntent(['idle', 'look', 'talk', 'stretch']);
  return pickIntent(['look', 'think', 'idle', 'nod', 'shy']);
}

/** 一个人：坐下、出神、伸懒腰、换个站法，像人自己待着 */
export function aloneIdleIntent(mood: string): Intent | undefined {
  const r = Math.random();
  if (r < 0.26) return 'sit';
  if (r < 0.46) return 'look';
  if (r < 0.58) return 'idle';
  if (r < 0.68) return 'stretch';
  if (r < 0.78) return 'think';
  if (mood === 'happy') return pickIntent(['cute', 'tease', 'idle']);
  if (mood === 'sad') return pickIntent(['sit', 'comfort', 'think']);
  return pickIntent(['idle', 'cute', 'tease', 'walk', 'comfort']);
}

export function idleIntentForMode(kind: IdleKind, mood: string): Intent | undefined {
  return kind === 'alone' ? aloneIdleIntent(mood) : chatIdleIntent(mood);
}

/** @deprecated 用 idleIntentForMode */
export function idleIntentForMood(mood: string): Intent | undefined {
  return chatIdleIntent(mood);
}

export function idleCutGap(kind: IdleKind = 'chat') {
  const [a, b] = kind === 'alone' ? IDLE_CADENCE.aloneCuts : IDLE_CADENCE.betweenCuts;
  return a + Math.random() * (b - a);
}

export function idleAfterSpeakGap() {
  const [a, b] = IDLE_CADENCE.afterSpeak;
  return a + Math.random() * (b - a);
}
