<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';
import BrandLogo from '../../components/BrandLogo.vue';

const QQ_NO = '1124054481';
const DISCORD = 'https://discord.gg/xxvXxHP8T';
const DISCORD_SHOWN = 'discord.gg/xxvXxHP8T';
const GITHUB = 'https://github.com/liupig/xiaokeai';
const GITHUB_SHOWN = 'github.com/liupig/xiaokeai';

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
const openTitle = computed(() => {
  settings.locale.ui;
  return t('chrome.open');
});
function minimizeWindow() { window.companionDesktop?.minimize?.(); }
function maximizeWindow() { window.companionDesktop?.maximize?.(); }
function closeWindow() { window.companionDesktop?.close?.(); }

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
    <BrandLogo :size="20" />
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
      <a class="link" :href="GITHUB" target="_blank" rel="noopener" :title="openTitle">
        <span>GitHub</span>
        <span class="value">{{ GITHUB_SHOWN }}</span>
      </a>
    </span>
    <span class="window-actions">
      <button type="button" title="最小化" @click.stop="minimizeWindow"><svg viewBox="0 0 20 20"><path d="M4 10h12" /></svg></button>
      <button type="button" title="最大化 / 还原" @click.stop="maximizeWindow"><svg viewBox="0 0 20 20"><rect x="4.5" y="4.5" width="11" height="11" rx="2" /></svg></button>
      <button type="button" class="window-close" title="关闭" @click.stop="closeWindow"><svg viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15" /></svg></button>
    </span>
  </div>
</template>

<style scoped>
.chrome {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
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
.name {
  opacity: 0.9;
  flex: none;
}
.window-actions { display: flex; align-items: stretch; height: 100%; margin-left: auto; pointer-events: auto; position: relative; z-index: 50; -webkit-app-region: no-drag; }
.window-actions button { width: 42px; border: 0; background: transparent; color: rgba(232,232,240,.68); cursor: pointer; }
.window-actions button:hover { background: rgba(255,255,255,.09); color: #fff; }
.window-actions .window-close:hover { background: rgba(210,70,95,.78); }
.window-actions svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.45; stroke-linecap: round; stroke-linejoin: round; vertical-align: middle; }
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
  text-decoration: none;
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
