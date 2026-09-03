<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  NButton, NDrawer, NDrawerContent, NInput, NPopconfirm, NSelect, useMessage,
} from 'naive-ui';
import type { CharacterItem } from '../../api/client';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { catLabel, parseMotionCat, stripCatPrefix } from '../assets/motionMeta';
import { PERSONA_TEMPLATE_OPTIONS, genericPersona, personaTemplate } from './personas';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const characters = useCharacterStore();
const assets = useAssetsStore();
const settings = useSettingsStore();
const chat = useChatStore();
const message = useMessage();

const editing = ref<CharacterItem | null>(null);

// 情绪映射编辑：每种情绪可叠加模型自带的形态键
const EMO_LABELS: { key: string; label: string }[] = [
  { key: 'happy', label: '开心' },
  { key: 'angry', label: '生气' },
  { key: 'sad', label: '伤心' },
  { key: 'relaxed', label: '放松' },
];
const emotionMap = ref<Record<string, string[]>>({});

const morphOptions = computed(() =>
  (characters.modelInfo?.morphNames ?? []).map((n) => ({ label: n, value: n }))
);

function parseMap(json: string) {
  try {
    const obj = JSON.parse(json || '{}');
    return typeof obj === 'object' && obj ? obj : {};
  } catch {
    return {};
  }
}

const modelOptions = computed(() =>
  assets.models.map((m) => ({ label: `${m.label} (${m.fmt})`, value: m.id }))
);
const voiceOptions = computed(() =>
  settings.voices
    .filter((v) => !v.engine || v.engine === settings.tts.engine)
    .map((v) => ({ label: v.label, value: v.id }))
);
const motionOptions = computed(() => [
  { label: '（无）', value: '' },
  ...assets.motions.map((m) => ({
    label: `${catLabel(parseMotionCat(m))} · ${stripCatPrefix(m.label)}`,
    value: m.name,
  })),
]);

watch(() => props.show, (v) => {
  if (v && characters.current) {
    editing.value = { ...characters.current };
    const ids = voiceOptions.value.map((o) => o.value);
    if (editing.value.voice && !ids.includes(editing.value.voice)) {
      editing.value.voice = '';
    }
    emotionMap.value = parseMap(characters.current.emotion_map);
  }
});

async function switchTo(id: number) {
  await characters.switchTo(id);
  if (characters.current) {
    editing.value = { ...characters.current };
    emotionMap.value = parseMap(characters.current.emotion_map);
  }
  await chat.loadHistory();
  await chat.beginVisit();
}

// 红线层管暧昧的上限；露骨违法在任何档都挡。角色平时的口吻由人设卡决定
const boundaryOptions = [
  { label: '清爽：全年龄向，暧昧也不接茬', value: 'strict' },
  { label: '心动：接得住暧昧、若即若离，不主动撩', value: 'warm' },
  { label: '可撩：撩骚擦边可聊可回撩，露骨仍挡', value: 'flirt' },
  { label: '恋人：亲密称呼撒娇吃醋都行，露骨仍挡', value: 'lover' },
  { label: '自由：不设上限，分寸由人设和对话把握', value: 'free' },
];

function applyTemplate(id: string | null) {
  if (!id || !editing.value) return;
  editing.value.persona = personaTemplate(id, editing.value.name || '新角色');
  message.info('已套用模板，记得保存');
}

async function save() {
  if (!editing.value) return;
  editing.value.emotion_map = JSON.stringify(emotionMap.value);
  await characters.save(editing.value);
  message.success('已保存');
}

async function createNew() {
  const created = await characters.create({
    name: '新角色',
    model_asset_id: assets.models[0]?.id ?? 0,
    persona: genericPersona('新角色'),
    voice: '',
  });
  await switchTo(created.id!);
}

async function removeCurrent() {
  if (!editing.value?.id) return;
  await characters.remove(editing.value.id);
  editing.value = characters.current ? { ...characters.current } : null;
}
</script>

<template>
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="480" placement="right" show-mask="transparent" to="body">
    <n-drawer-content title="角色管理" closable :native-scrollbar="false">
    <div class="body">
      <div class="list">
        <div v-for="c in characters.list" :key="c.id"
             class="item" :class="{ active: c.id === characters.currentId }"
             @click="switchTo(c.id!)">
          <span class="item-avatar">{{ c.name.slice(0, 1) }}</span>
          <span>{{ c.name }}</span>
        </div>
        <n-button dashed size="small" @click="createNew">+ 新建角色</n-button>
      </div>

      <div v-if="editing" class="form">
        <label>名字</label>
        <n-input v-model:value="editing.name" />
        <label>绑定模型</label>
        <n-select v-model:value="editing.model_asset_id" :options="modelOptions" />
        <label>声音（跟随设置里的 TTS 引擎）</label>
        <n-select v-model:value="editing.voice" :options="voiceOptions" filterable
                  :fallback-option="false" placeholder="空=用设置里的默认音色"
                  :disabled="settings.tts.engine !== 'edge' && settings.tts.engine !== 'qwen' && settings.tts.engine !== 'cosy'" />
        <label>聊天尺度（越界请求的挡法由后端红线层控制）</label>
        <n-select :value="editing.boundary || 'free'" :options="boundaryOptions"
                  @update:value="(v: string) => { if (editing) editing.boundary = v; }" />
        <label>人设（System Prompt）</label>
        <n-select :value="null" :options="PERSONA_TEMPLATE_OPTIONS" size="small"
                  placeholder="套用人设模板（会覆盖下方人设，按角色名代入）"
                  @update:value="applyTemplate" />
        <n-input v-model:value="editing.persona" type="textarea" :rows="14"
                 placeholder="身份、怎么接下一句、临时扮演进出、对白样例。见 docs/persona-guide.md" />
        <label>打招呼语</label>
        <n-input v-model:value="editing.greeting" />
        <label>闲时动作偏好（进入闲时池轮换，不再单条死循环）</label>
        <n-select v-model:value="editing.idle_motion" :options="motionOptions" />
        <label>情绪映射（在内置表情之上，叠加模型自带形态键）</label>
        <div v-for="e in EMO_LABELS" :key="e.key" class="emo-row">
          <span class="emo-label">{{ e.label }}</span>
          <n-select v-model:value="emotionMap[e.key]" multiple filterable clearable
                    size="small" :options="morphOptions"
                    :placeholder="`选择「${e.label}」时叠加的形态键`" />
        </div>
        <div class="form-actions">
          <n-button type="primary" @click="save">保存</n-button>
          <n-popconfirm @positive-click="removeCurrent">
            <template #trigger>
              <n-button quaternary type="error" :disabled="characters.list.length <= 1">
                删除角色
              </n-button>
            </template>
            确定删除该角色？聊天记录也会失效。
          </n-popconfirm>
        </div>
      </div>
    </div>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
/* 抽屉里改为上下布局：角色列表横排在上，编辑表单在下 */
.body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  font-size: 14px;
}

.item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.item.active {
  background: rgba(91, 91, 214, 0.18);
  border-color: rgba(91, 91, 214, 0.5);
}

.item-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #5b5bd6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #fff;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form label {
  font-size: 12px;
  opacity: 0.65;
  margin-top: 4px;
}

.form-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.emo-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.emo-label {
  width: 34px;
  flex-shrink: 0;
  font-size: 12px;
  opacity: 0.7;
}
</style>
