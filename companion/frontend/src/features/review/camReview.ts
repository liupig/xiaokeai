/**
 * 审查空间：景别 × 运镜 × 站位 × 具体动作资产。
 * 分类（挥手/点头…）只用来筛选，笛卡尔积按每一条 VMD 走。
 */
import { api } from '../../api/client';
import type { AssetItem } from '../../api/client';
import { CAM_SHOTS } from '../../engine/camera';
import type { StandSlot } from '../../engine/stage';
import type { CamShotId } from '../../engine/types';
import { parseMotionCat, stripCatPrefix, type MotionCat } from '../assets/motionMeta';
import { isFramingCam } from '../performance/camLexicon';
import { INTENTS, buildMotionCards, type Intent } from '../performance/lexicon';

export type Verdict = 'unset' | 'ok' | 'bad';

export const SIZES: { id: CamShotId; label: string }[] = [
  { id: 'close', label: '特写' },
  { id: 'bust', label: '1/4' },
  { id: 'half', label: '1/2' },
  { id: 'threeQ', label: '3/4' },
  { id: 'full', label: '全身' },
  { id: 'long', label: '远景' },
];

const SIZE_IDS = new Set(SIZES.map((s) => s.id));

export const MOVES: { id: CamShotId; label: string }[] = CAM_SHOTS
  .filter((s) => !SIZE_IDS.has(s.id))
  .map((s) => ({ id: s.id, label: s.label }));

export const STANDS: { id: StandSlot; label: string }[] = [
  { id: 'left', label: '左 ¼' },
  { id: 'center', label: '中 ½' },
  { id: 'right', label: '右 ¾' },
];

export const INTENT_LABEL: Record<Intent, string> = {
  greet: '挥手', nod: '点头', shake: '摇头', think: '思考', shy: '害羞',
  heart: '比心', kiss: '飞吻', bow: '鞠躬', sit: '坐下', talk: '说话',
  stretch: '伸懒腰', cute: '卖萌', look: '看', clap: '鼓掌',
  comfort: '安慰', tease: '俏皮', idle: '待机', dance: '舞蹈', walk: '走路',
};

export type ActionPick =
  | { kind: 'none'; label: string }
  | { kind: 'builtin'; id: 'nod' | 'shake'; label: string }
  | { kind: 'asset'; name: string; label: string; cat: MotionCat; tags: Intent[]; loop: boolean };

export type ActFilter = 'all' | 'none' | Intent;

export type CamPick =
  | { kind: 'hold'; label: string }
  | { kind: 'move'; id: CamShotId; label: string }
  | { kind: 'vmd'; name: string; label: string };

export function camKey(cam: CamPick): string {
  if (cam.kind === 'hold') return 'hold';
  if (cam.kind === 'move') return `move:${cam.id}`;
  return `vmd:${cam.name}`;
}

export function actionKey(a: ActionPick): string {
  if (a.kind === 'none') return 'none';
  if (a.kind === 'builtin') return `builtin:${a.id}`;
  return `asset:${a.name}`;
}

export function parseActionKey(key: string, actions: ActionPick[]): ActionPick {
  return actions.find((a) => actionKey(a) === key) ?? actions[0];
}

export interface ComboSel {
  size: CamShotId;
  cam: CamPick;
  stand: StandSlot;
  action: ActionPick;
}

export function comboId(sel: ComboSel): string {
  return [sel.size, camKey(sel.cam), sel.stand, actionKey(sel.action)]
    .map(encodeURIComponent)
    .join('|');
}

export function comboLabel(sel: ComboSel): string {
  const size = SIZES.find((s) => s.id === sel.size)?.label ?? sel.size;
  const stand = STANDS.find((s) => s.id === sel.stand)?.label ?? sel.stand;
  const group = actionGroupLabel(sel.action);
  const act = sel.action.kind === 'asset'
    ? `${group} · ${sel.action.label}`
    : sel.action.label;
  return `${size} × ${sel.cam.label} × ${stand} × ${act}`;
}

export function actionGroupLabel(a: ActionPick): string {
  if (a.kind === 'none') return '无动作';
  if (a.kind === 'builtin') return INTENT_LABEL[a.id];
  const tag = a.tags[0];
  return tag ? INTENT_LABEL[tag] : '其它';
}

export function parseCamKey(key: string, cams: CamPick[]): CamPick {
  return cams.find((c) => camKey(c) === key) ?? cams[0];
}

export function allCamPicks(vmds: { name: string; label: string }[]): CamPick[] {
  return [
    { kind: 'hold', label: '定镜' },
    ...MOVES.map((m) => ({ kind: 'move' as const, id: m.id, label: m.label })),
    ...vmds
      .filter((v) => !isFramingCam(v))
      .map((v) => ({ kind: 'vmd' as const, name: v.name, label: v.label })),
  ];
}

export function allActions(motions: AssetItem[]): ActionPick[] {
  const cards = buildMotionCards(motions);
  const byName = new Map(motions.map((m) => [m.name, m]));
  const assets: ActionPick[] = cards.map((c) => {
    const raw = byName.get(c.name);
    return {
      kind: 'asset' as const,
      name: c.name,
      label: stripCatPrefix(c.label) || c.name,
      cat: raw ? parseMotionCat(raw) : 'interact',
      tags: c.tags,
      loop: c.loop,
    };
  });
  assets.sort((a, b) => {
    if (a.kind !== 'asset' || b.kind !== 'asset') return 0;
    const ia = INTENTS.indexOf(a.tags[0]);
    const ib = INTENTS.indexOf(b.tags[0]);
    const ga = ia < 0 ? 99 : ia;
    const gb = ib < 0 ? 99 : ib;
    if (ga !== gb) return ga - gb;
    return a.label.localeCompare(b.label, 'zh');
  });
  return [
    { kind: 'none', label: '无动作' },
    { kind: 'builtin', id: 'nod', label: '点头（程序）' },
    { kind: 'builtin', id: 'shake', label: '摇头（程序）' },
    ...assets,
  ];
}

export function actionMatchesFilter(a: ActionPick, filter: ActFilter): boolean {
  if (filter === 'all') return a.kind !== 'none';
  if (filter === 'none') return a.kind === 'none';
  if (a.kind === 'none') return false;
  if (a.kind === 'builtin') return a.id === filter;
  return a.tags.includes(filter);
}

export function intentFilters(actions: ActionPick[]): { id: ActFilter; label: string; n: number }[] {
  const chips: { id: ActFilter; label: string; n: number }[] = [
    { id: 'all', label: '全部', n: actions.filter((a) => a.kind !== 'none').length },
    { id: 'none', label: '无动作', n: 1 },
  ];
  for (const intent of INTENTS) {
    const n = actions.filter((a) => actionMatchesFilter(a, intent)).length;
    if (n) chips.push({ id: intent, label: INTENT_LABEL[intent], n });
  }
  return chips;
}

export function filterOfAction(a: ActionPick): ActFilter {
  if (a.kind === 'none') return 'none';
  if (a.kind === 'builtin') return a.id;
  return a.tags[0] ?? 'all';
}

export function comboCount(nCam: number, nAct: number) {
  return SIZES.length * nCam * STANDS.length * nAct;
}

/** 同一运镜×站位×动作里，当前景别及更远的景别（特写→远景） */
export function widerSizes(size: CamShotId): CamShotId[] {
  const i = SIZES.findIndex((s) => s.id === size);
  if (i < 0) return [size];
  return SIZES.slice(i).map((s) => s.id);
}

export function comboIdWithSize(id: string, size: CamShotId): string {
  const parts = id.split('|');
  if (!parts.length) return id;
  parts[0] = encodeURIComponent(size);
  return parts.join('|');
}

export function comboIdWithStand(id: string, stand: StandSlot): string {
  const parts = id.split('|');
  if (parts.length < 3) return id;
  parts[2] = encodeURIComponent(stand);
  return parts.join('|');
}

/** 左可用 → 中、右都可用。只改站位。 */
export function laterStands(stand: StandSlot): StandSlot[] {
  const i = STANDS.findIndex((s) => s.id === stand);
  if (i < 0) return [stand];
  return STANDS.slice(i).map((s) => s.id);
}

function inheritIds(id: string): string[] {
  const parts = id.split('|');
  if (parts.length !== 4) return [];
  const rawSize = decodeURIComponent(parts[0] || '') as CamShotId;
  const rawStand = decodeURIComponent(parts[2] || '') as StandSlot;
  if (!STANDS.some((s) => s.id === rawStand)) return [];
  const out: string[] = [];
  for (const size of widerSizes(rawSize)) {
    for (const stand of laterStands(rawStand)) {
      out.push(comboIdWithStand(comboIdWithSize(id, size), stand));
    }
  }
  return out;
}

function stampInherit(
  next: Record<string, Verdict>,
  source: Record<string, Verdict>,
  verdict: 'ok' | 'bad',
  overwrite: boolean,
) {
  for (const [id, v] of Object.entries(source)) {
    if (v !== verdict) continue;
    for (const tid of inheritIds(id)) {
      if (verdict === 'ok') {
        // 当场去掉的格子保持不可用，近景可用不再盖回去
        if (next[tid] !== 'bad') next[tid] = 'ok';
      } else if (overwrite || (next[tid] !== 'ok' && next[tid] !== 'bad')) {
        next[tid] = 'bad';
      }
    }
  }
}

/** 近景可用 → 更远景别都可用。不可用只填还没标的更远景别。 */
export function expandSizeOk(map: Record<string, Verdict>): Record<string, Verdict> {
  const next: Record<string, Verdict> = { ...map };
  for (const [id, v] of Object.entries(map)) {
    if (v !== 'ok' && v !== 'bad') continue;
    const rawSize = decodeURIComponent(id.split('|')[0] || '') as CamShotId;
    for (const s of widerSizes(rawSize)) {
      const tid = comboIdWithSize(id, s);
      if (v === 'ok') {
        if (next[tid] !== 'bad') next[tid] = 'ok';
      } else if (next[tid] !== 'ok' && next[tid] !== 'bad') {
        next[tid] = 'bad';
      }
    }
  }
  return next;
}

/** 左可用 → 中、右可用。不可用同样抄到还没标的中、右。 */
export function expandStandOk(map: Record<string, Verdict>): Record<string, Verdict> {
  const next: Record<string, Verdict> = { ...map };
  for (const [id, v] of Object.entries(map)) {
    if ((v !== 'ok' && v !== 'bad') || id.split('|').length < 4) continue;
    const rawStand = decodeURIComponent(id.split('|')[2] || '') as StandSlot;
    if (!STANDS.some((s) => s.id === rawStand)) continue;
    for (const s of laterStands(rawStand)) {
      const tid = comboIdWithStand(id, s);
      if (v === 'ok') {
        if (next[tid] !== 'bad') next[tid] = 'ok';
      } else if (next[tid] !== 'ok' && next[tid] !== 'bad') {
        next[tid] = 'bad';
      }
    }
  }
  return next;
}

/**
 * 景别近→远、站位左→右。
 * 可用、不可用都继承；没标保持没标，不会和不可用混成一种。
 * 不可用只填空白，不覆盖已经标过的可用。
 * 当场去掉的格子保持不可用，近景可用不会再盖回去。
 */
export function expandCompatOk(map: Record<string, Verdict>): Record<string, Verdict> {
  const next: Record<string, Verdict> = { ...map };
  stampInherit(next, map, 'ok', true);
  stampInherit(next, next, 'bad', false);
  return next;
}

/**
 * 审核顺序：运镜 → 站位 → 动作 → 景别（特写…远景）。
 * 每个组合从左边最近的景别开始，一档一档往右。
 */
export function indexOfCombo(sel: ComboSel, cams: CamPick[], actions: ActionPick[]): number {
  const si = Math.max(0, SIZES.findIndex((s) => s.id === sel.size));
  const ci = Math.max(0, cams.findIndex((c) => camKey(c) === camKey(sel.cam)));
  const ti = Math.max(0, STANDS.findIndex((s) => s.id === sel.stand));
  const ai = Math.max(0, actions.findIndex((a) => actionKey(a) === actionKey(sel.action)));
  const nS = SIZES.length;
  const nT = STANDS.length;
  const nA = actions.length;
  return ((ci * nT + ti) * nA + ai) * nS + si;
}

export function comboAt(index: number, cams: CamPick[], actions: ActionPick[]): ComboSel {
  const nC = Math.max(1, cams.length);
  const nT = STANDS.length;
  const nA = Math.max(1, actions.length);
  const nS = SIZES.length;
  const total = nC * nT * nA * nS;
  const i = ((index % total) + total) % total;
  const si = i % nS;
  const t = Math.floor(i / nS);
  const ai = t % nA;
  const u = Math.floor(t / nA);
  const ti = u % nT;
  const ci = Math.floor(u / nT) % nC;
  return {
    size: SIZES[si].id,
    cam: cams[ci],
    stand: STANDS[ti].id,
    action: actions[ai],
  };
}

const STORE_KEY = 'companion-cam-review-v3';
const LEGACY_KEYS = ['companion-cam-review', 'companion-cam-review-v2'];

function readLocal(key: string): Record<string, Verdict> {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Verdict>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function loadLocalVerdicts(): Record<string, Verdict> {
  const merged: Record<string, Verdict> = {};
  for (const key of [...LEGACY_KEYS, STORE_KEY]) Object.assign(merged, readLocal(key));
  return merged;
}

export function saveLocalVerdicts(map: Record<string, Verdict>) {
  localStorage.setItem(STORE_KEY, JSON.stringify(map));
}

/** 后端磁盘为准；若后端还是空的，把浏览器里旧标记迁过去。 */
export async function hydrateVerdicts(): Promise<{
  map: Record<string, Verdict>;
  path: string;
  migrated: boolean;
  inherited: number;
}> {
  const local = loadLocalVerdicts();
  const remote = await api.getCamReview();
  const server = (remote.verdicts || {}) as Record<string, Verdict>;
  const merged = expandCompatOk({ ...local, ...server });
  const inherited = Object.keys(merged).filter((k) => server[k] !== merged[k]).length;
  const migrated = Object.keys(server).length === 0 && Object.keys(local).length > 0;
  const extra = Object.keys(local).some((k) => server[k] !== local[k] && !server[k]);
  if (migrated || extra || inherited) {
    await api.putCamReview(merged);
    saveLocalVerdicts(merged);
  } else {
    saveLocalVerdicts(merged);
  }
  const { repertoire } = await import('../performance/repertoire');
  await repertoire.load().catch(() => {});
  return {
    map: merged,
    path: remote.path || 'companion/backend/data/cam_review.json',
    migrated,
    inherited,
  };
}

export async function persistVerdicts(map: Record<string, Verdict>) {
  const expanded = expandCompatOk(map);
  saveLocalVerdicts(expanded);
  await api.putCamReview(expanded);
  const { repertoire } = await import('../performance/repertoire');
  await repertoire.load().catch(() => {});
}

/** 线上正在播的这一拍标不可用：只动这一格，不让近景可用再继承回来。 */
export async function banApprovedCombo(id: string) {
  const remote = await api.getCamReview();
  const map: Record<string, Verdict> = {};
  for (const [k, v] of Object.entries(remote.verdicts || {})) {
    if (v === 'ok' || v === 'bad') map[k] = v as Verdict;
  }
  map[id] = 'bad';
  saveLocalVerdicts(map);
  await api.putCamReview(map);
  const { repertoire } = await import('../performance/repertoire');
  await repertoire.load().catch(() => {});
}

export function formatReport(
  map: Record<string, Verdict>,
  cams: CamPick[],
  actions: ActionPick[],
  resolveLabel: (id: string) => string,
) {
  const entries = Object.entries(map).filter(([, v]) => v === 'ok' || v === 'bad');
  const ok = entries.filter(([, v]) => v === 'ok');
  const bad = entries.filter(([, v]) => v === 'bad');
  const total = comboCount(cams.length, actions.length);
  return [
    '【镜头审查报告】运镜 × 站位 × 动作 × 景别（近→远、左→右：可用/不可用都继承，没标≠不可用）',
    `组合空间 ${total} 条（动作资产 ${actions.length}），已标 ${entries.length}（可用 ${ok.length}，不可用 ${bad.length}）`,
    '',
    '可用：',
    ...(ok.length ? ok.map(([id]) => `- ${resolveLabel(id)}`) : ['（无）']),
    '',
    '不可用：',
    ...(bad.length ? bad.map(([id]) => `- ${resolveLabel(id)}`) : ['（无）']),
  ].join('\n');
}

export function labelFromId(id: string, cams: CamPick[], actions: ActionPick[]): string {
  const [size, cam, stand, action] = id.split('|').map(decodeURIComponent);
  const sel: ComboSel = {
    size: size as CamShotId,
    cam: parseCamKey(cam, cams),
    stand: stand as StandSlot,
    action: parseActionKey(action, actions),
  };
  return comboLabel(sel);
}
