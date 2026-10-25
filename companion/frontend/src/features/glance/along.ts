import { api } from '../../api/client';
import { speechPlayer } from '../voice/tts';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';

export const alongLive = { on: false };

let timer = 0;
let busy = false;
let acked = 0;
let lastTried = 0;
let retryAt = 0;

async function tick() {
  if (busy) return;
  if (!useSettingsStore().modules.glance) {
    alongLive.on = false;
    return;
  }
  let snap;
  try {
    snap = await api.glanceAlong();
  } catch {
    return;
  }
  alongLive.on = !!snap.on;
  if (!snap.on || !snap.text || snap.seq === acked) return;
  const chars = useCharacterStore();
  const chat = useChatStore();
  if (!chars.currentId || snap.character_id !== chars.currentId) return;
  if (chat.sending || speechPlayer.streamOpen || speechPlayer.isSpeaking()) return;
  if (Date.now() < retryAt && snap.seq === lastTried) return;
  if (useSettingsStore().modules.tarot) {
    const { tarotLive } = await import('../tarot/gate');
    if (tarotLive.value) return;
  }
  busy = true;
  lastTried = snap.seq;
  try {
    const result = await chat.alongSpeak(snap.text);
    if (result === 'skip') return;
    if (result === 'spoke') {
      acked = snap.seq;
      await api.glanceAlongAck(snap.seq).catch(() => {});
    } else {
      retryAt = Date.now() + 15000;
    }
  } finally {
    busy = false;
  }
}

export function installAlong() {
  if (timer) return;
  timer = window.setInterval(() => { void tick(); }, 2000);
}
