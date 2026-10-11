<script setup lang="ts">
import { computed } from 'vue';
import { NAvatar, NTooltip } from 'naive-ui';
import { MocapToolbar } from '../mocap';
import XkIcon from '../icons/XkIcon.vue';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { t } from '../../i18n';

type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log';

defineProps<{ active: PanelKey | null }>();
const emit = defineEmits<{ (e: 'toggle', p: PanelKey): void }>();

const characters = useCharacterStore();
const settings = useSettingsStore();
const currentName = computed(() => characters.current?.name ?? t('top.none'));

const tools = computed(() => {
  settings.locale.ui;
  const list: { key: PanelKey; label: string }[] = [
    { key: 'quick', label: t('top.quick') },
    { key: 'review', label: t('top.review') },
    { key: 'log', label: t('top.log') },
    { key: 'assets', label: t('top.assets') },
    { key: 'settings', label: t('top.settings') },
  ];
  if (settings.modules.keepsake) {
    list.splice(2, 0, { key: 'keepsake', label: t('top.keepsake') });
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
      <XkIcon name="chevron" :size="12" class="chev" />
    </div>
    <div class="toolbar glass">
      <MocapToolbar />
      <n-tooltip v-for="t in tools" :key="t.key" :delay="300">
        <template #trigger>
          <button class="tool" :class="{ active: active === t.key }"
                  @click="emit('toggle', t.key)">
            <XkIcon :name="t.key" :size="22" />
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
  top: calc(16px + var(--desk-chrome, 0px));
  left: 16px;
  right: 16px;
  -webkit-app-region: no-drag;
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
  opacity: 0.9;
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
