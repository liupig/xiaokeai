<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { NButton, NInput } from 'naive-ui';
import { useSettingsStore } from '../../stores/settings';

const settings = useSettingsStore();
const path = ref(settings.content.path || '');
const busy = ref(false);
const hint = ref('');
const skipped = ref(false);
const canPick = computed(() => typeof window.companionDesktop?.pickFolder === 'function');

async function pick() {
  const folder = await window.companionDesktop?.pickFolder?.();
  if (folder) path.value = folder;
}

async function save() {
  busy.value = true;
  hint.value = '';
  try {
    const r = await settings.applyContent(path.value.trim());
    hint.value = r.message || (r.ok ? '已保存' : '设置失败');
  } catch (e) {
    hint.value = String(e);
  } finally {
    busy.value = false;
  }
}

function skip() {
  skipped.value = true;
}

onMounted(async () => {
  if (!settings.content.packed || settings.content.ok || skipped.value) return;
  if (canPick.value) {
    await pick();
  }
})
</script>

<template>
  <div v-if="settings.content.packed && !settings.content.ok && !skipped" class="gate">
    <div class="card">
      <p class="title">xiaoke.ai</p>
      <p class="lead">选 B 那个文件夹（例如 xiaoke-ai-B），不要点里面的 xiaoke-content.json。那个文件只是标记，选中文件夹即可。</p>
      <div class="row">
        <n-input v-model:value="path" placeholder="例如 E:\xiaoke-ai-B" />
        <n-button v-if="canPick" @click="pick">浏览</n-button>
      </div>
      <p v-if="hint" class="hint">{{ hint }}</p>
      <div class="actions">
        <n-button type="primary" :loading="busy" :disabled="!path.trim()" @click="save">使用这个目录</n-button>
        <n-button quaternary @click="skip">稍后再说</n-button>
      </div>
      <p class="note">保存后请关掉窗口再打开。程序包（A）改代码时不用动 B。</p>
    </div>
  </div>
</template>

<style scoped>
.gate {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 10, 18, 0.72);
  backdrop-filter: blur(8px);
}
.card {
  width: min(520px, calc(100vw - 48px));
  padding: 28px 28px 22px;
  border-radius: 16px;
  background: #1a1a28;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #e8e8f0;
}
.title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: 0.04em;
}
.lead, .note, .hint {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.55;
  opacity: 0.78;
}
.hint { color: #c8c8ff; }
.note { margin: 16px 0 0; opacity: 0.5; font-size: 12px; }
.row {
  display: flex;
  gap: 8px;
}
.actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
</style>
