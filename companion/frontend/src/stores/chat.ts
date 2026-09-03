import { defineStore } from 'pinia';
import { api } from '../api/client';
import { caster } from '../features/performance/caster';
import { orchestrator } from '../features/performance/orchestrator';
import { shots } from '../features/performance/shotConductor';
import { speechPlayer } from '../features/voice/tts';
import { stage } from '../engine/stage';
import { useCharacterStore } from './character';
import { useSettingsStore } from './settings';
import { humanSilenceSec } from '../features/voice/duplex';
import {
  fallbackIngress, localIngress, mergeHold, peekIngressCut,
  type IngressBusy,
} from '../features/voice/ingress';
import { ensureScene, sceneExtra, restoreOrRotateScene, maybeAutoRotateScene, nextAutoRotateAt, sceneSession, spokenWelcome } from '../features/scenes/session';
import { refreshMemory } from '../features/memory/session';
import type { ChatExtra } from '../api/client';

/** 口型 / 眨眼等由系统占用的基础形态键，不暴露给 LLM */
const BASE_MORPHS = new Set(['あ', 'い', 'う', 'え', 'お', 'ん', 'ワ', 'まばたき', '瞬き']);

export interface Message {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  /** qa = 用户问完的正式回复；delayed / proactive / goodbye / welcome 为会话节奏句；aside = 附和，不打断 */
  kind?: 'qa' | 'delayed' | 'proactive' | 'goodbye' | 'welcome' | 'aside';
  created_at?: string;
  when?: string;
  /** 模型完整回复（语音插话后 content 可能更短） */
  fullContent?: string;
  /** 重说留下的旧版本 */
  alts?: string[];
  /** 已经开口读过的字数；历史消息不设，视为读完 */
  spokenLen?: number;
  speakingFrom?: number;
  speakingTo?: number;
}

const PERF_TAG = /\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]/g;

function stripPerfTags(s: string) {
  return (s || '')
    .replace(PERF_TAG, '')
    .replace(/[（(【][^）)】]{1,48}[）)】]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function localStamp() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function ingestTarotEvent(ev: any) {
  if (ev?.type !== 'tarot') return false;
  void import('../features/tarot').then((m) => m.syncTarotMeta(ev)).catch((e) => {
    console.warn('[tarot] meta', e);
  });
  return true;
}

function sleep(ms: number) {
  return new Promise<void>((r) => { window.setTimeout(r, ms); });
}

async function waitWhile(pred: () => boolean) {
  for (let i = 0; i < 150; i++) {
    if (!pred()) return;
    await sleep(400);
  }
}

function applyBubbleEvent(msg: Message, ev: any, bag: { speech: boolean }) {
  if (ev.type === 'text') {
    const piece = stripPerfTags(ev.delta || '');
    if (piece) msg.fullContent = (msg.fullContent || '') + piece;
    if (!bag.speech && speechPlayer.engine === 'off') msg.content += piece;
    return;
  }
  if (ev.type === 'speech' && ev.kind !== 'filler') {
    bag.speech = true;
    if (speechPlayer.engine === 'off') {
      const piece = stripPerfTags(ev.text || '');
      if (piece && !msg.content.endsWith(piece)) msg.content += piece;
    }
    return;
  }
  if (ev.type === 'done' && ev.full_text) {
    const full = stripPerfTags(ev.full_text);
    if (full) msg.fullContent = full;
    if (!msg.content && speechPlayer.engine === 'off') msg.content = full;
  }
}

/** 无 LLM key 时的本地兜底回复：保证表演链路可用 */
function fallbackReply(input: string, motionNames: string[]): string {
  if (/跳.*舞|dance|来一段|来一支/.test(input)) {
    const pick = motionNames[Math.floor(Math.random() * motionNames.length)] ?? '';
    return `[emo:happy]好呀，看我的！[dance:${pick}]`;
  }
  if (/你好|hi|hello|在吗|嗨/i.test(input)) {
    return '[emo:happy][act:wave]你好呀～我在呢。想聊天还是想看我跳舞？';
  }
  if (/难过|伤心|不开心|烦/.test(input)) {
    return '[emo:sad]别难过啦…有我陪着你呢。[act:nod]说说看发生什么了？';
  }
  const generic = [
    '[emo:relaxed]嗯嗯，我听着呢～不过要解锁真正的聊天能力，记得去设置里填上大模型的 API Key 哦。',
    '[emo:happy]收到！[act:nod]现在我还是本地应答模式，配置好 API Key 我就能真正陪你聊天啦。',
    '[emo:relaxed]我在哦～想让我跳舞可以直接说"跳个舞"，或者打开右上角的动作面板。',
  ];
  return generic[Math.floor(Math.random() * generic.length)];
}

function sidecarFallback(
  mode: 'continue' | 'proactive' | 'goodbye' | 'welcome',
  messages: Message[],
): string {
  if (mode === 'goodbye') {
    return '[emo:relaxed][intent:wave]那我先去忙啦，想我了再叫我～';
  }
  if (mode === 'proactive') {
    return '[emo:happy][intent:tease]还在吗？我这边还想听你再说两句呢～';
  }
  if (mode === 'welcome') {
    if (sceneSession.current) return spokenWelcome(sceneSession.current);
    const lastUser = [...messages].reverse().find((m) => m.role === 'user' && m.content.trim());
    if (lastUser) {
      return '[emo:relaxed][intent:tease]哟，又进来了。刚才那茬还没聊完呢。';
    }
    return '[emo:relaxed][intent:look]刚好在。别愣着呀。';
  }
  return '[emo:relaxed][intent:tease]还在想刚才那句？还是想听我再贫两句？';
}

function visitContext(): string {
  const h = new Date().getHours();
  const tod = h < 5 ? '凌晨' : h < 11 ? '上午' : h < 14 ? '中午' : h < 18 ? '下午' : '晚上';
  return `对方刚打开页面。现在是${tod}，大约${h}点。`;
}

function liveScenePack(extra: ChatExtra = {}): ChatExtra {
  if (!useSettingsStore().modules.scenes) return extra;
  return { ...sceneExtra(sceneSession.current), ...extra };
}

const WELCOME_GAP_MS = 3 * 60 * 1000;

function lastChatKey(characterId: number) {
  return `companion.lastChatAt.${characterId}`;
}

function lastUserChatKey(characterId: number) {
  return `companion.lastUserChatAt.${characterId}`;
}

function touchLastChat(characterId: number) {
  if (!characterId) return;
  try { localStorage.setItem(lastChatKey(characterId), String(Date.now())); } catch { /* 隐私模式 */ }
}

function touchLastUserChat(characterId: number) {
  if (!characterId) return;
  try { localStorage.setItem(lastUserChatKey(characterId), String(Date.now())); } catch { /* 隐私模式 */ }
}

function storedTime(key: string): number {
  try {
    const n = Number(localStorage.getItem(key) || 0);
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

function storedLastChat(characterId: number): number {
  if (!characterId) return 0;
  return storedTime(lastChatKey(characterId));
}

function storedLastUserChat(characterId: number): number {
  if (!characterId) return 0;
  return storedTime(lastUserChatKey(characterId));
}

function parseMsgTime(raw?: string): number {
  if (!raw) return 0;
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

/** 把兜底回复文本按标签协议本地解析并逐段下发 */
function emitLocal(text: string, onEvent: (ev: any) => void) {
      const re = /\[(emo|act|dance|cam|expr|intent|stand):([^\[\]]{1,80})\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let plain = '';
  while ((m = re.exec(text))) {
    if (m.index > last) {
      const seg = text.slice(last, m.index);
      plain += seg;
      onEvent({ type: 'text', delta: seg });
    }
    onEvent({ type: m[1], value: m[2] });
    last = re.lastIndex;
  }
  if (last < text.length) {
    const seg = text.slice(last);
    plain += seg;
    onEvent({ type: 'text', delta: seg });
  }
  onEvent({ type: 'done', full_text: plain });
}

/** 进行中的 SSE 对话流，切换角色时 abort */
let streamAbort: AbortController | null = null;
let delayedTimer: ReturnType<typeof setTimeout> | null = null;
let tarotNextTimer: ReturnType<typeof setTimeout> | null = null;
let sessionMaxTimer: ReturnType<typeof setTimeout> | null = null;
let lastUserAt = 0;
let sessionAt = 0;
let sessionClosed = false;
let sessionOverdue = false;
let goodbyeDeadline = 0;
let silencePhase: 'delayed' | 'proactive' | 'goodbye' | 'idle' = 'idle';
let sceneRotateTimer: ReturnType<typeof setTimeout> | null = null;
let holdBuf = '';

function clearDelayed() {
  if (delayedTimer != null) {
    clearTimeout(delayedTimer);
    delayedTimer = null;
  }
}

function clearTarotNext() {
  if (tarotNextTimer != null) {
    clearTimeout(tarotNextTimer);
    tarotNextTimer = null;
  }
}

function clearSessionMax() {
  if (sessionMaxTimer != null) {
    clearTimeout(sessionMaxTimer);
    sessionMaxTimer = null;
  }
}

function clearSceneRotate() {
  if (sceneRotateTimer != null) {
    clearTimeout(sceneRotateTimer);
    sceneRotateTimer = null;
  }
}

function resetSession() {
  clearDelayed();
  clearSessionMax();
  lastUserAt = 0;
  sessionAt = 0;
  sessionClosed = false;
  sessionOverdue = false;
  goodbyeDeadline = 0;
  silencePhase = 'idle';
  holdBuf = '';
}

function dancePlaying() {
  return caster.holdingDance && stage.motion.active;
}

const SIDECAR_KIND: Record<'continue' | 'proactive' | 'goodbye' | 'welcome', Message['kind']> = {
  continue: 'delayed',
  proactive: 'proactive',
  goodbye: 'goodbye',
  welcome: 'welcome',
};

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as Message[],
    sending: false,
    lastError: '',
    /** 正在读的那一句（不依赖气泡切片，避免对不上就卡住） */
    captionLine: '',
    captionStartedAt: 0,
  }),
  getters: {
    speakingCaption(s): string {
      return s.captionLine;
    },
  },
  actions: {
    async bargeIn() {
      clearDelayed();
      clearTarotNext();
      sessionClosed = false;
      shots.setIdleMode('chat');
      streamAbort?.abort();
      streamAbort = null;
      this.sending = false;
      this.captionLine = '';
      this.captionStartedAt = 0;
      orchestrator.cancelPendingFiller();
      speechPlayer.onUserBargeIn();
      await this.commitSpoken();
    },
    /** 麦克风刚响：只掐续聊。看牌游戏锁期间不掐她正在讲的牌。 */
    onMicStart() {
      if (dancePlaying()) return;
      if (useSettingsStore().modules.tarot) {
        void import('../features/tarot').then((m) => {
          if (m.tarotGameLock()) return;
          orchestrator.cancelPendingFiller();
          speechPlayer.hushSidecar();
        });
        return;
      }
      orchestrator.cancelPendingFiller();
      speechPlayer.hushSidecar();
    },
    peekIngressCut(text: string) {
      return peekIngressCut(text);
    },
    /** TTS 真正开口才把这句写进气泡；没读到的不进历史。 */
    markSpeaking(text: string) {
      const piece = stripPerfTags(text).trim();
      if (!piece) return;
      this.captionLine = piece;
      this.captionStartedAt = performance.now();
      const last = [...this.messages].reverse().find((m) => m.role === 'assistant');
      if (!last) return;
      if (last.speakingTo != null) {
        last.spokenLen = Math.max(last.spokenLen || 0, last.speakingTo);
      }
      const from = last.content.indexOf(piece, last.spokenLen || 0);
      if (from >= 0) {
        last.speakingFrom = from;
        last.speakingTo = from + piece.length;
        return;
      }
      last.content += piece;
      last.speakingFrom = last.content.length - piece.length;
      last.speakingTo = last.content.length;
    },
    markSpokenAll() {
      this.captionLine = '';
      this.captionStartedAt = 0;
      const last = [...this.messages].reverse().find((m) => m.role === 'assistant');
      if (!last) return;
      last.spokenLen = last.content.length;
      last.speakingFrom = undefined;
      last.speakingTo = undefined;
    },
    /** 插话：气泡只留已开口的，库里的未读尾巴一并裁掉。 */
    async commitSpoken() {
      const last = this.messages[this.messages.length - 1];
      if (!last || last.role !== 'assistant') return;
      const spoken = (last.content || '').trim();
      last.speakingFrom = undefined;
      last.speakingTo = undefined;
      last.spokenLen = spoken.length;
      const id = last.id;
      if (!spoken) {
        this.messages.pop();
        if (id) {
          try { await api.patchChatMessage(id, ''); } catch { /* 流还没落库 */ }
        }
        return;
      }
      if (id) {
        try { await api.patchChatMessage(id, last.content); } catch { /* */ }
      }
    },
    ingressBusy(): IngressBusy | null {
      if (dancePlaying()) return 'dance';
      if (this.sending) return 'generate';
      if (speechPlayer.isSpeaking() || speechPlayer.streamOpen) return 'speech';
      return null;
    },
    takeHold() {
      const t = holdBuf.trim();
      holdBuf = '';
      return t;
    },
    noteAside(text: string) {
      const line = text.trim();
      if (!line) return;
      this.messages.push({
        role: 'user', content: line, kind: 'aside',
        created_at: new Date().toISOString(),
      });
      if (dancePlaying()) {
        try { stage.setEmotion('happy', 0.4); } catch { /* */ }
      }
    },
    async classifyIngress(text: string, busy: IngressBusy) {
      const settings = useSettingsStore();
      const { deskActivity } = await import('../features/desk/activity');
      const onDesk = deskActivity();
      if (settings.modules.tarot && onDesk !== 'dance') {
        const tarot = await import('../features/tarot');
        const phase = tarot.tarotUi.phase || '';
        if (tarot.tarotGameLock()) {
          if (tarot.isTarotVoiceCommand(text, phase)) return 'cut' as const;
          return 'hold' as const;
        }
        if (tarot.tarotLive.value && tarot.isTarotVoiceCommand(text, phase)) {
          return 'cut' as const;
        }
      }
      if (settings.tts.duplex_ingress === false) return 'cut' as const;
      const local = localIngress(text, busy);
      if (local) return local;
      if (!settings.hasLlm) return fallbackIngress(busy);
      try {
        const lastU = [...this.messages].reverse().find((m) => m.role === 'user' && m.kind !== 'aside');
        const lastA = this.lastQaAssistant();
        const hit = await api.classifyIngress({
          text, busy,
          last_user: lastU?.content || '',
          last_assistant: lastA?.content || '',
        });
        if (hit.act === 'drop' || hit.act === 'hold' || hit.act === 'cut') return hit.act;
      } catch { /* 分类失败就按忙时默认 */ }
      return fallbackIngress(busy);
    },
    /** 中断进行中的对话流（切换角色时调用），并停掉语音队列 */
    async cancelStream() {
      resetSession();
      streamAbort?.abort();
      streamAbort = null;
      this.sending = false;
      speechPlayer.stop();
      await this.commitSpoken();
    },
    /** 欢迎语开场：还没用户 QA，沉默后走 Proactive → Goodbye，不走 Delayed */
    openSession() {
      sessionClosed = false;
      sessionOverdue = false;
      const now = Date.now();
      sessionAt = now;
      lastUserAt = now;
      silencePhase = 'proactive';
      this.rollGoodbyeDeadline();
      this.armSessionMax();
    },
    rollGoodbyeDeadline() {
      const typical = Number(useSettingsStore().tts.duplex_goodbye_sec);
      const sec = humanSilenceSec('goodbye', typical);
      goodbyeDeadline = sec > 0 && lastUserAt ? lastUserAt + sec * 1000 : 0;
    },
    /** 刷新 / 进页 / 换角色：场景按天记住；超过 3 分钟没聊才开口。 */
    async beginVisit() {
      const settings = useSettingsStore();
      if (!settings.voices.length) {
        try {
          settings.voices = await api.getVoices();
        } catch { /* 音色表失败也继续，用设置里的 voice */ }
      }
      this.applyVoice();
      const chars = useCharacterStore();
      if (settings.modules.scenes && chars.currentId) {
        const need = sceneSession.characterId !== chars.currentId || !sceneSession.current;
        const { rotated } = need
          ? await restoreOrRotateScene({
              characterId: chars.currentId,
              lastChatAt: this.lastUserChatAt(),
            })
          : { rotated: false };
        this.armSceneRotate();
        if (rotated) {
          this.openSession();
          await this.replayOpening(sceneExtra(sceneSession.current));
          return;
        }
      }
      if (!this.shouldWelcome()) {
        sessionClosed = false;
        sessionOverdue = false;
        lastUserAt = Date.now();
        sessionAt = lastUserAt;
        silencePhase = 'idle';
        shots.setIdleMode('chat');
        return;
      }
      this.openSession();
      if (settings.modules.scenes && sceneSession.current) {
        await this.replayOpening({ ...sceneExtra(sceneSession.current), scene_resume: '1' });
      } else {
        await this.sidecarChat('welcome', visitContext());
      }
    },
    /** 用户上次开口：隔夜换景用，不含角色自己的节奏句 */
    lastUserChatAt() {
      const chars = useCharacterStore();
      let latest = storedLastUserChat(chars.currentId);
      for (const m of this.messages) {
        if (m.role !== 'user') continue;
        const t = parseMsgTime(m.created_at);
        if (t > latest) latest = t;
      }
      return latest;
    },
    armSceneRotate() {
      clearSceneRotate();
      const settings = useSettingsStore();
      const chars = useCharacterStore();
      if (!settings.modules.scenes || !chars.currentId) return;
      const at = nextAutoRotateAt(chars.currentId, this.lastUserChatAt());
      const delay = Math.min(Math.max(1500, at - Date.now()), 86400000);
      sceneRotateTimer = setTimeout(() => { void this.onSceneRotateDue(); }, delay);
    },
    async onSceneRotateDue() {
      const chars = useCharacterStore();
      if (useSettingsStore().modules.tarot) {
        const { tarotLive } = await import('../features/tarot/gate');
        if (tarotLive.value) {
          this.armSceneRotate();
          return;
        }
      }
      if (!chars.currentId || this.sending || speechPlayer.streamOpen) {
        this.armSceneRotate();
        return;
      }
      const rotated = await maybeAutoRotateScene({
        characterId: chars.currentId,
        lastChatAt: this.lastUserChatAt(),
      });
      if (rotated) {
        await this.replayOpening(sceneExtra(rotated));
      }
      this.armSceneRotate();
    },
    /** 上次开口距今不到 3 分钟：刷新不再打招呼 */
    shouldWelcome() {
      const chars = useCharacterStore();
      const stored = storedLastChat(chars.currentId);
      let latest = stored;
      for (const m of this.messages) {
        const t = parseMsgTime(m.created_at);
        if (t > latest) latest = t;
      }
      if (!latest) return true;
      return Date.now() - latest > WELCOME_GAP_MS;
    },
    armSessionMax() {
      clearSessionMax();
      const min = Number(useSettingsStore().tts.duplex_session_max_min);
      if (!Number.isFinite(min) || min <= 0 || !sessionAt) return;
      const jitter = 0.85 + Math.random() * 0.3;
      const left = sessionAt + min * jitter * 60 * 1000 - Date.now();
      sessionMaxTimer = setTimeout(() => {
        sessionOverdue = true;
        if (!this.sending && !speechPlayer.streamOpen) void this.sidecarChat('goodbye', 'SessionTimeover');
      }, Math.max(0, left));
    },
    /** 双方都沉默、当前音频播完后：Delayed → Proactive → Goodbye */
    async scheduleDelayed() {
      clearDelayed();
      if (sessionClosed || this.sending || speechPlayer.streamOpen) return;
      if (useSettingsStore().modules.tarot) {
        const chars = useCharacterStore();
        const tarot = await import('../features/tarot');
        if (chars.currentId) await tarot.syncTarotSession(chars.currentId);
        if (tarot.tarotLive.value && tarot.tarotUi.canContinue) {
          this.armTarotNext();
          return;
        }
        if (tarot.tarotLive.value) {
          silencePhase = 'idle';
          return;
        }
      }
      if (holdBuf.trim()) {
        if (dancePlaying() || this.sending || speechPlayer.isSpeaking() || speechPlayer.streamOpen) {
          delayedTimer = setTimeout(() => { void this.scheduleDelayed(); }, 1200);
          return;
        }
        const pending = this.takeHold();
        if (pending) {
          void this.send(pending, { fromHold: true });
          return;
        }
      }
      if (sessionClosed || this.sending || speechPlayer.streamOpen) return;
      if (useSettingsStore().modules.scenes) {
        const chars = useCharacterStore();
        if (chars.currentId && !speechPlayer.isSpeaking()) {
          const rotated = await maybeAutoRotateScene({
            characterId: chars.currentId,
            lastChatAt: this.lastUserChatAt(),
          });
          if (rotated) {
            await this.replayOpening(sceneExtra(rotated));
            return;
          }
        }
      }
      if (sessionClosed || this.sending || speechPlayer.streamOpen) return;
      if (sessionOverdue) {
        void this.sidecarChat('goodbye', 'SessionTimeover');
        return;
      }
      const tts = useSettingsStore().tts;
      if (silencePhase !== 'idle' && goodbyeDeadline > 0 && Date.now() >= goodbyeDeadline) {
        void this.sidecarChat('goodbye', 'SessionTimeout');
        return;
      }
      const waitThen = (sec: number, fn: () => void) => {
        delayedTimer = setTimeout(fn, Math.max(0, sec) * 1000);
      };
      if (silencePhase === 'delayed') {
        const sec = humanSilenceSec('delayed', Number(tts.duplex_delayed_sec));
        if (sec <= 0) {
          silencePhase = 'proactive';
          this.scheduleDelayed();
          return;
        }
        waitThen(sec, () => { void this.sidecarChat('continue'); });
        return;
      }
      if (silencePhase === 'proactive') {
        const sec = humanSilenceSec('proactive', Number(tts.duplex_proactive_sec));
        if (sec <= 0) {
          silencePhase = 'goodbye';
          this.scheduleDelayed();
          return;
        }
        waitThen(sec, () => { void this.sidecarChat('proactive'); });
        return;
      }
      if (silencePhase === 'goodbye') {
        if (!goodbyeDeadline) {
          silencePhase = 'idle';
          return;
        }
        const left = (goodbyeDeadline - Date.now()) / 1000;
        waitThen(left, () => { void this.sidecarChat('goodbye', 'SessionTimeout'); });
      }
    },
    applyVoice() {
      const chars = useCharacterStore();
      const settings = useSettingsStore();
      settings.applyTts();
      const engineVoices = settings.voices.filter(
        (v) => !v.engine || v.engine === settings.tts.engine
      );
      const allowed = new Set(engineVoices.map((v) => v.id));
      const charVoice = (chars.current?.voice || '').trim();
      const settingVoice = (settings.tts.voice || '').trim();
      const pick = (id: string) => !allowed.size || allowed.has(id);
      if (charVoice && pick(charVoice)) {
        speechPlayer.voice = charVoice;
      } else if (settingVoice && pick(settingVoice)) {
        speechPlayer.voice = settingVoice;
      } else if (charVoice || settingVoice) {
        speechPlayer.voice = charVoice || settingVoice;
      } else {
        speechPlayer.voice = '';
        this.lastError = '当前 TTS 引擎没有可用音色，请在设置或角色卡里选择该引擎支持的声音';
      }
    },
    async loadHistory() {
      const chars = useCharacterStore();
      if (!chars.currentId) return;
      const rows = await api.getChatHistory(chars.currentId);
      this.messages = rows.map((r) => ({
        id: r.id,
        role: r.role as Message['role'],
        // rp = 后端标记的扮演片段（仅用于记忆隔离），展示上等同普通 QA
        kind: r.kind === 'rp' ? 'qa' : (r.kind as Message['kind']) || 'qa',
        content: r.content.replace(/\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]/g, '').trim(),
        fullContent: (r.full_content || r.content || '')
          .replace(/\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]/g, '').trim(),
        created_at: r.created_at || '',
        when: r.when || '',
      }));
    },
    async clear() {
      const chars = useCharacterStore();
      if (chars.currentId) {
        await api.clearChatHistory(chars.currentId);
        try {
          localStorage.removeItem(lastChatKey(chars.currentId));
          localStorage.removeItem(lastUserChatKey(chars.currentId));
        } catch { /* */ }
      }
      this.messages = [];
      resetSession();
    },
    async send(text: string, opts: { fromHold?: boolean; scripted?: boolean; tarotRole?: string; fromVoice?: boolean } = {}) {
      let input = text.trim();
      if (!input) return 'empty';
      let tarotLock = false;
      let tarotPass = false;
      let tarotMod: typeof import('../features/tarot') | null = null;
      if (useSettingsStore().modules.tarot) {
        tarotMod = await import('../features/tarot');
        const phase = tarotMod.tarotUi.phase || '';
        tarotLock = tarotMod.tarotGameLock();
        tarotPass = tarotMod.isTarotVoiceCommand(input, phase)
          || tarotMod.isTarotExit(input, phase);
        if (phase === 'intent') tarotPass = true;
      }
      if (tarotLock && !tarotPass && !opts.scripted && !opts.fromHold) {
        holdBuf = mergeHold(holdBuf, input);
        return 'hold';
      }
      const busy = opts.fromHold || opts.scripted ? null : this.ingressBusy();
      if (busy) {
        const act = await this.classifyIngress(input, busy);
        if (act === 'drop') {
          this.noteAside(input);
          return 'drop';
        }
        if (act === 'hold') {
          holdBuf = mergeHold(holdBuf, input);
          clearDelayed();
          delayedTimer = setTimeout(() => { void this.scheduleDelayed(); }, 1200);
          return 'hold';
        }
        const held = this.takeHold();
        if (held) input = mergeHold(held, input);
      } else if (holdBuf.trim()) {
        input = mergeHold(this.takeHold(), input);
      }
      const phase = tarotMod?.tarotUi.phase || '';
      const tarotLiveNow = !!(tarotMod && (tarotMod.tarotLive.value
        || (phase !== 'off' && phase !== 'leaving')));
      const hushTarot = !!(tarotMod && (tarotMod.isTarotCut(input, phase) || tarotMod.isTarotExit(input, phase)));
      const queueTarot = tarotLiveNow && !hushTarot;
      speechPlayer.tarotHold = tarotLiveNow && !(tarotMod?.isTarotExit(input, phase));
      if (queueTarot) {
        const waitSpeech = opts.tarotRole === 'reveal' || opts.tarotRole === 'ask'
          || phase === 'placed' || phase === 'open' || phase === 'synth' || phase === 'linger';
        await waitWhile(() => this.sending || (waitSpeech && speechPlayer.isSpeaking()));
      } else {
        await this.bargeIn();
        speechPlayer.tarotHold = tarotLiveNow && !(tarotMod?.isTarotExit(input, phase));
      }
      const chars = useCharacterStore();
      this.lastError = '';
      this.sending = true;
      sessionClosed = false;
      sessionOverdue = false;
      lastUserAt = Date.now();
      if (!sessionAt) {
        sessionAt = lastUserAt;
        this.armSessionMax();
      }
      silencePhase = 'delayed';
      this.rollGoodbyeDeadline();
      this.messages.push({
        role: 'user', content: input,
        created_at: new Date().toISOString(),
        when: localStamp(),
      });
      const assistant: Message = {
        role: 'assistant', content: '', fullContent: '', kind: 'qa', spokenLen: 0,
        created_at: new Date().toISOString(), when: localStamp(),
      };
      this.messages.push(assistant);
      this.applyVoice();
      touchLastChat(chars.currentId);
      touchLastUserChat(chars.currentId);
      this.armSceneRotate();
      orchestrator.beginTurn(input);

      if (useSettingsStore().modules.tarot && chars.currentId) {
        try {
          const tarot = await import('../features/tarot');
          const live = tarot.tarotLive.value
            || (tarot.tarotUi.phase !== 'off' && tarot.tarotUi.phase !== 'leaving');
          if (live || tarot.canWakeTarot(input)) {
            await tarot.prepareTarotTurn(chars.currentId, input, { fromVoice: !!opts.fromVoice });
          }
        } catch (e) {
          console.warn('[tarot]', e);
        }
      }

      let apiKeyMissing = false;
      const bag = { speech: false };
      const onEvent = (ev: any) => {
        if (ingestTarotEvent(ev)) return;
        if (ev.type === 'error') {
          if (ev.code === 'no_api_key') apiKeyMissing = true;
          else this.lastError = ev.message;
          return;
        }
        if (ev.type === 'meta') {
          if (ev.user_id) {
            const u = [...this.messages].reverse().find((m) => m.role === 'user' && !m.id);
            if (u) u.id = ev.user_id;
          }
          if (ev.message_id) assistant.id = ev.message_id;
          return;
        }
        applyBubbleEvent(assistant, ev, bag);
        orchestrator.handle(ev);
      };

      const morphs = (chars.modelInfo?.morphNames ?? [])
        .filter((n) => !BASE_MORPHS.has(n))
        .slice(0, 50);

      const controller = new AbortController();
      streamAbort = controller;
      void (async () => {
        try {
          await api.streamChat(chars.currentId, input, onEvent, controller.signal, morphs, 'user', liveScenePack());
        } catch (e) {
          if (!controller.signal.aborted) this.lastError = String(e);
        }
        if (apiKeyMissing && !assistant.content && !controller.signal.aborted) {
          const { useAssetsStore } = await import('./assets');
          const names = useAssetsStore().motions.map((m) => m.name);
          orchestrator.allowLocalSpeech();
          emitLocal(fallbackReply(input, names), onEvent);
        }
        if (!assistant.content && this.lastError && streamAbort === controller) {
          assistant.content = `（出错了：${this.lastError}）`;
        }
        if (streamAbort === controller) {
          streamAbort = null;
          this.sending = false;
        }
        if (useSettingsStore().modules.tarot && chars.currentId) {
          const tarot = await import('../features/tarot');
          const next = await tarot.afterTarotSpeak(chars.currentId, 'user', opts.tarotRole);
          if (next === 'synth') this.armTarotNext();
        }
        if (useSettingsStore().modules.memory && chars.currentId) {
          const id = chars.currentId;
          window.setTimeout(() => { void refreshMemory(id); }, 2800);
          window.setTimeout(() => { void refreshMemory(id); }, 8000);
        }
      })();
      return 'sent';
    },
    async sidecarChat(mode: 'continue' | 'proactive' | 'goodbye' | 'welcome', reason = '', extra: ChatExtra = {}) {
      const sceneWelcome = mode === 'welcome'
        && !!(extra.scene_id || extra.scene_text || extra.scene_title);
      if (sceneWelcome) {
        await this.bargeIn();
        sessionClosed = false;
        this.sending = false;
        speechPlayer.streamOpen = false;
      }
      let tarotBusy = false;
      if (useSettingsStore().modules.tarot) {
        const tarot = await import('../features/tarot');
        tarotBusy = tarot.tarotGameLock() || !!tarot.tarotUi.canContinue;
      }
      if (this.sending || speechPlayer.streamOpen) {
        if (tarotBusy && mode === 'continue') this.armTarotNext();
        return;
      }
      if (mode !== 'goodbye' && sessionClosed) return;
      // 看牌游戏：不等舞停，语音没完就稍后再续张。其它续聊仍避开舞和正在说的句。
      if (!sceneWelcome && (dancePlaying() || speechPlayer.isSpeaking())) {
        if (tarotBusy && mode === 'continue') {
          this.armTarotNext();
          return;
        }
        delayedTimer = setTimeout(() => { void this.sidecarChat(mode, reason, extra); }, 2000);
        return;
      }
      if (mode === 'continue' || mode === 'welcome') {
        if (useSettingsStore().modules.tarot) {
          const { tarotLive } = await import('../features/tarot/gate');
          silencePhase = tarotLive.value ? 'delayed' : 'proactive';
        } else {
          silencePhase = 'proactive';
        }
      }
      else if (mode === 'proactive') silencePhase = 'goodbye';
      else if (mode === 'goodbye') {
        sessionClosed = true;
        silencePhase = 'idle';
        clearSessionMax();
      }
      const chars = useCharacterStore();
      if (!chars.currentId) return;
      if (tarotBusy && mode === 'continue') speechPlayer.tarotHold = true;
      this.applyVoice();
      this.sending = true;
      const assistant: Message = {
        role: 'assistant', content: '', fullContent: '', kind: SIDECAR_KIND[mode],
        spokenLen: 0,
        created_at: new Date().toISOString(),
        when: localStamp(),
      };
      this.messages.push(assistant);
      touchLastChat(chars.currentId);
      orchestrator.beginContinue(mode === 'continue' ? 'delayed' : mode);

      let apiKeyMissing = false;
      const bag = { speech: false };
      const onEvent = (ev: any) => {
        if (ingestTarotEvent(ev)) return;
        if (ev.type === 'error') {
          if (ev.code === 'no_api_key') apiKeyMissing = true;
          else this.lastError = ev.message || this.lastError;
          return;
        }
        if (ev.type === 'meta') {
          if (ev.message_id) assistant.id = ev.message_id;
          return;
        }
        applyBubbleEvent(assistant, ev, bag);
        orchestrator.handle(ev);
      };
      const morphs = (chars.modelInfo?.morphNames ?? [])
        .filter((n) => !BASE_MORPHS.has(n))
        .slice(0, 50);
      const controller = new AbortController();
      streamAbort = controller;
      const payload = mode === 'goodbye'
        ? (reason || 'SessionTimeout')
        : mode === 'welcome'
          ? (reason || visitContext())
          : '';
      try {
        await api.streamChat(chars.currentId, payload, onEvent, controller.signal, morphs, mode, liveScenePack(extra));
      } catch (e) {
        if (!controller.signal.aborted) this.lastError = String(e);
      }
      if (apiKeyMissing && !assistant.content && !controller.signal.aborted) {
        orchestrator.allowLocalSpeech();
        emitLocal(sidecarFallback(mode, this.messages), onEvent);
      }
      if (!assistant.content && streamAbort === controller) {
        if ((mode === 'goodbye' || mode === 'welcome') && !controller.signal.aborted) {
          orchestrator.allowLocalSpeech();
          emitLocal(sidecarFallback(mode, this.messages), onEvent);
        } else {
          this.messages.pop();
        }
      }
      if (streamAbort === controller) {
        streamAbort = null;
        this.sending = false;
        speechPlayer.streamOpen = false;
      }
      if (useSettingsStore().modules.tarot && chars.currentId) {
        const tarot = await import('../features/tarot');
        const next = await tarot.afterTarotSpeak(chars.currentId, mode);
        if (mode === 'continue' && next === 'synth') this.armTarotNext();
      }
      if (mode === 'welcome' && !sessionClosed) this.scheduleDelayed();
    },
    cancelTarotNext() {
      clearTarotNext();
    },
    armTarotNext() {
      if (!useSettingsStore().modules.tarot) return;
      clearTarotNext();
      tarotNextTimer = setTimeout(() => { void this.tickTarotNext(); }, 480);
    },
    async tickTarotNext() {
      tarotNextTimer = null;
      if (!useSettingsStore().modules.tarot || sessionClosed) return;
      const chars = useCharacterStore();
      const tarot = await import('../features/tarot');
      if (chars.currentId) await tarot.syncTarotSession(chars.currentId);
      if (!tarot.tarotLive.value || !tarot.tarotUi.canContinue) return;
      if (tarot.tarotUi.phase === 'dealing' || tarot.tarotUi.phase === 'leaving') {
        tarotNextTimer = setTimeout(() => { void this.tickTarotNext(); }, 400);
        return;
      }
      if (this.sending || speechPlayer.streamOpen || speechPlayer.isSpeaking()) {
        tarotNextTimer = setTimeout(() => { void this.tickTarotNext(); }, 400);
        return;
      }
      console.info('[tarot] synth-continue');
      await this.sidecarChat('continue');
    },
    /** 换情境后重新开口：末尾的欢迎/节奏句换成这场戏的第一句。 */
    async replayOpening(extra?: ChatExtra) {
      const settings = useSettingsStore();
      let pack = extra || {};
      if (settings.modules.scenes && !pack.scene_id && !pack.scene_text && !pack.scene_title) {
        const card = sceneSession.current || await ensureScene();
        pack = sceneExtra(card);
      }
      this.armSceneRotate();
      await this.bargeIn();
      sessionClosed = false;
      this.sending = false;
      speechPlayer.streamOpen = false;
      while (this.messages.length) {
        const last = this.messages[this.messages.length - 1];
        if (last.role === 'assistant' && last.kind && last.kind !== 'qa') this.messages.pop();
        else break;
      }
      this.openSession();
      const hasKey = settings.hasLlm;
      if (!hasKey) {
        await this.playLocalSidecar('welcome', spokenWelcome(sceneSession.current));
        return;
      }
      await this.sidecarChat('welcome', '', { ...pack, scene_salt: pack.scene_salt });
    },
    /** 预设卡开口：不走模型，避免被历史寒暄盖掉。 */
    async playLocalSidecar(mode: 'welcome', text: string) {
      const chars = useCharacterStore();
      if (!chars.currentId) return;
      this.applyVoice();
      this.sending = true;
      const assistant: Message = {
        role: 'assistant', content: '', fullContent: '', kind: SIDECAR_KIND[mode],
        spokenLen: 0,
        created_at: new Date().toISOString(),
        when: localStamp(),
      };
      this.messages.push(assistant);
      touchLastChat(chars.currentId);
      orchestrator.beginContinue(mode);
      orchestrator.allowLocalSpeech();
      const bag = { speech: false };
      const onEvent = (ev: any) => {
        if (ingestTarotEvent(ev)) return;
        applyBubbleEvent(assistant, ev, bag);
        orchestrator.handle(ev);
      };
      emitLocal(text, onEvent);
      this.sending = false;
      speechPlayer.streamOpen = false;
      if (!sessionClosed) this.scheduleDelayed();
    },
    lastQaUser(): Message | undefined {
      return [...this.messages].reverse().find((m) => m.role === 'user' && m.kind !== 'aside');
    },
    lastQaAssistant(): Message | undefined {
      return [...this.messages].reverse().find(
        (m) => m.role === 'assistant'
          && m.kind !== 'delayed' && m.kind !== 'proactive'
          && m.kind !== 'goodbye' && m.kind !== 'welcome' && m.kind !== 'aside');
    },
    async rerollLast() {
      if (this.sending) return;
      const lastA = this.lastQaAssistant();
      const lastU = this.lastQaUser();
      if (!lastA || !lastU?.content) return;
      await this.bargeIn();
      const chars = useCharacterStore();
      const oldId = lastA.id;
      const prev = lastA.content.trim();
      const prevAlts = lastA.alts ? [...lastA.alts] : [];
      if (prev) lastA.alts = [...prevAlts, prev];
      lastA.content = '';
      lastA.spokenLen = 0;
      lastA.speakingFrom = undefined;
      lastA.speakingTo = undefined;
      lastA.id = undefined;
      this.sending = true;
      this.lastError = '';
      lastUserAt = Date.now();
      silencePhase = 'delayed';
      this.rollGoodbyeDeadline();
      this.applyVoice();
      orchestrator.beginTurn(lastU.content);
      let apiKeyMissing = false;
      const bag = { speech: false };
      const onEvent = (ev: any) => {
        if (ingestTarotEvent(ev)) return;
        if (ev.type === 'error') {
          if (ev.code === 'no_api_key') apiKeyMissing = true;
          else this.lastError = ev.message;
          return;
        }
        if (ev.type === 'meta') {
          if (ev.message_id) lastA.id = ev.message_id;
          return;
        }
        applyBubbleEvent(lastA, ev, bag);
        orchestrator.handle(ev);
      };
      const morphs = (chars.modelInfo?.morphNames ?? [])
        .filter((n) => !BASE_MORPHS.has(n))
        .slice(0, 50);
      const controller = new AbortController();
      streamAbort = controller;
      try {
        await api.streamChat(chars.currentId, lastU.content, onEvent, controller.signal, morphs, 'user', {
          reroll: true,
          variation: '换个说法，不要重复上一句的措辞和句式。',
        });
      } catch (e) {
        if (!controller.signal.aborted) this.lastError = String(e);
      }
      if (apiKeyMissing && !lastA.content && !controller.signal.aborted) {
        const { useAssetsStore } = await import('./assets');
        const names = useAssetsStore().motions.map((m) => m.name);
        orchestrator.allowLocalSpeech();
        emitLocal(fallbackReply(lastU.content, names), onEvent);
      }
      if (lastA.content.trim()) {
        if (oldId && chars.currentId) {
          try { await api.dropChatMessage(chars.currentId, oldId); } catch { /* 本地兜底句没有库 id */ }
        }
      } else {
        lastA.content = prev;
        lastA.id = oldId;
        lastA.alts = prevAlts;
      }
      if (streamAbort === controller) {
        streamAbort = null;
        this.sending = false;
      }
    },
    async rewindTo(messageId: number) {
      const chars = useCharacterStore();
      if (!chars.currentId || !messageId) return;
      await this.bargeIn();
      try {
        const r = await api.rewindChat(chars.currentId, messageId, false);
        this.messages = r.messages.map((row) => ({
          id: row.id,
          role: row.role as Message['role'],
          kind: row.kind === 'rp' ? 'qa' : (row.kind as Message['kind']) || 'qa',
          content: row.content.replace(/\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]/g, '').trim(),
        }));
      } catch (e) {
        this.lastError = String(e);
      }
    },
    async recastLast(emo: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' = 'relaxed', intent = 'talk') {
      const lastA = this.lastQaAssistant();
      if (!lastA?.content) return;
      await this.bargeIn();
      orchestrator.recast(lastA.content, emo, intent);
    },
    showAlt(msg: Message, dir: 1 | -1 = -1) {
      if (!msg.alts?.length) return;
      const prev = msg.content;
      const next = dir < 0 ? msg.alts.pop()! : msg.alts.shift()!;
      if (prev) {
        if (dir < 0) msg.alts.unshift(prev);
        else msg.alts.push(prev);
      }
      msg.content = next;
    },
    /** @deprecated 用 sidecarChat('continue') */
    async continueChat() {
      await this.sidecarChat('continue');
    },
  },
});
