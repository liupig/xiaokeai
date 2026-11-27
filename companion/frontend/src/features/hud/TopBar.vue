<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { NAvatar, NTooltip } from 'naive-ui';
import { MocapToolbar } from '../mocap';
import XkIcon from '../icons/XkIcon.vue';
import { rememberCurrentCharacter, useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { useGlancePower } from '../glance/power';
import { t } from '../../i18n';
import { setShellMode } from '../shell/mode';
import CoinPill from '../coins/CoinPill.vue';
import { lifePanelOpen, userCenterOpen } from '../coins/session';

type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log' | 'live' | 'music';

defineProps<{ active: PanelKey | null; updateAvailable?: boolean; updateLabel?: string }>();
const emit = defineEmits<{ (e: 'toggle', p: PanelKey): void; (e: 'check-update'): void }>();

const characters = useCharacterStore();
const compact = ref(false);
const edgeOpen = ref(false);
const navZone = ref<HTMLElement>();

function trackEdge(event: MouseEvent) {
  const edge = edgeOpen.value ? (navZone.value?.offsetWidth ?? 32) + 8 : 32;
  edgeOpen.value = event.clientX >= 0 && event.clientX < edge;
}

function leaveEdge() {
  edgeOpen.value = false;
}

onMounted(() => {
  window.addEventListener('mousemove', trackEdge, true);
  document.documentElement.addEventListener('mouseleave', leaveEdge);
  window.addEventListener('blur', leaveEdge);
});
onUnmounted(() => {
  window.removeEventListener('mousemove', trackEdge, true);
  document.documentElement.removeEventListener('mouseleave', leaveEdge);
  window.removeEventListener('blur', leaveEdge);
});
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
    { key: 'quick', label: t('stageShell.controls') },
    { key: 'review', label: t('top.review') },
    { key: 'log', label: t('top.log') },
    { key: 'assets', label: t('top.assets') },
    { key: 'music', label: t('musicPlayer.title') },
    { key: 'live', label: t('set.group.live') },
    { key: 'settings', label: t('top.settings') },
  ];
  if (settings.modules.keepsake) {
    list.splice(2, 0, { key: 'keepsake', label: t('top.keepsake') });
  }
  return list;
});
</script>

<template>
  <div ref="navZone" class="stage-nav-zone"
       :class="{ 'edge-open': edgeOpen, 'panel-open': !!active || lifePanelOpen || userCenterOpen }">
    <button type="button" class="stage-edge" :aria-label="t('stageShell.navigation')"></button>
  <nav class="stage-nav" :class="{ compact }" :aria-label="t('stageShell.navigation')">
    <div class="nav-header">
      <button type="button" class="tool character" :class="{ active: active === 'characters' }"
              :aria-label="currentName" :aria-pressed="active === 'characters'" :title="currentName"
              @click="emit('toggle', 'characters')">
        <n-avatar round size="small" class="avatar">{{ currentName.slice(0, 1) }}</n-avatar>
        <span class="nav-label">{{ currentName }}</span>
      </button>
      <button type="button" class="tool resize" :aria-label="t(compact ? 'stageShell.expand' : 'stageShell.collapse')"
              :title="t(compact ? 'stageShell.expand' : 'stageShell.collapse')" @click="compact = !compact">
        <XkIcon :name="compact ? 'expand' : 'collapse'" :size="16" />
      </button>
    </div>
    <div class="nav-items">
      <button type="button" class="tool" :title="t('stageShell.space')" :aria-label="t('stageShell.space')" :class="{ active: lifePanelOpen }" :aria-pressed="lifePanelOpen" @click="lifePanelOpen = !lifePanelOpen">
        <img v-bind:src="'/assets/life/flower.png'" alt="" class="life-icon" />
        <span class="nav-label">{{ t('stageShell.space') }}</span>
      </button>
      <button v-for="item in tools" :key="item.key" type="button" class="tool"
              :class="{ active: active === item.key }" :aria-pressed="active === item.key"
              :aria-label="item.label" :title="item.label" @click="emit('toggle', item.key)">
        <span v-if="item.key === 'music'" class="music-icon" aria-hidden="true">♫</span>
        <XkIcon v-else :name="item.key === 'live' ? 'mic' : item.key" :size="19" />
        <span class="nav-label">{{ item.label }}</span>
      </button>
      <button v-if="canPet" type="button" class="tool" :title="t('top.pet')"
              :aria-label="t('top.pet')" @click="setShellMode('pet')">
        <XkIcon name="pet" :size="19" />
        <span class="nav-label">{{ t('top.pet') }}</span>
      </button>
    </div>
    <details class="utilities">
      <summary :title="t('stageShell.more')" :aria-label="t('stageShell.more')">
        <XkIcon name="chevron" :size="16" />
        <span class="nav-label">{{ t('stageShell.more') }}</span>
        <i v-if="updateAvailable" class="update-dot"></i>
      </summary>
      <div class="utility-tools">
        <n-tooltip :delay="300">
          <template #trigger>
            <button type="button" class="tool" :class="{ 'has-update': updateAvailable }" @click="emit('check-update')" :aria-label="t('stageShell.update')">
              <XkIcon name="update" :size="20" />
              <i v-if="updateAvailable" class="update-dot"></i>
            </button>
          </template>
          {{ updateAvailable ? '有新版本，点击查看' : updateLabel || t('stageShell.update') }}
        </n-tooltip>
        <MocapToolbar />
        <n-tooltip :delay="300">
          <template #trigger>
            <button class="tool" :class="{ active: glanceOn, starting: glance.eyes === 'starting' || glanceBusy }"
                    type="button" :aria-label="glanceTip" @click="toggleGlance">
              <XkIcon name="glance" :size="22" />
            </button>
          </template>
          {{ glanceTip }}
        </n-tooltip>
        <n-tooltip v-if="canReload" :delay="300">
          <template #trigger>
            <button class="tool" type="button" :aria-label="t('top.reload')" @click="reloadShell">
              <XkIcon name="reload" :size="22" />
            </button>
          </template>
          {{ t('top.reload') }}
        </n-tooltip>
      </div>
    </details>
    <div class="balance"><CoinPill /></div>
  </nav>
  </div>
</template>

<style scoped>
.music-icon { width: 19px; flex: 0 0 19px; text-align: center; font-size: 18px; color: #ebc5a1; }
.stage-nav-zone {
  --nav-width: var(--stage-nav-width);
  position: absolute;
  z-index: 18;
  inset: 0 auto 0 0;
  width: 8px;
  -webkit-app-region: no-drag;
}
.stage-edge {
  position: absolute;
  inset: 0;
  width: 100%;
  border: 0;
  background: transparent;
}
.stage-nav-zone:has(.compact) { --nav-width: var(--stage-nav-compact-width); }
.stage-nav-zone:is(.edge-open, .panel-open, :hover, :has(:focus-visible)) { width: calc(var(--nav-width) + 12px); }
.stage-nav {
  position: absolute;
  inset: calc(12px + var(--desk-chrome, 0px)) auto 12px 12px;
  z-index: 11;
  width: var(--stage-nav-width);
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden auto;
  scrollbar-width: thin;
  scrollbar-color: #795e74 transparent;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid #e8c5d021;
  border-radius: 20px;
  background: linear-gradient(160deg, #372b3c, #251f2d 75%);
  color: #f1f0f4;
  -webkit-app-region: no-drag;
  visibility: hidden;
  opacity: 0;
  transform: translateX(-20px);
  transition: transform .18s ease, opacity .18s ease, visibility .18s;
}
.stage-nav-zone:is(.edge-open, .panel-open, :hover, :has(:focus-visible)) .stage-nav {
  visibility: visible;
  opacity: 1;
  transform: translateX(0);
}
@media (prefers-reduced-motion: reduce) { .stage-nav { transition: none; } }

.nav-header { display: flex; align-items: center; gap: 2px; padding-bottom: 10px; border-bottom: 1px solid #e8c5d021; }
.nav-header .character { flex: 1; min-width: 0; padding: 3px; }
.nav-header .resize { flex: 0 0 24px; justify-content: center; padding: 0; }
.avatar { flex: none; background: #765568; color: #f6e2e9; }
.nav-items { display: grid; grid-template-columns: minmax(0, 1fr); gap: 3px; }
.nav-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.life-icon { width: 19px; height: 19px; object-fit: contain; }

.tool, .utilities summary {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 40px;
  padding: 5px 8px;
  box-sizing: border-box;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.tool :deep(svg), .utilities summary :deep(svg) { flex: none; }
.tool:hover, .utilities summary:hover { background: #ffffff14; }
.tool.active { background: #edc29d1f; color: #f5d7bd; box-shadow: inset 0 0 0 1px #edc29d32; }
.tool.active::before { content: ''; position: absolute; left: 0; width: 2px; height: 18px; border-radius: 2px; background: #ebc5a1; }
.tool:focus-visible, .utilities summary:focus-visible { outline: 2px solid #ebc5a1; outline-offset: -2px; }
.tool.starting, .tool.has-update { color: #c4e9ff; }
.utilities { border-top: 1px solid #ffffff1a; padding-top: 6px; }
.utilities summary { list-style: none; }
.utilities summary::-webkit-details-marker { display: none; }
.utilities[open] summary :deep(svg) { transform: rotate(90deg); }
.utility-tools { display: flex; flex-wrap: wrap; }
.utility-tools .tool { width: 36px; justify-content: center; padding: 0; }
.update-dot { position: absolute; top: 5px; right: 5px; width: 6px; height: 6px; border-radius: 50%; background: #b8e3ff; }
.balance { margin-top: auto; display: flex; justify-content: center; }
.balance :deep(.pill) { max-width: 100%; padding-inline: 6px; }
.balance :deep(.pill .body) { min-width: 0; gap: 5px; }
.balance :deep(.pill .mark) { flex: none; }
.balance :deep(.pill .amt) { overflow: hidden; text-overflow: ellipsis; }
.stage-nav.compact { width: var(--stage-nav-compact-width); }
.compact .nav-label { display: none; }
.compact .nav-header { flex-direction: column; align-items: stretch; }
.compact .nav-header .resize { flex-basis: auto; }
.compact .tool, .compact .utilities summary { justify-content: center; }
.compact .utility-tools { justify-content: center; }

@media (max-width: 640px) {
  .nav-label, .nav-header .resize { display: none; }
  .tool, .utilities summary { justify-content: center; }
  .utility-tools { justify-content: center; }
}
</style>
