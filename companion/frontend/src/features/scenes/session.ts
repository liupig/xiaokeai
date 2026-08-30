import { reactive } from 'vue';
import { api, type ChatExtra, type SceneCard } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { stage } from '../../engine/stage';
import type { CamShotId, EmotionKey } from '../../engine/types';
import { shots } from '../performance/shotConductor';
import { LOCAL_SCENES, type LocalSceneCard } from './catalog';
import { noteSceneTookBg } from '../keepsake/session';

const RECENT_KEY = 'companion.scenes.recent';
const MEM_KEY = 'companion.scene.mem';
const SALTS = ['潮', '刺', '懒', '近', '短', '热', '冷', '困', '轻', '硬'];
/** 超过这个时长没聊，跨过次日 6 点才主动换一场 */
const AUTO_SWITCH_QUIET_MS = 3 * 60 * 60 * 1000;
const DAY_ROLL_HOUR = 6;

interface SceneMem {
  id: string;
  assignedDay: string;
}

export const sceneSession = reactive({
  cards: [...LOCAL_SCENES] as SceneCard[],
  current: null as LocalSceneCard | null,
  characterId: 0,
  generating: false,
  lastLine: '',
  nextRotateAt: 0,
});

function localOf(card: SceneCard | null | undefined): LocalSceneCard | null {
  if (!card) return null;
  const hit = LOCAL_SCENES.find((c) => c.id === card.id);
  return hit ? { ...hit, ...card } : { ...card };
}

function pad2(n: number) {
  return n < 10 ? `0${n}` : String(n);
}

/** 场景日：凌晨 6 点前算前一天，当天不主动换景 */
export function sceneDay(ts = Date.now()): string {
  const d = new Date(ts);
  if (d.getHours() < DAY_ROLL_HOUR) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function memKey(characterId: number) {
  return `${MEM_KEY}.${characterId}`;
}

function readMem(characterId: number): SceneMem | null {
  if (!characterId) return null;
  try {
    const raw = JSON.parse(localStorage.getItem(memKey(characterId)) || 'null');
    if (!raw || typeof raw.id !== 'string' || typeof raw.assignedDay !== 'string') return null;
    return { id: raw.id, assignedDay: raw.assignedDay };
  } catch {
    return null;
  }
}

function writeMem(characterId: number, id: string, assignedDay = sceneDay()) {
  if (!characterId || !id) return;
  try {
    localStorage.setItem(memKey(characterId), JSON.stringify({ id, assignedDay }));
  } catch { /* 隐私模式 */ }
}

function findCard(id: string): LocalSceneCard | null {
  const pool = sceneSession.cards.length ? sceneSession.cards : LOCAL_SCENES;
  return localOf(pool.find((c) => c.id === id) || LOCAL_SCENES.find((c) => c.id === id));
}

export function rememberPickedScene(characterId: number, card: SceneCard | null | undefined) {
  if (!characterId || !card?.id) return;
  writeMem(characterId, card.id, sceneDay());
}

function readRecent(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    return Array.isArray(raw) ? raw.map(String) : [];
  } catch {
    return [];
  }
}

function pushRecent(id: string) {
  if (!id) return;
  const ids = [id, ...readRecent().filter((x) => x !== id)].slice(0, 10);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(ids));
  } catch { /* 隐私模式 */ }
}

function pickFresh(pool: SceneCard[]): LocalSceneCard {
  const recent = new Set(readRecent());
  const cur = sceneSession.current?.id;
  let cand = pool.filter((c) => !recent.has(c.id) && c.id !== cur);
  if (!cand.length) cand = pool.filter((c) => c.id !== cur);
  const src = cand.length ? cand : pool;
  return localOf(src[Math.floor(Math.random() * src.length)])!;
}

export function avoidLines(card: SceneCard | null | undefined): string {
  const full = localOf(card);
  if (!full) return '';
  const pool = [...(full.lines || [])];
  if (full.line) pool.push(full.line);
  return [...new Set(pool.filter(Boolean))].join(' / ');
}

export function sceneSalt() {
  return SALTS[Math.floor(Math.random() * SALTS.length)] + String(Math.floor(Math.random() * 90 + 10));
}

export function randomScene() {
  const pool = sceneSession.cards.length ? sceneSession.cards : LOCAL_SCENES;
  pickScene(pickFresh(pool));
  return sceneSession.current;
}

export function pickScene(card: SceneCard | null) {
  sceneSession.current = localOf(card);
  sceneSession.characterId = currentCharacterId();
  if (sceneSession.current) {
    pushRecent(sceneSession.current.id);
    persistCurrent(sceneSession.characterId, sceneSession.current);
  }
  applySceneStage(sceneSession.current);
}

function persistCurrent(characterId: number, card: SceneCard | null | undefined) {
  rememberPickedScene(characterId, card);
  if (!characterId || !card?.id) return;
  void api.putCurrentScene(characterId, card).catch(() => { /* 下次进页会再对齐 */ });
}

function currentCharacterId() {
  try {
    return useCharacterStore().currentId || 0;
  } catch {
    return 0;
  }
}

let cardsLoaded = false;

export async function loadSceneCards() {
  if (cardsLoaded) return;
  try {
    const remote = await api.listScenes();
    if (remote.length) {
      const extras = sceneSession.cards.filter((c) => c.id.startsWith('tonight-'));
      sceneSession.cards = [...extras, ...remote];
    }
    cardsLoaded = true;
  } catch {
    cardsLoaded = true;
    if (!sceneSession.cards.length) sceneSession.cards = [...LOCAL_SCENES];
  }
}

export async function ensureScene(opts?: {
  fresh?: boolean;
  characterId?: number;
}): Promise<LocalSceneCard | null> {
  const settings = useSettingsStore();
  if (!settings.modules.scenes) return null;
  await loadSceneCards();
  const pool = sceneSession.cards.length ? sceneSession.cards : LOCAL_SCENES;
  const id = opts?.characterId || currentCharacterId();
  if (opts?.fresh) {
    const next = pickFresh(pool);
    pickScene(next);
    return next;
  }
  if (sceneSession.current && sceneSession.characterId === id) return sceneSession.current;
  const mem = readMem(id);
  const remembered = mem?.id ? findCard(mem.id) : null;
  if (remembered) {
    sceneSession.current = remembered;
    sceneSession.characterId = id;
    applySceneStage(remembered);
    return remembered;
  }
  const first = pickFresh(pool);
  pickScene(first);
  return first;
}

/**
 * 记住当天的戏。跨过次日 6 点、并且超过 3 小时没聊，才主动换一场。
 */
export async function restoreOrRotateScene(opts: {
  characterId: number;
  lastChatAt: number;
  forceFresh?: boolean;
}): Promise<{ card: LocalSceneCard | null; rotated: boolean }> {
  const settings = useSettingsStore();
  if (!settings.modules.scenes) return { card: null, rotated: false };
  await loadSceneCards();
  const pool = sceneSession.cards.length ? sceneSession.cards : LOCAL_SCENES;
  const id = opts.characterId || currentCharacterId();
  const mem = readMem(id);

  try {
    const remote = await api.getCurrentScene(id, {
      lastUserAt: opts.lastChatAt,
      seedId: mem?.id,
      seedDay: mem?.assignedDay,
      seedBackground: settings.quality.background_image || '',
      fresh: !!opts.forceFresh,
    });
    const full = localOf(remote.card);
    if (full) {
      sceneSession.current = full;
      sceneSession.characterId = id;
      sceneSession.nextRotateAt = Number(remote.next_rotate_at) || 0;
      if (remote.rotated) pushRecent(full.id);
      rememberPickedScene(id, full);
      applySceneStage(full);
      return { card: full, rotated: !!remote.rotated };
    }
  } catch {
    /* 接口失败时用本地记忆兜底，避免进页没有景 */
  }

  if (opts.forceFresh) {
    const next = pickFresh(pool);
    pickScene(next);
    return { card: next, rotated: true };
  }

  const remembered = mem?.id ? findCard(mem.id) : null;
  const today = sceneDay();
  const quiet = !opts.lastChatAt || Date.now() - opts.lastChatAt >= AUTO_SWITCH_QUIET_MS;

  if (remembered && mem) {
    if (mem.assignedDay === today || !quiet) {
      sceneSession.current = remembered;
      applySceneStage(remembered);
      return { card: remembered, rotated: false };
    }
    const next = pickFresh(pool);
    pickScene(next);
    return { card: next, rotated: true };
  }

  const first = remembered || pickFresh(pool);
  pickScene(first);
  return { card: first, rotated: false };
}

/** 下一次允许主动换景的时刻：次日 6 点，且距上次用户开口满 3 小时 */
export function nextAutoRotateAt(characterId: number, lastChatAt: number): number {
  if (sceneSession.nextRotateAt > Date.now()) return sceneSession.nextRotateAt;
  const quietFrom = (lastChatAt || 0) + AUTO_SWITCH_QUIET_MS;
  const mem = readMem(characterId);
  const today = sceneDay();
  if (mem?.assignedDay === today) {
    return Math.max(nextDayRoll(), quietFrom);
  }
  return Math.max(Date.now(), quietFrom);
}

/** 页面一直开着时：次日 6 点后、3 小时没聊，换一场并返回新卡 */
export async function maybeAutoRotateScene(opts: {
  characterId: number;
  lastChatAt: number;
}): Promise<LocalSceneCard | null> {
  const before = sceneSession.current?.id;
  const { card, rotated } = await restoreOrRotateScene(opts);
  if (rotated && card && card.id !== before) return card;
  return null;
}

function nextDayRoll(from = Date.now()) {
  const d = new Date(from);
  d.setHours(DAY_ROLL_HOUR, 0, 0, 0);
  if (from >= d.getTime()) d.setDate(d.getDate() + 1);
  return d.getTime();
}

export function sceneExtra(card: SceneCard | null | undefined): ChatExtra {
  if (!card) return {};
  return {
    scene_id: card.id || '',
    scene_text: card.setting || '',
    scene_title: card.title || '',
    scene_conflict: card.conflict || '',
    scene_opening: card.opening || '',
    scene_cam: card.cam || 'half',
    scene_intent: card.intent || 'look',
    scene_background: card.background || '',
    scene_avoid: avoidLines(card),
    scene_salt: sceneSalt(),
  };
}

const SCENE_CAMS = new Set<CamShotId>(['close', 'bust', 'half', 'threeQ', 'full', 'long']);
const INTENT_MOOD: Record<string, { key: EmotionKey; intensity: number }> = {
  look: { key: 'neutral', intensity: 0.3 },
  tease: { key: 'happy', intensity: 0.42 },
  think: { key: 'relaxed', intensity: 0.4 },
  shy: { key: 'relaxed', intensity: 0.48 },
  talk: { key: 'neutral', intensity: 0.28 },
  cute: { key: 'happy', intensity: 0.5 },
  comfort: { key: 'sad', intensity: 0.38 },
  relax: { key: 'relaxed', intensity: 0.5 },
  idle: { key: 'relaxed', intensity: 0.35 },
};

function frameIntent(raw: string | undefined) {
  const i = (raw || 'look').trim();
  return i === 'relax' ? 'idle' : (i || 'look');
}

/** 进场：背景 + 台面 + 这场戏的景别/情绪，后面闲时也跟着。 */
export function applySceneStage(card: SceneCard | null | undefined) {
  applySceneBackground(card);
  const full = localOf(card);
  if (!full) {
    stage.director.setSceneFrame(null, null);
    return;
  }
  const cam = (full.cam || 'half') as CamShotId;
  const intent = frameIntent(full.intent);
  stage.director.setSceneFrame(SCENE_CAMS.has(cam) ? cam : 'half', intent);
  const mood = INTENT_MOOD[full.intent || 'look'] || INTENT_MOOD.look;
  if (mood.key !== 'neutral') stage.setEmotion(mood.key, mood.intensity);
  if (SCENE_CAMS.has(cam)) {
    shots.suggest(cam, {
      phase: 'welcome',
      beat: 'open',
      llmShot: cam,
      intents: [intent],
    });
  }
}

export function clearSceneStage() {
  stage.director.setSceneFrame(null, null);
}

export function applySceneBackground(card: SceneCard | null | undefined) {
  const full = localOf(card);
  if (!full) return;
  const q = useSettingsStore().quality;
  // 只认这场戏的图，不回落到设置里另存的那套
  stage.setBackground(q.background_color, full.background || '');
  stage.setStagePlatform({
    show: q.stage_show,
    color: full.stage?.color ?? q.stage_color,
    glow: full.stage?.glow ?? q.stage_glow,
    style: q.stage_style,
    texture: full.stage?.texture || q.stage_texture,
    opacity: q.stage_opacity,
  });
  noteSceneTookBg();
}

export function restoreSettingsStage() {
  useSettingsStore().applyQuality();
}

export function spokenWelcome(card: SceneCard | null | undefined): string {
  const full = localOf(card);
  if (!full) return '[emo:relaxed][intent:look]刚好在。';
  const cam = full.cam || 'half';
  const intent = full.intent || 'look';
  const pool = [...(full.lines || [])];
  if (full.line) pool.push(full.line);
  const uniq = [...new Set(pool.filter(Boolean))];
  const others = uniq.filter((l) => l !== sceneSession.lastLine);
  const line = (others.length ? others : uniq)[
    Math.floor(Math.random() * (others.length || uniq.length || 1))
  ] || '你来了。';
  sceneSession.lastLine = line;
  return `[emo:relaxed][cam:${cam}][intent:${intent}]${line}`;
}

export async function generateTonight(characterId: number): Promise<SceneCard | null> {
  sceneSession.generating = true;
  try {
    const card = await api.generateTonight(characterId);
    if (card && !sceneSession.cards.some((c) => c.id === card.id)) {
      sceneSession.cards = [card, ...sceneSession.cards.filter((c) => !c.id.startsWith('tonight-') || c.id === card.id)];
    }
    pickScene(card);
    return card;
  } catch {
    pickScene(pickFresh(LOCAL_SCENES));
    return sceneSession.current;
  } finally {
    sceneSession.generating = false;
  }
}
