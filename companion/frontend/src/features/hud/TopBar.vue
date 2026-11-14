<script setup lang="ts">
import { computed, ref } from 'vue';
import { NAvatar, NTooltip } from 'naive-ui';
import { MocapToolbar } from '../mocap';
import XkIcon from '../icons/XkIcon.vue';
import { rememberCurrentCharacter, useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { useGlancePower } from '../glance/power';
import { t } from '../../i18n';
import { setShellMode } from '../shell/mode';
import CoinPill from '../coins/CoinPill.vue';

type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log';

defineProps<{ active: PanelKey | null; updateAvailable?: boolean; updateLabel?: string }>();
const emit = defineEmits<{ (e: 'toggle', p: PanelKey): void; (e: 'check-update'): void }>();

const characters = useCharacterStore();
const collapsed = ref(false);
const settings = useSettingsStore();
const currentName = computed(() => characters.current?.name ?? t('top.none'));
const canPet = typeof window.companionDesktop?.setShellMode === 'function';
const canReload = typeof window.companionDesktop?.reload === 'function';

function reloadShell() {
  rememberCurrentCharacter();
  void window.companionDesktop?.reload?.();
}

const { glance, glanceOn, glanceBusy, glanceTip, toggleGlance } = useGlancePower();

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
  <div class="topbar" :class="{ collapsed }">
    <div class="left-group">
      <div class="left glass" :class="{ active: active === 'characters' }"
           @click="emit('toggle', 'characters')">
        <n-avatar round size="small" class="avatar">{{ currentName.slice(0, 1) }}</n-avatar>
        <span class="name">{{ currentName }}</span>
        <XkIcon name="chevron" :size="12" class="chev" />
      </div>
      <CoinPill />
    </div>
    <button v-if="collapsed" class="collapse-toggle glass" type="button" @click.stop="collapsed = false" aria-label="展开导航"><XkIcon name="expand" :size="20" /></button>
    <div v-else class="toolbar glass">
      <n-tooltip :delay="300">
        <template #trigger>
          <button type="button" class="tool update-tool" :class="{ 'has-update': updateAvailable }" @click="emit('check-update')" aria-label="检查更新">
            <XkIcon name="update" :size="20" />
            <i v-if="updateAvailable"></i>
          </button>
        </template>
        {{ updateAvailable ? '有新版本，点击查看' : updateLabel || '检查更新' }}
      </n-tooltip>
      <MocapToolbar />
      <n-tooltip :delay="300">
        <template #trigger>
          <button class="tool" :class="{ active: glanceOn, starting: glance.eyes === 'starting' || glanceBusy }"
                  type="button" @click="toggleGlance">
            <XkIcon name="glance" :size="22" />
          </button>
        </template>
        {{ glanceTip }}
      </n-tooltip>
      <n-tooltip v-if="canReload" :delay="300">
        <template #trigger>
          <button class="tool" type="button" @click="reloadShell">
            <XkIcon name="reload" :size="22" />
          </button>
        </template>
        {{ t('top.reload') }}
      </n-tooltip>
      <n-tooltip v-if="canPet" :delay="300">
        <template #trigger>
          <button class="tool" type="button" @click="setShellMode('pet')">
            <XkIcon name="pet" :size="22" />
          </button>
        </template>
        {{ t('top.pet') }}
      </n-tooltip>
      <n-tooltip v-for="item in tools" :key="item.key" :delay="300">
        <template #trigger>
          <button class="tool" :class="{ active: active === item.key }"
                  @click="emit('toggle', item.key)">
            <XkIcon :name="item.key" :size="22" />
          </button>
        </template>
        {{ item.label }}
      </n-tooltip>
      <button class="tool collapse-icon" type="button" @click.stop="collapsed = true" aria-label="收起导航"><XkIcon name="collapse" :size="20" /></button>
    </div>
  </div>
</template>

<style scoped>
.update-tool { position: relative; }
.update-tool.has-update { color: #c4afff; }
.update-tool i { position: absolute; top: 5px; right: 5px; width: 6px; height: 6px; border-radius: 50%; background: #bd9bff; box-shadow: 0 0 6px #bd9bff80; }
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
.topbar.collapsed { justify-content: flex-end; }
.collapse-toggle { pointer-events: auto; width: 38px; height: 28px; border: 0; border-radius: 12px; color: #ddd; cursor: pointer; }

.left-group {
  display: flex;
  align-items: center;
  gap: 8px;
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

.tool.starting {
  background: rgba(91, 91, 214, 0.45);
}

.tool.rec {
  background: #c44545;
}
</style>
