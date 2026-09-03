import { reactive } from 'vue';
import { api, type TarotCard, type TarotPlay, type TarotSession, type TarotWait } from '../../api/client';
import { stage } from '../../engine/stage';
import { shots } from '../performance/shotConductor';
import { speechPlayer } from '../voice/tts';
import { dancingNow } from '../desk/activity';
import { openTarotLayer, tarotLive } from './gate';
import { canWakeTarot } from './intent';
import type { DrawnView } from './plugin';

export const tarotUi = reactive({
  phase: 'off' as string,
  spread: '' as string,
  title: '' as string,
  layout: 'row' as string,
  question: '' as string,
  cards: [] as TarotCard[],
  fan: [] as TarotCard[],
  picked: [] as number[],
  revealed: [] as number[],
  focus: null as DrawnView | null,
  inspect: null as number | null,
  disclaimer: false,
  caption: '',
  busy: false,
  step: 0,
  need: 0,
  hint: '',
  canContinue: false,
  canCut: false,
  canPick: false,
  canHerDraw: false,
  canClarifier: false,
  clarifierUsed: false,
  done: false,
  allRevealed: false,
  voicePlay: false,
  canPickPlay: false,
  plays: [] as TarotPlay[],
});

let pluginReady: Promise<typeof import('./plugin')> | null = null;
let camHeld = false;
let skipIntent = false;
let disclaimerShown = false;
let acting = false;
let placedOnce = false;
let voicePlay = false;
let flipTimer: ReturnType<typeof setTimeout> | null = null;
let lastProgKey = '';
let armedWaitKey = '';
const queued: Array<() => void> = [];

function withActing(fn: () => Promise<void>) {
  if (acting) {
    queued.push(() => { withActing(fn); });
    return;
  }
  acting = true;
  void (async () => {
    try {
      await fn();
    } finally {
      acting = false;
      const next = queued.shift();
      next?.();
    }
  })();
}

function setVoicePlay(on: boolean) {
  voicePlay = on;
  tarotUi.voicePlay = on;
  if (!on) clearAutoFlip();
}

function clearAutoFlip() {
  if (flipTimer != null) {
    clearTimeout(flipTimer);
    flipTimer = null;
  }
  armedWaitKey = '';
}

function nextUnrevealed(): number | null {
  const rev = new Set(tarotUi.revealed || []);
  for (let i = 0; i < (tarotUi.cards || []).length; i++) {
    if (!rev.has(i)) return i;
  }
  return null;
}

function waitKey(wait: TarotWait | null | undefined) {
  if (!wait?.next) return '';
  return `${wait.next}|${tarotUi.phase}|${(tarotUi.revealed || []).join(',')}|${(tarotUi.picked || []).length}`;
}

function whenSpeechClear(fn: () => void) {
  const tick = () => {
    if (!voicePlay) return;
    if (speechPlayer.isSpeaking()) {
      window.setTimeout(tick, 400);
      return;
    }
    fn();
  };
  tick();
}

function armWait(wait?: TarotWait | null) {
  if (!voicePlay || !wait?.next || !(Number(wait.sec) > 0)) {
    clearAutoFlip();
    return;
  }
  const key = waitKey(wait);
  if (key && key === armedWaitKey) return;
  clearAutoFlip();
  armedWaitKey = key;
  const next = wait.next;
  const rawMs = Math.max(1000, Math.round(Number(wait.sec) * 1000));
  const afterIdle = next === 'reveal' ? Math.min(rawMs, 2200) : rawMs;
  const fire = () => {
    flipTimer = null;
    armedWaitKey = '';
    if (!voicePlay) return;
    if (speechPlayer.isSpeaking()) {
      armedWaitKey = key;
      whenSpeechClear(() => { armWait(wait); });
      return;
    }
    if (next === 'cut') void doCut('auto-wait');
    else if (next === 'her_draw') void doHerDraw();
    else if (next === 'reveal') {
      const i = nextUnrevealed();
      if (i != null) void doReveal(i, 'auto');
    }
  };
  whenSpeechClear(() => {
    if (!voicePlay || armedWaitKey !== key) return;
    flipTimer = window.setTimeout(fire, afterIdle);
  });
}

function progressKey(action: string, snap: TarotSession) {
  return `${action}|${snap?.phase || ''}|${(snap?.revealed || []).join(',')}|${(snap?.picked || []).length}`;
}

function rememberProgress(action: string, snap: TarotSession) {
  lastProgKey = progressKey(action, snap);
}

type SpeakRole = 'ritual' | 'reveal' | 'ask' | 'chat';

function seenDisclaimer() {
  try {
    return localStorage.getItem('companion.tarot.disclaimer') === '1';
  } catch {
    return false;
  }
}

function markDisclaimer() {
  disclaimerShown = true;
  try { localStorage.setItem('companion.tarot.disclaimer', '1'); } catch { /* */ }
}

async function pluginMod() {
  if (!pluginReady) pluginReady = import('./plugin');
  return pluginReady;
}

async function ensurePlugin() {
  const mod = await pluginMod();
  return mod.installTarot(stage);
}

function applySnap(snap: TarotSession) {
  tarotUi.spread = snap.spread || '';
  tarotUi.title = snap.title || '';
  tarotUi.layout = snap.layout || 'row';
  tarotUi.question = snap.question || '';
  tarotUi.cards = snap.cards || [];
  tarotUi.fan = snap.fan || [];
  tarotUi.picked = snap.picked || [];
  tarotUi.revealed = snap.revealed || [];
  tarotUi.step = snap.step ?? 0;
  tarotUi.need = snap.need ?? (snap.cards?.length || 0);
  tarotUi.hint = snap.hint || '';
  tarotUi.canContinue = !!snap.can_continue;
  tarotUi.canCut = !!snap.can_cut;
  tarotUi.canPick = !!snap.can_pick;
  tarotUi.canHerDraw = !!snap.can_her_draw;
  tarotUi.canClarifier = !!snap.can_clarifier;
  tarotUi.clarifierUsed = !!snap.clarifier_used;
  tarotUi.done = !!snap.done;
  tarotUi.allRevealed = !!snap.all_revealed;
  tarotUi.canPickPlay = !!snap.can_pick_play;
  tarotUi.plays = snap.plays || [];
  if (snap.active && snap.phase) tarotUi.phase = snap.phase;
  if (snap.disclaimer && !seenDisclaimer() && !disclaimerShown) {
    tarotUi.disclaimer = true;
    markDisclaimer();
    window.setTimeout(() => { tarotUi.disclaimer = false; }, 5600);
  }
}

/** 仪式未结束时锁住闲聊；未翻完也锁。综合后 linger 放开追问。 */
export function tarotGameLock() {
  if (!tarotLive.value) return false;
  if (tarotUi.phase === 'off' || tarotUi.phase === 'leaving' || tarotUi.phase === 'linger') return false;
  if (tarotUi.busy) return true;
  if (tarotUi.canContinue) return true;
  return tarotUi.phase === 'intent' || tarotUi.phase === 'shuffle' || tarotUi.phase === 'cut' || tarotUi.phase === 'pick'
    || tarotUi.phase === 'placed' || tarotUi.phase === 'open' || tarotUi.phase === 'dealing'
    || tarotUi.phase === 'synth';
}

export async function syncTarotSession(characterId: number) {
  try {
    const snap = await api.tarotSession(characterId);
    if (snap.active) applySnap(snap);
    else {
      tarotUi.canContinue = false;
      tarotUi.canCut = false;
      tarotUi.canPick = false;
      tarotUi.canHerDraw = false;
      tarotUi.canClarifier = false;
    }
    return snap;
  } catch {
    return null;
  }
}

const TAROT_SHOTS = ['threeQ', 'full'] as const;

function captionOf(view: DrawnView | null) {
  if (!view) return '';
  if (!view.faceUp) return `${view.position} · 背面`;
  return `${view.position} · ${view.name}${view.reversed ? ' · 逆位' : ''}`;
}

async function charId() {
  const { useCharacterStore } = await import('../../stores/character');
  return useCharacterStore().currentId;
}

async function pushFocus(index: number | null) {
  const id = await charId();
  if (id) void api.tarotFocus(id, index);
}

async function speak(line: string, role: SpeakRole = 'ritual') {
  armSkipIntent();
  const { useChatStore } = await import('../../stores/chat');
  await useChatStore().send(line, { scripted: true, tarotRole: role });
}

/** 玩家已经切/抽/落位时，掐掉还在说「伸手切一下」的旧仪式句。 */
async function hushRitualSpeech() {
  try {
    const { useChatStore } = await import('../../stores/chat');
    await useChatStore().bargeIn();
  } catch { /* */ }
}

export function inspectCard(index: number | null) {
  void pluginMod().then((m) => m.getTarotPlugin()?.inspect(index));
}

function lockCam() {
  camHeld = shots.reviewLock;
  stage.camSizeLock = [...TAROT_SHOTS];
  shots.reviewLock = true;
  const open = Math.random() < 0.45 ? 'full' : 'threeQ';
  stage.playShot(open, false, 1.2);
  shots.holdShot(open);
}

function settleCam() {
  if (!camHeld) shots.reviewLock = false;
  const next = shots.current === 'threeQ' ? 'full' : 'threeQ';
  stage.playShot(next, false, 1.15);
  shots.beginIdle();
  shots.holdShot(next);
}

function unlockCam() {
  stage.camSizeLock = null;
  if (!camHeld) shots.reviewLock = false;
  camHeld = false;
  shots.beginIdle();
}

export function armSkipIntent() {
  skipIntent = true;
}

async function bindPlugin() {
  const plugin = await ensurePlugin();
  plugin.setRitualHandler({
    onShuffleReady: () => { void onShuffleReady(); },
    onCut: (entropy) => { void doCut(entropy); },
    onPick: (fanIndex) => { void doPick(fanIndex); },
    onReveal: (index) => { void doReveal(index); },
    onAsk: (index) => { void askAbout(index); },
    onFocus: (view, why) => {
      if (why === 'inspect') {
        tarotUi.inspect = view?.index ?? null;
        tarotUi.focus = view;
        tarotUi.caption = captionOf(view);
        void pushFocus(view?.index ?? null);
        return;
      }
      if (tarotUi.inspect !== null) return;
      tarotUi.focus = view;
      tarotUi.caption = captionOf(view);
    },
  });
  return plugin;
}

async function onShuffleReady() {
  const id = await charId();
  if (!id) return;
  const snap = await api.tarotReadyCut(id);
  applySnap(snap);
  armWait(snap.wait);
}

async function playOffer(snap: TarotSession) {
  openTarotLayer();
  applySnap(snap);
  tarotUi.caption = '';
  tarotUi.busy = false;
  tarotLive.value = true;
  placedOnce = false;
  lockCam();
}

export async function playRitual(snap: TarotSession) {
  openTarotLayer();
  applySnap(snap);
  tarotUi.busy = true;
  tarotUi.caption = '';
  tarotLive.value = true;
  placedOnce = false;
  lockCam();
  try {
    const plugin = await bindPlugin();
    const phase = snap.phase || 'shuffle';
    if (phase === 'pick') {
      if (!plugin.open) await plugin.beginRing();
      plugin.presentFan((snap.fan || []).length, snap.picked || []);
    } else if (phase === 'placed' || phase === 'open' || phase === 'linger' || phase === 'synth') {
      await plugin.dealTable(snap.cards || [], snap.layout || 'row', snap.revealed || []);
      settleCam();
    } else {
      await plugin.beginRing();
    }
    armWait(snap.wait);
  } finally {
    tarotUi.busy = false;
  }
}

export async function doCut(entropy = '') {
  withActing(async () => {
    const id = await charId();
    if (!id || (!tarotUi.canCut && tarotUi.phase !== 'shuffle' && tarotUi.phase !== 'cut')) return;
    if (entropy !== 'auto-wait') await hushRitualSpeech();
    const snap = await api.tarotCut(id, entropy || `${Date.now()}`);
    applySnap(snap);
    rememberProgress('cut', snap);
    const plugin = await ensurePlugin();
    plugin.presentFan((snap.fan || []).length, snap.picked || []);
    armWait(snap.wait);
  });
}

export async function doPick(fanIndex: number) {
  withActing(async () => {
    const id = await charId();
    if (!id || tarotUi.phase !== 'pick') return;
    await hushRitualSpeech();
    const plugin = await ensurePlugin();
    plugin.markPicked(fanIndex);
    const snap = await api.tarotPick(id, fanIndex);
    applySnap(snap);
    rememberProgress(snap.phase === 'placed' ? 'place' : 'pick', snap);
    if (snap.phase === 'placed' || (snap.cards || []).length) {
      await finishPlace(snap);
    } else {
      plugin.presentFan((snap.fan || []).length, snap.picked || []);
      armWait(snap.wait);
    }
  });
}

export async function doHerDraw() {
  withActing(async () => {
    const id = await charId();
    if (!id || tarotUi.phase !== 'pick') return;
    await hushRitualSpeech();
    const snap = await api.tarotHerDraw(id);
    applySnap(snap);
    rememberProgress('place', snap);
    await finishPlace(snap);
  });
}

async function finishPlace(snap: TarotSession) {
  if (placedOnce && tarotUi.cards.length && tarotUi.phase !== 'placed') return;
  placedOnce = true;
  await hushRitualSpeech();
  tarotUi.busy = true;
  try {
    const plugin = await ensurePlugin();
    await plugin.dealTable(snap.cards || [], snap.layout || 'row', snap.revealed || []);
    tarotUi.phase = snap.phase || 'placed';
    settleCam();
    armWait(snap.wait);
  } finally {
    tarotUi.busy = false;
  }
}

export async function doReveal(index: number, src: 'auto' | 'hand' = 'hand') {
  if (src === 'hand') setVoicePlay(false);
  withActing(async () => {
    const id = await charId();
    if (!id) return;
    if ((tarotUi.revealed || []).includes(index)) return;
    const snap = await api.tarotReveal(id, index);
    applySnap(snap);
    rememberProgress('reveal', snap);
    const plugin = await ensurePlugin();
    plugin.revealAt(index);
    plugin.inspect(index);
    const card = (snap.cards || [])[index];
    tarotUi.inspect = index;
    tarotUi.caption = card
      ? `${card.position} · ${card.name}${card.reversed ? ' · 逆位' : ''}`
      : '';
    const pos = card?.position || `第${index + 1}`;
    void speak(`翻开第${index + 1}张，${pos}`, 'reveal');
    armWait(snap.wait);
  });
}

export async function askAbout(index: number) {
  const card = tarotUi.cards[index];
  if (!card || !(tarotUi.revealed || []).includes(index)) return;
  tarotUi.inspect = index;
  tarotUi.focus = {
    index,
    name: card.name,
    position: card.position,
    reversed: !!card.reversed,
    faceUp: true,
  };
  tarotUi.caption = `${card.position} · ${card.name}${card.reversed ? ' · 逆位' : ''}`;
  void pushFocus(index);
  if (tarotUi.phase !== 'linger') return;
  await speak(`这张「${card.position}」什么意思`, 'ask');
}

export async function doClarifier() {
  if (tarotUi.clarifierUsed) return;
  withActing(async () => {
    const id = await charId();
    if (!id) return;
    const host = tarotUi.inspect ?? tarotUi.focus?.index ?? null;
    const snap = await api.tarotClarifier(id, host);
    applySnap(snap);
    const extra = (snap.cards || []).find((c) => c.clarifier);
    const plugin = await ensurePlugin();
    if (extra) await plugin.appendCard(extra, true, host);
    const pos = extra?.position || '补';
    void speak(`再翻一张补在「${pos}」旁边`, 'reveal');
  });
}

export async function playDismiss() {
  setVoicePlay(false);
  tarotUi.busy = true;
  tarotUi.phase = 'leaving';
  tarotUi.caption = '';
  tarotUi.focus = null;
  tarotUi.inspect = null;
  try {
    const mod = pluginReady ? await pluginReady : null;
    const plugin = mod?.getTarotPlugin();
    if (plugin?.open) await plugin.dismiss();
  } finally {
    tarotUi.phase = 'off';
    tarotUi.cards = [];
    tarotUi.fan = [];
    tarotUi.picked = [];
    tarotUi.revealed = [];
    tarotUi.spread = '';
    tarotUi.title = '';
    tarotUi.question = '';
    tarotUi.step = 0;
    tarotUi.need = 0;
    tarotUi.hint = '';
    tarotUi.canContinue = false;
    tarotUi.canCut = false;
    tarotUi.canPick = false;
    tarotUi.canHerDraw = false;
    tarotUi.canClarifier = false;
    tarotUi.canPickPlay = false;
    tarotUi.plays = [];
    tarotUi.busy = false;
    tarotLive.value = false;
    placedOnce = false;
    lastProgKey = '';
    speechPlayer.tarotHold = false;
    unlockCam();
    try {
      const { useChatStore } = await import('../../stores/chat');
      useChatStore().cancelTarotNext();
    } catch { /* */ }
  }
}

export async function beginPlay(
  characterId: number,
  spread: string,
  question = '',
  opts: { keepVoice?: boolean } = {},
) {
  if (!opts.keepVoice) setVoicePlay(false);
  openTarotLayer();
  const res = await api.tarotBegin(characterId, spread, question);
  await playRitual(res.session);
  const title = res.session?.title || '牌';
  const line = question.trim()
    ? `帮我看「${title}」，想问：${question.trim()}`
    : `帮我看「${title}」`;
  void speak(line, 'ritual');
}

export async function pickPlay(spread: string) {
  const id = await charId();
  if (!id) return;
  await beginPlay(id, spread, tarotUi.question || '', { keepVoice: voicePlay });
}

/** 兼容旧入口 */
export async function drawAndSpeak(characterId: number, spread: string, question = '') {
  return beginPlay(characterId, spread, question);
}

export async function dismissAndSpeak(characterId: number) {
  await api.tarotDismiss(characterId);
  await playDismiss();
  armSkipIntent();
  const { useChatStore } = await import('../../stores/chat');
  await useChatStore().send('收起来');
}

export async function redealAndSpeak(characterId: number) {
  const spread = tarotUi.spread || 'daily';
  const question = tarotUi.question || '';
  await beginPlay(characterId, spread, question);
}

async function applyIntentAction(res: { action: string; session: TarotSession }) {
  const act = res.action;
  const snap = res.session;
  try {
    if (act === 'draw') {
      await playRitual(snap);
      return;
    }
    if (act === 'offer' || snap.phase === 'intent') {
      await playOffer(snap);
      return;
    }
    if (act === 'dismiss') {
      await playDismiss();
      return;
    }
    if (act === 'cut') {
      await hushRitualSpeech();
      applySnap(snap);
      const plugin = await ensurePlugin();
      plugin.presentFan((snap.fan || []).length, snap.picked || []);
      return;
    }
    if (act === 'place') {
      applySnap(snap);
      await finishPlace(snap);
      return;
    }
    if (act === 'pick') {
      applySnap(snap);
      const plugin = await ensurePlugin();
      plugin.presentFan((snap.fan || []).length, snap.picked || []);
      return;
    }
    if (act === 'reveal') {
      const idx = typeof snap.focus === 'number'
        ? snap.focus
        : (snap.revealed || []).slice(-1)[0];
      const wasUp = typeof idx === 'number' && (tarotUi.revealed || []).includes(idx);
      applySnap(snap);
      const plugin = await ensurePlugin();
      if (typeof idx === 'number') {
        plugin.revealAt(idx);
        plugin.inspect(idx);
      }
      if (!wasUp) {
        const card = typeof idx === 'number' ? (snap.cards || [])[idx] : undefined;
        const pos = card?.position || `第${(idx ?? 0) + 1}`;
        void speak(`翻开第${(idx ?? 0) + 1}张，${pos}`, 'reveal');
      }
      return;
    }
    if (act === 'clarifier') {
      applySnap(snap);
      const extra = (snap.cards || []).find((c) => c.clarifier);
      const plugin = await ensurePlugin();
      if (extra) await plugin.appendCard(extra, true, tarotUi.inspect);
      return;
    }
  if (act === 'keep' && snap?.active && (tarotUi.phase === 'off' || snap.phase === 'intent')) {
    if (snap.phase === 'intent') await playOffer(snap);
    else await playRitual(snap);
    } else if (snap?.active) {
      applySnap(snap);
      if (snap.phase === 'pick') {
        const plugin = await ensurePlugin();
        plugin.presentFan((snap.fan || []).length, snap.picked || []);
      } else if (
        (snap.phase === 'placed' || snap.phase === 'open' || snap.phase === 'synth' || snap.phase === 'linger')
        && !placedOnce
        && (snap.cards || []).length
      ) {
        await finishPlace(snap);
      } else if (
        (snap.phase === 'placed' || snap.phase === 'open' || snap.phase === 'linger')
        && placedOnce
      ) {
        const plugin = await ensurePlugin();
        for (const i of snap.revealed || []) plugin.revealAt(i);
      }
    }
  } finally {
    if (act === 'dismiss' || !snap?.active) clearAutoFlip();
    else armWait(snap.wait);
  }
}

/** 聊天流里的塔罗 metadata：以后端 FSM 快照为准，口令/计时器只是跟班。 */
export async function syncTarotMeta(ev: {
  action?: string;
  session?: TarotSession;
  wait?: TarotWait | null;
}) {
  const snap = ev.session || ({ active: false } as TarotSession);
  const action = ev.action || snap.last_action || 'keep';
  const wait = ev.wait !== undefined ? ev.wait : snap.wait;
  if (!snap.active) {
    if (action === 'dismiss' && (tarotLive.value || (tarotUi.phase !== 'off' && tarotUi.phase !== 'leaving'))) {
      lastProgKey = 'dismiss';
      await playDismiss();
    }
    return;
  }
  const key = progressKey(action, snap);
  if (key === lastProgKey) {
    armWait(wait);
    return;
  }
  lastProgKey = key;
  openTarotLayer();
  await applyIntentAction({ action, session: snap });
}

export async function prepareTarotTurn(
  characterId: number,
  text: string,
  opts: { fromVoice?: boolean } = {},
) {
  if (skipIntent) {
    skipIntent = false;
    return;
  }
  if (opts.fromVoice) setVoicePlay(true);
  const live = tarotLive.value || (tarotUi.phase !== 'off' && tarotUi.phase !== 'leaving');
  if (!live) {
    if (dancingNow() && !canWakeTarot(text)) return;
    if (!canWakeTarot(text)) return;
  }
  openTarotLayer();
  const res = await api.tarotIntent(characterId, text);
  rememberProgress(res.action, res.session);
  await applyIntentAction(res);
}

/** 讲完一轮之后：只有翻开/追问这一轮才收线；洗切选不要误触发综合。 */
export async function afterTarotSpeak(
  characterId: number,
  mode = 'user',
  role: SpeakRole | string = 'chat',
) {
  const snap = await syncTarotSession(characterId);
  if (!snap?.active) return 'idle';
  if (mode === 'continue' && (snap.phase === 'synth' || snap.can_continue)) {
    applySnap(await api.tarotSynthDone(characterId));
    return 'linger';
  }
  if (role === 'ritual') return 'idle';
  if (role === 'reveal' || role === 'ask') {
    if (snap.can_continue) return 'synth';
    if (snap.phase === 'open' && snap.all_revealed && (snap.need || 1) <= 1) {
      applySnap(await api.tarotLinger(characterId));
      return 'linger';
    }
    if (snap.phase === 'linger') {
      await api.tarotSeal(characterId);
      return 'linger';
    }
    return 'idle';
  }
  if (snap.phase === 'linger') {
    await api.tarotSeal(characterId);
    return 'linger';
  }
  return 'idle';
}

export async function onCharacterSwitch() {
  if (tarotUi.phase === 'off') return;
  await playDismiss();
}

export async function onModuleOff() {
  const { useCharacterStore } = await import('../../stores/character');
  const id = useCharacterStore().currentId;
  if (id) await api.tarotDismiss(id).catch(() => {});
  await playDismiss();
  const mod = pluginReady ? await pluginReady : null;
  if (mod) mod.uninstallTarot(stage);
  pluginReady = null;
}
