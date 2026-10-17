import { stage } from '../../engine/stage';
import type { TouchZone } from '../../engine/types';
import { replyLang } from '../../i18n';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { caster } from '../performance/caster';
import { mocap } from '../mocap';
import { tarotLive } from '../tarot/gate';
import { speechPlayer } from '../voice/tts';
import { decideTouch } from './decide';
import { pickLine, touchBrief } from './lines';
import { commitTouch, liveZone, loadTouch, recentSpeech, saveTouch } from './memory';

const sessions = new Map<number, number>();
let lastTap = 0;

function sessionOf(id: number, now: number) {
  const hit = sessions.get(id);
  if (hit) return hit;
  sessions.set(id, now);
  return now;
}

function blocked() {
  if (stage.danceLive) return true;
  if (caster.holdingDance && stage.motion.active) return true;
  if (mocap.active) return true;
  if (tarotLive.value) return true;
  return false;
}

function seedBond(messageCount: number) {
  return Math.min(0.58, 0.32 + Math.min(0.24, messageCount * 0.008));
}

function knownFrom(messages: { created_at?: string }[], now: number) {
  let oldest = now;
  for (const m of messages) {
    const t = Date.parse(m.created_at || '');
    if (Number.isFinite(t) && t > 0 && t < oldest) oldest = t;
  }
  return oldest;
}

const DBL_MS = 420;
const DBL_PX = 36;
let prevAt = 0;
let prevX = 0;
let prevY = 0;

/**
 * 第一下只记住位置。420 毫秒内、差不多同一处再点一下，才算摸到。
 * 拖拽不会进这里。桌宠和舞台都走这一套。
 */
export function noteBodyClick(clientX: number, clientY: number) {
  const now = Date.now();
  const near = Math.hypot(clientX - prevX, clientY - prevY) <= DBL_PX;
  if (prevAt && now - prevAt <= DBL_MS && near) {
    prevAt = 0;
    onBodyTap(clientX, clientY);
    return;
  }
  prevAt = now;
  prevX = clientX;
  prevY = clientY;
}

/** 点在身上、并且不是拖拽。桌宠和舞台都走这里。 */
export function onBodyTap(clientX: number, clientY: number) {
  const settings = useSettingsStore();
  if (settings.modules.touch === false) return;
  if (blocked()) return;
  const zone = stage.probeTouch(clientX, clientY);
  if (!zone) return;
  const now = Date.now();
  if (now - lastTap < 160) return;
  lastTap = now;
  react(zone, now);
}

function react(zone: TouchZone, now: number) {
  const chars = useCharacterStore();
  const id = chars.currentId;
  if (!id) return;
  const chat = useChatStore();
  const mem = loadTouch(id, now, seedBond(chat.messages.length));
  if (!mem.knownSince || mem.knownSince > now - 1000) {
    const seeded = knownFrom(chat.messages, now);
    if (seeded < mem.knownSince) mem.knownSince = seeded;
  }
  const live = liveZone(mem.zones[zone], zone, now);
  const idleAt = Math.max(mem.lastTouchAt, chat.lastUserChatAt());
  const roll = decideTouch({
    zone,
    hour: new Date(now).getHours(),
    bond: mem.bond,
    knownMs: Math.max(0, now - mem.knownSince),
    idleMs: idleAt ? Math.max(0, now - idleAt) : Math.max(0, now - mem.knownSince),
    sessionMs: Math.max(0, now - sessionOf(id, now)),
    heat: live.heat,
    streak: live.streak,
    boundary: chars.current?.boundary || 'free',
    speechRecent: recentSpeech(mem, now),
    muted: mem.muteUntil > now,
    recentPoses: mem.recentPoses,
  });
  const lang = replyLang();
  const prevSpoken = mem.lastSpoken;
  const voiceBusy = chat.sending || speechPlayer.streamOpen || speechPlayer.isSpeaking();
  const spoken = roll.speak && !voiceBusy ? pickLine(lang, zone, roll.tone, prevSpoken) : '';
  commitTouch(mem, zone, now, {
    heatAdd: roll.heatAdd,
    bondDelta: roll.bondDelta,
    muteMs: spoken ? roll.muteMs : 0,
    pose: roll.pose,
    spoken,
  });
  saveTouch(id, mem);
  if (roll.pose) stage.director.playTouch(roll.pose);
  if (!spoken) return;
  const brief = touchBrief(lang, {
    zone,
    tone: roll.tone,
    bond: mem.bond,
    knownMs: Math.max(0, now - mem.knownSince),
    idleMs: idleAt ? Math.max(0, now - idleAt) : 0,
    sessionMs: Math.max(0, now - sessionOf(id, now)),
    hour: new Date(now).getHours(),
    streak: mem.zones[zone].streak,
    boundary: chars.current?.boundary || 'free',
    lastSpoken: prevSpoken,
  });
  void chat.touchSpeak(brief, spoken);
}

/** 舞台上点模型。桌宠的点击在 petPointer 里送进来，这里不重复接。 */
export function installTouch() {
  let down = false;
  let moved = false;
  let x = 0;
  let y = 0;

  const onDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    if (document.documentElement.classList.contains('is-pet')) return;
    if (e.target !== stage.canvas) return;
    down = true;
    moved = false;
    x = e.clientX;
    y = e.clientY;
  };
  const onMove = (e: PointerEvent) => {
    if (!down) return;
    if (Math.hypot(e.clientX - x, e.clientY - y) > 14) moved = true;
  };
  const onUp = (e: PointerEvent) => {
    if (!down) return;
    down = false;
    if (moved || e.button !== 0) return;
    noteBodyClick(x, y);
  };

  window.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('blur', () => { down = false; });
  return () => {
    window.removeEventListener('pointerdown', onDown);
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
  };
}
