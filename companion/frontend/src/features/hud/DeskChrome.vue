<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';

const QQ_NO = '1124054481';
const DISCORD = 'https://discord.gg/xxvXxHP8T';
const DISCORD_SHOWN = 'discord.gg/xxvXxHP8T';

const show = Boolean(window.companionDesktop?.isShell);
const settings = useSettingsStore();
const copied = ref<'qq' | 'discord' | ''>('');
let timer = 0;

const copiedHint = computed(() => {
  settings.locale.ui;
  return t('chrome.copied');
});
const copyTitle = computed(() => {
  settings.locale.ui;
  return t('chrome.copy');
});

async function copy(text: string, which: 'qq' | 'discord') {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const el = document.createElement('textarea');
    el.value = text;
    el.setAttribute('readonly', '');
    el.style.position = 'fixed';
    el.style.left = '-9999px';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    el.remove();
  }
  copied.value = which;
  window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    copied.value = '';
  }, 1400);
}

onUnmounted(() => window.clearTimeout(timer));
</script>

<template>
  <div v-if="show" class="chrome">
    <span class="dot" />
    <span class="name">xiaoke.ai</span>
    <span class="links">
      <button type="button" class="link" :title="copyTitle" @click="copy(QQ_NO, 'qq')">
        <span>QQ群</span>
        <span class="value" :class="{ on: copied === 'qq' }">{{ copied === 'qq' ? copiedHint : QQ_NO }}</span>
      </button>
      <button type="button" class="link" :title="copyTitle" @click="copy(DISCORD, 'discord')">
        <span>Discord</span>
        <span class="value" :class="{ on: copied === 'discord' }">{{ copied === 'discord' ? copiedHint : DISCORD_SHOWN }}</span>
      </button>
    </span>
  </div>
</template>

<style scoped>
.chrome {
  position: absolute;
  top: 0;
  left: 0;
  right: var(--desk-controls, 0px);
  height: var(--desk-chrome, 36px);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  z-index: 30;
  pointer-events: none;
  -webkit-app-region: drag;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: rgba(232, 232, 240, 0.78);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7a7af0;
  box-shadow: 0 0 10px rgba(91, 91, 214, 0.85);
  flex: none;
}
.name {
  opacity: 0.9;
  flex: none;
}
.links {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-left: 8px;
  pointer-events: auto;
  -webkit-app-region: no-drag;
}
.link {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 2px 8px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: 0.02em;
  cursor: pointer;
  pointer-events: auto;
  -webkit-app-region: no-drag;
}
.link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.value {
  font-weight: 500;
  letter-spacing: 0;
  opacity: 0.92;
  font-variant-numeric: tabular-nums;
}
.value.on {
  color: #b7f0c8;
  opacity: 1;
}
</style>
