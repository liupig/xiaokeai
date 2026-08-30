/**
 * 表演语法：镜头 / 情绪 / 动作 / 站位 成套。
 *
 * 景别六档（先定景，再滤表演）：
 *   ecu    特写 —— 表情为主，头面微动
 *   bust   1/4  —— 肩胸以上：思考、害羞、看
 *   half   1/2  —— 半身聊天，大量手势（挥手、比心、卖萌、说话）
 *   threeQ 3/4  —— 七分身：鞠躬、转身、更大的身体
 *   full   全身 —— 坐下、走路、跳舞、换站位
 *   long   远景 —— 舞台、舞蹈、走位
 *
 * 等级：S 55% / A 32% / B 13%。运镜只在景别变了时切。
 */
import type { CamShotId, EmotionKey } from '../../engine/types';
import type { ExprKind, Grade, Intent } from './lexicon';
import { DIST_RANK, type Distance } from './lexicon';

export type { Grade, Distance, MotionScale } from './lexicon';
export type CamPolicy = 'hold' | 'breathe' | 'cut';

export const GRADE_P: Record<Grade, number> = { S: 0.55, A: 0.32, B: 0.13 };

export interface Combo {
  id: string;
  distance: Distance;
  shots: { id: CamShotId; grade: Grade }[];
  intents: Intent[];
  exprLead: boolean;
  standOk: boolean;
  cam: CamPolicy;
  moods: EmotionKey[];
}

const ALL_MOODS: EmotionKey[] = ['happy', 'sad', 'relaxed', 'angry', 'neutral'];

export const COMBOS: Combo[] = [
  {
    id: 'ecu',
    distance: 'ecu',
    shots: [
      { id: 'close', grade: 'S' },
    ],
    intents: ['nod', 'look', 'shake'],
    exprLead: true,
    standOk: false,
    cam: 'hold',
    moods: ALL_MOODS,
  },
  {
    id: 'bust',
    distance: 'bust',
    shots: [
      { id: 'bust', grade: 'S' },
      { id: 'yawL45', grade: 'A' },
      { id: 'yawR45', grade: 'A' },
    ],
    intents: ['nod', 'look', 'shake', 'talk', 'think', 'shy'],
    exprLead: true,
    standOk: false,
    cam: 'hold',
    moods: ALL_MOODS,
  },
  {
    id: 'half',
    distance: 'half',
    shots: [
      { id: 'half', grade: 'S' },
      { id: 'yawL45', grade: 'A' },
      { id: 'yawR45', grade: 'A' },
    ],
    intents: [
      'nod', 'shake', 'think', 'look', 'talk', 'tease', 'shy', 'cute',
      'comfort', 'greet', 'heart', 'kiss', 'clap', 'stretch',
    ],
    exprLead: false,
    standOk: false,
    cam: 'breathe',
    moods: ALL_MOODS,
  },
  {
    id: 'threeQ',
    distance: 'threeQ',
    shots: [
      { id: 'threeQ', grade: 'S' },
      { id: 'low45', grade: 'A' },
      { id: 'yawL90', grade: 'B' },
      { id: 'yawR90', grade: 'B' },
    ],
    intents: [
      'nod', 'shake', 'think', 'look', 'talk', 'tease', 'shy', 'cute',
      'comfort', 'greet', 'heart', 'kiss', 'clap', 'stretch', 'bow',
    ],
    exprLead: false,
    standOk: false,
    cam: 'breathe',
    moods: ALL_MOODS,
  },
  {
    id: 'full',
    distance: 'full',
    shots: [
      { id: 'full', grade: 'S' },
      { id: 'low45', grade: 'A' },
      { id: 'high45', grade: 'A' },
      { id: 'yawL90', grade: 'B' },
      { id: 'yawR90', grade: 'B' },
    ],
    intents: [
      'greet', 'bow', 'clap', 'stretch', 'sit', 'walk', 'dance',
      'heart', 'kiss', 'nod', 'talk', 'look', 'cute', 'idle',
    ],
    exprLead: false,
    standOk: true,
    cam: 'cut',
    moods: ALL_MOODS,
  },
  {
    id: 'long',
    distance: 'long',
    shots: [
      { id: 'long', grade: 'S' },
      { id: 'high45', grade: 'A' },
      { id: 'yawL90', grade: 'A' },
      { id: 'yawR90', grade: 'A' },
    ],
    intents: ['dance', 'walk', 'sit', 'greet', 'idle'],
    exprLead: false,
    standOk: true,
    cam: 'cut',
    moods: ALL_MOODS,
  },
];

const INTIMATE_RE = /小声|悄悄|喜欢你|爱你|想你|靠近|飞吻|亲亲|mua/i;
const SHY_RE = /害羞|脸红|心动/i;
const SHOW_RE = /跳.*舞|来一段|来一支|坐下|走路|换边|左边|右边|dance/i;

export const EXPR_GRADE: Record<ExprKind, Grade> = {
  smile: 'S',
  relax: 'S',
  sadEye: 'S',
  blush: 'A',
  wink: 'A',
  sparkle: 'A',
  tear: 'B',
  angry: 'B',
  heartEye: 'B',
  surprise: 'B',
};

export const ANCHOR_SHOT: Record<Distance, CamShotId> = {
  ecu: 'close',
  bust: 'bust',
  half: 'half',
  threeQ: 'threeQ',
  full: 'full',
  long: 'long',
};

export function distanceOfShot(id: CamShotId | null | undefined): Distance {
  if (!id) return 'half';
  if (id === 'close') return 'ecu';
  if (id === 'bust') return 'bust';
  if (id === 'threeQ') return 'threeQ';
  if (id === 'full') return 'full';
  if (id === 'long') return 'long';
  // 运镜（仰拍/左转…）不改景别
  if (id === 'half') return 'half';
  return 'half';
}

export function minDistOfIntent(intent: Intent): Distance {
  if (['nod', 'look', 'shake'].includes(intent)) return 'ecu';
  if (['think', 'shy'].includes(intent)) return 'bust';
  if (['bow'].includes(intent)) return 'threeQ';
  if (['sit', 'walk', 'dance', 'idle'].includes(intent)) return 'full';
  return 'half';
}

export function distAllowed(need: Distance, current: Distance): boolean {
  return DIST_RANK[current] >= DIST_RANK[need];
}

export function comboByDistance(d: Distance): Combo {
  return COMBOS.find((c) => c.distance === d) ?? COMBOS[2];
}

export interface SceneNeed {
  dancing?: boolean;
  intimate?: boolean;
  forceWide?: boolean;
  phase?: string;
  intent?: Intent | null;
  text?: string;
}

export function neededDistance(need: SceneNeed): Distance {
  if (need.dancing) return 'full';
  if (need.forceWide) return 'full';
  const t = need.text || '';
  if (/跳.*舞|来一段|来一支|dance/i.test(t)) return 'full';
  if (/坐下/.test(t)) return 'full';
  if (/走路|换边|左边|右边/.test(t)) return 'full';
  if (need.intent === 'bow' || /鞠躬|谢谢你/.test(t)) return 'threeQ';
  if (need.intimate || INTIMATE_RE.test(t)) return 'ecu';
  if (need.intent === 'think' || need.intent === 'shy' || SHY_RE.test(t)) return 'bust';
  if (SHOW_RE.test(t)) return 'full';
  return 'half';
}

export function pickByGrade<T extends { grade: Grade }>(pool: T[]): T | null {
  if (!pool.length) return null;
  const buckets: Record<Grade, T[]> = { S: [], A: [], B: [] };
  for (const item of pool) buckets[item.grade].push(item);
  const roll = Math.random();
  const order: Grade[] = roll < GRADE_P.S
    ? ['S', 'A', 'B']
    : roll < GRADE_P.S + GRADE_P.A
      ? ['A', 'S', 'B']
      : ['B', 'A', 'S'];
  for (const g of order) {
    const bin = buckets[g];
    if (bin.length) return bin[Math.floor(Math.random() * bin.length)];
  }
  return pool[Math.floor(Math.random() * pool.length)] ?? null;
}

export function pickGraded<T extends { grade: Grade; name: string }>(
  pool: T[],
  recent: string[],
): T | null {
  const fresh = pool.filter((x) => !recent.includes(x.name));
  const src = fresh.length ? fresh : pool;
  return pickByGrade(src);
}

export function pickShotFor(distance: Distance, prefer?: CamShotId | null): CamShotId {
  const combo = comboByDistance(distance);
  if (prefer && combo.shots.some((s) => s.id === prefer)) return prefer;
  const hit = pickByGrade(combo.shots);
  return hit?.id ?? combo.shots[0].id;
}

export function canPlayIntent(intent: Intent, shot: CamShotId | null | undefined): boolean {
  const d = distanceOfShot(shot);
  const combo = comboByDistance(d);
  if (combo.intents.length && !combo.intents.includes(intent)) return false;
  return distAllowed(minDistOfIntent(intent), d);
}

export function canStand(shot: CamShotId | null | undefined): boolean {
  return comboByDistance(distanceOfShot(shot)).standOk;
}

export function fitsDistance(
  card: { minDist: Distance; maxDist: Distance },
  shot: CamShotId | null | undefined,
): boolean {
  const d = distanceOfShot(shot);
  return DIST_RANK[d] >= DIST_RANK[card.minDist] && DIST_RANK[d] <= DIST_RANK[card.maxDist];
}

export function exprKindsAllowed(
  kinds: ExprKind[],
  shot: CamShotId | null | undefined,
  mood: EmotionKey,
): ExprKind[] {
  const combo = comboByDistance(distanceOfShot(shot));
  const filtered = kinds.filter((k) => {
    const g = EXPR_GRADE[k] ?? 'B';
    if (!combo.exprLead) return true;
    if (g !== 'B') return true;
    if (mood === 'sad' && k === 'tear') return true;
    if (mood === 'angry' && k === 'angry') return true;
    return false;
  });
  const max = combo.exprLead ? 2 : combo.distance === 'long' ? 1 : 2;
  const picked: ExprKind[] = [];
  const graded = filtered.map((k) => ({ id: k, grade: EXPR_GRADE[k] ?? 'B' as Grade }));
  while (picked.length < max && graded.length) {
    const hit = pickByGrade(graded);
    if (!hit) break;
    const i = graded.findIndex((x) => x.id === hit.id);
    if (i >= 0) graded.splice(i, 1);
    if (!picked.includes(hit.id)) picked.push(hit.id);
  }
  return picked.length ? picked : filtered.slice(0, max);
}

export interface CoverCue {
  text?: string;
  phase?: string;
  dancing?: boolean;
  beat?: string;
  llmShot?: CamShotId | null;
  intents?: string[];
  forceWide?: boolean;
}

export type CoverDecision =
  | { action: 'hold' }
  | { action: 'go'; shot: CamShotId; distance: Distance };

export function resolveCover(input: {
  current: CamShotId | null;
  holding: boolean;
  lastAt: number;
  now: number;
  cue: CoverCue;
}): CoverDecision {
  const dancing = !!(input.cue.dancing || input.cue.beat === 'dance');
  const target = neededDistance({
    dancing,
    forceWide: input.cue.forceWide,
    intimate: INTIMATE_RE.test(input.cue.text || ''),
    phase: input.cue.phase,
    intent: (input.cue.intents?.[0] as Intent) || null,
    text: input.cue.text,
  });
  const combo = comboByDistance(target);
  const currentD = distanceOfShot(input.current);
  const llm = input.cue.llmShot ?? null;
  const llmOk = llm && combo.shots.some((s) => s.id === llm) ? llm : null;

  if (dancing) {
    if ((currentD === 'full' || currentD === 'long') && input.current) return { action: 'hold' };
    return { action: 'go', shot: pickShotFor('full', llmOk), distance: 'full' };
  }

  if (currentD !== target || !input.current) {
    return { action: 'go', shot: pickShotFor(target, llmOk), distance: target };
  }

  if (input.now - input.lastAt < 1100) return { action: 'hold' };

  if (combo.cam === 'hold') {
    if (input.holding) return { action: 'hold' };
    if (Math.random() > GRADE_P.A) return { action: 'hold' };
  } else if (combo.cam === 'breathe') {
    if (input.holding) return { action: 'hold' };
    const g = combo.shots.find((s) => s.id === input.current)?.grade ?? 'A';
    if (g === 'S' && Math.random() < GRADE_P.S) return { action: 'hold' };
    if (g === 'A' && Math.random() < GRADE_P.A) return { action: 'hold' };
  } else if (input.holding) {
    return { action: 'hold' };
  }

  const pool = combo.shots.filter((s) => s.id !== input.current);
  const hit = pickByGrade(pool.length ? pool : combo.shots);
  const shot = llmOk && Math.random() < GRADE_P.A ? llmOk : (hit?.id ?? combo.shots[0].id);
  if (shot === input.current) return { action: 'hold' };
  return { action: 'go', shot, distance: target };
}

export function shotHoldMs(id: CamShotId, cue: CoverCue): number {
  const combo = comboByDistance(distanceOfShot(id));
  const g = combo.shots.find((s) => s.id === id)?.grade ?? 'A';
  const base = g === 'S' ? 4200 : g === 'A' ? 3200 : 2200;
  const sad = cue.phase === 'goodbye' || /难过|伤心|唉/.test(cue.text || '');
  const policy = combo.cam === 'hold' ? 1.35 : combo.cam === 'cut' ? 0.9 : 1;
  return base * policy * (sad ? 1.2 : 1) * (0.85 + Math.random() * 0.3);
}

export function shotMoveSec(id: CamShotId): number {
  const table: Partial<Record<CamShotId, number>> = {
    close: 1.6, bust: 1.5, half: 1.5, threeQ: 1.7, full: 1.8, long: 2.0,
    low45: 1.5, high45: 1.5,
    yawL45: 1.6, yawR45: 1.6,
    yawL90: 2.0, yawR90: 2.0,
  };
  return (table[id] ?? 1.6) * (0.9 + Math.random() * 0.25);
}
