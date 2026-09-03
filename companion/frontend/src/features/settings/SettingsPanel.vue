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
};
const llmPresetOptions = [
  { label: '阿里云百炼（通义千问 / Kimi）', value: 'bailian' },
  { label: '火山方舟（豆包）', value: 'volcano' },
  { label: '火山方舟（豆包角色）', value: 'volcano_character' },
  { label: 'DeepSeek 官方', value: 'deepseek' },
  { label: 'Moonshot（Kimi 官方）', value: 'moonshot' },
  { label: '智谱 GLM', value: 'zhipu' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'Google Gemini（OpenAI 兼容）', value: 'gemini' },
  { label: 'OpenRouter（海外模型聚合）', value: 'openrouter' },
];
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
}

const thinkingOptions = [
  { label: '跟随模型默认（推荐）', value: 'default' },
  { label: '强制开启思考', value: 'on' },
  { label: '强制关闭思考', value: 'off' },
];

const testing = ref(false);
async function testLlm() {
  testing.value = true;
  try {
    const r = await api.testLlm(settings.llm);
    if (r.ok) message.success(r.message);
    else message.error(r.message, { duration: 8000, closable: true });
  } catch (e) {
    message.error('测试请求失败：' + e);
  } finally {
    testing.value = false;
  }
}

// 背景预设色板
const BG_PRESETS = [
  { label: '深空蓝', value: '#141420' },
  { label: '纯黑', value: '#000000' },
  { label: '暖灰', value: '#2a2624' },
  { label: '薄暮紫', value: '#241a30' },
  { label: '森绿', value: '#16241c' },
  { label: '奶白', value: '#ece7df' },
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
  { label: '纯色台面', value: '' },
  { label: '玉石雕纹', value: TEX.jade },
  { label: '赛博电路', value: TEX.circuit },
  { label: '星辰魔阵', value: TEX.star },
  { label: '原木拼花', value: TEX.wood },
  { label: '樱瓣水面', value: TEX.petal },
  { label: '金属舞台', value: TEX.stage },
];
// 预制 3D 场景（AI 生成，随前端一起发布）。stage 字段为该场景的配套底座（贴图/台面色/发光色），
// 点场景时自动应用，之后仍可手动微调。
const SCENE_PRESETS = [
  { label: '古风仙境', value: '/backgrounds/bg_guofeng.png',
    stage: { texture: TEX.jade, color: '#1d2f2a', glow: '#58e6c8' } },
  { label: '赛博夜城', value: '/backgrounds/bg_cyber.png',
    stage: { texture: TEX.circuit, color: '#171226', glow: '#b45ce6' } },
  { label: '星空极光', value: '/backgrounds/bg_starry.png',
    stage: { texture: TEX.star, color: '#10142e', glow: '#7a8cff' } },
  { label: '演唱会舞台', value: '/backgrounds/bg_concert.png',
    stage: { texture: TEX.stage, color: '#1a1220', glow: '#e658c8' } },
  { label: '樱花庭院', value: '/backgrounds/bg_sakura.png',
    stage: { texture: TEX.petal, color: '#33222a', glow: '#ff9ec4' } },
  { label: '黄昏海岸', value: '/backgrounds/bg_beach.png',
    stage: { texture: TEX.wood, color: '#33261c', glow: '#ffb163' } },
  { label: '雪夜小镇', value: '/backgrounds/bg_snow.png',
    stage: { texture: TEX.wood, color: '#22282e', glow: '#9fd7ff' } },
  { label: '魔法森林', value: '/backgrounds/bg_forest.png',
    stage: { texture: TEX.star, color: '#14261c', glow: '#58e6a0' } },
  { label: '未来实验室', value: '/backgrounds/bg_lab.png',
    stage: { texture: TEX.circuit, color: '#101a24', glow: '#58c8e6' } },
  { label: '金殿宫阙', value: '/backgrounds/bg_palace.png',
    stage: { texture: TEX.jade, color: '#2a2114', glow: '#e6b358' } },
  { label: '夏日祭典', value: '/backgrounds/bg_matsuri.png',
    stage: { texture: TEX.wood, color: '#2c1e16', glow: '#ffa64d' } },
  { label: '海底龙宫', value: '/backgrounds/bg_underwater.png',
    stage: { texture: TEX.jade, color: '#10222b', glow: '#58c8e6' } },
  { label: '天空之城', value: '/backgrounds/bg_skycity.png',
    stage: { texture: TEX.star, color: '#23283a', glow: '#ffd97a' } },
  { label: '暖屋咖啡', value: '/backgrounds/bg_cafe.png',
    stage: { texture: TEX.wood, color: '#2b211a', glow: '#e6a358' } },
  { label: '魔法图书馆', value: '/backgrounds/bg_library.png',
    stage: { texture: TEX.wood, color: '#241c14', glow: '#d7a55e' } },
  { label: '雨夜小巷', value: '/backgrounds/bg_alley.png',
    stage: { texture: TEX.stage, color: '#171420', glow: '#ff5ca8' } },
  { label: '黄昏花田', value: '/backgrounds/bg_flower.png',
    stage: { texture: TEX.petal, color: '#2e2018', glow: '#ffac6e' } },
  { label: '星际舷窗', value: '/backgrounds/bg_space.png',
    stage: { texture: TEX.circuit, color: '#0e1220', glow: '#5878e6' } },
  { label: '温馨卧室', value: '/backgrounds/bg_bedroom.png',
    stage: { texture: TEX.petal, color: '#2e2226', glow: '#ffb9c9' } },
];
// 舞台底座风格
const STAGE_STYLES = [
  { label: '经典圆盘', value: 'classic' },
  { label: '双层舞台', value: 'double' },
  { label: '魔法阵', value: 'magic' },
  { label: '水晶棱台', value: 'crystal' },
  { label: '科幻光环', value: 'tech' },
  { label: '莲花宝座', value: 'lotus' },
  { label: '星环轨道', value: 'orbit' },
  { label: '极简光环', value: 'minimal' },
  { label: '黑胶唱片', value: 'vinyl' },
  { label: '迪斯科舞池', value: 'disco' },
];
const bgFileInput = ref<HTMLInputElement | null>(null);

function pickBgColor(color: string) {
  settings.quality.background_color = color;
  settings.quality.background_image = '';
  if (settings.modules.scenes) {
    pickPlayScene({
      id: `look-color-${color}`,
      title: '纯色',
      setting: '没有贴图，只亮着这层底色。',
      conflict: '',
      opening: '按这场场合随口接。',
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
      title: scene.label,
      setting: scene.label,
      conflict: '',
      opening: '按这场场合随口接。',
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
    message.warning('图片太大（超过 8MB），请换一张');
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const url = String(reader.result);
    settings.quality.background_image = url;
    if (settings.modules.scenes) {
      pickPlayScene({
        id: 'look-custom',
        title: '自定义',
        setting: '用你刚选的图当这场的场合。',
        conflict: '',
        opening: '按这场场合随口接。',
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
const ttsEngineOptions = [
  { label: '离线 · Qwen3-TTS 本地流式（推荐）', value: 'qwen' },
  { label: '在线 · edge-tts 流式（微软云）', value: 'edge' },
  { label: '在线 · CosyVoice 流式（需百炼 sk- Key）', value: 'cosy' },
  { label: '浏览器内置（无真实口型）', value: 'browser' },
  { label: '关闭语音', value: 'off' },
];
const qwenSizeOptions = [
  { label: '0.6B（更快、更省显存）', value: '0.6b' },
  { label: '1.7B（音质更好，约 4GB 权重）', value: '1.7b' },
];
const qwenStyleOptions = [
  { label: '默认（不改语气）', value: 'off' },
  { label: '清冷御姐', value: 'yujie' },
  { label: '磁性气声', value: 'husky' },
  { label: '温柔撩人', value: 'flirt' },
  { label: '自定义语气', value: 'custom' },
];
const duplexCmdOptions = [
  { label: '下一轮：剩余 >Ns 才打断（InterruptOrQueue）', value: 'interrupt_or_queue' },
  { label: '下一轮：马上打断上一轮', value: 'interrupt' },
  { label: '下一轮：等上一轮全部说完', value: 'queue' },
  { label: '下一轮：不够 Ns 才接，否则丢掉', value: 'conditional_queue' },
  { label: '下一轮：超过 Ns 才切，否则丢掉', value: 'conditional_interrupt' },
];
const asrEngineOptions = [
  { label: '在线 · 浏览器 Web Speech（Chrome/Edge）', value: 'browser' },
  { label: '离线 · SenseVoice-Small（本地 CPU）', value: 'sensevoice' },
];
const hwHint = computed(() => {
  const h = settings.hardware as {
    auto?: boolean; tier?: string; ram_gb?: number; vram_gb?: number; reason?: string;
  };
  if (!h?.tier && !h?.reason) return '';
  const names: Record<string, string> = { low: '低配', mid: '中配', high: '高配' };
  const tier = names[h.tier || ''] || h.tier || '未知';
  const bits = [
    h.ram_gb ? `${h.ram_gb}GB 内存` : '',
    (h.vram_gb || 0) > 0 ? `${h.vram_gb}GB 显存` : '无独显',
  ].filter(Boolean).join('，');
  const mode = h.auto ? '已按配置自动选择引擎，保证能启动' : '已按你保存的设置（不再自动改）';
  return `本机 ${tier}${bits ? `（${bits}）` : ''}。${mode}。${h.reason || ''}`;
});
const ttsNeedsVoice = computed(() =>
  settings.tts.engine === 'cosy' || settings.tts.engine === 'edge' || settings.tts.engine === 'qwen'
);

watch(() => settings.tts.engine, (eng) => {
  const list = settings.voices.filter((v) => v.engine === eng);
  if (list.length && !list.some((v) => v.id === settings.tts.voice)) {
    settings.tts.voice = '';
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
    message.info(r.message || '已开始准备');
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
  if (v) startStatusPoll();
  else stopStatusPoll();
});
onUnmounted(stopStatusPoll);

async function save() {
  await settings.save();
  message.success('设置已保存');
  emit('update:show', false);
}

function onPhysics(v: boolean) {
  settings.quality.physics = !!v;
  settings.applyQuality();
  void settings.save().catch(() => {});
}

async function toggleMod(key: 'memory' | 'scenes' | 'rewrite' | 'keepsake' | 'tarot', on: boolean) {
  const prev = settings.modules[key];
  settings.modules[key] = on;
  try {
    await settings.save();
    if (key === 'tarot' && !on) {
      const { onModuleOff } = await import('../tarot');
      await onModuleOff();
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
    <n-drawer-content title="设置" closable :native-scrollbar="false">
    <n-tabs type="line">
      <n-tab-pane name="modules" tab="体验模块">
        <div class="form">
          <p class="hint">关掉等于没装：对话、舞台和界面都不再走这条能力。低配会自动关掉记忆，避免向量库把进程拖死。</p>
          <p v-if="hwHint" class="hint">{{ hwHint }}</p>
          <div class="switch-row">
            <span>记忆 · 她会记住你说过的事</span>
            <n-switch :value="settings.modules.memory" @update:value="(v: boolean) => toggleMod('memory', v)" />
          </div>
          <p class="hint">Mem0 抽取并按语义召回。无 API Key 时不写入，已有记忆仍可看。</p>
          <div class="switch-row">
            <span>情境 · 今晚有一场戏</span>
            <n-switch :value="settings.modules.scenes" @update:value="(v: boolean) => toggleMod('scenes', v)" />
          </div>
          <p class="hint">进门就在戏里，后面每一句也还在这场。可随机、点选或现编。背景、镜头、情绪跟着走。</p>
          <div class="switch-row">
            <span>重写 · 重说、回溯、再演</span>
            <n-switch :value="settings.modules.rewrite" @update:value="(v: boolean) => toggleMod('rewrite', v)" />
          </div>
          <p class="hint">上一句换个说法；回到某句之后重来；同一句换情绪再演一遍（不调模型）。</p>
          <div class="switch-row">
            <span>证物 · 剧照和 8 秒短片</span>
            <n-switch :value="settings.modules.keepsake" @update:value="(v: boolean) => toggleMod('keepsake', v)" />
          </div>
          <p class="hint">从舞台截下今晚的画面。记忆开启时，保存证物也会记一笔。开关立即生效，不必再点保存。</p>
          <div class="switch-row">
            <span>塔罗 · 面对面抽牌</span>
            <n-switch :value="settings.modules.tarot" @update:value="(v: boolean) => toggleMod('tarot', v)" />
          </div>
          <p class="hint">她坐在对面给你抽。口头说「抽一张」或点对话栏的牌。仅供娱乐，不构成建议。关掉等于没装。</p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="ai" tab="AI 对话">
        <div class="form">
          <label>服务商（选择后自动填写接口地址和推荐模型）</label>
          <n-select :value="currentPreset" :options="llmPresetOptions"
                    placeholder="选择服务商，或在下方手动填写"
                    @update:value="applyLlmPreset" />
          <label>接口地址（OpenAI 兼容，国内外均支持）</label>
          <n-input v-model:value="settings.llm.base_url"
                   placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          <label>API Key</label>
          <n-input v-model:value="settings.llm.api_key" type="password"
                   show-password-on="click" placeholder="留空则使用系统环境变量 / .env" />
          <label>模型名</label>
          <n-input v-model:value="settings.llm.model"
                   placeholder="qwen-plus / deepseek-chat / doubao-seed-1-6 …" />
          <div>
            <n-button size="small" type="primary" secondary
                      :loading="testing" @click="testLlm">测试连接</n-button>
          </div>
          <p v-if="settings.llm_env || settings.llm_local" class="hint">
            设置里未填 Key，正在使用系统环境变量 / 本地 .env。密钥不会写入数据库。
          </p>
          <p class="hint">
            切换服务商后记得同时换成该服务商的 API Key（Key 不通用）。
            也可以把 Key 写到环境变量或 companion/scripts/.env（COMPANION_LLM_API_KEY / ARK_API_KEY），
            前端留空即可直接用。火山方舟可用模型名（如 doubao-seed-character-260628），或填 ep- 接入点 ID。
            填完点「测试连接」自检，通过后再保存。
          </p>
          <label>思考（推理）模式</label>
          <n-select v-model:value="settings.llm.thinking" :options="thinkingOptions" />
          <p class="hint">
            思考模式会先推理再回答，更聪明但首句变慢。部分模型不支持切换
            （如百炼 kimi-k3 只能思考），报错时请改回「跟随模型默认」。
          </p>
          <label>温度 temperature（越高越活泼发散，{{ settings.llm.temperature.toFixed(2) }}）</label>
          <n-slider v-model:value="settings.llm.temperature"
                    :min="0" :max="1.5" :step="0.05" />
          <label>top_p 采样（一般不用动，{{ settings.llm.top_p.toFixed(2) }}）</label>
          <n-slider v-model:value="settings.llm.top_p"
                    :min="0.1" :max="1" :step="0.05" />
          <label>回复长度上限 max_tokens（0 = 用服务商默认）</label>
          <n-input-number v-model:value="settings.llm.max_tokens"
                          :min="0" :max="32768" :step="256" style="width: 200px" />
          <p class="hint">
            不填 Key 也能用：聊天会用本地预设回复兜底，语音、口型、舞蹈全部可用。
          </p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="voice" tab="语音">
        <div class="form">
          <p v-if="hwHint" class="hint">{{ hwHint }}</p>
          <h3 class="section-title">语音识别 ASR</h3>
          <label>识别引擎（与合成互相独立）</label>
          <n-select v-model:value="settings.stt.engine" :options="asrEngineOptions" />
          <p class="hint">
            在线：Chrome/Edge 的 Web Speech，走云端。离线：SenseVoice-Small INT8，CPU 实时，约 230MB。开麦后由浏览器端 Silero VAD 检测说话起止，切出语音段再识别。
          </p>
          <div v-if="settings.stt.engine === 'sensevoice'" class="speech-status">
            <p class="hint">{{ speechStatus?.asr.message || '查询状态中…' }}</p>
            <n-button size="small" :loading="warmingAsr || !!speechStatus?.asr.downloading"
                      @click="warmup('asr')">准备 / 下载模型</n-button>
          </div>

          <h3 class="section-title">语音合成 TTS</h3>
          <label>合成引擎</label>
          <n-select v-model:value="settings.tts.engine" :options="ttsEngineOptions" />
          <template v-if="settings.tts.engine === 'qwen'">
            <label>模型规格</label>
            <n-select v-model:value="settings.tts.qwen_size" :options="qwenSizeOptions" />
            <p class="hint">
              0.6B 更快更省显存；1.7B 音质更好。两套共用下面 9 个音色，切换会卸载当前模型再加载。
              0.6B {{ speechStatus?.tts.sizes?.['0.6b']?.installed ? '已在本地' : '未下载' }}
              · 1.7B {{ speechStatus?.tts.sizes?.['1.7b']?.installed ? '已在本地' : '未下载（约 4GB）' }}
              <template v-if="speechStatus?.tts.size">
                · 当前内存 {{ speechStatus.tts.size === '1.7b' ? '1.7B' : '0.6B' }}
              </template>
            </p>
            <label>语气风格</label>
            <n-select v-model:value="settings.tts.qwen_style" :options="qwenStyleOptions" />
            <n-input v-if="settings.tts.qwen_style === 'custom'"
                     v-model:value="settings.tts.qwen_instruct" type="textarea"
                     :autosize="{ minRows: 2, maxRows: 4 }"
                     placeholder="例如：用低沉磁性、带一点气声的御姐语气，慢慢说。" />
            <p class="hint">
              语气只在 1.7B 生效，0.6B 会忽略。清宵建议：1.7B + 塞蕾娜 + 清冷御姐。
              换语气不用重新加载模型，保存后下一句就变。
            </p>
          </template>
          <label>默认音色</label>
          <n-select v-model:value="settings.tts.voice" :options="voiceOptions" filterable
                    :fallback-option="false" placeholder="请选择当前引擎的音色"
                    :disabled="!ttsNeedsVoice" />
          <p class="hint">
            只显示当前引擎支持的音色，不会自动换成别的声音。
            角色卡若填了同引擎的音色，对话时用角色的；没填或引擎对不上，用这里的。
            Qwen 走本机 GPU，PCM 边生成边播。edge-tts / CosyVoice 是云端备选。
          </p>
          <label>上一轮还在说时，下一轮 QA 怎么接</label>
          <n-select v-model:value="settings.tts.duplex_cmd" :options="duplexCmdOptions" />
          <label>剩余音频超过 {{ Number(settings.tts.duplex_remain_sec).toFixed(1) }} 秒才打断</label>
          <n-slider v-model:value="settings.tts.duplex_remain_sec"
                    :min="1" :max="8" :step="0.5" />
          <label>超时续聊 Delayed（大约 {{ settings.tts.duplex_delayed_sec }} 秒，0 关闭；每次在附近随机）</label>
          <n-slider v-model:value="settings.tts.duplex_delayed_sec"
                    :min="0" :max="40" :step="1" />
          <label>主动搭话 Proactive（大约 {{ settings.tts.duplex_proactive_sec }} 秒，0 关闭；每次在附近随机）</label>
          <n-slider v-model:value="settings.tts.duplex_proactive_sec"
                    :min="0" :max="90" :step="1" />
          <label>用户沉默告别 Goodbye（大约 {{ settings.tts.duplex_goodbye_sec }} 秒，0 关闭；每次在附近随机）</label>
          <n-slider v-model:value="settings.tts.duplex_goodbye_sec"
                    :min="0" :max="300" :step="5" />
          <label>会话总长告别 SessionTimeover（分钟，0 关闭；会略微抖动）</label>
          <n-slider v-model:value="settings.tts.duplex_session_max_min"
                    :min="0" :max="60" :step="1" />
          <div class="switch-row">
            <span>插话分流：跳舞/说话时，夸奖先听着，有事才打断</span>
            <n-switch v-model:value="settings.tts.duplex_ingress" />
          </div>
          <p class="hint">
            同一轮回复按完整句子切成 A1、A2、A3 多段音频：只排队顺播，互不打断。
            你又问了一句、上一轮还在播：剩得比上面的秒数多就切到新回答，少就让当前这句说完再播新的；上一轮还没开口的后半段丢掉。
            插话分流开着时：正在跳舞你说「跳的真好」不会停，说「换一支」才会停；正在说话时，嗯啊先记下，问句才开新一轮。语音也等出字再判，不会一出声就掐表演。
            双方都沉默时：先过一会儿再续聊（大约 10–28 秒，不会卡在整 6 秒），再过一阵主动搭话（大约半分钟到一分多），再按你多久没开口告别（大约 1.5–3.5 分钟）。每次都在区间里随机，像人在想要不要再开口。会话总长到了也会告别，之后不再自动说话，你开口才继续。
          </p>
          <p v-if="settings.tts.engine === 'cosy'" class="hint">
            音色是 CosyVoice 龙安系列（如龙安欢），和本地 Qwen 的 Vivian/Dylan、微软晓伊不是同一套，需重新选。
          </p>
          <div v-if="settings.tts.engine === 'qwen'" class="speech-status">
            <p class="hint">
              {{ speechStatus?.tts.message || '查询状态中…' }}
              <template v-if="speechStatus?.tts.gpu"> · 检测到 NVIDIA GPU</template>
            </p>
            <n-button size="small"
                      :loading="warmingTts || !!speechStatus?.tts.loading || !!speechStatus?.tts.downloading"
                      @click="warmup('tts')">加载 / 切换规格</n-button>
          </div>
        </div>
      </n-tab-pane>
      <n-tab-pane name="download" tab="下载">
        <div class="form">
          <label>模之屋登录 Token（部分作品要求点赞/收藏后下载，需要登录态）</label>
          <n-input v-model:value="settings.download.aplaybox_token" type="password"
                   show-password-on="click" placeholder="浏览器登录模之屋后，从开发者工具请求头里复制 token" />
          <p class="hint">
            获取方法：浏览器登录 aplaybox.com → F12 打开开发者工具 → 网络面板 →
            任意 api.aplaybox.com 请求 → 请求头中的 token 字段。
            自动满足下载规则会用你的账号点赞/收藏/关注作品作者。
          </p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="quality" tab="画质">
        <div class="form">
          <div class="switch-row">
            <span>物理模拟（头发/裙摆摆动，低配机可关闭）</span>
            <n-switch v-model:value="settings.quality.physics"
                      @update:value="onPhysics" />
          </div>
          <p class="hint">仅对 PMX 模型有效。开关立刻生效并记住。</p>
          <label>渲染分辨率上限（devicePixelRatio）</label>
          <n-slider v-model:value="settings.quality.pixel_ratio_cap"
                    :min="1" :max="3" :step="0.5" />
          <label>灯光亮度（觉得模型偏亮/偏暗时微调，1.0 为标准）</label>
          <n-slider v-model:value="settings.quality.light_level"
                    :min="0.5" :max="1.5" :step="0.05"
                    :format-tooltip="(v: number) => v.toFixed(2) + '×'"
                    @update:value="settings.applyQuality()" />
          <label>舞蹈 BGM 音量</label>
          <n-slider v-model:value="settings.quality.bgm_volume"
                    :min="0" :max="1" :step="0.05"
                    :format-tooltip="(v: number) => Math.round(v * 100) + '%'"
                    @update:value="settings.applyQuality()" />
          <label>预制场景（AI 生成，点击切换）</label>
          <p v-if="settings.modules.scenes" class="hint">
            情境开着时背景跟今晚这场戏走，点这里会换成对应那场，不再另存一套。
          </p>
          <div class="scene-presets">
            <div v-for="s in SCENE_PRESETS" :key="s.value" class="scene-card"
                 :class="{ active: settings.modules.scenes
                   ? sceneSession.current?.background === s.value
                   : settings.quality.background_image === s.value }"
                 :title="s.label" @click="pickPresetLook(s)">
              <img :src="s.value" :alt="s.label" loading="lazy" />
              <span>{{ s.label }}</span>
            </div>
          </div>
          <label>纯色背景</label>
          <div class="bg-presets">
            <div v-for="p in BG_PRESETS" :key="p.value" class="bg-swatch"
                 :class="{ active: !settings.quality.background_image
                             && settings.quality.background_color === p.value }"
                 :style="{ background: p.value }" :title="p.label"
                 @click="pickBgColor(p.value)" />
            <n-color-picker
              :value="settings.quality.background_color" :show-alpha="false"
              :modes="['hex']" class="bg-picker"
              @update:value="pickBgColor" />
          </div>
          <div class="bg-image-row">
            <n-button size="small" @click="bgFileInput?.click()">
              {{ settings.quality.background_image ? '更换自定义图片' : '使用自定义图片…' }}
            </n-button>
            <n-button v-if="settings.quality.background_image" size="small" quaternary
                      @click="clearBgImage">恢复纯色背景</n-button>
            <input ref="bgFileInput" type="file" accept="image/*" hidden
                   @change="onBgImageChosen" />
          </div>
          <div class="switch-row" style="margin-top: 10px">
            <span>圆形舞台底座</span>
            <n-switch v-model:value="settings.quality.stage_show"
                      @update:value="settings.applyQuality()" />
          </div>
          <template v-if="settings.quality.stage_show">
            <div class="style-chips">
              <n-button v-for="s in STAGE_STYLES" :key="s.value" size="tiny" round
                        :type="settings.quality.stage_style === s.value ? 'primary' : 'default'"
                        :secondary="settings.quality.stage_style !== s.value"
                        @click="settings.quality.stage_style = s.value; settings.applyQuality()">
                {{ s.label }}
              </n-button>
            </div>
            <label>台面贴图（选场景时自动配套，可手动更换）</label>
            <div class="tex-presets">
              <div v-for="t in STAGE_TEXTURES" :key="t.value" class="tex-card"
                   :class="{ active: settings.quality.stage_texture === t.value }"
                   :title="t.label"
                   @click="settings.quality.stage_texture = t.value; settings.applyQuality()">
                <img v-if="t.value" :src="t.value" :alt="t.label" loading="lazy" />
                <div v-else class="tex-none"
                     :style="{ background: settings.quality.stage_color }" />
                <span>{{ t.label }}</span>
              </div>
            </div>
            <div class="stage-colors">
              <div class="stage-color-item">
                <span>台面颜色</span>
                <n-color-picker v-model:value="settings.quality.stage_color"
                                :show-alpha="false" :modes="['hex']" class="bg-picker"
                                @update:value="settings.applyQuality()" />
              </div>
              <div class="stage-color-item">
                <span>发光色</span>
                <n-color-picker v-model:value="settings.quality.stage_glow"
                                :show-alpha="false" :modes="['hex']" class="bg-picker"
                                @update:value="settings.applyQuality()" />
              </div>
            </div>
            <label>底座不透明度（调低可透出背景，更好地融入场景）</label>
            <n-slider v-model:value="settings.quality.stage_opacity"
                      :min="0.15" :max="1" :step="0.05"
                      :format-tooltip="(v: number) => Math.round(v * 100) + '%'"
                      @update:value="settings.applyQuality()" />
          </template>
          <p class="hint">选择即时生效；点下方「保存」才会记住。图片场景会自动关闭景深雾，只保留圆形舞台底座。</p>
        </div>
      </n-tab-pane>
    </n-tabs>
    <template #footer>
      <div style="display:flex;justify-content:flex-end;gap:10px;width:100%">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" @click="save">保存</n-button>
      </div>
    </template>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
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
