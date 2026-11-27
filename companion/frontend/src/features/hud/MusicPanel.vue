<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { api, encodeAssetPath, type MusicTrack } from '../../api/client';
import { t } from '../../i18n';
import StagePanel from './StagePanel.vue';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ 'update:show': [show: boolean] }>();
const audio = ref<HTMLAudioElement>();
const tracks = ref<MusicTrack[]>([]);
const current = ref<MusicTrack>();
const playing = ref(false);
const loading = ref(false);
const loadFailed = ref(false);
const playFailed = ref(false);
const elapsed = ref(0);
const duration = ref(0);
const index = computed(() => tracks.value.findIndex((track) => track.path === current.value?.path));

async function load() {
  if (loading.value) return;
  loading.value = true;
  loadFailed.value = false;
  try {
    tracks.value = await api.listMusic();
  } catch {
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.show, (show) => { if (show) void load(); }, { immediate: true });
onBeforeUnmount(() => audio.value?.pause());

async function play(track: MusicTrack) {
  const media = audio.value;
  if (!media) return;
  playFailed.value = false;
  const src = `/assets/${encodeAssetPath(track.path)}`;
  if (media.getAttribute('src') !== src || media.error) {
    current.value = track;
    elapsed.value = 0;
    duration.value = 0;
    media.src = src;
  }
  try {
    await media.play();
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) playFailed.value = true;
  }
}

function toggle() {
  if (playing.value) audio.value?.pause();
  else if (current.value || tracks.value[0]) void play(current.value ?? tracks.value[0]);
}

function step(offset: number) {
  const count = tracks.value.length;
  if (!count) return;
  const next = index.value < 0 ? 0 : (index.value + offset + count) % count;
  void play(tracks.value[next]);
}

function syncTime() {
  if (!audio.value) return;
  elapsed.value = audio.value.currentTime;
  duration.value = Number.isFinite(audio.value.duration) ? audio.value.duration : 0;
}

function seek(event: Event) {
  if (!audio.value || !duration.value) return;
  audio.value.currentTime = (event.target as HTMLInputElement).valueAsNumber;
  syncTime();
}

function clock(time: number) {
  const seconds = Math.floor(time);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
</script>

<template>
  <audio ref="audio" preload="none" @play="playing = true" @pause="playing = false"
         @ended="step(1)" @timeupdate="syncTime" @durationchange="syncTime"
         @error="playing = false; playFailed = true" />
  <StagePanel :show="show" :title="t('musicPlayer.title')" size="small" @update:show="emit('update:show', $event)">
    <div class="player">
      <div class="now">
        <span class="art" aria-hidden="true">♫</span>
        <strong>{{ current?.name ?? t('musicPlayer.choose') }}</strong>
      </div>
      <input class="seek" type="range" min="0" :max="duration" :value="elapsed" step="0.1"
             :disabled="!duration" :aria-label="t('musicPlayer.seek')" @input="seek" />
      <div class="timing"><span>{{ clock(elapsed) }}</span><span>{{ clock(duration) }}</span></div>
      <div class="transport">
        <button type="button" :disabled="!tracks.length" :aria-label="t('musicPlayer.previous')" @click="step(-1)">⏮</button>
        <button type="button" class="primary" :disabled="!current && !tracks.length"
                :aria-label="t(playing ? 'musicPlayer.pause' : 'musicPlayer.play')" @click="toggle">{{ playing ? 'Ⅱ' : '▶' }}</button>
        <button type="button" :disabled="!tracks.length" :aria-label="t('musicPlayer.next')" @click="step(1)">⏭</button>
      </div>
      <p v-if="playFailed" class="notice" role="alert">{{ t('musicPlayer.playFailed') }}</p>
    </div>
    <h3>{{ t('musicPlayer.playlist') }}</h3>
    <p v-if="loading" class="notice" role="status">{{ t('musicPlayer.loading') }}</p>
    <button v-else-if="loadFailed" type="button" class="retry" @click="load">{{ t('musicPlayer.retry') }}</button>
    <p v-else-if="!tracks.length" class="notice">{{ t('musicPlayer.empty') }}</p>
    <ol class="tracks">
      <li v-for="(track, i) in tracks" :key="track.path">
        <button type="button" :aria-current="current?.path === track.path ? 'true' : undefined" @click="play(track)">
          <span class="number" aria-hidden="true">{{ current?.path === track.path ? '♪' : i + 1 }}</span>
          <span>{{ track.name }}</span>
          <small v-if="track.name === '有你小可爱'">{{ t('musicPlayer.theme') }}</small>
        </button>
      </li>
    </ol>
  </StagePanel>
</template>

<style scoped>
.player { border: 1px solid #e9bdad32; border-radius: 17px; padding: 15px; background: linear-gradient(145deg, #5b414d, #2d253a); }
.now { display: flex; align-items: center; gap: 11px; overflow-wrap: anywhere; }
.art { display: grid; place-items: center; flex: 0 0 42px; height: 42px; border-radius: 12px; background: #f1c1ae24; color: #ffdebd; font-size: 23px; }
.seek { display: block; width: 100%; margin: 14px 0 2px; accent-color: #ebc5a1; }
.timing { display: flex; justify-content: space-between; color: #e0c9d4; font-size: 11px; font-variant-numeric: tabular-nums; }
.transport { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 6px; }
button { font: inherit; color: inherit; cursor: pointer; }
.transport button, .retry { border: 1px solid #e8c5d034; border-radius: 10px; background: #ffffff0a; min-width: 34px; min-height: 34px; }
.transport .primary { width: 42px; height: 42px; border-radius: 50%; background: #ebc5a1; color: #292131; }
button:disabled { opacity: .42; cursor: default; }
button:focus-visible { outline: 2px solid #ebc5a1; outline-offset: 2px; }
h3 { margin: 20px 0 8px; font-size: 14px; }
.notice { margin: 9px 0; color: var(--panel-muted); font-size: 13px; }
.tracks { list-style: none; margin: 0; padding: 0; }
.tracks button { display: flex; align-items: center; gap: 8px; width: 100%; text-align: start; padding: 8px 7px; border: 1px solid transparent; border-radius: 9px; background: transparent; overflow-wrap: anywhere; }
.tracks button:hover, .tracks button[aria-current] { background: #ebc5a116; border-color: #ebc5a12b; }
.number { flex: 0 0 20px; text-align: center; color: var(--panel-accent); font-size: 12px; }
small { margin-inline-start: auto; color: #ffdfbc; font-size: 10px; }
</style>
