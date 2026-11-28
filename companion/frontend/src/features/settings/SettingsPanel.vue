<script setup lang="ts">
import StagePanel from '../hud/StagePanel.vue';
import PanelGroup from '../hud/PanelGroup.vue';
import NativeSelect from './NativeSelect.vue';
import LightingControls from '../lighting/LightingControls.vue';
import { computed, onUnmounted, ref, watch } from 'vue';
import {
  NButton, NColorPicker, NInput, NInputNumber, NSelect,
  NSlider, NSwitch, useMessage,
} from 'naive-ui';
import { api } from '../../api/client';
import { useSettingsStore } from '../../stores/settings';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { LOCAL_SCENES } from '../scenes/catalog';
import { featureOn, t } from '../../i18n';
import { CURRENT_VERSION } from '../update/updateService';
import {
  pickScene as pickPlayScene, restoreOrRotateScene, sceneExtra, sceneSession,
} from '../scenes/session';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const settings = useSettingsStore();
const characters = useCharacterStore();
const chat = useChatStore();
const message = useMessage();

const llmPresetOptions = computed(() => {
  settings.locale.ui;
  const all = [
    { label: t('set.llm.ph'), value: 'custom' },
    { label: t('set.llm.bailian'), value: 'bailian' },
    { label: t('set.llm.qwen_intl'), value: 'qwen_intl' },
    { label: t('set.llm.volcano'), value: 'volcano' },
    { label: t('set.llm.volcano_character'), value: 'volcano_character' },
    { label: t('set.llm.minicpm'), value: 'minicpm' },
    { label: t('set.llm.deepseek'), value: 'deepseek' },
    { label: t('set.llm.moonshot'), value: 'moonshot' },
    { label: t('set.llm.moonshot_intl'), value: 'moonshot_intl' },
    { label: t('set.llm.zhipu'), value: 'zhipu' },
    { label: t('set.llm.siliconflow'), value: 'siliconflow' },
    { label: t('set.llm.stepfun'), value: 'stepfun' },
    { label: t('set.llm.baichuan'), value: 'baichuan' },
    { label: t('set.llm.minimax'), value: 'minimax' },
    { label: t('set.llm.modelscope'), value: 'modelscope' },
    { label: t('set.llm.hunyuan'), value: 'hunyuan' },
    { label: t('set.llm.mimo'), value: 'mimo' },
    { label: t('set.llm.mimo_pro'), value: 'mimo_pro' },
    { label: t('set.llm.aihubmix'), value: 'aihubmix' },
    { label: t('set.llm.ai302'), value: 'ai302' },
    { label: 'OpenAI', value: 'openai' },
    { label: t('set.llm.anthropic'), value: 'anthropic' },
    { label: t('set.llm.gemini'), value: 'gemini' },
    { label: t('set.llm.openrouter'), value: 'openrouter' },
    { label: t('set.llm.groq'), value: 'groq' },
    { label: t('set.llm.mistral'), value: 'mistral' },
    { label: t('set.llm.xai'), value: 'xai' },
    { label: t('set.llm.together'), value: 'together' },
    { label: t('set.llm.fireworks'), value: 'fireworks' },
    { label: t('set.llm.nvidia'), value: 'nvidia' },
    { label: t('set.llm.cerebras'), value: 'cerebras' },
    { label: t('set.llm.perplexity'), value: 'perplexity' },
    { label: t('set.llm.novita'), value: 'novita' },
    { label: t('set.llm.comet'), value: 'comet' },
    { label: t('set.llm.featherless'), value: 'featherless' },
    { label: t('set.llm.ollama'), value: 'ollama' },
    { label: t('set.llm.vllm'), value: 'vllm' },
    { label: t('set.llm.sglang'), value: 'sglang' },
    { label: t('set.llm.player2'), value: 'player2' },
  ];
  if (settings.locale.ui !== 'en') return all;
  const front = new Set(['openai', 'anthropic', 'gemini', 'openrouter', 'groq', 'mistral', 'xai']);
  return [...all.filter((o) => front.has(o.value)), ...all.filter((o) => !front.has(o.value))];
});
const visionOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.vision.minicpm'), value: 'minicpm' },
    { label: t('set.vision.openai'), value: 'openai' },
  ];
});
const alongGeneratorOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.mod.generatorChat'), value: 'chat' },
    { label: t('set.mod.generatorMinicpm'), value: 'minicpm' },
  ];
});
const langOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('lang.zh'), value: 'zh-CN' as const },
    { label: t('lang.en'), value: 'en' as const },
    { label: t('lang.ja'), value: 'ja' as const },
    { label: t('lang.ko'), value: 'ko' as const },
    { label: 'Русский', value: 'ru' as const },
  ];
});
const replyModeOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('lang.fixed'), value: 'fixed' as const },
    { label: t('lang.follow'), value: 'follow' as const },
  ];
});
function characterModelNeedsEndpoint(model: string, base: string): boolean {
  const name = (model || '').trim();
  if (!name || name.toLowerCase().startsWith('ep-')) return false;
  if (!name.toLowerCase().includes('character')) return false;
  const raw = (base || '').trim();
  if (!raw) return true;
  try {
    const host = new URL(raw).hostname.toLowerCase();
    return host.endsWith('volces.com') || host.endsWith('volcengine.com');
  } catch {
    return true;
  }
}

const thinkingOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.think.default'), value: 'default' },
    { label: t('set.think.on'), value: 'on' },
    { label: t('set.think.off'), value: 'off' },
  ];
});

const contentPath = ref(settings.content.path || '');
const contentBusy = ref(false);
const contentHint = ref('');
const canPickFolder = computed(() => typeof window.companionDesktop?.pickFolder === 'function');
const isShell = !!window.companionDesktop?.isShell;
const sections = [
  { id: 'lang', label: 'lang.tab' },
  { id: 'desktop', label: 'settings.desktop' },
  { id: 'content', label: 'settings.content' },
  { id: 'modules', label: 'settings.modules' },
  { id: 'ai', label: 'settings.ai' },
  { id: 'omni', label: 'settings.omni' },
  { id: 'voice', label: 'settings.voice' },
  { id: 'download', label: 'settings.download' },
  { id: 'quality', label: 'settings.quality' },
].filter(({ id }) => id !== 'desktop' || isShell);
const section = ref('lang');
const trayMinimize = ref(true);
const trayClose = ref(true);

async function loadTrayPrefs() {
  const prefs = await window.companionDesktop?.getTrayPrefs?.();
  if (!prefs) return;
  trayMinimize.value = !!prefs.minimize;
  trayClose.value = !!prefs.close;
}

async function saveTray(patch: { minimize?: boolean; close?: boolean }) {
  const prefs = await window.companionDesktop?.setTrayPrefs?.(patch);
  if (!prefs) return;
  trayMinimize.value = !!prefs.minimize;
  trayClose.value = !!prefs.close;
}
const contentFound = computed(() => {
  settings.locale.ui;
  const f = settings.content.found || {};
  const keys = ['models', 'motions', 'cameras', 'music', 'speech', 'embed', 'torch'];
  return keys.map((k) => `${t('set.pack.' + k)}${f[k] ? '✓' : '–'}`).join('  ');
});

async function pickContentFolder() {
  const folder = await window.companionDesktop?.pickFolder?.();
  if (folder) contentPath.value = folder;
}

async function saveContentPath() {
  contentBusy.value = true;
  contentHint.value = '';
  try {
    const r = await settings.applyContent(contentPath.value.trim());
    contentHint.value = r.message || (r.ok ? t('set.pack.saved') : t('set.pack.fail'));
    if (r.ok && r.path) contentPath.value = r.path;
    if (!r.ok) message.error(r.message || t('set.pack.fail'), { duration: 6000, closable: true });
    else if (r.restart) message.success(r.message || t('set.pack.reopen'));
  } catch (e) {
    contentHint.value = String(e);
  } finally {
    contentBusy.value = false;
  }
}

watch(() => settings.content.path, (v) => {
  if (v && !contentPath.value) contentPath.value = v;
});

const showEndpointHint = computed(() => {
  settings.locale.ui;
  if (!settings.modules.harness) return false;
  const name = (settings.llm.harness_model || '').trim();
  if (!name) return characterModelNeedsEndpoint(settings.llm.model, settings.llm.base_url);
  const base = (settings.llm.harness_base_url || '').trim() || settings.llm.base_url;
  return characterModelNeedsEndpoint(name, base);
});

const testing = ref(false);
async function testLlm() {
  testing.value = true;
  try {
    const r = await api.testLlm(settings.llm);
    if (r.ok) message.success(r.message, { duration: 8000 });
    else message.error(r.message, { duration: 8000, closable: true });
  } catch (e) {
    message.error(t('set.testFail', { err: String(e) }));
  } finally {
    testing.value = false;
  }
}

const omniPrompt = ref('');
const omniReply = ref('');
const omniHint = ref('');
const omniBusy = ref(false);
const omniImageName = ref('');
const omniImageB64 = ref('');
const omniImg = ref<HTMLInputElement | null>(null);
let omniAbort: AbortController | null = null;
let omniAudioCtx: AudioContext | null = null;
let omniHorizon = 0;

function stopOmniAudio() {
  try { omniAudioCtx?.close(); } catch { /* ignore */ }
  omniAudioCtx = null;
  omniHorizon = 0;
}

function playOmniPcm(pcmB64: string, rate: number) {
  const raw = atob(pcmB64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
  if (!samples.length) return;
  if (!omniAudioCtx || omniAudioCtx.sampleRate !== rate || omniAudioCtx.state === 'closed') {
    omniAudioCtx = new AudioContext({ sampleRate: rate });
    omniHorizon = 0;
  }
  const f32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) f32[i] = samples[i] / 32768;
  const buf = omniAudioCtx.createBuffer(1, f32.length, rate);
  buf.copyToChannel(f32, 0);
  const src = omniAudioCtx.createBufferSource();
  src.buffer = buf;
  src.connect(omniAudioCtx.destination);
  const now = omniAudioCtx.currentTime;
  const t = omniHorizon > now + 0.004 ? omniHorizon : now + 0.02;
  omniHorizon = t + buf.duration;
  src.start(t);
}

function pickOmniImage() {
  omniImg.value?.click();
}

function onOmniImage(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 4 * 1024 * 1024) {
    message.warning(t('set.omni.tooBig'));
    (e.target as HTMLInputElement).value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const url = String(reader.result || '');
    const comma = url.indexOf(',');
    omniImageB64.value = comma >= 0 ? url.slice(comma + 1) : url;
    omniImageName.value = file.name;
  };
  reader.readAsDataURL(file);
  (e.target as HTMLInputElement).value = '';
}

function clearOmniImage() {
  omniImageB64.value = '';
  omniImageName.value = '';
}

async function runOmniTest(mode: 'chat' | 'speech') {
  omniAbort?.abort();
  stopOmniAudio();
  const ac = new AbortController();
  omniAbort = ac;
  omniBusy.value = true;
  omniReply.value = '';
  omniHint.value = mode === 'speech' ? t('set.omni.connecting') : t('set.omni.requesting');
  try {
    await api.streamOmniTest({
      text: omniPrompt.value.trim() || t('set.omni.sample'),
      mode,
      image_b64: omniImageB64.value,
      chat_url: settings.omni.chat_url,
      realtime_host: settings.omni.realtime_host,
      api_key: settings.omni.api_key,
      model: settings.omni.model,
      llm_api_key: settings.llm.api_key,
      llm_base_url: settings.llm.base_url,
    }, (ev) => {
      if (ev.type === 'queue') {
        omniHint.value = String(ev.message || t('set.omni.queue'));
        return;
      }
      if (ev.type === 'text' && ev.delta) {
        omniReply.value += String(ev.delta);
        omniHint.value = mode === 'speech' ? t('set.omni.speaking') : t('set.omni.writing');
        return;
      }
      if (ev.type === 'audio' && ev.pcm_b64) {
        playOmniPcm(String(ev.pcm_b64), Number(ev.rate) || 24000);
        return;
      }
      if (ev.type === 'listen') {
        omniHint.value = t('set.omni.listening');
        return;
      }
      if (ev.type === 'error') {
        omniHint.value = String(ev.message || t('set.omni.fail'));
        message.error(omniHint.value, { duration: 8000, closable: true });
        return;
      }
      if (ev.type === 'done') {
        if (ev.text && !omniReply.value) omniReply.value = String(ev.text);
        omniHint.value = ev.audio
          ? t('set.omni.doneAudio', { ms: Math.round(Number(ev.audio_bytes || 0) / 48) })
          : t('set.omni.doneSilent');
      }
    }, ac.signal);
  } catch (e) {
    if ((e as Error).name === 'AbortError') omniHint.value = t('set.omni.cancelled');
    else {
      omniHint.value = String(e);
      message.error(omniHint.value);
    }
  } finally {
    omniBusy.value = false;
    if (omniAbort === ac) omniAbort = null;
  }
}

// 背景预设色板
const BG_PRESETS = [
  { key: 'deep', value: '#141420' },
  { key: 'black', value: '#000000' },
  { key: 'warm', value: '#2a2624' },
  { key: 'dusk', value: '#241a30' },
  { key: 'forest', value: '#16241c' },
  { key: 'cream', value: '#ece7df' },
];
// 台面贴图（AI 生成的顶视圆形贴图，贴在底座台面上）
const TEX = {
  jade: '/textures/tex_jade.png',
  circuit: '/textures/tex_circuit.png',
  star: '/textures/tex_star.png',
  wood: '/textures/tex_wood.png',
  petal: '/textures/tex_petal.png',
  stage: '/textures/tex_stagefloor.png',
};
const STAGE_TEXTURES = [
  { key: 'none', value: '' },
  { key: 'jade', value: TEX.jade },
  { key: 'circuit', value: TEX.circuit },
  { key: 'star', value: TEX.star },
  { key: 'wood', value: TEX.wood },
  { key: 'petal', value: TEX.petal },
  { key: 'metal', value: TEX.stage },
];
// 预制 3D 场景（AI 生成，随前端一起发布）。stage 字段为该场景的配套底座（贴图/台面色/发光色），
// 点场景时自动应用，之后仍可手动微调。
const SCENE_PRESETS = [
  { key: 'guofeng', value: '/backgrounds/bg_guofeng.png',
    stage: { texture: TEX.jade, color: '#1d2f2a', glow: '#58e6c8' } },
  { key: 'cyber', value: '/backgrounds/bg_cyber.png',
    stage: { texture: TEX.circuit, color: '#171226', glow: '#b45ce6' } },
  { key: 'starry', value: '/backgrounds/bg_starry.png',
    stage: { texture: TEX.star, color: '#10142e', glow: '#7a8cff' } },
  { key: 'concert', value: '/backgrounds/bg_concert.png',
    stage: { texture: TEX.stage, color: '#1a1220', glow: '#e658c8' } },
  { key: 'sakura', value: '/backgrounds/bg_sakura.png',
    stage: { texture: TEX.petal, color: '#33222a', glow: '#ff9ec4' } },
  { key: 'beach', value: '/backgrounds/bg_beach.png',
    stage: { texture: TEX.wood, color: '#33261c', glow: '#ffb163' } },
  { key: 'snow', value: '/backgrounds/bg_snow.png',
    stage: { texture: TEX.wood, color: '#22282e', glow: '#9fd7ff' } },
  { key: 'forest', value: '/backgrounds/bg_forest.png',
    stage: { texture: TEX.star, color: '#14261c', glow: '#58e6a0' } },
  { key: 'lab', value: '/backgrounds/bg_lab.png',
    stage: { texture: TEX.circuit, color: '#101a24', glow: '#58c8e6' } },
  { key: 'palace', value: '/backgrounds/bg_palace.png',
    stage: { texture: TEX.jade, color: '#2a2114', glow: '#e6b358' } },
  { key: 'matsuri', value: '/backgrounds/bg_matsuri.png',
    stage: { texture: TEX.wood, color: '#2c1e16', glow: '#ffa64d' } },
  { key: 'underwater', value: '/backgrounds/bg_underwater.png',
    stage: { texture: TEX.jade, color: '#10222b', glow: '#58c8e6' } },
  { key: 'skycity', value: '/backgrounds/bg_skycity.png',
    stage: { texture: TEX.star, color: '#23283a', glow: '#ffd97a' } },
  { key: 'cafe', value: '/backgrounds/bg_cafe.png',
    stage: { texture: TEX.wood, color: '#2b211a', glow: '#e6a358' } },
  { key: 'library', value: '/backgrounds/bg_library.png',
    stage: { texture: TEX.wood, color: '#241c14', glow: '#d7a55e' } },
  { key: 'alley', value: '/backgrounds/bg_alley.png',
    stage: { texture: TEX.stage, color: '#171420', glow: '#ff5ca8' } },
  { key: 'flower', value: '/backgrounds/bg_flower.png',
    stage: { texture: TEX.petal, color: '#2e2018', glow: '#ffac6e' } },
  { key: 'space', value: '/backgrounds/bg_space.png',
    stage: { texture: TEX.circuit, color: '#0e1220', glow: '#5878e6' } },
  { key: 'bedroom', value: '/backgrounds/bg_bedroom.png',
    stage: { texture: TEX.petal, color: '#2e2226', glow: '#ffb9c9' } },
];
// 舞台底座风格
const STAGE_STYLES = [
  'classic', 'double', 'magic', 'crystal', 'tech',
  'lotus', 'orbit', 'minimal', 'vinyl', 'disco',
];
const bgFileInput = ref<HTMLInputElement | null>(null);

function pickBgColor(color: string) {
  settings.quality.background_color = color;
  settings.quality.background_image = '';
  if (settings.modules.scenes) {
    pickPlayScene({
      id: `look-color-${color}`,
      title: t('set.look.solid'),
      setting: t('set.look.solidSet'),
      conflict: '',
      opening: t('set.look.open'),
      cam: 'half',
      intent: 'look',
      background: '',
    });
    return;
  }
  settings.applyQuality();
}

function matchSceneByBg(url: string) {
  if (!url) return undefined;
  return sceneSession.cards.find((c) => c.background === url)
    || LOCAL_SCENES.find((c) => c.background === url);
}

function pickPresetLook(scene: typeof SCENE_PRESETS[number]) {
  if (settings.modules.scenes) {
    const card = matchSceneByBg(scene.value);
    if (card) {
      pickPlayScene(card);
      void chat.replayOpening(sceneExtra(card));
      return;
    }
    pickPlayScene({
      id: `look-${scene.value}`,
      title: t('set.scene.' + scene.key),
      setting: t('set.scene.' + scene.key),
      conflict: '',
      opening: t('set.look.open'),
      cam: 'half',
      intent: 'look',
      background: scene.value,
    });
    void chat.replayOpening(sceneExtra(sceneSession.current));
    return;
  }
  settings.quality.background_image = scene.value;
  // 场景与底座自动配套：换背景时同步切换台面贴图与配色（仍可手动微调）
  if (scene.stage) {
    settings.quality.stage_texture = scene.stage.texture;
    settings.quality.stage_color = scene.stage.color;
    settings.quality.stage_glow = scene.stage.glow;
  }
  settings.applyQuality();
}

function onBgImageChosen(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    message.warning(t('set.q.tooBig'));
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const url = String(reader.result);
    settings.quality.background_image = url;
    if (settings.modules.scenes) {
      pickPlayScene({
        id: 'look-custom',
        title: t('set.look.custom'),
        setting: t('set.look.customSet'),
        conflict: '',
        opening: t('set.look.open'),
        cam: 'half',
        intent: 'look',
        background: url,
      });
      return;
    }
    settings.applyQuality();
  };
  reader.readAsDataURL(file);
  (e.target as HTMLInputElement).value = '';
}

function clearBgImage() {
  settings.quality.background_image = '';
  if (settings.modules.scenes && sceneSession.current) {
    pickPlayScene({ ...sceneSession.current, background: '' });
    return;
  }
  settings.applyQuality();
}

const voiceOptions = computed(() =>
  settings.voices
    .filter((v) => !v.engine || v.engine === settings.tts.engine)
    .map((v) => ({ label: v.label, value: v.id }))
);
const tavernSeats = ['you', 'qin', 'bar', 'her', 'host'] as const;
function tavernEngineLabel(engine: string) {
  if (engine === 'qwen') return t('set.tavern.local');
  if (engine === 'mimo') return t('set.tavern.mimo');
  return t('set.tavern.online');
}
const tavernCastOptions = computed(() => {
  const lang = settings.locale.ui;
  const rows = settings.voices.filter((v) => (
    (v.engine === 'qwen' || v.engine === 'edge' || v.engine === 'mimo')
    && (!v.lang || v.lang === lang)
  ));
  return [
    { label: t('set.tavern.auto'), value: '' },
    ...rows.map((v) => ({
      label: `${tavernEngineLabel(v.engine || '')} · ${v.label}`,
      value: `${v.engine}:${v.id}`,
    })),
  ];
});
function tavernCastValue(seat: string) {
  const row = settings.tts.tavern_cast?.[settings.locale.ui]?.[seat];
  return row?.voice ? `${row.engine}:${row.voice}` : '';
}
function setTavernCast(seat: string, value: string) {
  const lang = settings.locale.ui;
  const book = { ...(settings.tts.tavern_cast || {}) };
  const page = { ...(book[lang] || {}) };
  if (!value) delete page[seat];
  else {
    const cut = value.indexOf(':');
    page[seat] = { engine: value.slice(0, cut), voice: value.slice(cut + 1) };
  }
  book[lang] = page;
  settings.tts.tavern_cast = book;
}
const ttsEngineOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.tts.mimoEngine'), value: 'mimo' },
    { label: t('set.tts.volcEngine'), value: 'volc' },
    { label: t('set.tts.cosyEngine'), value: 'cosy' },
    { label: t('set.tts.openaiEngine'), value: 'openai' },
    { label: t('set.tts.elevenEngine'), value: 'eleven' },
    { label: t('set.tts.geminiEngine'), value: 'gemini' },
    { label: t('set.tts.qwen'), value: 'qwen' },
    { label: 'TeraTTSv2 · Русский (offline)', value: 'tera' },
    { label: t('set.tts.edge'), value: 'edge' },
    { label: t('set.tts.browser'), value: 'browser' },
    { label: t('set.tts.off'), value: 'off' },
  ];
});
const qwenSizeOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.tts.s06'), value: '0.6b' },
    { label: t('set.tts.s17'), value: '1.7b' },
  ];
});
const qwenStyleOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.style.off'), value: 'off' },
    { label: t('set.style.yujie'), value: 'yujie' },
    { label: t('set.style.husky'), value: 'husky' },
    { label: t('set.style.flirt'), value: 'flirt' },
    { label: t('set.style.custom'), value: 'custom' },
  ];
});
const duplexCmdOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.duplex.interrupt_or_queue'), value: 'interrupt_or_queue' },
    { label: t('set.duplex.interrupt'), value: 'interrupt' },
    { label: t('set.duplex.queue'), value: 'queue' },
    { label: t('set.duplex.conditional_queue'), value: 'conditional_queue' },
    { label: t('set.duplex.conditional_interrupt'), value: 'conditional_interrupt' },
  ];
});
const asrEngineOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.asr.ali'), value: 'ali' },
    { label: t('set.asr.volc'), value: 'volc' },
    { label: t('set.asr.openai'), value: 'openai' },
    { label: t('set.asr.eleven'), value: 'eleven' },
    { label: t('set.asr.gemini'), value: 'gemini' },
    { label: t('set.asr.browser'), value: 'browser' },
    { label: settings.locale.reply === 'ru' ? 'GigaAM-v3 · Русский (offline)' : t('set.asr.sense'), value: 'sensevoice' },
  ];
});
const embedderOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.embed.auto'), value: 'auto' },
    { label: t('set.embed.local'), value: 'local' },
    { label: t('set.embed.doubao'), value: 'doubao' },
    { label: t('set.embed.qwen'), value: 'qwen' },
    { label: t('set.embed.openai'), value: 'openai' },
    { label: t('set.embed.gemini'), value: 'gemini' },
  ];
});
const hwHint = computed(() => {
  settings.locale.ui;
  const h = settings.hardware as {
    auto?: boolean; tier?: string; ram_gb?: number; vram_gb?: number; reason?: string;
  };
  if (!h?.tier && !h?.reason) return '';
  const known = h.tier === 'low' || h.tier === 'mid' || h.tier === 'high';
  const tier = known ? t('set.hw.' + h.tier) : (h.tier || t('set.hw.unknown'));
  const cjk = settings.locale.ui === 'zh-CN' || settings.locale.ui === 'ja';
  const bits = [
    h.ram_gb ? t('set.hw.ram', { n: h.ram_gb }) : '',
    (h.vram_gb || 0) > 0 ? t('set.hw.vram', { n: h.vram_gb || 0 }) : t('set.hw.none'),
  ].filter(Boolean).join(cjk ? '，' : ', ');
  const mode = h.auto ? t('set.hw.auto') : t('set.hw.manual');
  const wrapped = bits ? (cjk ? `${tier}（${bits}）` : `${tier} (${bits})`) : tier;
  return t('set.hw.line', {
    tier: wrapped,
    bits: '',
    mode,
    reason: h.reason || '',
  });
});
const ttsNeedsVoice = computed(() =>
  settings.tts.engine === 'cosy' || settings.tts.engine === 'edge'
  || settings.tts.engine === 'qwen' || settings.tts.engine === 'tera' || settings.tts.engine === 'volc'
  || settings.tts.engine === 'openai' || settings.tts.engine === 'eleven'
  || settings.tts.engine === 'gemini' || settings.tts.engine === 'mimo'
);

type SpeechStatus = {
  asr: { available: boolean; installed?: boolean; ready: boolean; downloading?: boolean;
         progress?: number; message: string };
  tts: { available: boolean; ready: boolean; loading?: boolean; downloading?: boolean;
         gpu?: boolean; device?: string; size?: string; message: string;
         sizes?: Record<string, { installed: boolean; label: string; gb: string }> };
  tera: { installed: boolean; ready: boolean; downloading: boolean; gpu_runtime: boolean; gpu_downloading: boolean; loading: boolean; message: string; url: string };
};
const speechStatus = ref<SpeechStatus | null>(null);
let statusTimer: number | null = null;

async function refreshSpeechStatus() {
  try {
    speechStatus.value = await api.getSpeechStatus(settings.locale.reply);
  } catch { /* 后端未开时忽略 */ }
}

function startStatusPoll() {
  stopStatusPoll();
  void refreshSpeechStatus();
  statusTimer = window.setInterval(() => { void refreshSpeechStatus(); }, 2000);
}
function stopStatusPoll() {
  if (statusTimer != null) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
}

const warmingAsr = ref(false);
const warmingTts = ref(false);
async function warmup(target: 'asr' | 'tts') {
  if (target === 'asr') warmingAsr.value = true;
  else warmingTts.value = true;
  try {
    if (target === 'tts') await settings.save();
    const r = await api.warmupSpeech(
      target,
      target === 'tts' ? settings.tts.qwen_size : undefined,
    );
    message.info(r.message || t('set.warmup.started'));
    startStatusPoll();
    await refreshSpeechStatus();
  } catch (e) {
    message.error(String(e));
  } finally {
    warmingAsr.value = false;
    warmingTts.value = false;
  }
}

watch(() => props.show, (v) => {
  if (v) {
    startStatusPoll();
    void loadTrayPrefs();
  } else stopStatusPoll();
});
onUnmounted(() => {
  stopStatusPoll();
  omniAbort?.abort();
  stopOmniAudio();
});

const savingSettings = ref(false);
async function save() {
  if (savingSettings.value) return;
  savingSettings.value = true;
  try {
    await settings.save();
    message.success(t('set.saved'));
    emit('update:show', false);
  } catch (error) {
    message.error(String(error));
  } finally {
    savingSettings.value = false;
  }
}

function onPhysics(v: boolean) {
  settings.quality.physics = !!v;
  settings.applyQuality();
  void settings.save().catch(() => {});
}

async function onLive2D(v: boolean) {
  settings.quality.live2d_enabled = !!v;
  if (!v && characters.modelInfo?.format === 'live2d') {
    characters.disableLive2D();
  }
  await settings.save();
  if (v && !characters.modelInfo && characters.currentId) {
    await characters.switchTo(characters.currentId);
  }
}

async function saveEmbedder(v: string) {
  const prev = settings.memory.embedder;
  settings.memory.embedder = (v === 'local' || v === 'doubao' || v === 'qwen' || v === 'openai' || v === 'gemini' ? v : 'auto');
  try {
    await settings.save();
    message.success(t('set.embed.switched'));
  } catch (e) {
    settings.memory.embedder = prev;
    message.error(String(e));
  }
}

async function openWatchLab() {
  try {
    await api.glanceLabOpen();
  } catch (e) {
    message.error(String(e));
  }
}

async function toggleMod(key: keyof typeof settings.modules, on: boolean) {
  const prev = settings.modules[key];
  settings.modules[key] = on;
  try {
    await settings.save();
    if (key === 'tarot' && !on) {
      const { onModuleOff } = await import('../tarot');
      await onModuleOff();
    }
    if (key === 'tavern' && !on) {
      const { closeTavern } = await import('../tavern/session');
      closeTavern();
    }
    if (key === 'codewatch' && !on) {
      const { onModuleOff } = await import('../codewatch');
      onModuleOff();
    }
    if (key === 'harness' && !on) {
      await api.harnessRelease();
    }
    if (key === 'glance') {
      await api.harnessRelease();
      if (!on) await api.glancePowerSet(false, characters.currentId || 0);
    }
    if (key !== 'scenes') return;
    if (on && characters.currentId) {
      await restoreOrRotateScene({
        characterId: characters.currentId,
        lastChatAt: chat.lastUserChatAt(),
      });
    } else if (!on) {
      const { clearSceneStage } = await import('../scenes/session');
      clearSceneStage();
      settings.applyQuality();
    }
  } catch (e) {
    settings.modules[key] = prev;
    message.error(String(e));
  }
}
</script>

<template>
  <StagePanel :show="show" :title="t('settings.title')" size="large" fixed-body
              @update:show="(v: boolean) => emit('update:show', v)">
    <div class="settings-layout">
      <nav class="settings-index" :aria-label="t('settings.title')">
        <button v-for="item in sections" :key="item.id" type="button"
                :aria-current="section === item.id ? 'true' : undefined"
                @click="section = item.id">{{ t(item.label) }}</button>
      </nav>
      <div :key="section" class="settings-content">
        <h3>{{ t(sections.find((item) => item.id === section)?.label || 'settings.title') }}</h3>
        <template v-if="section === 'lang'">
          <div class="form">
            <PanelGroup tone="teal" :title="t('lang.ui')">
              <NativeSelect :aria-label="t('lang.ui')" :value="settings.locale.ui" :options="langOptions"
                        @update:value="(v: 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru') => settings.setLocale({ ui: v })" />
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.reply')">
              <p class="hint">{{ t('lang.hint') }}</p>
              <label>{{ t('lang.reply') }}</label>
              <NativeSelect :value="settings.locale.reply" :options="langOptions"
                        @update:value="(v: 'zh-CN' | 'en' | 'ja' | 'ko' | 'ru') => settings.setLocale({ reply: v })" />
              <label>{{ t('lang.mode') }}</label>
              <NativeSelect :value="settings.locale.reply_mode" :options="replyModeOptions"
                        @update:value="(v: 'fixed' | 'follow') => settings.setLocale({ reply_mode: v })" />
              <p v-if="!featureOn('tarot', settings.locale.reply)" class="hint">{{ t('mod.missing') }} · {{ t('mod.tarot') }}</p>
              <p v-if="!featureOn('scenes', settings.locale.reply)" class="hint">{{ t('mod.missing') }} · {{ t('mod.scenes') }}</p>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'desktop'">
          <div class="form">
            <PanelGroup :title="t('set.group.tray')">
              <p class="hint">{{ t('set.tray.hint') }}</p>
              <div class="preference">
                <div>
                  <strong>{{ t('set.tray.minimize') }}</strong>
                  <p class="hint">{{ t('set.tray.minimizeHint') }}</p>
                </div>
                <n-switch :aria-label="t('set.tray.minimize')" :value="trayMinimize" @update:value="(v: boolean) => saveTray({ minimize: v })" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('set.tray.close') }}</strong>
                  <p class="hint">{{ t('set.tray.closeHint') }}</p>
                </div>
                <n-switch :aria-label="t('set.tray.close')" :value="trayClose" @update:value="(v: boolean) => saveTray({ close: v })" />
              </div>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'content'">
          <div class="form">
            <PanelGroup :title="t('set.pack.dir')">
              <p class="hint">{{ t('set.pack.hint') }}</p>
              <div class="content-row">
                <n-input v-model:value="contentPath" :placeholder="t('set.pack.ph')" />
                <n-button v-if="canPickFolder" @click="pickContentFolder">{{ t('set.pack.browse') }}</n-button>
              </div>
              <p class="hint">{{ contentFound }}</p>
              <p v-if="contentHint" class="hint">{{ contentHint }}</p>
              <n-button type="primary" :loading="contentBusy" :disabled="!contentPath.trim()"
                        @click="saveContentPath">{{ t('set.pack.save') }}</n-button>
              <p class="hint">{{ t('set.pack.restart') }}</p>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'modules'">
          <div class="form">
            <PanelGroup tone="rose" :title="t('set.group.companion')">
              <div class="preference">
                <div>
                  <strong>{{ t('mod.memory') }}</strong>
                  <p class="hint">{{ t('set.mod.memory') }}</p>
                </div>
                <n-switch :aria-label="t('mod.memory')" :value="settings.modules.memory" @update:value="(v: boolean) => toggleMod('memory', v)" />
              </div>
              <details v-if="settings.modules.memory" class="inline-options">
                <summary>{{ t('set.mod.embed') }}</summary>
                <div class="inline-options-body">
                  <NativeSelect :aria-label="t('set.mod.embed')" :value="settings.memory.embedder"
                                :options="embedderOptions" @update:value="saveEmbedder" />
                  <p class="hint">{{ t('set.mod.embedHint') }}</p>
                </div>
              </details>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.scenes') }}</strong>
                  <p class="hint">{{ t('set.mod.scenes') }}</p>
                </div>
                <n-switch :aria-label="t('mod.scenes')" :value="settings.modules.scenes" @update:value="(v: boolean) => toggleMod('scenes', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.rewrite') }}</strong>
                  <p class="hint">{{ t('set.mod.rewrite') }}</p>
                </div>
                <n-switch :aria-label="t('mod.rewrite')" :value="settings.modules.rewrite" @update:value="(v: boolean) => toggleMod('rewrite', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.touch') }}</strong>
                  <p class="hint">{{ t('set.mod.touch') }}</p>
                </div>
                <n-switch :aria-label="t('mod.touch')" :value="settings.modules.touch" @update:value="(v: boolean) => toggleMod('touch', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.keepsake') }}</strong>
                  <p class="hint">{{ t('set.mod.keepsake') }}</p>
                </div>
                <n-switch :aria-label="t('mod.keepsake')" :value="settings.modules.keepsake" @update:value="(v: boolean) => toggleMod('keepsake', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.journey') }}</strong>
                  <p class="hint">{{ t('set.mod.journey') }}</p>
                </div>
                <n-switch :aria-label="t('mod.journey')" :value="settings.modules.journey" @update:value="(v: boolean) => toggleMod('journey', v)" />
              </div>
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.games')">
              <div class="preference">
                <div>
                  <strong>{{ t('mod.tarot') }}</strong>
                  <p class="hint">{{ t('set.mod.tarot') }}</p>
                </div>
                <n-switch :aria-label="t('mod.tarot')" :value="settings.modules.tarot" @update:value="(v: boolean) => toggleMod('tarot', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.tavern') }}</strong>
                  <p class="hint">{{ t('set.mod.tavern') }}</p>
                </div>
                <n-switch :aria-label="t('mod.tavern')" :value="settings.modules.tavern" @update:value="(v: boolean) => toggleMod('tavern', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.play') }}</strong>
                  <p class="hint">{{ t('set.mod.play') }}</p>
                </div>
                <n-switch :aria-label="t('mod.play')" :value="settings.modules.play" @update:value="(v: boolean) => toggleMod('play', v)" />
              </div>
            </PanelGroup>
            <PanelGroup tone="teal" :title="t('set.group.tools')" collapsible>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.codewatch') }}</strong>
                  <p class="hint">{{ t('set.mod.code') }}</p>
                </div>
                <n-switch :aria-label="t('mod.codewatch')" :value="settings.modules.codewatch" @update:value="(v: boolean) => toggleMod('codewatch', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.harness') }}</strong>
                  <p class="hint">{{ t('set.mod.harness') }}</p>
                </div>
                <n-switch :aria-label="t('mod.harness')" :value="settings.modules.harness" @update:value="(v: boolean) => toggleMod('harness', v)" />
              </div>
              <div class="preference">
                <div>
                  <strong>{{ t('mod.glance') }}</strong>
                  <p class="hint">{{ t('set.mod.glance') }}</p>
                </div>
                <n-switch :aria-label="t('mod.glance')" :value="settings.modules.glance" @update:value="(v: boolean) => toggleMod('glance', v)" />
              </div>
              <template v-if="settings.modules.glance">
                <label>{{ t('set.mod.alongGenerator') }}</label>
                <NativeSelect v-model:value="settings.vision.generator" :options="alongGeneratorOptions"
                          @update:value="() => settings.save()" />
                <p class="hint">{{ t('set.mod.alongGeneratorHint') }}</p>
              </template>
              <n-button size="small" @click="openWatchLab">{{ t('set.mod.glanceLab') }}</n-button>
              <p class="hint">{{ t('set.mod.glanceLabHint') }}</p>
            </PanelGroup>
            <PanelGroup tone="blue" :title="t('set.group.vision')" collapsible>
              <label>{{ t('set.vision.label') }}</label>
              <NativeSelect v-model:value="settings.vision.provider" :options="visionOptions" />
              <template v-if="settings.vision.provider === 'openai'">
                <label>{{ t('set.vision.url') }}</label>
                <n-input v-model:value="settings.vision.base_url"
                         placeholder="https://api.openai.com/v1" />
                <label>API Key</label>
                <n-input v-model:value="settings.vision.api_key" type="password"
                         show-password-on="click" :placeholder="t('set.vision.keyPh')" />
                <label>{{ t('set.vision.model') }}</label>
                <n-input v-model:value="settings.vision.model"
                         placeholder="gpt-4o / qwen-vl-max / gemini-2.5-flash" />
              </template>
              <p class="hint">{{ t('set.vision.hint') }}</p>
            </PanelGroup>
            <details class="settings-note">
              <summary>{{ t('set.group.moduleHelp') }}</summary>
              <p class="hint">{{ t('set.mod.off') }}</p>
              <p v-if="hwHint" class="hint">{{ hwHint }}</p>
            </details>
          </div>
        </template>
        <template v-if="section === 'ai'">
          <div class="form">
            <PanelGroup tone="teal" :title="t('set.group.connection')">
              <label>{{ t('set.llm.label') }}</label>
              <NativeSelect :value="settings.llmPreset" :options="llmPresetOptions"
                        @update:value="(value) => settings.selectLlmPreset(String(value))" />
              <label>{{ t('set.llm.url') }}</label>
              <n-input v-model:value="settings.llm.base_url"
                       placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
              <label>API Key</label>
              <n-input v-model:value="settings.llm.api_key" type="password"
                       show-password-on="click" :placeholder="t('set.llm.keyPh')" />
              <label>{{ t('set.llm.model') }}</label>
              <n-input v-model:value="settings.llm.model"
                       placeholder="qwen-plus / deepseek-chat / ep-…" />
              <p v-if="settings.llmPreset === 'mimo' || settings.llmPreset === 'mimo_pro'" class="hint">{{ t('set.llm.mimoHint') }}</p>
              <p v-if="showEndpointHint" class="hint warn">{{ t('set.llm.endpoint') }}</p>
              <div>
                <n-button size="small" type="primary" secondary
                          :loading="testing" @click="testLlm">{{ t('settings.test') }}</n-button>
              </div>
              <p v-if="settings.llm_env || settings.llm_local" class="hint">{{ t('set.llm.env') }}</p>
              <p class="hint">{{ t('set.llm.hint') }}</p>
              <p class="hint">{{ t('set.llm.nokey') }}</p>
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.generation')" collapsible>
              <label>{{ t('set.llm.think') }}</label>
              <NativeSelect v-model:value="settings.llm.thinking" :options="thinkingOptions" />
              <p class="hint">{{ t('set.llm.thinkHint') }}</p>
              <label>{{ t('set.llm.temp', { n: settings.llm.temperature.toFixed(2) }) }}</label>
              <n-slider v-model:value="settings.llm.temperature"
                        :min="0" :max="1.5" :step="0.05" />
              <label>{{ t('set.llm.topp', { n: settings.llm.top_p.toFixed(2) }) }}</label>
              <n-slider v-model:value="settings.llm.top_p"
                        :min="0.1" :max="1" :step="0.05" />
              <label>{{ t('set.llm.max') }}</label>
              <n-input-number v-model:value="settings.llm.max_tokens"
                              :min="0" :max="32768" :step="256" style="width: 200px" />
            </PanelGroup>
            <PanelGroup tone="blue" :title="t('set.group.harness')" collapsible>
              <label>{{ t('set.llm.harness') }}</label>
              <n-input v-model:value="settings.llm.harness_model"
                       :placeholder="t('set.llm.harnessPh')" />
              <label>{{ t('set.llm.harnessUrl') }}</label>
              <n-input v-model:value="settings.llm.harness_base_url"
                       :placeholder="t('set.llm.harnessUrlPh')" />
              <label>{{ t('set.llm.harnessKey') }}</label>
              <n-input v-model:value="settings.llm.harness_api_key" type="password"
                       show-password-on="click" :placeholder="t('set.llm.harnessKeyPh')" />
              <p class="hint">{{ t('set.llm.harnessHint') }}</p>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'omni'">
          <div class="form">
            <PanelGroup tone="teal" :title="t('set.group.connection')">
              <p class="hint">{{ t('set.omni.hint') }}</p>
              <label>{{ t('set.omni.chat') }}</label>
              <n-input v-model:value="settings.omni.chat_url"
                       placeholder="https://api.modelbest.cn/v1" />
              <label>{{ t('set.omni.realtime') }}</label>
              <n-input v-model:value="settings.omni.realtime_host"
                       placeholder="https://minicpmo45.modelbest.cn" />
              <label>{{ t('set.omni.model') }}</label>
              <n-input v-model:value="settings.omni.model" placeholder="MiniCPM-O-4.5-9B" />
              <label>{{ t('set.omni.key') }}</label>
              <n-input v-model:value="settings.omni.api_key" type="password"
                       show-password-on="click"
                       :placeholder="t('set.omni.keyPh')" />
              <p v-if="settings.omni_env" class="hint">{{ t('set.omni.env') }}</p>
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.test')">
              <label>{{ t('set.omni.sentence') }}</label>
              <n-input v-model:value="omniPrompt" type="textarea"
                       :autosize="{ minRows: 2, maxRows: 4 }"
                       :placeholder="t('set.omni.sample')" />
              <div class="bg-image-row">
                <n-button size="small" @click="pickOmniImage">
                  {{ omniImageName || t('set.omni.image') }}
                </n-button>
                <n-button v-if="omniImageName" size="small" @click="clearOmniImage">{{ t('set.omni.clearImage') }}</n-button>
                <input ref="omniImg" type="file" accept="image/*" hidden @change="onOmniImage" />
              </div>
              <div class="omni-actions">
                <n-button size="small" type="primary" secondary
                          :loading="omniBusy" :disabled="omniBusy"
                          @click="runOmniTest('chat')">{{ t('settings.testText') }}</n-button>
                <n-button size="small" type="primary"
                          :loading="omniBusy" :disabled="omniBusy"
                          @click="runOmniTest('speech')">{{ t('settings.testSpeech') }}</n-button>
                <n-button v-if="omniBusy" size="small" @click="omniAbort?.abort()">{{ t('settings.cancel') }}</n-button>
              </div>
              <p v-if="omniHint" class="hint">{{ omniHint }}</p>
              <p v-if="omniReply" class="omni-reply">{{ omniReply }}</p>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'voice'">
          <div class="form">
            <PanelGroup tone="teal" :title="t('set.asr.title')">
              <label>{{ t('set.asr.engine') }}</label>
              <NativeSelect v-model:value="settings.stt.engine" :options="asrEngineOptions" />
              <p class="hint">{{ t('set.asr.hint') }}</p>
              <p v-if="settings.stt.engine === 'ali' || settings.stt.engine === 'volc'" class="hint">{{ t('set.asr.cloud') }}</p>
              <p v-if="settings.stt.engine === 'openai' || settings.stt.engine === 'eleven' || settings.stt.engine === 'gemini'" class="hint">{{ t('set.asr.cloudIntl') }}</p>
              <div v-if="settings.stt.engine === 'sensevoice'" class="speech-status">
                <p class="hint">{{ speechStatus?.asr.message || t('set.asr.status') }}</p>
                <n-button size="small" :loading="warmingAsr || !!speechStatus?.asr.downloading"
                          @click="warmup('asr')">{{ t('set.asr.warmup') }}</n-button>
              </div>
            </PanelGroup>
            <PanelGroup tone="rose" :title="t('set.tts.title')">
              <label>{{ t('set.tts.engine') }}</label>
              <NativeSelect :value="settings.tts.engine" :options="ttsEngineOptions"
                            @update:value="(value) => settings.selectTtsEngine(value as typeof settings.tts.engine)" />
              <div v-if="settings.tts.engine === 'tera'" class="speech-status">
                <p class="hint">{{ speechStatus?.tera.message || (speechStatus?.tera.installed ? 'TeraTTSv2 ✓' : t('set.tera.missing')) }}</p>
                <n-button size="small" :loading="!!speechStatus?.tera.downloading"
                          @click="async () => { await api.downloadTera(); await refreshSpeechStatus(); }">{{ t('set.tera.download') }}</n-button>
                <n-button size="small" :loading="!!speechStatus?.tera.gpu_downloading"
                          @click="async () => { await api.downloadTeraGpu(); await refreshSpeechStatus(); }">{{ t('set.tera.gpu') }} {{ speechStatus?.tera.gpu_runtime ? '✓' : '' }}</n-button>
                <n-button size="small" :loading="!!speechStatus?.tera.loading"
                          :disabled="!speechStatus?.tera.installed || !speechStatus?.tera.gpu_runtime"
                          @click="async () => { await api.warmupTera(); await refreshSpeechStatus(); }">{{ t('set.tera.warmup') }}</n-button>
                <a href="https://huggingface.co/TeraSpace/TeraTTSv2" target="_blank" rel="noopener noreferrer">TeraTTSv2 · Hugging Face</a>
                <p class="hint">{{ t('set.tera.hint') }}</p>
              </div>
              <template v-if="settings.tts.engine === 'qwen'">
                <label>{{ t('set.tts.size') }}</label>
                <NativeSelect v-model:value="settings.tts.qwen_size" :options="qwenSizeOptions" />
                <p class="hint">
                  {{ t('set.tts.sizeLead') }}
                  0.6B {{ speechStatus?.tts.sizes?.['0.6b']?.installed ? t('set.tts.local') : t('set.tts.missing') }}
                  · 1.7B {{ speechStatus?.tts.sizes?.['1.7b']?.installed ? t('set.tts.local') : t('set.tts.missingBig') }}
                  <template v-if="speechStatus?.tts.size">
                    · {{ t('set.tts.ram', { size: speechStatus.tts.size === '1.7b' ? '1.7B' : '0.6B' }) }}
                  </template>
                </p>
                <label>{{ t('set.tts.style') }}</label>
                <NativeSelect v-model:value="settings.tts.qwen_style" :options="qwenStyleOptions" />
                <n-input v-if="settings.tts.qwen_style === 'custom'"
                         v-model:value="settings.tts.qwen_instruct" type="textarea"
                         :autosize="{ minRows: 2, maxRows: 4 }"
                         :placeholder="t('set.tts.stylePh')" />
                <p class="hint">{{ t('set.tts.styleHint') }}</p>
              </template>
              <label>{{ t('set.tts.voice') }}</label>
              <NativeSelect v-model:value="settings.tts.voice" :options="voiceOptions" filterable
                        :fallback-option="false" :placeholder="t('set.tts.voicePh')"
                        :disabled="!ttsNeedsVoice" />
              <p class="hint">{{ t('set.tts.voiceHint') }}</p>
              <p v-if="settings.tts.engine === 'cosy'" class="hint">{{ t('set.tts.cosy') }}</p>
              <p v-if="settings.tts.engine === 'volc'" class="hint">{{ t('set.tts.volc') }}</p>
              <p v-if="settings.tts.engine === 'openai'" class="hint">{{ t('set.tts.openai') }}</p>
              <p v-if="settings.tts.engine === 'eleven'" class="hint">{{ t('set.tts.eleven') }}</p>
              <p v-if="settings.tts.engine === 'gemini'" class="hint">{{ t('set.tts.gemini') }}</p>
              <p v-if="settings.tts.engine === 'mimo'" class="hint">{{ t('set.tts.mimo') }}</p>
              <div v-if="settings.tts.engine === 'qwen'" class="speech-status">
                <p class="hint">
                  {{ speechStatus?.tts.message || t('set.asr.status') }}
                  <template v-if="speechStatus?.tts.gpu"> · {{ t('set.tts.gpu') }}</template>
                </p>
                <n-button size="small"
                          :loading="warmingTts || !!speechStatus?.tts.loading || !!speechStatus?.tts.downloading"
                          @click="warmup('tts')">{{ t('set.tts.load') }}</n-button>
              </div>
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.voiceFlow')" collapsible>
              <label>{{ t('set.tts.duplex') }}</label>
              <NativeSelect v-model:value="settings.tts.duplex_cmd" :options="duplexCmdOptions" />
              <label>{{ t('set.tts.remain', { n: Number(settings.tts.duplex_remain_sec).toFixed(1) }) }}</label>
              <n-slider v-model:value="settings.tts.duplex_remain_sec"
                        :min="1" :max="8" :step="0.5" />
              <label>{{ t('set.tts.delayed', { n: settings.tts.duplex_delayed_sec }) }}</label>
              <n-slider v-model:value="settings.tts.duplex_delayed_sec"
                        :min="0" :max="40" :step="1" />
              <label>{{ t('set.tts.proactive', { n: settings.tts.duplex_proactive_sec }) }}</label>
              <n-slider v-model:value="settings.tts.duplex_proactive_sec"
                        :min="0" :max="90" :step="1" />
              <label>{{ t('set.tts.goodbye', { n: settings.tts.duplex_goodbye_sec }) }}</label>
              <n-slider v-model:value="settings.tts.duplex_goodbye_sec"
                        :min="0" :max="300" :step="5" />
              <label>{{ t('set.tts.session') }}</label>
              <n-slider v-model:value="settings.tts.duplex_session_max_min"
                        :min="0" :max="60" :step="1" />
              <div class="preference">
                <div>
                  <strong>{{ t('set.tts.ingress') }}</strong>
                  <p class="hint">{{ t('set.tts.duplexHint') }}</p>
                </div>
                <n-switch :aria-label="t('set.tts.ingress')" v-model:value="settings.tts.duplex_ingress" />
              </div>
            </PanelGroup>
            <PanelGroup tone="amber" :title="t('set.tavern.cast')" collapsible>
              <p class="hint">{{ t('set.tavern.castHint') }}</p>
              <template v-for="seat in tavernSeats" :key="seat">
                <label>{{ t('set.tavern.' + seat) }}</label>
                <NativeSelect :value="tavernCastValue(seat)" :options="tavernCastOptions" filterable
                          @update:value="(value) => setTavernCast(seat, String(value || ''))" />
              </template>
            </PanelGroup>
            <PanelGroup tone="blue" :title="t('set.persona.title')" collapsible>
              <p class="hint">{{ t('set.persona.hint') }}</p>
              <div class="switch-row">
                <n-switch :value="settings.user_persona.enabled"
                          @update:value="(v: boolean) => { settings.user_persona.enabled = v; }" />
                <span>{{ t('set.persona.enabled') }}</span>
              </div>
              <template v-if="settings.user_persona.enabled">
                <label>{{ t('set.persona.name') }}</label>
                <n-input v-model:value="settings.user_persona.name"
                         :placeholder="t('set.persona.namePh')" />
                <label>{{ t('set.persona.desc') }}</label>
                <n-input v-model:value="settings.user_persona.description" type="textarea"
                         :autosize="{ minRows: 3, maxRows: 8 }"
                         :placeholder="t('set.persona.descPh')" />
              </template>
            </PanelGroup>
            <p v-if="hwHint" class="hint">{{ hwHint }}</p>
          </div>
        </template>
        <template v-if="section === 'download'">
          <div class="form">
            <PanelGroup tone="teal" :title="t('set.group.version')">
              <p class="version-value">{{ CURRENT_VERSION === 'dev' ? t('set.group.devVersion') : CURRENT_VERSION }}</p>
            </PanelGroup>
            <PanelGroup tone="blue" :title="t('set.group.downloadAccess')">
              <label>{{ t('set.dl.token') }}</label>
              <n-input v-model:value="settings.download.aplaybox_token" type="password"
                       show-password-on="click" :placeholder="t('set.dl.ph')" />
              <p class="hint">{{ t('set.dl.hint') }}</p>
            </PanelGroup>
          </div>
        </template>
        <template v-if="section === 'quality'">
          <div class="form">
            <PanelGroup tone="rose" :title="t('set.group.background')">
              <label>{{ t('set.q.presets') }}</label>
              <p v-if="settings.modules.scenes" class="hint">{{ t('set.q.sceneOn') }}</p>
              <div class="scene-presets">
                <button v-for="s in SCENE_PRESETS" :key="s.value" type="button" class="scene-card"
                      :aria-pressed="settings.modules.scenes
                        ? sceneSession.current?.background === s.value
                        : settings.quality.background_image === s.value"
                     :class="{ active: settings.modules.scenes
                       ? sceneSession.current?.background === s.value
                       : settings.quality.background_image === s.value }"
                      :title="t('set.scene.' + s.key)" @click="pickPresetLook(s)">
                  <img :src="s.value" alt="" loading="lazy" />
                  <span>{{ t('set.scene.' + s.key) }}</span>
                </button>
              </div>
              <label>{{ t('set.q.solid') }}</label>
              <div class="bg-presets">
                <button v-for="p in BG_PRESETS" :key="p.value" type="button" class="bg-swatch"
                     :aria-pressed="!settings.quality.background_image && settings.quality.background_color === p.value"
                     :aria-label="t('set.bg.' + p.key)"
                     :class="{ active: !settings.quality.background_image
                                 && settings.quality.background_color === p.value }"
                     :style="{ background: p.value }" :title="t('set.bg.' + p.key)"
                     @click="pickBgColor(p.value)" />
                <n-color-picker
                  :value="settings.quality.background_color" :show-alpha="false"
                  :modes="['hex']" class="bg-picker"
                  @update:value="pickBgColor" />
              </div>
              <div class="bg-image-row">
                <n-button size="small" @click="bgFileInput?.click()">
                  {{ settings.quality.background_image ? t('set.q.changeImage') : t('set.q.useImage') }}
                </n-button>
                <n-button v-if="settings.quality.background_image" size="small" quaternary
                          @click="clearBgImage">{{ t('set.q.clearImage') }}</n-button>
                <input ref="bgFileInput" type="file" accept="image/*" hidden
                       @change="onBgImageChosen" />
              </div>
            </PanelGroup>
            <PanelGroup tone="teal" :title="t('set.group.render')">
              <div class="switch-row">
                <span>{{ t('set.q.physics') }}</span>
                <n-switch v-model:value="settings.quality.physics"
                          @update:value="onPhysics" />
              </div>
              <p class="hint">{{ t('set.q.physicsHint') }}</p>
              <div v-if="characters.modelInfo?.supportsPbr" class="switch-row">
                <span>{{ t('set.q.pbr') }}</span>
                <n-switch v-model:value="settings.quality.pbr" @update:value="settings.applyQuality()" />
              </div>
              <div class="switch-row">
                <span>{{ t('set.q.live2d') }}</span>
                <n-switch v-model:value="settings.quality.live2d_enabled"
                          @update:value="onLive2D" />
              </div>
              <p class="hint">{{ t('set.q.live2dHint') }}</p>
              <label>{{ t('set.q.dpr') }}</label>
              <n-slider v-model:value="settings.quality.pixel_ratio_cap"
                        :min="1" :max="3" :step="0.5" />
            </PanelGroup>
            <PanelGroup tone="amber" :title="t('set.group.lighting')">
              <label>{{ t('set.q.light') }}</label>
              <n-slider v-model:value="settings.quality.light_level"
                        :min="0.5" :max="1.5" :step="0.05"
                        :format-tooltip="(v: number) => v.toFixed(2) + '×'"
                        @update:value="settings.applyQuality()" />
            </PanelGroup>
            <PanelGroup tone="amber" :title="t('set.group.lightAdvanced')" collapsible>
              <LightingControls />
            </PanelGroup>
            <PanelGroup tone="blue" :title="t('set.group.audio')">
              <label>{{ t('set.q.bgm') }}</label>
              <n-slider v-model:value="settings.quality.bgm_volume"
                        :min="0" :max="1" :step="0.05"
                        :format-tooltip="(v: number) => Math.round(v * 100) + '%'"
                        @update:value="settings.applyQuality()" />
            </PanelGroup>
            <PanelGroup tone="violet" :title="t('set.group.floor')">
              <div class="switch-row">
                <span>{{ t('set.q.stage') }}</span>
                <n-switch :aria-label="t('set.q.stage')" v-model:value="settings.quality.stage_show"
                          @update:value="settings.applyQuality()" />
              </div>
              <template v-if="settings.quality.stage_show">
                <div class="style-chips">
                  <n-button v-for="style in STAGE_STYLES" :key="style" size="tiny" round
                            :type="settings.quality.stage_style === style ? 'primary' : 'default'"
                            :secondary="settings.quality.stage_style !== style"
                            @click="settings.quality.stage_style = style; settings.applyQuality()">
                    {{ t('set.stage.' + style) }}
                  </n-button>
                </div>
                <label>{{ t('set.q.tex') }}</label>
                <div class="tex-presets">
                  <button v-for="tex in STAGE_TEXTURES" :key="tex.key" type="button" class="tex-card"
                       :aria-pressed="settings.quality.stage_texture === tex.value"
                       :class="{ active: settings.quality.stage_texture === tex.value }"
                       :title="t('set.tex.' + tex.key)"
                       @click="settings.quality.stage_texture = tex.value; settings.applyQuality()">
                    <img v-if="tex.value" :src="tex.value" alt="" loading="lazy" />
                    <div v-else class="tex-none"
                         :style="{ background: settings.quality.stage_color }" />
                    <span>{{ t('set.tex.' + tex.key) }}</span>
                  </button>
                </div>
                <div class="stage-colors">
                  <div class="stage-color-item">
                    <span>{{ t('set.q.stageColor') }}</span>
                    <n-color-picker v-model:value="settings.quality.stage_color"
                                    :show-alpha="false" :modes="['hex']" class="bg-picker"
                                    @update:value="settings.applyQuality()" />
                  </div>
                  <div class="stage-color-item">
                    <span>{{ t('set.q.glow') }}</span>
                    <n-color-picker v-model:value="settings.quality.stage_glow"
                                    :show-alpha="false" :modes="['hex']" class="bg-picker"
                                    @update:value="settings.applyQuality()" />
                  </div>
                </div>
                <label>{{ t('set.q.opacity') }}</label>
                <n-slider v-model:value="settings.quality.stage_opacity"
                          :min="0.15" :max="1" :step="0.05"
                          :format-tooltip="(v: number) => Math.round(v * 100) + '%'"
                          @update:value="settings.applyQuality()" />
              </template>
              <p class="hint">{{ t('set.q.hint') }}</p>
            </PanelGroup>
          </div>
        </template>
      </div>
    </div>
    <template #footer>
      <div style="display:flex;justify-content:flex-end;gap:10px;width:100%">
        <n-button @click="emit('update:show', false)">{{ t('settings.cancel') }}</n-button>
        <n-button type="primary" :loading="savingSettings" @click="save">{{ t('settings.save') }}</n-button>
      </div>
    </template>
  </StagePanel>
</template>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: minmax(110px, 26%) minmax(0, 1fr);
  height: 100%;
}
.settings-index {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-self: stretch;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  padding: 16px 10px;
  border-right: 1px solid var(--panel-line);
  background: #1c172338;
}
.settings-index button {
  padding: 9px 11px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--panel-muted);
  font: inherit;
  font-size: 13px;
  text-align: start;
  cursor: pointer;
}
.settings-index button:hover { background: var(--panel-card); color: var(--panel-ink); }
.settings-index button[aria-current] {
  border-color: #ebc5a135;
  background: #ebc5a118;
  color: #f6d8bd;
}
.settings-index button:focus-visible { outline: 2px solid var(--panel-accent); outline-offset: -2px; }
.settings-content {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: #795e74 transparent;
  padding: var(--panel-pad);
}
.settings-content h3 { margin: 0 0 16px; font-size: 18px; line-height: 1.35; }
.settings-note { padding: 8px 2px; }
.settings-note summary, .inline-options summary {
  color: var(--panel-muted);
  font-size: 12px;
  cursor: pointer;
}
.settings-note summary:hover, .inline-options summary:hover { color: var(--panel-accent); }
.settings-note .hint + .hint { margin-top: 6px; }
.preference {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  padding-block: 8px;
}
.preference + .preference, .inline-options + .preference { border-top: 1px solid var(--panel-line); }
.preference strong { font-size: 13px; font-weight: 600; }
.preference .hint { margin-bottom: 0; }
.inline-options {
  padding: 8px 10px;
  border-left: 2px solid #ebc5a16b;
  background: #1c172338;
  border-radius: 0 8px 8px 0;
}
.inline-options-body { display: grid; gap: 6px; margin-top: 9px; }
.version-value { color: var(--panel-muted); font-variant-numeric: tabular-nums; }
@container stage-panel (max-width: 440px) {
  .settings-layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0,1fr); }
  .settings-index { flex-direction: row; padding: 8px; border-right: 0; border-bottom: 1px solid var(--panel-line); }
  .settings-index button { flex: none; white-space: nowrap; }
}

.form {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}

.form label {
  font-size: 13px;
  font-weight: 550;
  color: var(--panel-ink);
  margin-top: 4px;
}

.content-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.content-row :deep(.n-input) { flex: 1 1 140px; }

.speech-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-radius: 8px;
  background: #1c172338;
}
.speech-status .hint { flex-basis: 100%; }

.switch-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  font-size: 13px;
}

.switch-row > span {
  opacity: 0.8;
}

.hint {
  font-size: 12px;
  color: var(--panel-muted);
  line-height: 1.65;
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}

.hint.warn {
  opacity: 1;
  color: #e8b86d;
}

.omni-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.omni-reply {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  opacity: 0.9;
  white-space: pre-wrap;
}

.bg-presets {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bg-swatch {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid rgba(255, 255, 255, 0.15);
  transition: border-color 0.15s, transform 0.15s;
}

.bg-swatch:hover {
  transform: scale(1.08);
}

.bg-swatch.active {
  border-color: #5b5bd6;
}

.bg-picker {
  width: 90px;
}

.bg-image-row {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}

.scene-presets {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 94px), 1fr));
  gap: 8px;
}

.scene-card, .tex-card {
  min-width: 0;
  padding: 0;
  background: #231e2a;
  color: var(--panel-ink);
  font: inherit;
}
.scene-card:focus-visible, .tex-card:focus-visible, .bg-swatch:focus-visible {
  outline: 2px solid var(--panel-accent);
  outline-offset: 2px;
}

.scene-card {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid rgba(255, 255, 255, 0.12);
  transition: border-color 0.15s, transform 0.15s;
}

.scene-card:hover {
  transform: scale(1.03);
}

.scene-card.active {
  border-color: #5b5bd6;
}

.scene-card img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}

.scene-card span {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 2px 6px;
  font-size: 11px;
  background: rgba(0, 0, 0, 0.55);
}

.style-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tex-presets {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
}

.tex-card {
  position: relative;
  border-radius: 50%;
  overflow: hidden;
  cursor: pointer;
  aspect-ratio: 1;
  border: 2px solid rgba(255, 255, 255, 0.12);
  transition: border-color 0.15s, transform 0.15s;
}

.tex-card:hover {
  transform: scale(1.06);
}

.tex-card.active {
  border-color: #5b5bd6;
}

.tex-card img,
.tex-card .tex-none {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tex-card span {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 1px 0 3px;
  font-size: 10px;
  text-align: center;
  background: rgba(0, 0, 0, 0.55);
}

.stage-colors {
  display: flex;
  gap: 18px;
  margin-top: 4px;
}

.stage-colors .bg-picker {
  width: 130px;
  flex: none;
}

.stage-color-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  opacity: 0.85;
}

.stage-color-item span {
  white-space: nowrap;
}
</style>
