<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';
import BrandLogo from '../../components/BrandLogo.vue';

const QQ_NO = '1124054481';
const WECHAT_ID = 'xiaokeai3d';
const DISCORD = 'https://discord.gg/xxvXxHP8T';
const YOUTUBE = 'https://www.youtube.com/@liupig';
const X = 'https://x.com/iliuPIG';
const GITHUB = 'https://github.com/liupig/xiaokeai';
const GITHUB_SHOWN = 'github.com/liupig/xiaokeai';
const DOWNLOADS = [
  { name: '百度云盘', url: 'https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai' },
  { name: 'Hugging Face', url: 'https://huggingface.co/datasets/liupigai/xiaokeai/tree/main' },
  { name: 'Google Drive', url: 'https://drive.google.com/drive/folders/1mZcD4K90WgO2x2UxteAyMFsQlgTairPl?usp=drive_link' },
];

const show = Boolean(window.companionDesktop?.isShell);
const settings = useSettingsStore();
const copied = ref<'qq' | 'wechat' | ''>('');
const card = ref<'qq' | 'wechat' | 'download' | ''>('');
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

async function copy(text: string, which: 'qq' | 'wechat') {
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

function showQq() {
  card.value = 'qq';
  void copy(QQ_NO, 'qq');
}

function showWechat() {
  card.value = 'wechat';
  void copy(WECHAT_ID, 'wechat');
}

function closeCard() {
  card.value = '';
}

onUnmounted(() => window.clearTimeout(timer));
</script>

<template>
  <div v-if="show" class="chrome">
    <a class="brand-home" href="https://xiaoke.ai/" target="_blank" rel="noopener" title="打开 xiaoke.ai 官网" aria-label="打开 xiaoke.ai 官网">
      <BrandLogo :size="20" />
      <span class="name">xiaoke.ai</span>
    </a>
    <span class="links">
      <button type="button" class="link" :title="copyTitle" @click="showQq">
        <span>QQ群</span>
        <span class="value" :class="{ on: copied === 'qq' }">{{ copied === 'qq' ? copiedHint : QQ_NO }}</span>
      </button>
      <button type="button" class="link" :title="copyTitle" @click="showWechat">
        <span>微信</span>
        <span class="value" :class="{ on: copied === 'wechat' }">{{ copied === 'wechat' ? copiedHint : WECHAT_ID }}</span>
      </button>
      <a class="link icon-link discord" :href="DISCORD" target="_blank" rel="noopener" title="Discord" aria-label="Discord">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.317 4.369a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.865-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037 19.736 19.736 0 0 0-4.885 1.515.07.07 0 0 0-.032.027C.533 9.045-.32 13.579.099 18.058a.082.082 0 0 0 .031.056 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .078-.01c3.928 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .079.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.331c-1.182 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.182 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.947 2.418-2.157 2.418z" /></svg>
      </a>
      <a class="link icon-link youtube" :href="YOUTUBE" target="_blank" rel="noopener" title="YouTube" aria-label="YouTube">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" /></svg>
      </a>
      <a class="link icon-link" :href="X" target="_blank" rel="noopener" title="X" aria-label="X">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z" /></svg>
      </a>
      <button type="button" class="link icon-link" title="下载" aria-label="下载" @click="card = 'download'">
        <svg class="download-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 20h14" /></svg>
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
  <Teleport v-if="show && card" to="body">
    <div class="community-overlay" @click.self="closeCard">
      <section class="community-card" role="dialog" aria-modal="true" :aria-label="card === 'download' ? '下载' : card === 'qq' ? 'QQ群' : '微信'">
        <button type="button" class="card-close" aria-label="关闭" @click="closeCard">×</button>
        <template v-if="card === 'qq'">
          <h2>QQ群</h2>
          <p>群号 {{ QQ_NO }} · {{ copied === 'qq' ? copiedHint : '点击上方QQ群入口可复制' }}</p>
          <img class="community-qr" src="/community/qq-group.jpg" alt="QQ群 1124054481 的二维码">
        </template>
        <template v-else-if="card === 'wechat'">
          <h2>微信</h2>
          <p>微信号 {{ WECHAT_ID }} · {{ copied === 'wechat' ? copiedHint : '点击上方微信入口可复制' }}</p>
          <img class="community-qr" src="/community/wechat-qr.png" alt="微信号 xiaokeai3d 的二维码">
        </template>
        <template v-else>
          <h2>下载 xiaoke.ai</h2>
          <p>选择你习惯的下载方式</p>
          <div class="download-list">
            <a v-for="item in DOWNLOADS" :key="item.name" :href="item.url" target="_blank" rel="noopener">
              <strong>{{ item.name }}</strong>
              <span>{{ item.url }}</span>
            </a>
          </div>
        </template>
      </section>
    </div>
  </Teleport>
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
.brand-home {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  color: inherit;
  text-decoration: none;
  pointer-events: auto;
  -webkit-app-region: no-drag;
}
.brand-home:hover { color: #fff; }
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
.icon-link {
  justify-content: center;
  width: 30px;
  height: 28px;
  padding: 4px 6px;
}
.icon-link svg {
  width: 18px;
  height: 18px;
  fill: currentColor;
}
.icon-link .download-icon {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.discord:hover { color: #8b95ff; }
.youtube:hover { color: #ff3347; }
.community-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(7, 8, 15, 0.68);
  backdrop-filter: blur(8px);
  pointer-events: auto;
  -webkit-app-region: no-drag;
}
.community-card {
  position: relative;
  width: min(480px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 26px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  background: #171824;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
  color: #ececf5;
  text-align: center;
}
.community-card h2 {
  margin: 0 0 8px;
  font-size: 20px;
}
.community-card p {
  margin: 0 0 18px;
  color: rgba(236, 236, 245, 0.68);
  font-size: 13px;
}
.card-close {
  position: absolute;
  top: 10px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: rgba(236, 236, 245, 0.7);
  font-size: 24px;
  cursor: pointer;
}
.card-close:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
.community-qr {
  display: block;
  width: min(360px, 100%);
  max-height: 62vh;
  margin: 0 auto;
  border-radius: 12px;
  object-fit: contain;
}
.download-list { display: grid; gap: 10px; text-align: left; }
.download-list a {
  display: grid;
  gap: 6px;
  padding: 15px 16px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  color: #ececf5;
  text-decoration: none;
}
.download-list a:hover { border-color: #b8a3ff88; background: rgba(184, 163, 255, 0.1); }
.download-list strong { font-size: 14px; }
.download-list span { color: rgba(236, 236, 245, 0.6); font-size: 12px; overflow-wrap: anywhere; }
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
