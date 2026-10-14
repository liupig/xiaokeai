<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { micAvailable, speechInput } from '../voice/stt';
import { stage } from '../../engine/stage';
import { speechPlayer } from '../voice/tts';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import XkIcon from '../icons/XkIcon.vue';
import { t } from '../../i18n';
import { setShellMode } from './mode';

const chat = useChatStore();
const settings = useSettingsStore();
const message = useMessage();
const text = ref('');
const listening = ref(false);
const open = ref(false);
const screens = ref<PetDisplay[]>([]);
const inputEl = ref<HTMLInputElement | null>(null);
const dockStyle = ref<Record<string, string>>({
  left: '24px',
  top: '24px',
  '--tail': '160px',
});
let voiceSent = false;
let hideTimer = 0;
let stopDisplays = () => {};
const SHOW_MS = 30000;

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

function placeDock() {
  const p = stage.petBubblePoint();
  const width = Math.min(320, window.innerWidth - 32);
  if (!p) return;
  const left = Math.min(window.innerWidth - width - 12, Math.max(12, p.x - width / 2));
  const top = Math.max(12, p.y - 118);
  const tail = Math.min(width - 22, Math.max(22, p.x - left));
  dockStyle.value = { left: `${left}px`, top: `${top}px`, '--tail': `${tail}px` };
}

function bumpDock() {
  window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(() => { open.value = false; }, SHOW_MS);
}

function showDock() {
  placeDock();
  open.value = true;
  bumpDock();
  requestAnimationFrame(() => inputEl.value?.focus());
}

function onPetUi() {
  showDock();
}

watch(listening, (on) => stage.director.setListening(on));
watch(text, () => { if (open.value) bumpDock(); });

onMounted(() => {
  window.addEventListener('xiaoke-pet-ui', onPetUi);
  void refreshScreens();
  stopDisplays = window.companionDesktop?.onDisplaysChanged?.(() => { void refreshScreens(); }) || (() => {});
});
onUnmounted(() => {
  window.removeEventListener('xiaoke-pet-ui', onPetUi);
  window.clearTimeout(hideTimer);
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

function toggleMic() {
  const engine = settings.stt.engine === 'sensevoice' ? 'sensevoice' : 'browser';
  if (!micAvailable(engine)) {
    message.warning(t('pet.micNo'));
    return;
  }
  speechPlayer.unlock();
  if (speechInput.opening) return;
  if (listening.value) {
    if (engine === 'sensevoice') void speechInput.stopAndRecognize();
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
  <div v-show="open" class="pet-dock" data-pet-hit :style="dockStyle">
    <div class="row">
      <button v-if="micAvailable(settings.stt.engine === 'sensevoice' ? 'sensevoice' : 'browser')"
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
      <button type="button" @click="setShellMode('stage')">{{ t('pet.back') }}</button>
      <i />
      <button type="button" @click="minimize">{{ t('pet.min') }}</button>
      <i />
      <button type="button" class="danger" @click="closePet">{{ t('pet.close') }}</button>
    </div>
    <span class="tail" />
  </div>
</template>

<style scoped>
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

.ops button:hover {
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
