<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  NButton, NDrawer, NDrawerContent, NInput, NInputNumber, NPopconfirm, NSelect,
  NSwitch, useMessage,
} from 'naive-ui';
import type { CharacterItem } from '../../api/client';
import { api } from '../../api/client';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { parseMotionCat, stripCatPrefix } from '../assets/motionMeta';
import { t } from '../../i18n';
import { personaOptions, personaTemplate } from './personas';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const characters = useCharacterStore();
const assets = useAssetsStore();
const settings = useSettingsStore();
const chat = useChatStore();
const message = useMessage();

const editing = ref<CharacterItem | null>(null);

// 情绪映射编辑：每种情绪可叠加模型自带的形态键
const EMO_KEYS = ['happy', 'angry', 'sad', 'relaxed'] as const;
const emotionMap = ref<Record<string, string[]>>({});

// 角色卡 v2：世界书条目编辑态（存结构化行，保存时序列化进 Character.lorebook）
interface LorebookRow {
  keys: string;
  content: string;
  constant: boolean;
  enabled: boolean;
  selective: boolean;
  selective_keys: string;
  order: number;
  position: 'before_char' | 'before_hist';
}
const lorebookRows = ref<LorebookRow[]>([]);
const greetingsText = ref('');

const lorebookPositionOptions = computed(() => [
  { label: t('char.lorebookPosChar'), value: 'before_char' },
  { label: t('char.lorebookPosMid'), value: 'after_char' },
  { label: t('char.lorebookPosHist'), value: 'before_hist' },
]);

function emptyLorebookRow(): LorebookRow {
  return {
    keys: '', content: '', constant: false, enabled: true,
    selective: false, selective_keys: '', order: 100, position: 'before_char',
  };
}

function parseLorebookRows(json: string): LorebookRow[] {
  try {
    const arr = JSON.parse(json || '[]');
    if (!Array.isArray(arr)) return [];
    return arr.map((e: Record<string, unknown>) => ({
      keys: Array.isArray(e.keys) ? (e.keys as string[]).join(', ') : String(e.keys || ''),
      content: String(e.content || ''),
      constant: !!e.constant,
      enabled: e.enabled !== false,
      selective: !!e.selective,
      selective_keys: Array.isArray(e.selective_keys)
        ? (e.selective_keys as string[]).join(', ') : String(e.selective_keys || ''),
      order: Number(e.order ?? 100) || 100,
      position: e.position === 'before_hist' ? 'before_hist' : 'before_char',
    }));
  } catch {
    return [];
  }
}

function serializeLorebook(rows: LorebookRow[]): string {
  const list = rows
    .filter((r) => (r.keys.trim() || r.constant) && r.content.trim())
    .map((r) => ({
      keys: r.keys.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      content: r.content,
      constant: r.constant,
      enabled: r.enabled,
      selective: r.selective,
      selective_keys: r.selective_keys.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      order: r.order,
      position: r.position,
    }));
  return JSON.stringify(list);
}

function splitLines(text: string): string[] {
  return text.split('\n').map((s) => s.trim()).filter(Boolean);
}

const greetingVariants = computed(() => splitLines(greetingsText.value));

function nextGreeting() {
  if (!editing.value || greetingVariants.value.length < 2) return;
  const cur = editing.value.greeting || '';
  const idx = greetingVariants.value.indexOf(cur);
  editing.value.greeting = greetingVariants.value[(idx + 1) % greetingVariants.value.length];
}

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
const motionOptions = computed(() => {
  settings.locale.ui;
  return [
    { label: t('char.noIdle'), value: '' },
    ...assets.motions.map((m) => ({
      label: `${t(`cat.${parseMotionCat(m)}`)} · ${stripCatPrefix(m.label)}`,
      value: m.name,
    })),
  ];
});

function fillEditor(c: CharacterItem) {
  editing.value = { ...c };
  const ids = voiceOptions.value.map((o) => o.value);
  if (editing.value.voice && !ids.includes(editing.value.voice)) {
    editing.value.voice = '';
  }
  emotionMap.value = parseMap(c.emotion_map);
  lorebookRows.value = parseLorebookRows(c.lorebook || '[]');
  greetingsText.value = splitLines(
    (() => { try { return JSON.parse(c.greetings || '[]').join('\n'); } catch { return ''; } })(),
  ).join('\n');
}

watch(() => props.show, (v) => {
  if (v && characters.current) {
    fillEditor(characters.current);
  }
});

async function switchTo(id: number) {
  await characters.switchTo(id);
  if (characters.current) {
    fillEditor(characters.current);
  }
  await chat.loadHistory();
  await chat.beginVisit();
}

// 红线层管暧昧的上限；露骨违法在任何档都挡。角色平时的口吻由人设卡决定
const boundaryOptions = computed(() => {
  settings.locale.ui;
  return ['strict', 'warm', 'flirt', 'lover', 'free'].map((value) => ({
    value,
    label: t(`bound.${value}`),
  }));
});

function applyTemplate(id: string | null) {
  if (!id || !editing.value) return;
  editing.value.persona = personaTemplate(id, editing.value.name || t('char.untitled'));
  message.info(t('char.applied'));
}

async function save() {
  if (!editing.value) return;
  editing.value.emotion_map = JSON.stringify(emotionMap.value);
  editing.value.lorebook = serializeLorebook(lorebookRows.value);
  editing.value.greetings = JSON.stringify(splitLines(greetingsText.value));
  await characters.save(editing.value);
  message.success(t('char.saved'));
}

async function createNew() {
  const created = await characters.create({
    name: t('char.untitled'),
    model_asset_id: assets.models[0]?.id ?? 0,
    persona: personaTemplate(settings.locale.reply === 'zh-CN' ? 'puppygf' : 'generic', t('char.untitled')),
    boundary: 'free',
    voice: '',
  });
  await switchTo(created.id!);
}

async function removeCurrent() {
  if (!editing.value?.id) return;
  await characters.remove(editing.value.id);
  editing.value = characters.current ? { ...characters.current } : null;
}

// --- 酒馆卡导入 / 导出 ---
const importInput = ref<HTMLInputElement | null>(null);
const importing = ref(false);
const showSources = ref(false);

function pickImport() {
  importInput.value?.click();
}

async function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file || importing.value) return;
  importing.value = true;
  try {
    const created = await api.importCharacter(file);
    await characters.loadList();
    await switchTo(created.id!);
    message.success(t('char.imported', { name: created.name }));
  } catch (e) {
    message.error(t('char.importFail', { err: String(e) }), { duration: 6000, closable: true });
  } finally {
    importing.value = false;
  }
}

function exportCurrent() {
  const id = editing.value?.id ?? characters.currentId;
  if (!id) return;
  const a = document.createElement('a');
  a.href = api.characterExportUrl(id);
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function avatarUrl(c: CharacterItem): string {
  return c.avatar_path ? api.characterAvatarUrl(c.id!) : '';
}
</script>

<template>
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="480" placement="right" show-mask="transparent" to="body">
    <n-drawer-content :title="t('char.title')" closable :native-scrollbar="false">
    <div class="body">
      <div class="list">
        <div v-for="c in characters.list" :key="c.id"
             class="item" :class="{ active: c.id === characters.currentId }"
             @click="switchTo(c.id!)">
          <img v-if="avatarUrl(c)" class="item-avatar img" :src="avatarUrl(c)" alt="" />
          <span v-else class="item-avatar">{{ c.name.slice(0, 1) }}</span>
          <span>{{ c.name }}</span>
        </div>
        <n-button dashed size="small" @click="createNew">+ {{ t('char.new') }}</n-button>
        <div class="list-actions">
          <n-button size="small" :loading="importing" @click="pickImport">
            {{ t('char.import') }}
          </n-button>
          <n-button size="small" :disabled="!editing?.id" @click="exportCurrent">
            {{ t('char.export') }}
          </n-button>
          <input ref="importInput" type="file" accept=".png,.json" hidden
                 @change="onImportFile" />
        </div>
      </div>

      <button class="sources-toggle" type="button" @click="showSources = !showSources">
        {{ t('char.sources') }}
      </button>
      <div v-if="showSources" class="sources">
        <a href="https://chub.ai" target="_blank" rel="noopener">
          chub.ai<span class="src-desc">{{ t('char.sourceChub') }}</span>
        </a>
        <a href="https://aicharactercards.com" target="_blank" rel="noopener">
          aicharactercards.com<span class="src-desc">{{ t('char.sourceAicc') }}</span>
        </a>
        <a href="https://character-tavern.com" target="_blank" rel="noopener">
          character-tavern.com<span class="src-desc">{{ t('char.sourceCt') }}</span>
        </a>
        <p class="hint">{{ t('char.sourcesHint') }}</p>
      </div>

      <div v-if="editing" class="form">
        <label>{{ t('char.name') }}</label>
        <n-input v-model:value="editing.name" />
        <label>{{ t('char.model') }}</label>
        <n-select v-model:value="editing.model_asset_id" :options="modelOptions" />
        <label>{{ t('char.voice') }}</label>
        <n-select v-model:value="editing.voice" :options="voiceOptions" filterable
                  :fallback-option="false" :placeholder="t('char.voicePh')"
                  :disabled="settings.tts.engine !== 'edge' && settings.tts.engine !== 'qwen' && settings.tts.engine !== 'cosy' && settings.tts.engine !== 'volc' && settings.tts.engine !== 'openai' && settings.tts.engine !== 'eleven' && settings.tts.engine !== 'gemini' && settings.tts.engine !== 'mimo'" />
        <label>{{ t('char.boundary') }}</label>
        <n-select :value="editing.boundary || 'free'" :options="boundaryOptions"
                  @update:value="(v: string) => { if (editing) editing.boundary = v; }" />
        <label>{{ t('char.persona') }}</label>
        <n-select :value="null" :options="personaOptions()" size="small"
                  :placeholder="t('char.personaPh')"
                  @update:value="applyTemplate" />
        <n-input v-model:value="editing.persona" type="textarea" :rows="14"
                 :placeholder="t('char.personaBody')" />
        <label>{{ t('char.personality') }}</label>
        <n-input v-model:value="editing.personality" type="textarea" :rows="2"
                 :placeholder="t('char.personalityPh')" />
        <label>{{ t('char.scenario') }}</label>
        <n-input v-model:value="editing.scenario" type="textarea" :rows="2"
                 :placeholder="t('char.scenarioPh')" />
        <label>{{ t('char.mesExample') }}</label>
        <n-input v-model:value="editing.mes_example" type="textarea" :rows="3"
                 :placeholder="t('char.mesExamplePh')" />
        <label>{{ t('char.greeting') }}</label>
        <div class="greeting-row">
          <n-input v-model:value="editing.greeting" />
          <n-button size="tiny" :disabled="greetingVariants.length < 2"
                    @click="nextGreeting">{{ t('char.greetingNext') }}</n-button>
        </div>
        <label>{{ t('char.greetings') }}</label>
        <n-input v-model:value="greetingsText" type="textarea" :rows="2"
                 :placeholder="t('char.greetingsPh')" />
        <label>{{ t('char.tags') }}</label>
        <n-input v-model:value="editing.tags" :placeholder="t('char.tagsPh')" />
        <label>{{ t('char.creator') }}</label>
        <n-input v-model:value="editing.creator" />

        <div class="lorebook-head">
          <label>{{ t('char.lorebook') }}</label>
          <n-button size="tiny" dashed @click="lorebookRows.push(emptyLorebookRow())">
            + {{ t('char.lorebookAdd') }}
          </n-button>
        </div>
        <p class="hint">{{ t('char.lorebookHint') }}</p>
        <div v-for="(row, idx) in lorebookRows" :key="idx" class="lorebook-row">
          <div class="lb-bar">
            <n-input v-model:value="row.keys" size="small"
                     :placeholder="t('char.lorebookKeysPh')" />
            <n-input-number v-model:value="row.order" size="small" :min="0" :max="9999"
                            style="width: 84px" :placeholder="t('char.lorebookOrder')" />
            <n-select v-model:value="row.position" size="small" :options="lorebookPositionOptions"
                      style="width: 104px" />
            <n-switch v-model:value="row.enabled" size="small" />
            <n-button size="tiny" quaternary type="error"
                      @click="lorebookRows.splice(idx, 1)">×</n-button>
          </div>
          <n-input v-model:value="row.content" type="textarea" :rows="2" size="small"
                   :placeholder="t('char.lorebookContentPh')" />
          <div class="lb-flags">
            <label class="lb-flag">
              <n-switch v-model:value="row.constant" size="small" />
              <span>{{ t('char.lorebookConstant') }}</span>
            </label>
            <label class="lb-flag">
              <n-switch v-model:value="row.selective" size="small" />
              <span>{{ t('char.lorebookSelective') }}</span>
            </label>
            <n-input v-if="row.selective" v-model:value="row.selective_keys" size="small"
                     :placeholder="t('char.lorebookSecPh')" style="flex: 1" />
          </div>
        </div>

        <label>{{ t('char.idle') }}</label>
        <n-select v-model:value="editing.idle_motion" :options="motionOptions" />
        <label>{{ t('char.morph') }}</label>
        <div v-for="key in EMO_KEYS" :key="key" class="emo-row">
          <span class="emo-label">{{ t('emo.' + key) }}</span>
          <n-select v-model:value="emotionMap[key]" multiple filterable clearable
                    size="small" :options="morphOptions"
                    :placeholder="t('char.morphPh', { name: t('emo.' + key) })" />
        </div>
        <div class="form-actions">
          <n-button type="primary" @click="save">{{ t('settings.save') }}</n-button>
          <n-popconfirm @positive-click="removeCurrent">
            <template #trigger>
              <n-button quaternary type="error" :disabled="characters.list.length <= 1">
                {{ t('char.delete') }}
              </n-button>
            </template>
            {{ t('char.deleteAsk') }}
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
  flex-shrink: 0;
}

.item-avatar.img {
  object-fit: cover;
  background: none;
}

.sources-toggle {
  background: none;
  border: none;
  color: #8b8bd6;
  font-size: 12px;
  text-align: left;
  padding: 0;
  cursor: pointer;
  width: fit-content;
}

.sources-toggle:hover {
  color: #b0b0ff;
}

.sources {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  font-size: 12px;
}

.sources a {
  color: #b0b0ff;
  text-decoration: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sources a:hover {
  text-decoration: underline;
}

.src-desc {
  opacity: 0.6;
  font-size: 11px;
}

.greeting-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.list-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
  width: 100%;
  justify-content: flex-end;
}

.lorebook-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.lorebook-head label {
  margin-top: 0;
}

.hint {
  font-size: 12px;
  opacity: 0.55;
  margin: 0;
}

.lorebook-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
}

.lb-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.lb-flags {
  display: flex;
  align-items: center;
  gap: 12px;
}

.lb-flag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  opacity: 0.75;
  margin-top: 0;
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
