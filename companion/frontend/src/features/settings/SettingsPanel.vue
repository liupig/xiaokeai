<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import {
  NButton, NColorPicker, NDrawer, NDrawerContent, NInput, NInputNumber, NSelect,
  NSlider, NSwitch, NTabPane, NTabs, useMessage,
} from 'naive-ui';
import { api } from '../../api/client';
import { useSettingsStore } from '../../stores/settings';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { LOCAL_SCENES } from '../scenes/catalog';
import { defaultVoice, featureOn, t } from '../../i18n';
import {
  pickScene as pickPlayScene, restoreOrRotateScene, sceneExtra, sceneSession,
} from '../scenes/session';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const settings = useSettingsStore();
const characters = useCharacterStore();
const chat = useChatStore();
const message = useMessage();

// LLM 服务商预设（全部 OpenAI 兼容协议），选择后自动填接口地址和推荐模型
const LLM_PRESETS: Record<string, { base: string; model: string }> = {
  bailian: { base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  volcano: { base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-1-6-250615' },
  volcano_character: { base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-character-260628' },
  deepseek: { base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  moonshot: { base: 'https://api.moonshot.cn/v1', model: 'kimi-k2-turbo-preview' },
  zhipu: { base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.5-flash' },
  openai: { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  gemini: { base: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.0-flash' },
  openrouter: { base: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
  anthropic: { base: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-5' },
  groq: { base: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
  mistral: { base: 'https://api.mistral.ai/v1', model: 'mistral-small-latest' },
  xai: { base: 'https://api.x.ai/v1', model: 'grok-3' },
  together: { base: 'https://api.together.xyz/v1', model: 'meta-llama/Llama-3.3-70B-Instruct-Turbo' },
  fireworks: { base: 'https://api.fireworks.ai/inference/v1', model: 'accounts/fireworks/models/llama-v3p3-70b-instruct' },
  nvidia: { base: 'https://integrate.api.nvidia.com/v1', model: 'meta/llama-3.3-70b-instruct' },
  cerebras: { base: 'https://api.cerebras.ai/v1', model: 'llama-3.3-70b' },
  perplexity: { base: 'https://api.perplexity.ai', model: 'sonar' },
  novita: { base: 'https://api.novita.ai/v3/openai', model: 'deepseek/deepseek-v3' },
  comet: { base: 'https://api.cometapi.com/v1', model: 'gpt-4o-mini' },
  featherless: { base: 'https://api.featherless.ai/v1', model: 'meta-llama/Llama-3.3-70B-Instruct' },
  aihubmix: { base: 'https://aihubmix.com/v1', model: 'gpt-4o-mini' },
  ai302: { base: 'https://api.302.ai/v1', model: 'gpt-4o-mini' },
  siliconflow: { base: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
  stepfun: { base: 'https://api.stepfun.com/v1', model: 'step-2-mini' },
  baichuan: { base: 'https://api.baichuan-ai.com/v1', model: 'Baichuan4-Turbo' },
  minimax: { base: 'https://api.minimaxi.com/v1', model: 'MiniMax-M2' },
  modelscope: { base: 'https://api-inference.modelscope.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct' },
  hunyuan: { base: 'https://api.hunyuan.cloud.tencent.com/v1', model: 'hunyuan-turbos-latest' },
  mimo: { base: 'https://api.xiaomimimo.com/v1', model: 'mimo-v2-flash' },
  moonshot_intl: { base: 'https://api.moonshot.ai/v1', model: 'kimi-k2-turbo-preview' },
  qwen_intl: { base: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  ollama: { base: 'http://127.0.0.1:11434/v1', model: 'llama3.2' },
  vllm: { base: 'http://127.0.0.1:8000/v1', model: 'default' },
  sglang: { base: 'http://127.0.0.1:30000/v1', model: 'default' },
  player2: { base: 'http://127.0.0.1:4315/v1', model: 'player2' },
  minicpm: { base: 'https://api.modelbest.cn/v1', model: 'MiniCPM-O-4.5-9B' },
};
const llmPresetOptions = computed(() => {
  settings.locale.ui;
  const all = [
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
const langOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('lang.zh'), value: 'zh-CN' as const },
    { label: t('lang.en'), value: 'en' as const },
    { label: t('lang.ja'), value: 'ja' as const },
    { label: t('lang.ko'), value: 'ko' as const },
  ];
});
const replyModeOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('lang.fixed'), value: 'fixed' as const },
    { label: t('lang.follow'), value: 'follow' as const },
  ];
});
// 根据当前 base_url + 模型名反推预设（同地址的豆包通用/角色要分开高亮）
const currentPreset = computed(() => {
  const url = settings.llm.base_url;
  const model = settings.llm.model;
  const entries = Object.entries(LLM_PRESETS);
  const exact = entries.find(([, p]) => url.startsWith(p.base) && p.model === model);
  if (exact) return exact[0];
  const found = entries.find(([, p]) => url.startsWith(p.base));
  return found ? found[0] : null;
});

function applyLlmPreset(key: string) {
  const p = LLM_PRESETS[key];
  if (!p) return;
  settings.llm.base_url = p.base;
  settings.llm.model = p.model;
  if (key === 'volcano_character') settings.llm.thinking = 'off';
  if ((key === 'ollama' || key === 'vllm' || key === 'sglang' || key === 'player2')
      && !(settings.llm.api_key || '').trim()) {
    settings.llm.api_key = 'ollama';
  }
  if (key === 'minicpm') {
    settings.llm.thinking = 'off';
    settings.omni.chat_url = p.base;
    settings.omni.model = p.model;
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

const testing = ref(false);
async function testLlm() {
  testing.value = true;
  try {
    const r = await api.testLlm(settings.llm);
    if (r.ok) message.success(r.message);
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
const ttsEngineOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('set.tts.volcEngine'), value: 'volc' },
    { label: t('set.tts.cosyEngine'), value: 'cosy' },
    { label: t('set.tts.openaiEngine'), value: 'openai' },
    { label: t('set.tts.elevenEngine'), value: 'eleven' },
    { label: t('set.tts.geminiEngine'), value: 'gemini' },
    { label: t('set.tts.qwen'), value: 'qwen' },
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
    { label: t('set.asr.sense'), value: 'sensevoice' },
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
  || settings.tts.engine === 'qwen' || settings.tts.engine === 'volc'
  || settings.tts.engine === 'openai' || settings.tts.engine === 'eleven'
  || settings.tts.engine === 'gemini'
);

watch(() => settings.tts.engine, (eng) => {
  const list = settings.voices.filter((v) => v.engine === eng);
  if (list.length && !list.some((v) => v.id === settings.tts.voice)) {
    settings.tts.voice = (eng === 'qwen' || eng === 'edge' || eng === 'volc'
      || eng === 'openai' || eng === 'eleven' || eng === 'gemini')
      ? defaultVoice(eng, settings.locale.reply)
      : '';
  }
});

type SpeechStatus = {
  asr: { available: boolean; installed?: boolean; ready: boolean; downloading?: boolean;
         progress?: number; message: string };
  tts: { available: boolean; ready: boolean; loading?: boolean; downloading?: boolean;
         gpu?: boolean; device?: string; size?: string; message: string;
         sizes?: Record<string, { installed: boolean; label: string; gb: string }> };
};
const speechStatus = ref<SpeechStatus | null>(null);
let statusTimer: number | null = null;

async function refreshSpeechStatus() {
  try {
    speechStatus.value = await api.getSpeechStatus();
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

async function save() {
  await settings.save();
  message.success(t('set.saved'));
  emit('update:show', false);
}

function onPhysics(v: boolean) {
  settings.quality.physics = !!v;
  settings.applyQuality();
  void settings.save().catch(() => {});
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

async function toggleMod(key: 'memory' | 'scenes' | 'rewrite' | 'keepsake' | 'tarot' | 'codewatch' | 'touch' | 'harness' | 'glance', on: boolean) {
  const prev = settings.modules[key];
  settings.modules[key] = on;
  try {
    await settings.save();
    if (key === 'tarot' && !on) {
      const { onModuleOff } = await import('../tarot');
      await onModuleOff();
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
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="480" placement="right" show-mask="transparent" to="body">
    <n-drawer-content :title="t('settings.title')" closable :native-scrollbar="false">
    <n-tabs type="line" class="settings-tabs">
      <n-tab-pane name="lang" :tab="t('lang.tab')">
        <div class="form">
          <p class="hint">{{ t('lang.hint') }}</p>
          <label>{{ t('lang.ui') }}</label>
          <n-select :value="settings.locale.ui" :options="langOptions"
                    @update:value="(v: 'zh-CN' | 'en' | 'ja' | 'ko') => settings.setLocale({ ui: v })" />
          <label>{{ t('lang.reply') }}</label>
          <n-select :value="settings.locale.reply" :options="langOptions"
                    @update:value="(v: 'zh-CN' | 'en' | 'ja' | 'ko') => settings.setLocale({ reply: v })" />
          <label>{{ t('lang.mode') }}</label>
          <n-select :value="settings.locale.reply_mode" :options="replyModeOptions"
                    @update:value="(v: 'fixed' | 'follow') => settings.setLocale({ reply_mode: v })" />
          <p v-if="!featureOn('tarot', settings.locale.reply)" class="hint">{{ t('mod.missing') }} · {{ t('mod.tarot') }}</p>
          <p v-if="!featureOn('scenes', settings.locale.reply)" class="hint">{{ t('mod.missing') }} · {{ t('mod.scenes') }}</p>
        </div>
      </n-tab-pane>
      <n-tab-pane v-if="isShell" name="desktop" :tab="t('settings.desktop')">
        <div class="form">
          <p class="hint">{{ t('set.tray.hint') }}</p>
          <div class="switch-row">
            <span>{{ t('set.tray.minimize') }}</span>
            <n-switch :value="trayMinimize" @update:value="(v: boolean) => saveTray({ minimize: v })" />
          </div>
          <p class="hint">{{ t('set.tray.minimizeHint') }}</p>
          <div class="switch-row">
            <span>{{ t('set.tray.close') }}</span>
            <n-switch :value="trayClose" @update:value="(v: boolean) => saveTray({ close: v })" />
          </div>
          <p class="hint">{{ t('set.tray.closeHint') }}</p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="content" :tab="t('settings.content')">
        <div class="form">
          <p class="hint">{{ t('set.pack.hint') }}</p>
          <label>{{ t('set.pack.dir') }}</label>
          <div class="content-row">
            <n-input v-model:value="contentPath" :placeholder="t('set.pack.ph')" />
            <n-button v-if="canPickFolder" @click="pickContentFolder">{{ t('set.pack.browse') }}</n-button>
          </div>
          <p class="hint">{{ contentFound }}</p>
          <p v-if="contentHint" class="hint">{{ contentHint }}</p>
          <n-button type="primary" :loading="contentBusy" :disabled="!contentPath.trim()"
                    @click="saveContentPath">{{ t('set.pack.save') }}</n-button>
          <p class="hint">{{ t('set.pack.restart') }}</p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="modules" :tab="t('settings.modules')">
        <div class="form">
          <p class="hint">{{ t('set.mod.off') }}</p>
          <p v-if="hwHint" class="hint">{{ hwHint }}</p>
          <div class="switch-row">
            <span>{{ t('mod.memory') }}</span>
            <n-switch :value="settings.modules.memory" @update:value="(v: boolean) => toggleMod('memory', v)" />
          </div>
          <p class="hint">{{ t('set.mod.memory') }}</p>
          <template v-if="settings.modules.memory">
            <label>{{ t('set.mod.embed') }}</label>
            <n-select :value="settings.memory.embedder" :options="embedderOptions"
                      @update:value="saveEmbedder" />
            <p class="hint">{{ t('set.mod.embedHint') }}</p>
          </template>
          <div class="switch-row">
            <span>{{ t('mod.scenes') }}</span>
            <n-switch :value="settings.modules.scenes" @update:value="(v: boolean) => toggleMod('scenes', v)" />
          </div>
          <p class="hint">{{ t('set.mod.scenes') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.rewrite') }}</span>
            <n-switch :value="settings.modules.rewrite" @update:value="(v: boolean) => toggleMod('rewrite', v)" />
          </div>
          <p class="hint">{{ t('set.mod.rewrite') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.keepsake') }}</span>
            <n-switch :value="settings.modules.keepsake" @update:value="(v: boolean) => toggleMod('keepsake', v)" />
          </div>
          <p class="hint">{{ t('set.mod.keepsake') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.tarot') }}</span>
            <n-switch :value="settings.modules.tarot" @update:value="(v: boolean) => toggleMod('tarot', v)" />
          </div>
          <p class="hint">{{ t('set.mod.tarot') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.codewatch') }}</span>
            <n-switch :value="settings.modules.codewatch" @update:value="(v: boolean) => toggleMod('codewatch', v)" />
          </div>
          <p class="hint">{{ t('set.mod.code') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.touch') }}</span>
            <n-switch :value="settings.modules.touch" @update:value="(v: boolean) => toggleMod('touch', v)" />
          </div>
          <p class="hint">{{ t('set.mod.touch') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.harness') }}</span>
            <n-switch :value="settings.modules.harness" @update:value="(v: boolean) => toggleMod('harness', v)" />
          </div>
          <p class="hint">{{ t('set.mod.harness') }}</p>
          <div class="switch-row">
            <span>{{ t('mod.glance') }}</span>
            <n-switch :value="settings.modules.glance" @update:value="(v: boolean) => toggleMod('glance', v)" />
          </div>
          <p class="hint">{{ t('set.mod.glance') }}</p>
          <label>{{ t('set.vision.label') }}</label>
          <n-select v-model:value="settings.vision.provider" :options="visionOptions" />
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
        </div>
      </n-tab-pane>
      <n-tab-pane name="ai" :tab="t('settings.ai')">
        <div class="form">
          <label>{{ t('set.llm.label') }}</label>
          <n-select :value="currentPreset" :options="llmPresetOptions" filterable
                    :placeholder="t('set.llm.ph')"
                    @update:value="applyLlmPreset" />
          <label>{{ t('set.llm.url') }}</label>
          <n-input v-model:value="settings.llm.base_url"
                   placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          <label>API Key</label>
          <n-input v-model:value="settings.llm.api_key" type="password"
                   show-password-on="click" :placeholder="t('set.llm.keyPh')" />
          <label>{{ t('set.llm.model') }}</label>
          <n-input v-model:value="settings.llm.model"
                   placeholder="qwen-plus / deepseek-chat / doubao-seed-1-6 …" />
          <div>
            <n-button size="small" type="primary" secondary
                      :loading="testing" @click="testLlm">{{ t('settings.test') }}</n-button>
          </div>
          <p v-if="settings.llm_env || settings.llm_local" class="hint">{{ t('set.llm.env') }}</p>
          <p class="hint">{{ t('set.llm.hint') }}</p>
          <label>{{ t('set.llm.think') }}</label>
          <n-select v-model:value="settings.llm.thinking" :options="thinkingOptions" />
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
          <p class="hint">{{ t('set.llm.nokey') }}</p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="omni" :tab="t('settings.omni')">
        <div class="form">
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
        </div>
      </n-tab-pane>
      <n-tab-pane name="voice" :tab="t('settings.voice')">
        <div class="form">
          <p v-if="hwHint" class="hint">{{ hwHint }}</p>
          <h3 class="section-title">{{ t('set.asr.title') }}</h3>
          <label>{{ t('set.asr.engine') }}</label>
          <n-select v-model:value="settings.stt.engine" :options="asrEngineOptions" />
          <p class="hint">{{ t('set.asr.hint') }}</p>
          <p v-if="settings.stt.engine === 'ali' || settings.stt.engine === 'volc'" class="hint">{{ t('set.asr.cloud') }}</p>
          <p v-if="settings.stt.engine === 'openai' || settings.stt.engine === 'eleven' || settings.stt.engine === 'gemini'" class="hint">{{ t('set.asr.cloudIntl') }}</p>
          <div v-if="settings.stt.engine === 'sensevoice'" class="speech-status">
            <p class="hint">{{ speechStatus?.asr.message || t('set.asr.status') }}</p>
            <n-button size="small" :loading="warmingAsr || !!speechStatus?.asr.downloading"
                      @click="warmup('asr')">{{ t('set.asr.warmup') }}</n-button>
          </div>

          <h3 class="section-title">{{ t('set.tts.title') }}</h3>
          <label>{{ t('set.tts.engine') }}</label>
          <n-select v-model:value="settings.tts.engine" :options="ttsEngineOptions" />
          <template v-if="settings.tts.engine === 'qwen'">
            <label>{{ t('set.tts.size') }}</label>
            <n-select v-model:value="settings.tts.qwen_size" :options="qwenSizeOptions" />
            <p class="hint">
              {{ t('set.tts.sizeLead') }}
              0.6B {{ speechStatus?.tts.sizes?.['0.6b']?.installed ? t('set.tts.local') : t('set.tts.missing') }}
              · 1.7B {{ speechStatus?.tts.sizes?.['1.7b']?.installed ? t('set.tts.local') : t('set.tts.missingBig') }}
              <template v-if="speechStatus?.tts.size">
                · {{ t('set.tts.ram', { size: speechStatus.tts.size === '1.7b' ? '1.7B' : '0.6B' }) }}
              </template>
            </p>
            <label>{{ t('set.tts.style') }}</label>
            <n-select v-model:value="settings.tts.qwen_style" :options="qwenStyleOptions" />
            <n-input v-if="settings.tts.qwen_style === 'custom'"
                     v-model:value="settings.tts.qwen_instruct" type="textarea"
                     :autosize="{ minRows: 2, maxRows: 4 }"
                     :placeholder="t('set.tts.stylePh')" />
            <p class="hint">{{ t('set.tts.styleHint') }}</p>
          </template>
          <label>{{ t('set.tts.voice') }}</label>
          <n-select v-model:value="settings.tts.voice" :options="voiceOptions" filterable
                    :fallback-option="false" :placeholder="t('set.tts.voicePh')"
                    :disabled="!ttsNeedsVoice" />
          <p class="hint">{{ t('set.tts.voiceHint') }}</p>
          <label>{{ t('set.tts.duplex') }}</label>
          <n-select v-model:value="settings.tts.duplex_cmd" :options="duplexCmdOptions" />
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
          <div class="switch-row">
            <span>{{ t('set.tts.ingress') }}</span>
            <n-switch v-model:value="settings.tts.duplex_ingress" />
          </div>
          <p class="hint">{{ t('set.tts.duplexHint') }}</p>
          <p v-if="settings.tts.engine === 'cosy'" class="hint">{{ t('set.tts.cosy') }}</p>
          <p v-if="settings.tts.engine === 'volc'" class="hint">{{ t('set.tts.volc') }}</p>
          <p v-if="settings.tts.engine === 'openai'" class="hint">{{ t('set.tts.openai') }}</p>
          <p v-if="settings.tts.engine === 'eleven'" class="hint">{{ t('set.tts.eleven') }}</p>
          <p v-if="settings.tts.engine === 'gemini'" class="hint">{{ t('set.tts.gemini') }}</p>
          <div v-if="settings.tts.engine === 'qwen'" class="speech-status">
            <p class="hint">
              {{ speechStatus?.tts.message || t('set.asr.status') }}
              <template v-if="speechStatus?.tts.gpu"> · {{ t('set.tts.gpu') }}</template>
            </p>
            <n-button size="small"
                      :loading="warmingTts || !!speechStatus?.tts.loading || !!speechStatus?.tts.downloading"
                      @click="warmup('tts')">{{ t('set.tts.load') }}</n-button>
          </div>
        </div>
      </n-tab-pane>
      <n-tab-pane name="download" :tab="t('settings.download')">
        <div class="form">
          <label>{{ t('set.dl.token') }}</label>
          <n-input v-model:value="settings.download.aplaybox_token" type="password"
                   show-password-on="click" :placeholder="t('set.dl.ph')" />
          <p class="hint">{{ t('set.dl.hint') }}</p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="quality" :tab="t('settings.quality')">
        <div class="form">
          <div class="switch-row">
            <span>{{ t('set.q.physics') }}</span>
            <n-switch v-model:value="settings.quality.physics"
                      @update:value="onPhysics" />
          </div>
          <p class="hint">{{ t('set.q.physicsHint') }}</p>
          <label>{{ t('set.q.dpr') }}</label>
          <n-slider v-model:value="settings.quality.pixel_ratio_cap"
                    :min="1" :max="3" :step="0.5" />
          <label>{{ t('set.q.light') }}</label>
          <n-slider v-model:value="settings.quality.light_level"
                    :min="0.5" :max="1.5" :step="0.05"
                    :format-tooltip="(v: number) => v.toFixed(2) + '×'"
                    @update:value="settings.applyQuality()" />
          <label>{{ t('set.q.bgm') }}</label>
          <n-slider v-model:value="settings.quality.bgm_volume"
                    :min="0" :max="1" :step="0.05"
                    :format-tooltip="(v: number) => Math.round(v * 100) + '%'"
                    @update:value="settings.applyQuality()" />
          <label>{{ t('set.q.presets') }}</label>
          <p v-if="settings.modules.scenes" class="hint">{{ t('set.q.sceneOn') }}</p>
          <div class="scene-presets">
            <div v-for="s in SCENE_PRESETS" :key="s.value" class="scene-card"
                 :class="{ active: settings.modules.scenes
                   ? sceneSession.current?.background === s.value
                   : settings.quality.background_image === s.value }"
                  :title="t('set.scene.' + s.key)" @click="pickPresetLook(s)">
              <img :src="s.value" :alt="t('set.scene.' + s.key)" loading="lazy" />
              <span>{{ t('set.scene.' + s.key) }}</span>
            </div>
          </div>
          <label>{{ t('set.q.solid') }}</label>
          <div class="bg-presets">
            <div v-for="p in BG_PRESETS" :key="p.value" class="bg-swatch"
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
          <div class="switch-row" style="margin-top: 10px">
            <span>{{ t('set.q.stage') }}</span>
            <n-switch v-model:value="settings.quality.stage_show"
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
              <div v-for="tex in STAGE_TEXTURES" :key="tex.key" class="tex-card"
                   :class="{ active: settings.quality.stage_texture === tex.value }"
                   :title="t('set.tex.' + tex.key)"
                   @click="settings.quality.stage_texture = tex.value; settings.applyQuality()">
                <img v-if="tex.value" :src="tex.value" :alt="t('set.tex.' + tex.key)" loading="lazy" />
                <div v-else class="tex-none"
                     :style="{ background: settings.quality.stage_color }" />
                <span>{{ t('set.tex.' + tex.key) }}</span>
              </div>
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
        </div>
      </n-tab-pane>
    </n-tabs>
    <template #footer>
      <div style="display:flex;justify-content:flex-end;gap:10px;width:100%">
        <n-button @click="emit('update:show', false)">{{ t('settings.cancel') }}</n-button>
        <n-button type="primary" @click="save">{{ t('settings.save') }}</n-button>
      </div>
    </template>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
/* 标签比抽屉宽时会整行被裁掉。压回抽屉宽度并换行，下划线跟在每个标签自己底下。 */
.settings-tabs {
  width: 100%;
  min-width: 0;
}

.settings-tabs :deep(.n-tabs-nav),
.settings-tabs :deep(.n-tabs-nav-scroll-wrapper),
.settings-tabs :deep(.v-x-scroll) {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}

.settings-tabs :deep(.v-x-scroll) {
  overflow: visible;
}

.settings-tabs :deep(.n-tabs-nav-scroll-content) {
  width: 100%;
}

.settings-tabs :deep(.n-tabs-wrapper) {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  column-gap: 18px;
  row-gap: 2px;
}

.settings-tabs :deep(.n-tabs-tab-pad),
.settings-tabs :deep(.n-tabs-scroll-padding) {
  display: none;
}

.settings-tabs :deep(.n-tabs-bar) {
  display: none;
}

.settings-tabs :deep(.n-tabs-tab--active) {
  box-shadow: inset 0 -2px 0 var(--n-bar-color);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form label {
  font-size: 13px;
  opacity: 0.8;
  margin-top: 6px;
}

.content-row {
  display: flex;
  gap: 8px;
}

.section-title {
  margin: 12px 0 0;
  font-size: 14px;
  font-weight: 600;
}

.speech-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

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
  opacity: 0.55;
  line-height: 1.7;
  margin-top: 4px;
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
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
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
