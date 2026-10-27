<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { isClipStt, micAvailable, speechInput } from '../voice/stt';
import { stage } from '../../engine/stage';
import { speechPlayer } from '../voice/tts';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import XkIcon from '../icons/XkIcon.vue';
import { useGlancePower } from '../glance/power';
import { t } from '../../i18n';
import { setShellMode } from './mode';

const ORB = 46;
const GLANCE = 34;
const MARGIN = 10;
const IDLE_MS = 30_000;
const ORB_KEY = 'companion.pet.orb';

const chat = useChatStore();
const settings = useSettingsStore();
const message = useMessage();
const { glance, glanceBusy, glanceTip, toggleGlance } = useGlancePower();
const text = ref('');
const listening = ref(false);
const open = ref(false);
const speaking = ref(false);
const below = ref(false);
const parked = ref(true);
const draggingOrb = ref(false);
const screens = ref<PetDisplay[]>([]);
const inputEl = ref<HTMLInputElement | null>(null);
const orbStyle = ref<Record<string, string>>({ left: '10px', top: '120px' });
const glanceStyle = ref<Record<string, string>>({ left: '16px', top: '174px' });
const dockStyle = ref<Record<string, string>>({
  left: '10px',
  top: '10px',
  '--tail': '160px',
});
let voiceSent = false;
let stopDisplays = () => {};
let side: 'left' | 'right' = 'right';
let home: { x: number; y: number } | null = null;
let pos = { x: MARGIN, y: 120 };
let idleTimer = 0;
let speakTimer = 0;
let sideTimer = 0;
let drag = false;
let dragMoved = false;
let dragX = 0;
let dragY = 0;
let originX = 0;
let originY = 0;

function screenTitle(d: PetDisplay) {
  const bits = [`${d.width}×${d.height}`];
  if (d.label) bits.push(d.label);
  if (d.internal) bits.push(t('pet.screenBuiltIn'));
  if (d.primary) bits.push(t('pet.screenPrimary'));
  if (d.scaleFactor && Math.abs(d.scaleFactor - 1) > 0.05) bits.push(`@${d.scaleFactor}`);
  return bits.join(' · ');
}

async function refreshScreens() {
  const list = await window.companionDesktop?.listDisplays?.();
  screens.value = Array.isArray(list) ? list : [];
}

async function pickScreen(id: number) {
  const current = screens.value.find((d) => d.current);
  if (current?.id === id) return;
  const list = await window.companionDesktop?.setPetDisplay?.(id);
  if (Array.isArray(list)) screens.value = list;
}

function clampPoint(x: number, y: number) {
  return {
    x: Math.max(MARGIN, Math.min(window.innerWidth - ORB - MARGIN, x)),
    y: Math.max(MARGIN, Math.min(window.innerHeight - ORB - MARGIN, y)),
  };
}

function edgePoint(which: 'left' | 'right') {
  const y = Math.round(window.innerHeight * 0.42 - ORB / 2);
  const x = which === 'left' ? MARGIN : window.innerWidth - ORB - MARGIN;
  return clampPoint(x, y);
}

/** 停在她对面的那条边，避免盖住身体。窗口就是她所在的那块屏。 */
function sideBesideHer(): 'left' | 'right' {
  const p = stage.petBubblePoint();
  if (!p) return side;
  return p.x < window.innerWidth * 0.5 ? 'right' : 'left';
}

function layout() {
  const left = pos.x;
  const top = pos.y;
  orbStyle.value = { left: `${left}px`, top: `${top}px` };
  let gy = top + ORB + 8;
  if (gy + GLANCE > window.innerHeight - MARGIN) gy = Math.max(MARGIN, top - GLANCE - 8);
  glanceStyle.value = { left: `${left + (ORB - GLANCE) / 2}px`, top: `${gy}px` };
  const width = Math.min(320, window.innerWidth - 20);
  const panelLeft = Math.min(window.innerWidth - width - 10, Math.max(10, left + ORB / 2 - width / 2));
  const above = top - 128;
  below.value = above < 10;
  const panelTop = below.value ? top + ORB + 12 : above;
  const tail = Math.min(width - 22, Math.max(22, left + ORB / 2 - panelLeft));
  dockStyle.value = { left: `${panelLeft}px`, top: `${panelTop}px`, '--tail': `${tail}px` };
}

function setPos(x: number, y: number) {
  pos = clampPoint(x, y);
  layout();
}

function persist() {
  try {
    localStorage.setItem(ORB_KEY, JSON.stringify({ side, home }));
  } catch { /* 隐私模式 */ }
}

function restoreOrb() {
  try {
    const raw = localStorage.getItem(ORB_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as { side?: string; home?: { x?: number; y?: number } };
    if (parsed.side === 'left' || parsed.side === 'right') side = parsed.side;
    const hx = Number(parsed.home?.x);
    const hy = Number(parsed.home?.y);
    if (Number.isFinite(hx) && Number.isFinite(hy)) home = { x: hx, y: hy };
  } catch { /* 坏数据就用默认贴边 */ }
}

function park(remember: boolean) {
  if (open.value || listening.value || drag) return;
  if (remember && !parked.value) home = { x: pos.x, y: pos.y };
  side = sideBesideHer();
  parked.value = true;
  const edge = edgePoint(side);
  setPos(edge.x, edge.y);
  persist();
}

function armIdle() {
  window.clearTimeout(idleTimer);
  idleTimer = window.setTimeout(() => park(true), IDLE_MS);
}

function toggleChat() {
  open.value = !open.value;
  window.clearTimeout(idleTimer);
  if (open.value) requestAnimationFrame(() => inputEl.value?.focus());
  else armIdle();
}

function onOrbDown(e: PointerEvent) {
  if (e.button !== 0) return;
  drag = true;
  draggingOrb.value = true;
  dragMoved = false;
  dragX = e.clientX;
  dragY = e.clientY;
  originX = pos.x;
  originY = pos.y;
  window.clearTimeout(idleTimer);
  (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
}

function onOrbMove(e: PointerEvent) {
  if (!drag) return;
  const dx = e.clientX - dragX;
  const dy = e.clientY - dragY;
  if (Math.hypot(dx, dy) > 5) dragMoved = true;
  if (!dragMoved) return;
  parked.value = false;
  setPos(originX + dx, originY + dy);
}

function onOrbUp(e: PointerEvent) {
  if (!drag) return;
  drag = false;
  draggingOrb.value = false;
  try { (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId); } catch { /* 已经松开 */ }
  if (dragMoved) {
    home = { x: pos.x, y: pos.y };
    persist();
    armIdle();
    return;
  }
  if (parked.value && home) {
    const edge = edgePoint(side);
    if (Math.hypot(home.x - edge.x, home.y - edge.y) > 24) {
      parked.value = false;
      setPos(home.x, home.y);
      armIdle();
      return;
    }
  }
  toggleChat();
}

function onResize() {
  if (parked.value) {
    const edge = edgePoint(side);
    setPos(edge.x, edge.y);
    return;
  }
  setPos(pos.x, pos.y);
}

watch(listening, (on) => {
  stage.director.setListening(on);
  window.clearTimeout(idleTimer);
  if (!on && !open.value) armIdle();
});

onMounted(() => {
  restoreOrb();
  side = sideBesideHer();
  parked.value = true;
  setPos(edgePoint(side).x, edgePoint(side).y);
  armIdle();
  speakTimer = window.setInterval(() => {
    speaking.value = speechPlayer.isSpeaking();
  }, 200);
  window.addEventListener('resize', onResize);
  sideTimer = window.setTimeout(() => {
    if (!parked.value || drag) return;
    const next = sideBesideHer();
    if (next === side) return;
    side = next;
    setPos(edgePoint(side).x, edgePoint(side).y);
    persist();
  }, 1600);
  void refreshScreens();
  stopDisplays = window.companionDesktop?.onDisplaysChanged?.(() => { void refreshScreens(); }) || (() => {});
});
onUnmounted(() => {
  window.clearTimeout(idleTimer);
  window.clearTimeout(sideTimer);
  window.clearInterval(speakTimer);
  window.removeEventListener('resize', onResize);
  stopDisplays();
});

function onEnter(e: KeyboardEvent) {
  if (e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  void send();
}

async function send() {
  speechPlayer.unlock();
  const line = text.value;
  text.value = '';
  await chat.send(line);
}

function minimize() {
  window.companionDesktop?.minimize?.();
}

function closePet() {
  window.companionDesktop?.close?.();
}

const canReload = typeof window.companionDesktop?.reload === 'function';

function reloadPet() {
  void window.companionDesktop?.reload?.();
}

function toggleMic() {
  const engine = isClipStt(settings.stt.engine) ? settings.stt.engine : 'browser';
  if (!micAvailable(engine)) {
    message.warning(t('pet.micNo'));
    return;
  }
  speechPlayer.unlock();
  if (speechInput.opening) return;
  if (listening.value) {
    if (isClipStt(engine)) void speechInput.stopAndRecognize();
    else speechInput.stop();
    return;
  }
  speechInput.engine = engine;
  const ok = speechInput.start(
    (said, isFinal, meta) => {
      if (meta?.phase === 'ready' || meta?.phase === 'recognizing') return;
      if (said) text.value = said;
      const line = (said || '').trim();
      if (!line || !isFinal || voiceSent) return;
      voiceSent = true;
      text.value = '';
      void chat.send(line, { fromVoice: true }).finally(() => {
        voiceSent = false;
      });
    },
    () => { listening.value = false; },
    () => { chat.onMicStart(); },
    () => {
      listening.value = false;
      message.warning(t('pet.micNo'));
    },
  );
  listening.value = ok;
}
</script>

<template>
  <button type="button" class="pet-orb" data-pet-hit
          :class="{ open, live: speaking, parked, drag: draggingOrb }"
          :style="orbStyle" :title="t('pet.chat')"
          @pointerdown="onOrbDown" @pointermove="onOrbMove"
          @pointerup="onOrbUp" @pointercancel="onOrbUp">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v6a3.5 3.5 0 0 1-3.5 3.5H11l-3.6 2.7a.8.8 0 0 1-1.3-.6V16A3.5 3.5 0 0 1 5 12.5v-6Z" />
    </svg>
  </button>
  <button type="button" class="pet-glance" data-pet-hit
          :class="{ on: glance.along, starting: glance.eyes === 'starting' || glanceBusy }"
          :style="glanceStyle" :title="glanceTip"
          @click.stop="toggleGlance">
    <XkIcon name="glance" :size="16" />
  </button>
  <div v-show="open" class="pet-dock" data-pet-hit :class="{ below }" :style="dockStyle">
    <div class="row">
      <button v-if="micAvailable(isClipStt(settings.stt.engine) ? settings.stt.engine : 'browser')"
              type="button" class="mic" :class="{ live: listening }"
              :title="t('voice.hearing')" @click="toggleMic">
        <XkIcon name="mic" :size="15" />
      </button>
      <input ref="inputEl" v-model="text"
             :placeholder="listening ? t('chat.listening') : t('chat.placeholder')"
             @keydown.enter="onEnter" />
      <button type="button" class="send" :disabled="!text.trim() || chat.sending"
              :title="t('chat.send')" @click="send">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M2 21 23 12 2 3v7l15 2-15 2v7Z" />
        </svg>
      </button>
    </div>
    <div v-if="screens.length > 1" class="screens">
      <button v-for="d in screens" :key="d.id" type="button"
              :class="{ on: d.current }" :title="screenTitle(d)"
              @click="pickScreen(d.id)">
        {{ t('pet.screen', { n: d.index }) }}
      </button>
    </div>
    <div class="ops">
      <button type="button" :class="{ on: glance.along }" @click="toggleGlance">{{ glanceTip }}</button>
      <i />
      <button type="button" @click="setShellMode('stage')">{{ t('pet.back') }}</button>
      <i />
      <button v-if="canReload" type="button" @click="reloadPet">{{ t('pet.reload') }}</button>
      <i v-if="canReload" />
      <button type="button" @click="minimize">{{ t('pet.min') }}</button>
      <i />
      <button type="button" class="danger" @click="closePet">{{ t('pet.close') }}</button>
    </div>
    <span class="tail" />
  </div>
</template>

<style scoped>
.pet-orb {
  position: absolute;
  z-index: 21;
  width: 46px;
  height: 46px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  touch-action: none;
  transition: left 0.28s ease, top 0.28s ease;
  color: #fff;
  background:
    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.28), transparent 42%),
    linear-gradient(180deg, rgba(122, 120, 238, 0.92), rgba(62, 58, 150, 0.9));
  box-shadow:
    0 10px 24px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.pet-orb svg {
  width: 20px;
  height: 20px;
  fill: #fff;
}

.pet-orb.open {
  background:
    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.22), transparent 42%),
    linear-gradient(180deg, rgba(72, 70, 120, 0.92), rgba(28, 28, 48, 0.92));
}

.pet-orb.live {
  box-shadow:
    0 10px 24px rgba(0, 0, 0, 0.28),
    0 0 0 5px rgba(168, 160, 255, 0.28);
}

.pet-orb.drag {
  cursor: grabbing;
  transition: none;
}

.pet-orb:hover {
  filter: brightness(1.08);
}

.pet-glance {
  position: absolute;
  z-index: 22;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #fff;
  background: rgba(28, 28, 48, 0.82);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.28);
  transition: left 0.28s ease, top 0.28s ease, background 0.15s;
}

.pet-glance.on {
  background: #5b5bd6;
}

.pet-glance.starting {
  background: rgba(91, 91, 214, 0.55);
}

.pet-glance:hover {
  filter: brightness(1.08);
}

.pet-dock {
  position: absolute;
  width: min(320px, calc(100vw - 32px));
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 8px 8px 7px;
  border-radius: 22px;
  user-select: none;
  color: #f4f4fb;
  background:
    linear-gradient(180deg, rgba(48, 48, 72, 0.78), rgba(18, 18, 30, 0.86));
  backdrop-filter: blur(22px) saturate(1.3);
  border: 1px solid rgba(255, 255, 255, 0.16);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.tail {
  position: absolute;
  left: var(--tail, 50%);
  bottom: -5px;
  width: 12px;
  height: 12px;
  transform: translateX(-50%) rotate(45deg);
  background: rgba(18, 18, 30, 0.92);
  border-right: 1px solid rgba(255, 255, 255, 0.14);
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
  pointer-events: none;
}

.pet-dock.below .tail {
  bottom: auto;
  top: -5px;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.16);
  border-top: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(48, 48, 72, 0.92);
}

.row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 3px 3px 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 4px;
  border: none;
  background: transparent;
  color: #f7f7fc;
  user-select: text;
  font: inherit;
  font-size: 13px;
  outline: none;
}

input::placeholder {
  color: rgba(244, 244, 251, 0.38);
}

.mic,
.send {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  cursor: pointer;
  color: #fff;
}

.mic {
  background: rgba(255, 255, 255, 0.08);
}

.mic.live {
  background: #d4536a;
  box-shadow: 0 0 0 4px rgba(212, 83, 106, 0.22);
}

.send {
  background: linear-gradient(180deg, #7a78ee, #5654c8);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.send svg {
  width: 14px;
  height: 14px;
  fill: #fff;
  margin-left: 1px;
}

.send:disabled {
  opacity: 0.38;
  cursor: default;
  box-shadow: none;
}

.ops {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 6px 1px;
}

.screens {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  padding: 0 4px;
}

.screens button {
  border: none;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(244, 244, 251, 0.62);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.screens button.on {
  color: #fff;
  background: rgba(122, 120, 238, 0.45);
}

.screens button:hover {
  color: #fff;
}

.ops i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.28);
}

.ops button {
  border: none;
  padding: 0;
  background: transparent;
  color: rgba(244, 244, 251, 0.62);
  font: inherit;
  font-size: 11px;
  letter-spacing: 0.02em;
  cursor: pointer;
}

.ops button:hover,
.ops button.on {
  color: #fff;
}

.ops button.danger:hover {
  color: #ffb4c0;
}

.mic:hover,
.send:hover:not(:disabled) {
  filter: brightness(1.08);
}
</style>
