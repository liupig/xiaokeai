<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { NButton, NInput, NSelect } from 'naive-ui';
import { api } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { memorySession, refreshMemory } from './session';

const characters = useCharacterStore();
const draft = ref('');
const kind = ref('event');
const editingId = ref<string | null>(null);
const editText = ref('');
const busyId = ref<string | null>(null);
const kinds = [
  { label: '偏好', value: 'preference' },
  { label: '人物', value: 'person' },
  { label: '事件', value: 'event' },
  { label: '未完', value: 'open_loop' },
  { label: '性格', value: 'trait' },
];

const facts = computed(() => memorySession.facts);

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
      <span>她记得的{{ facts.length ? ` · ${facts.length}` : '' }}</span>
      <button class="x" @click="memorySession.open = false">关闭</button>
    </div>
    <div class="mem-list">
      <div v-if="memorySession.loading && !facts.length" class="empty">正在读取记忆…</div>
      <div v-else-if="!facts.length" class="empty">还没有记忆。聊几句后会慢慢长出来，也可以自己写一条。</div>
      <div v-for="f in facts" :key="f.id" class="fact" :class="{ busy: busyId === f.id }">
        <div class="fact-top">
          <span class="tag">{{ f.kind_cn }}</span>
          <span v-if="f.pinned" class="pin">置顶</span>
          <span class="grow" />
          <button @click="startEdit(f.id, f.content)">编辑</button>
          <button @click="pin(f.id, !f.pinned)">{{ f.pinned ? '取消置顶' : '置顶' }}</button>
          <button @click="forget(f.id)">遗忘</button>
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
      <n-input v-model:value="draft" size="tiny" placeholder="写一条她该记住的…"
               @keydown.enter.prevent="add" />
      <n-button size="tiny" type="primary" :disabled="!draft.trim()" @click="add">记下</n-button>
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
