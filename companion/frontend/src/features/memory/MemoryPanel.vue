<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { NButton, NInput, NSelect } from 'naive-ui';
import { api } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { memorySession, refreshMemory } from './session';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';

const characters = useCharacterStore();
const settings = useSettingsStore();
const draft = ref('');
const kind = ref('event');
const editingId = ref<string | null>(null);
const editText = ref('');
const busyId = ref<string | null>(null);
const kinds = computed(() => {
  settings.locale.ui;
  return ['preference', 'person', 'event', 'open_loop', 'trait'].map((value) => ({
    value,
    label: t(`mem.${value}`),
  }));
});

function kindText(kind: string) {
  settings.locale.ui;
  const key = `mem.${kind}`;
  const hit = t(key);
  return hit === key ? kind : hit;
}

const facts = computed(() => memorySession.facts);
const pins = computed(() => memorySession.pins);
const episodes = computed(() => memorySession.episodes);
const nothing = computed(() => !facts.value.length && !pins.value.length && !episodes.value.length);

watch(() => characters.currentId, (id) => {
  if (id && memorySession.open) void refreshMemory(id);
});
watch(() => memorySession.open, (open) => {
  if (open && characters.currentId) void refreshMemory(characters.currentId);
});

async function pin(id: string, pinned: boolean) {
  const row = facts.value.find((f) => f.id === id);
  if (!row || !characters.currentId) return;
  busyId.value = id;
  try {
    await api.saveMemory({
      character_id: characters.currentId, id, kind: row.kind,
      content: row.content, importance: row.importance, pinned,
    });
    await refreshMemory(characters.currentId);
  } finally {
    busyId.value = null;
  }
}

async function forget(id: string) {
  if (!characters.currentId) return;
  busyId.value = id;
  try {
    await api.deleteMemory(characters.currentId, id);
    if (editingId.value === id) editingId.value = null;
    await refreshMemory(characters.currentId);
  } finally {
    busyId.value = null;
  }
}

function startEdit(id: string, content: string) {
  editingId.value = id;
  editText.value = content;
}

async function commitEdit() {
  const id = editingId.value;
  if (!id || !characters.currentId) return;
  const row = facts.value.find((f) => f.id === id);
  const text = editText.value.trim();
  editingId.value = null;
  if (!row || !text || text === row.content) return;
  busyId.value = id;
  try {
    await api.saveMemory({
      character_id: characters.currentId, id, kind: row.kind,
      content: text, importance: row.importance, pinned: row.pinned,
    });
    await refreshMemory(characters.currentId);
  } finally {
    busyId.value = null;
  }
}

async function unpinLine(id: string) {
  if (!characters.currentId) return;
  busyId.value = `pin-${id}`;
  try {
    await api.unpinMessage(characters.currentId, id);
    await refreshMemory(characters.currentId);
  } finally {
    busyId.value = null;
  }
}

async function dropEpisode(id: string) {
  if (!characters.currentId) return;
  busyId.value = `ep-${id}`;
  try {
    await api.deleteEpisode(characters.currentId, id);
    await refreshMemory(characters.currentId);
  } finally {
    busyId.value = null;
  }
}

async function add() {
  const text = draft.value.trim();
  if (!text || !characters.currentId) return;
  await api.saveMemory({
    character_id: characters.currentId, kind: kind.value, content: text, importance: 0.7, pinned: false,
  });
  draft.value = '';
  await refreshMemory(characters.currentId);
}
</script>

<template>
  <div v-if="memorySession.open" class="mem">
    <div class="mem-head">
      <span>{{ t('mem.title') }}{{ facts.length || pins.length ? ` · ${facts.length + pins.length}` : '' }}</span>
      <button class="x" @click="memorySession.open = false">{{ t('mem.close') }}</button>
    </div>
    <div class="mem-list">
      <div v-if="memorySession.loading && nothing" class="empty">{{ t('mem.loading') }}</div>
      <div v-else-if="nothing" class="empty">{{ t('mem.empty') }}</div>
      <template v-if="pins.length">
        <p class="group">{{ t('mem.quotes') }}</p>
        <div v-for="p in pins" :key="`pin-${p.id}`" class="fact" :class="{ busy: busyId === `pin-${p.id}` }">
          <div class="fact-top">
            <span class="pin">{{ t('mem.pinnedLine') }}</span>
            <span v-if="p.kind === 'rp'" class="tag">{{ t('mem.rp') }}</span>
            <span class="grow" />
            <button @click="unpinLine(p.id)">{{ t('mem.unpin') }}</button>
          </div>
          <p>{{ p.content }}</p>
        </div>
      </template>
      <template v-if="episodes.length">
        <p class="group">{{ t('mem.episodes') }}</p>
        <div v-for="ep in episodes" :key="`ep-${ep.id}`" class="fact" :class="{ busy: busyId === `ep-${ep.id}` }">
          <div class="fact-top">
            <span class="tag">{{ t('mem.episodes') }}</span>
            <span class="grow" />
            <button @click="dropEpisode(ep.id)">{{ t('mem.forget') }}</button>
          </div>
          <p>{{ ep.summary }}</p>
        </div>
      </template>
      <div v-for="f in facts" :key="f.id" class="fact" :class="{ busy: busyId === f.id }">
        <div class="fact-top">
          <span class="tag">{{ kindText(f.kind) }}</span>
          <span v-if="f.pinned" class="pin">{{ t('mem.pin') }}</span>
          <span v-if="f.emotion && (f.kind === 'event' || f.kind === 'open_loop')" class="tag">{{ f.emotion }}</span>
          <span class="grow" />
          <button @click="startEdit(f.id, f.content)">{{ t('mem.edit') }}</button>
          <button @click="pin(f.id, !f.pinned)">{{ f.pinned ? t('mem.unpin') : t('mem.pin') }}</button>
          <button @click="forget(f.id)">{{ t('mem.forget') }}</button>
        </div>
        <n-input v-if="editingId === f.id" v-model:value="editText" type="textarea" size="tiny"
                 :autosize="{ minRows: 2, maxRows: 4 }"
                 @keydown.enter.exact.prevent="commitEdit"
                 @blur="commitEdit" />
        <p v-else>{{ f.content }}</p>
      </div>
    </div>
    <div class="mem-add">
      <n-select v-model:value="kind" :options="kinds" size="tiny" style="width:88px" />
      <n-input v-model:value="draft" size="tiny" :placeholder="t('mem.placeholder')"
               @keydown.enter.prevent="add" />
      <n-button size="tiny" type="primary" :disabled="!draft.trim()" @click="add">{{ t('mem.add') }}</n-button>
    </div>
  </div>
</template>

<style scoped>
.mem {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 100%;
  margin-bottom: 8px;
  max-height: 280px;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  background: rgba(12, 12, 22, 0.92);
  border: 1px solid rgba(255,255,255,0.1);
  overflow: hidden;
  z-index: 12;
}
.mem-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.x, .fact-top button {
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.55);
  cursor: pointer;
  font-size: 11px;
}
.fact-top button:hover, .x:hover { color: #fff; }
.mem-list { overflow: auto; padding: 8px 12px; flex: 1; }
.empty { font-size: 12px; opacity: 0.5; line-height: 1.5; }
.group {
  margin: 2px 0 6px;
  font-size: 10px;
  letter-spacing: 0.04em;
  opacity: 0.45;
}
.fact { margin-bottom: 10px; }
.fact.busy { opacity: 0.55; }
.fact p { margin: 4px 0 0; font-size: 12px; line-height: 1.55; opacity: 0.9; }
.fact-top { display: flex; align-items: center; gap: 6px; }
.grow { flex: 1; }
.tag, .pin {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(91,91,214,0.35);
}
.pin { background: rgba(251,191,36,0.25); }
.mem-add {
  display: flex;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
</style>
