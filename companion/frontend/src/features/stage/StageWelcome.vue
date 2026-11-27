<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
// The opening uses the approved 旋转鞠躬 and 低头害羞 presets from the motion library.
import poster from './xiaoke-welcome-lossless.webp';
import startupVideo from './xiaoke-startup-lossless.webm';
import shyPoster from './xiaoke-shy-lossless.webp';
import BrandLogo from '../../components/BrandLogo.vue';
import { encodeAssetPath } from '../../api/client';
import type { ReplyLang } from '../../i18n';

const props = defineProps<{ language: ReplyLang; saving: boolean; failed: boolean }>();
const emit = defineEmits<{ continue: [language: ReplyLang]; 'preload-stage': [] }>();
const language = ref(props.language);
const savingCopy: Record<ReplyLang, string> = {
  'zh-CN': '正在保存语言…',
  en: 'Saving language…',
  ja: '言語設定を保存中…',
  ko: '언어 설정 저장 중…',
  ru: 'Сохранение языка…',
};
const film = ref<HTMLVideoElement>();
const theme = ref<HTMLAudioElement>();
const themePlaying = ref(false);
const themeUrl = `/assets/${encodeAssetPath('music/有你小可爱.wav')}`;
const pixelRatio = ref(Math.max(1, window.devicePixelRatio));
const filmLimits = computed(() => ({
  '--film-max-width': `${1920 / pixelRatio.value}px`,
  '--film-max-height': `${1080 / pixelRatio.value}px`,
}));
const shyShot = ref(false);
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const showFilm = ref(!motionPreference.matches);
const showLanguage = computed(() => shyShot.value || !showFilm.value);
const progress = ref(0);
// The stream-copy edit offsets shot two by the first clip duration plus its 5.20 s hold.
const shyStart = 7.9; // Just before the second shot's 7.908 s keyframe.
const loopHoldMs = 13140;
let preloadSent = false;
let playbackTimer: ReturnType<typeof setTimeout> | undefined;
let loopTimer: ReturnType<typeof setTimeout> | undefined;
let frameRequest: number | undefined;

function armPlaybackTimeout() {
  clearTimeout(playbackTimer);
  if (showFilm.value) playbackTimer = setTimeout(skipFilm, 5000);
}

function clearFrameRequest() {
  if (frameRequest !== undefined) film.value?.cancelVideoFrameCallback(frameRequest);
  frameRequest = undefined;
}

function skipFilm() {
  clearTimeout(playbackTimer);
  clearTimeout(loopTimer);
  clearFrameRequest();
  film.value?.pause();
  showFilm.value = false;
  preloadStage();
}

function preloadStage() {
  if (preloadSent) return;
  preloadSent = true;
  emit('preload-stage');
}

function holdBeforeReplay() {
  clearTimeout(playbackTimer);
  clearTimeout(loopTimer);
  clearFrameRequest();
  loopTimer = setTimeout(() => {
    const media = film.value;
    if (!showFilm.value || !media) return;
    media.currentTime = 0;
    armPlaybackTimeout();
    void media.play().catch(skipFilm);
  }, loopHoldMs);
}

function syncShot(time: number) {
  shyShot.value = time >= shyStart;
  // Leave the opening motion free of 3D renderer and model initialization.
  if (time >= 2.65) preloadStage();
}

function trackFrames() {
  const media = film.value;
  if (!media || typeof media.requestVideoFrameCallback !== 'function') return;
  clearFrameRequest();
  const nextFrame: VideoFrameRequestCallback = (_, { mediaTime }) => {
    syncShot(mediaTime);
    frameRequest = media.requestVideoFrameCallback(nextFrame);
  };
  frameRequest = media.requestVideoFrameCallback(nextFrame);
}

function onPlaying() {
  clearTimeout(playbackTimer);
  trackFrames();
}

function updateProgress() {
  const media = film.value;
  if (!media || !Number.isFinite(media.duration) || media.duration <= 0) return;
  progress.value = media.currentTime / media.duration;
  if (typeof media.requestVideoFrameCallback !== 'function') syncShot(media.currentTime);
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && showFilm.value) skipFilm();
}

function followMotionPreference(event: MediaQueryListEvent) {
  if (event.matches) skipFilm();
}

function updateFilmLimits() {
  pixelRatio.value = Math.max(1, window.devicePixelRatio);
}

function playTheme() {
  void theme.value?.play().catch(() => { themePlaying.value = false; });
}

function toggleTheme() {
  if (themePlaying.value) theme.value?.pause();
  else playTheme();
}

onMounted(() => {
  window.addEventListener('keydown', handleEscape);
  window.addEventListener('resize', updateFilmLimits);
  motionPreference.addEventListener('change', followMotionPreference);
  if (!showFilm.value) preloadStage();
  armPlaybackTimeout();
  void film.value?.play().catch(skipFilm);
  playTheme();
});
onBeforeUnmount(() => {
  theme.value?.pause();
  clearTimeout(playbackTimer);
  clearTimeout(loopTimer);
  clearFrameRequest();
  window.removeEventListener('keydown', handleEscape);
  window.removeEventListener('resize', updateFilmLimits);
  motionPreference.removeEventListener('change', followMotionPreference);
});
const choices = [
  { id: 'zh-CN', name: '简体中文', skip: '跳过动画', languageLabel: '选择语言', heading: ['执子之魂，', '与子共生'], waiting: '等待语言确认', enter: '进入小可爱的舞台', retry: '语言设置未能保存，请重试。' },
  { id: 'en', name: 'English', skip: 'Skip animation', languageLabel: 'Choose your language', heading: ['Never one...', ' without the other.'], waiting: 'Awaiting language confirmation', enter: 'Enter the stage', retry: 'Your language could not be saved. Try again.' },
  { id: 'ja', name: '日本語', skip: '演出をスキップ', languageLabel: '言語を選択', heading: ['片方だけでは、', 'ありえない。'], waiting: '言語の確認待ち', enter: 'ステージへ', retry: '言語設定を保存できませんでした。もう一度お試しください。' },
  { id: 'ko', name: '한국어', skip: '애니메이션 건너뛰기', languageLabel: '언어 선택', heading: ['하나 없이는', ' 다른 하나도 없다.'], waiting: '언어 확인 대기', enter: '무대로 들어가기', retry: '언어 설정을 저장할 수 없습니다. 다시 시도해 주세요.' },
  { id: 'ru', name: 'Русский', skip: 'Пропустить анимацию', languageLabel: 'Выберите язык', heading: ['Никогда не один...', ' без другого.'], waiting: 'Ожидание выбора языка', enter: 'Войти на сцену', retry: 'Не удалось сохранить язык. Попробуйте ещё раз.' },
] as const;
const copy = computed(() => choices.find((choice) => choice.id === language.value) ?? choices[1]);
const themeLabel = computed(() => ({
  'zh-CN': '主题曲', en: 'Theme music', ja: 'テーマ曲', ko: '테마곡', ru: 'Музыкальная тема',
})[language.value]);
</script>

<template>
  <main class="welcome" :class="{ 'shy-shot': shyShot }" :style="filmLimits" :lang="language" :aria-busy="saving">
    <audio ref="theme" :src="themeUrl" loop preload="none"
           @playing="themePlaying = true" @pause="themePlaying = false" @error="themePlaying = false" />
    <video v-if="showFilm" ref="film" class="film" :src="startupVideo" :poster="poster"
           muted playsinline preload="auto" aria-hidden="true"
           @playing="onPlaying" @timeupdate="updateProgress" @waiting="armPlaybackTimeout"
           @ended="holdBeforeReplay" @error="skipFilm" />
    <img v-else class="film" :src="shyShot ? shyPoster : poster" alt="" draggable="false" />
    <div class="shade" aria-hidden="true"></div>
    <div class="frame-guides" aria-hidden="true"></div>
    <header class="brand"><BrandLogo :size="23" /><span>XIAOKE.AI</span></header>
    <button v-if="showFilm" type="button" class="skip" @click="skipFilm">{{ copy.skip }} <span aria-hidden="true">»</span></button>
    <form class="entry" @submit.prevent="showLanguage && emit('continue', language)">
      <fieldset :disabled="saving">
        <legend :key="`${language}-${shyShot}`">
          <span class="title-accessible">{{ copy.heading.join('') }}</span>
          <span v-for="(phrase, index) in copy.heading" :key="phrase" class="title-phrase"
                :style="{ '--arrival': `${index * 125}ms` }" aria-hidden="true">{{ phrase }}</span>
        </legend>
        <div v-if="showLanguage" class="languages" role="radiogroup" :aria-label="copy.languageLabel">
          <label v-for="(choice, index) in choices" :key="choice.id" :lang="choice.id"
                 :style="{ '--arrival': `${340 + index * 43}ms` }">
            <input v-model="language" type="radio" name="stage-language" :value="choice.id" />
            <span>{{ choice.name }}</span>
          </label>
        </div>
        <button v-if="showLanguage" class="enter" type="submit"><span :key="language" class="enter-text">{{ copy.enter }}</span> <span aria-hidden="true">↗</span></button>
      </fieldset>
      <p v-if="showLanguage && failed" role="alert">{{ copy.retry }}</p>
      <p v-else-if="showLanguage" class="sequence-status" role="status">{{ saving ? savingCopy[language] : copy.waiting }}</p>
    </form>
    <small class="art-credit" lang="zh-CN">小可爱 · liupig</small>
    <button type="button" class="theme-toggle" :aria-pressed="themePlaying" :aria-label="themeLabel"
            title="有你小可爱" @click="toggleTheme">
      <span aria-hidden="true">{{ themePlaying ? 'Ⅱ' : '♪' }}</span> {{ themeLabel }}
    </button>
    <div v-if="showFilm" class="film-progress" aria-hidden="true"><i :style="{ transform: `scaleX(${progress})` }"></i></div>
  </main>
</template>

<style scoped>
.welcome {
  user-select: text;
  -webkit-app-region: no-drag;
  position: fixed;
  inset: 0;
  z-index: 100;
  isolation: isolate;
  display: grid;
  align-items: center;
  justify-items: start;
  overflow: auto;
  background: #080d1c;
  color: #fffaed;
}
.welcome button, .welcome label { user-select: text; }
.film, .shade { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.film {
  z-index: -2;
  width: min(100%, var(--film-max-width));
  height: min(100%, var(--film-max-height));
  margin: auto;
  object-fit: contain;
}
.shade {
  z-index: -1;
  background:
    linear-gradient(90deg, transparent 40%, #080c19a8 82%),
    linear-gradient(180deg, #080b186c, transparent 15%, transparent 83%, #080b18b0 100%);
}
.shy-shot .shade {
  background:
    linear-gradient(270deg, transparent 40%, #080c19a8 82%),
    linear-gradient(180deg, #080b186c, transparent 15%, transparent 83%, #080b18b0 100%);
}
.frame-guides {
  position: fixed;
  inset: 25px;
  pointer-events: none;
  border: 1px solid #e1ecff13;
  background:
    linear-gradient(#d6e5ff3d, #d6e5ff3d) left top / 12px 1px,
    linear-gradient(#d6e5ff3d, #d6e5ff3d) left top / 1px 12px,
    linear-gradient(#d6e5ff3d, #d6e5ff3d) right bottom / 12px 1px,
    linear-gradient(#d6e5ff3d, #d6e5ff3d) right bottom / 1px 12px;
  background-repeat: no-repeat;
}
.brand, .skip, .art-credit { position: absolute; }
.brand {
  top: 43px;
  left: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  font: 600 12px/1.3 ui-monospace, monospace;
  letter-spacing: .17em;
}
.skip { top: 38px; right: 44px; padding: 7px 0; border: 0; background: none; color: #fff5df; font-size: 13px; }
.art-credit { bottom: 37px; left: 44px; color: #cad0e0; font-size: 11px; }
.theme-toggle {
  position: absolute;
  bottom: 30px;
  right: 44px;
  padding: 6px 0;
  border: 0;
  background: none;
  color: #fff5df;
  font-size: 12px;
}
.entry {
  --entry-offset: 26px;
  width: min(532px, 44vw);
  --entry-gutter: clamp(45px, 8vw, 155px);
  --film-span: min(100vw, var(--film-max-width));
  margin: 90px var(--entry-gutter) 68px calc((100vw - var(--film-span)) / 2 + var(--entry-gutter));
  translate: calc(var(--film-span) - 100% - 2 * var(--entry-gutter)) 0;
  text-align: center;
}
.shy-shot .entry { --entry-offset: -26px; translate: 0 0; }
fieldset { border: 0; padding: 0; margin: 0; min-inline-size: 0; }
legend {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 23px;
  padding: 0 0 15px;
  color: #fff6e9;
  font-size: clamp(21px, 3.1vw, 40px);
  font-weight: 500;
  line-height: 1.22;
}
legend::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  height: 1px;
  background: linear-gradient(90deg, #f8c799aa, #eef0ff44 38%, #eef0ff12);
  transform-origin: left;
  animation: rule-draw .46s .21s cubic-bezier(.15, .78, .2, 1) both;
}
.sequence-status {
  margin: 19px 0 0;
  color: #d5d8e3;
  font: 500 10px/1.4 ui-monospace, monospace;
  letter-spacing: .14em;
  text-transform: uppercase;
  --arrival: 690ms;
}
.sequence-status::before {
  content: '';
  display: inline-block;
  width: 9px;
  height: 1px;
  margin-right: 8px;
  vertical-align: middle;
  background: #efaf78;
  animation: status-lock .24s .84s ease-out both;
}
.title-phrase {
  display: inline-block;
  white-space: pre-wrap;
  text-shadow: 0 2px 16px #020613c0;
}
.title-accessible {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  user-select: none;
}
.enter-text {
  display: inline-block;
  animation: type-change .24s ease-out both;
}
.title-phrase, .languages label span, .enter, .sequence-status {
  animation: entry-strike .34s var(--arrival) cubic-bezier(.19, .78, .24, 1) both;
}
@keyframes entry-strike {
  from { opacity: 0; transform: translateX(var(--entry-offset)) scaleX(1.07); }
  58% { opacity: 1; transform: translateX(calc(var(--entry-offset) / -13)) scaleX(.99); }
  to { opacity: 1; transform: none; }
}
@keyframes rule-draw { from { opacity: 0; transform: scaleX(.04); } to { opacity: 1; transform: none; } }
@keyframes status-lock { from { opacity: .3; transform: scaleX(.4); } to { opacity: 1; transform: none; } }
@keyframes type-change { from { opacity: .4; } to { opacity: 1; } }
.languages {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 5px 8px;
}
label { position: relative; color: #e3dfd6; cursor: pointer; font-size: 14px; }
label span { display: block; padding: 7px 7px; border-bottom: 2px solid transparent; }
label:hover span { color: #fff; }
label:has(input:checked) span { color: #fff; border-bottom-color: #efaf78; }
input { position: absolute; opacity: 0; width: 100%; height: 100%; margin: 0; pointer-events: none; }
label:has(input:focus-visible) span, button:focus-visible { outline: 2px solid #ffc89d; outline-offset: 4px; }
button { font: inherit; cursor: pointer; }
.enter {
  --arrival: 570ms;
  display: inline-flex;
  align-items: center;
  gap: 20px;
  padding: 8px 13px;
  margin-top: 23px;
  border: 1px solid #ffe8bc85;
  background: #10162670;
  color: #fff5df;
}
.enter:hover { color: #ffc89d; }
.enter:disabled { opacity: .6; cursor: wait; }
.enter:disabled, .enter:focus-visible, label:has(input:focus-visible) span { animation: none; }
p { color: #ffb6c6; font-size: 13px; }
.film-progress { position: fixed; bottom: 0; inset-inline: 0; height: 2px; background: #fff5df21; }
.film-progress i { display: block; width: 100%; height: 100%; transform-origin: left; transition: transform .21s linear; background: #e9bd92; }
@media (prefers-reduced-motion: reduce) {
  legend::after, .title-phrase, .languages label span, .enter, .enter-text, .sequence-status, .sequence-status::before {
    animation: none;
  }
}
@media (max-width: 700px) {
  .welcome, .welcome.shy-shot { align-items: end; justify-items: center; }
  .frame-guides { inset: 14px; }
  .brand { top: 28px; left: 28px; }
  .skip { top: 22px; right: 28px; }
  .art-credit { bottom: 24px; left: 28px; }
  .theme-toggle { bottom: 17px; right: 28px; }
  .entry, .shy-shot .entry { width: calc(100% - 54px); margin: min(42vh, 320px) 0 58px; translate: none; }
  .shy-shot .entry { text-align: left; }
  .shy-shot .languages { justify-content: flex-start; }
  .shade, .shy-shot .shade { background: linear-gradient(180deg, #080b1870, transparent 18%, transparent 43%, #080b18b5 72%, #080b18f0 100%); }
}
</style>
