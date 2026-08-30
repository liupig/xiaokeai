<script setup lang="ts">
import { computed } from 'vue';
import { NAvatar, NTooltip } from 'naive-ui';
import { MocapToolbar } from '../mocap';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';

type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake';

defineProps<{ active: PanelKey | null }>();
const emit = defineEmits<{ (e: 'toggle', p: PanelKey): void }>();

const characters = useCharacterStore();
const settings = useSettingsStore();
const currentName = computed(() => characters.current?.name ?? '未选择角色');

const tools = computed(() => {
  const list: { key: PanelKey; label: string }[] = [
    { key: 'quick', label: '表情 / 动作 / 运镜' },
    { key: 'review', label: '镜头审查' },
    { key: 'assets', label: '资产中心' },
    { key: 'settings', label: '设置' },
  ];
  if (settings.modules.keepsake) {
    list.splice(2, 0, { key: 'keepsake', label: '证物相册' });
  }
  return list;
});
</script>

<template>
  <div class="topbar">
    <div class="left glass" :class="{ active: active === 'characters' }"
         @click="emit('toggle', 'characters')">
      <n-avatar round size="small" class="avatar">{{ currentName.slice(0, 1) }}</n-avatar>
      <span class="name">{{ currentName }}</span>
      <svg class="chev" viewBox="0 0 24 24" width="14" height="14" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
    <div class="toolbar glass">
      <MocapToolbar />
      <n-tooltip v-for="t in tools" :key="t.key" :delay="300">
        <template #trigger>
          <button class="tool" :class="{ active: active === t.key }"
                  @click="emit('toggle', t.key)">
            <svg v-if="t.key === 'quick'" viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M8.5 14a4.5 4.5 0 0 0 7 0" />
              <line x1="9" y1="9.6" x2="9.01" y2="9.6" stroke-width="2.6" />
              <line x1="15" y1="9.6" x2="15.01" y2="9.6" stroke-width="2.6" />
            </svg>
            <svg v-else-if="t.key === 'review'" viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="M7 5V3M17 5V3M3 9h18" />
              <circle cx="8.5" cy="14" r="1.2" fill="currentColor" stroke="none" />
              <circle cx="15.5" cy="14" r="1.2" fill="currentColor" stroke="none" />
            </svg>
            <svg v-else-if="t.key === 'assets'" viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 8l-9-5-9 5v8l9 5 9-5V8z" />
              <path d="M3 8l9 5 9-5" />
              <line x1="12" y1="13" x2="12" y2="21" />
            </svg>
            <svg v-else-if="t.key === 'keepsake'" viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3.2" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l-.06-.06a2 2 0 1 1 2.83 2.83l-.06-.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z" />
            </svg>
          </button>
        </template>
        {{ t.label }}
      </n-tooltip>
    </div>
  </div>
</template>

<style scoped>
.topbar {
  position: absolute;
  top: 16px;
  left: 16px;
  right: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;
  pointer-events: none;
}

.left {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px 6px 8px;
  cursor: pointer;
  pointer-events: auto;
  transition: border-color 0.2s, background 0.2s;
}

.left:hover {
  border-color: rgba(255, 255, 255, 0.25);
}

.left.active {
  border-color: rgba(122, 122, 240, 0.7);
  background: rgba(91, 91, 214, 0.18);
}

.avatar {
  background: #5b5bd6;
}

.name {
  font-size: 14px;
  font-weight: 600;
}

.chev {
  opacity: 0.5;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  pointer-events: auto;
}

.tool {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tool:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.tool.active {
  background: #5b5bd6;
  color: #fff;
}

.tool.rec {
  background: #c44545;
}
</style>
