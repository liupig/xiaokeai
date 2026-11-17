/** 直播主持循环。舞台轮询要念的一句，并用现有的语音和表演说出去。 */
import { reactive } from 'vue';
import { api } from '../../api/client';
import { playLiveTurn } from './playback';
import { speechPlayer } from '../voice/tts';
import { tavernUi } from '../tavern/session';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';

export interface LiveLine {
  seq: number;
  platform: string;
  kind: string;
  nickname: string;
  content: string;
  gift?: string;
  count?: number;
}

export const liveDesk = reactive({
  onAir: false,
  sessionId: '',
  missing: [] as string[],
  segment: { id: 'chat', left: 0 },
  budget: { spent_cny: 0, cap_cny: 30, tokens: 0, tripped: false, estimated: true },
  health: { uptime_sec: 0, last_error: '', llm_failures: 0, degraded: false },
  bilibili: { state: 'idle', error: '', anchor: '', room_id: '', reconnects: 0 },
  douyin: { callback: '/api/modules/live/douyin/callback', room_id: '', last_ago: -1 },
  events: [] as LiveLine[],
  regulars: 0,
  wishes: 0,
  aiLabel: true,
  schedule: '',
  community: '',
  queue: 0,
  processing: { accepted: 0, duplicate: 0, expired: 0, overflow: 0, playbackFailures: 0, generating: false },
  error: '',
  action: '',
  reply: null as null | {
    id: string; text: string; at: number;
    sources: Array<{ nickname: string; content: string; kind: string }>;
  },
  replies: [] as Array<{
    id: string; text: string; at: number;
    sources: Array<{ nickname: string; content: string; kind: string }>;
  }>,
  boardOpen: true,
  deskOpen: false,
});

let timer: ReturnType<typeof setInterval> | null = null;
let pulling = false;
let lastSpoken = '';
let holdUntil = 0;
let bound = false;
const playerId = crypto.randomUUID();
let playbackAbort: AbortController | null = null;
let pendingAck: { id: string; outcome: 'completed' | 'displayed' | 'interrupted' | 'failed'; text?: string } | null = null;

type LiveReply = NonNullable<typeof liveDesk.reply>;

function noteLiveReply(reply: LiveReply) {
  const index = liveDesk.replies.findIndex((item) => item.id === reply.id);
  if (index >= 0) liveDesk.replies[index] = reply;
  else liveDesk.replies.push(reply);
  liveDesk.replies = liveDesk.replies.slice(-6);
  liveDesk.reply = reply;
}

function busy() {
  const chat = useChatStore();
  return tavernUi.on || chat.sending || speechPlayer.streamOpen || speechPlayer.isSpeaking()
    || Date.now() < holdUntil;
}

async function speak(turn: { id: string; text: string; cue: string; act?: string; interrupt?: boolean }) {
  liveDesk.action = turn.act || '';
  holdUntil = Date.now() + 1000;
  const controller = new AbortController();
  playbackAbort = controller;
  const outcome = await playLiveTurn(turn, controller.signal);
  if (playbackAbort === controller) playbackAbort = null;
  pendingAck = { id: turn.id, outcome };
  await flushAck();
}

async function speakOriginal(turn: {
  id: string; sources?: Array<{ nickname: string; content: string }>;
}) {
  const sources = turn.sources || [];
  if (!sources.length) {
    pendingAck = { id: turn.id, outcome: 'failed' };
    return;
  }
  const chat = useChatStore();
  const primary = sources.length === 1 ? sources[0] : null;
  const input = primary ? primary.content : sources.map((s) => `${s.nickname}：${s.content}`).join('\n');
  const ticket = speechPlayer.playbackTicket();
  const timer = window.setInterval(() => {
    const latest = [...chat.liveMessages].reverse().find((m) => m.role === 'assistant');
    if (latest?.content) noteLiveReply({ id: turn.id, text: latest.content, at: Date.now(), sources });
  }, 120);
  try {
    const result = await chat.send(input, {
      channel: 'live', viewerId: primary ? '' : 'group',
      viewerName: primary?.nickname || '', liveSessionId: liveDesk.sessionId,
    });
    if (result !== 'sent') {
      pendingAck = { id: turn.id, outcome: 'failed' };
      return;
    }
    const outcome = await speechPlayer.playbackResult(ticket);
    const latest = [...chat.liveMessages].reverse().find((m) => m.role === 'assistant');
    const text = latest?.fullContent || latest?.content || '';
    noteLiveReply({ id: turn.id, text: latest?.content || text, at: Date.now(), sources });
    pendingAck = { id: turn.id, outcome, text };
  } catch (err) {
    liveDesk.error = String(err);
    pendingAck = { id: turn.id, outcome: 'failed' };
  } finally {
    window.clearInterval(timer);
    await flushAck();
  }
}

async function flushAck() {
  const ack = pendingAck;
  if (!ack) return;
  await api.liveAck(ack.id, ack.outcome, playerId, ack.text || '');
  if (pendingAck === ack) pendingAck = null;
}

export async function pullLiveDesk() {
  if (pulling) return;
  pulling = true;
  try {
    await flushAck();
    const characters = useCharacterStore();
    const data = await api.liveDesk(busy() ? 1 : 0, characters.currentId || 0);
    liveDesk.onAir = !!data.on_air;
    const nextSessionId = data.session_id || '';
    if (nextSessionId !== liveDesk.sessionId) liveDesk.replies = [];
    liveDesk.sessionId = nextSessionId;
    if (!liveDesk.onAir) playbackAbort?.abort();
    liveDesk.missing = data.missing || [];
    liveDesk.segment = { id: data.segment?.id || 'chat', left: Number(data.segment?.left || 0) };
    liveDesk.budget = {
      spent_cny: Number(data.budget?.spent_cny || 0),
      cap_cny: Number(data.budget?.cap_cny || 0),
      tokens: Number(data.budget?.tokens || 0),
      tripped: !!data.budget?.tripped,
      estimated: true,
    };
    liveDesk.health = {
      uptime_sec: Number(data.health?.uptime_sec || 0),
      last_error: data.health?.last_error || '',
      llm_failures: Number(data.health?.llm_failures || 0),
      degraded: !!data.health?.degraded,
    };
    liveDesk.bilibili = {
      state: data.bilibili?.state || 'idle',
      error: data.bilibili?.error || '',
      anchor: data.bilibili?.anchor || '',
      room_id: data.bilibili?.room_id || '',
      reconnects: Number(data.bilibili?.reconnects || 0),
    };
    liveDesk.douyin = {
      callback: data.douyin?.callback || '/api/modules/live/douyin/callback',
      room_id: data.douyin?.room_id || '',
      last_ago: Number(data.douyin?.last_ago ?? -1),
    };
    liveDesk.events = data.events || [];
    liveDesk.regulars = Number(data.regulars || 0);
    liveDesk.wishes = Number(data.wishes || 0);
    liveDesk.aiLabel = data.ai_label !== false;
    liveDesk.schedule = data.schedule || '';
    liveDesk.community = data.community || '';
    liveDesk.queue = Number(data.queue || 0);
    liveDesk.processing = {
      accepted: Number(data.processing?.intake?.accepted || 0),
      duplicate: Number(data.processing?.intake?.duplicate || 0),
      expired: Number(data.processing?.expired || 0),
      overflow: Number(data.processing?.overflow || 0),
      playbackFailures: Number(data.processing?.playback_failures || 0),
      generating: !!data.processing?.generating,
    };
    liveDesk.error = '';
    const turn = data.turn;
    if (turn?.id && turn.text && turn.delivery !== 'original_chat' && turn.id !== liveDesk.reply?.id) {
      noteLiveReply({
        id: turn.id, text: turn.text, at: Date.now(), sources: turn.sources || [],
      });
    }
    const originalChat = turn?.delivery === 'original_chat';
    if (turn?.id && (turn.text || originalChat) && turn.id !== lastSpoken && (turn.interrupt || !busy())) {
      if (!(await api.liveClaim(turn.id, playerId)).ok) return;
      lastSpoken = turn.id;
      if (originalChat) void speakOriginal(turn).catch((err) => { liveDesk.error = String(err); });
      else void speak(turn).catch((err) => { liveDesk.error = String(err); });
    }
  } catch (err) {
    liveDesk.error = err instanceof Error ? err.message : String(err);
  } finally {
    pulling = false;
  }
}

export function startLiveLoop() {
  if (timer) return;
  void pullLiveDesk();
  timer = setInterval(() => { void pullLiveDesk(); }, 500);
}

export function stopLiveLoop() {
  playbackAbort?.abort();
  if (timer) clearInterval(timer);
  timer = null;
  liveDesk.onAir = false;
}

export function bindLiveHost() {
  if (bound) return;
  bound = true;
  const settings = useSettingsStore();
  settings.$subscribe((_mut, state) => {
    if (state.modules.live) startLiveLoop();
    else stopLiveLoop();
  });
  if (settings.modules.live) startLiveLoop();
}
