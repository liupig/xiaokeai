import type { ActionKey, CamShotId, EmotionKey } from '../../engine/types';
import type { Intent } from '../performance/catalog';
import { caster } from '../performance/caster';
import { dancingNow, tarotNow } from '../desk/activity';
import { speechPlayer } from '../voice/tts';
import { useChatStore } from '../../stores/chat';
import { useCharacterStore } from '../../stores/character';
import { codewatchLive } from './live';
import type { CodewatchStatus } from '../../api/client';

type ShowKind = 'started' | 'done';

type ShowPack = {
  mood: EmotionKey;
  intent: Intent;
  shot: CamShotId;
  builtin?: ActionKey;
  intensity: number;
  holdMs: number;
};

type Job = { kind: ShowKind; snap: CodewatchStatus; until: number };

const PACKS: Record<ShowKind, ShowPack> = {
  started: {
    mood: 'happy', intent: 'look', shot: 'half',
    intensity: 0.72, holdMs: 9000,
  },
  done: {
    mood: 'relaxed', intent: 'nod', shot: 'half',
    builtin: 'nod', intensity: 0.7, holdMs: 8000,
  },
};

const POLL_MS = 400;
const CHANCE_MS = 16000;
const NEXT_GAP_MS = 2500;

let lastPhase = '';
let pending: Job | null = null;
let queued: Job | null = null;
let waitTimer = 0;
let playing = false;

function deskQuiet() {
  if (tarotNow() || dancingNow()) return false;
  const chat = useChatStore();
  if (chat.sending) return false;
  if (speechPlayer.streamOpen || speechPlayer.isSpeaking()) return false;
  if (!useCharacterStore().currentId) return false;
  return true;
}

function pickedHas(source: string) {
  const ids = codewatchLive.picked;
  if (!ids.length) return source === 'cursor';
  return ids.includes(source as typeof ids[number]);
}

function shortTitle(snap: CodewatchStatus) {
  return (snap.title || '').trim();
}

function preview(snap: CodewatchStatus) {
  const title = shortTitle(snap);
  if (snap.phase === 'started') {
    codewatchLive.hudPhase = 'started';
    codewatchLive.line = title;
    return;
  }
  if (snap.phase === 'working') {
    codewatchLive.hudPhase = 'working';
    codewatchLive.line = title;
    return;
  }
  if (snap.phase === 'done') {
    codewatchLive.hudPhase = 'done';
    codewatchLive.line = title;
  }
}

function playPack(kind: ShowKind) {
  const pack = PACKS[kind];
  caster.playShow({
    mood: pack.mood,
    intent: pack.intent,
    intensity: pack.intensity,
    shot: pack.shot,
    builtin: pack.builtin,
    holdMs: pack.holdMs,
  });
}

async function runShow(kind: ShowKind, snap: CodewatchStatus) {
  if (!deskQuiet()) return false;
  playPack(kind);
  await useChatStore().codewatchSpeak(snap);
  return true;
}

function stopWait() {
  if (waitTimer) {
    window.clearInterval(waitTimer);
    waitTimer = 0;
  }
}

function syncWaitFlag() {
  codewatchLive.waiting = !!pending;
}

function takeNext() {
  if (!queued) return;
  const next = queued;
  queued = null;
  pending = { ...next, until: Date.now() + NEXT_GAP_MS + CHANCE_MS };
  syncWaitFlag();
  if (!waitTimer) waitTimer = window.setInterval(() => { void tickWait(); }, POLL_MS);
}

async function tickWait() {
  if (playing || !pending) {
    if (!pending) stopWait();
    syncWaitFlag();
    return;
  }
  if (!deskQuiet()) {
    if (Date.now() >= pending.until) {
      pending = null;
      queued = null;
      stopWait();
      syncWaitFlag();
    }
    return;
  }
  const job = pending;
  pending = null;
  syncWaitFlag();
  playing = true;
  try {
    const ok = await runShow(job.kind, job.snap);
    if (!ok) {
      if (Date.now() < job.until) pending = job;
      syncWaitFlag();
      return;
    }
    if (queued) takeNext();
    else stopWait();
  } finally {
    playing = false;
  }
}

function scheduleShow(kind: ShowKind, snap: CodewatchStatus) {
  const job: Job = { kind, snap, until: Date.now() + CHANCE_MS };
  if (kind === 'done' && pending?.kind === 'started') {
    pending = job;
    queued = null;
  } else if (kind === 'started' && pending?.kind === 'done') {
    queued = job;
  } else if (pending && pending.kind === kind) {
    pending.snap = snap;
  } else {
    pending = job;
  }
  syncWaitFlag();
  if (!waitTimer) waitTimer = window.setInterval(() => { void tickWait(); }, POLL_MS);
  void tickWait();
}

export function resetCodewatchShow() {
  pending = null;
  queued = null;
  lastPhase = 'idle';
  playing = false;
  stopWait();
  codewatchLive.line = '';
  codewatchLive.waiting = false;
  codewatchLive.hudPhase = 'idle';
}

export function applyCodewatch(snap: CodewatchStatus) {
  if (!snap.watching) {
    resetCodewatchShow();
    return;
  }
  if (snap.source && !pickedHas(snap.source) && snap.phase !== 'idle') return;
  const phase = snap.phase || 'idle';
  if (phase === lastPhase && phase !== 'working') return;

  if (phase === 'started') {
    lastPhase = phase;
    preview(snap);
    scheduleShow('started', snap);
    return;
  }
  if (phase === 'working') {
    lastPhase = phase;
    preview(snap);
    return;
  }
  if (phase === 'done') {
    lastPhase = phase;
    preview(snap);
    scheduleShow('done', snap);
    return;
  }
  lastPhase = phase;
  if (phase === 'idle') {
    if (pending || queued) {
      codewatchLive.hudPhase = pending?.kind || queued?.kind || 'done';
      return;
    }
    codewatchLive.line = '';
    codewatchLive.hudPhase = 'idle';
  }
}
