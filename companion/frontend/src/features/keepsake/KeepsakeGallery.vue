<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NDrawer, NDrawerContent } from 'naive-ui';
import { api } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { applySceneStage, restoreSettingsStage, sceneSession } from '../scenes/session';
import {
  isKeepsakeBgUrl, keepsakeSession, refreshKeepsakes,
} from './session';

defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const characters = useCharacterStore();
const settings = useSettingsStore();

const overlayOn = computed(() =>
  !!keepsakeSession.bgOverride || isKeepsakeBgUrl(settings.quality.background_image));

function mediaUrl(url: string) {
  if (!url) return '';
  if (url.startsWith('/api/')) return url;
  const name = url.split('/').pop() || '';
  return name ? `/api/modules/keepsakes/file/${name}` : url;
}

function isCurrentBg(url: string) {
  const u = mediaUrl(url);
  return u && (keepsakeSession.bgOverride === u || settings.quality.background_image === u);
}

async function onShow(v: boolean) {
  emit('update:show', v);
  if (v && characters.currentId) await refreshKeepsakes(characters.currentId);
}

async function drop(id: number) {
  await api.deleteKeepsake(id);
  if (characters.currentId) await refreshKeepsakes(characters.currentId);
}

function useAsBg(url: string) {
  const u = mediaUrl(url);
  if (!u) return;
  if (!keepsakeSession.bgOverride && !isKeepsakeBgUrl(settings.quality.background_image)) {
    keepsakeSession.bgPrev = settings.quality.background_image || '';
  }
  keepsakeSession.bgOverride = u;
  settings.quality.background_image = u;
  settings.applyQuality();
}

async function clearKeepsakeBg() {
  keepsakeSession.bgOverride = '';
  settings.quality.background_image = keepsakeSession.bgPrev || '';
  if (settings.modules.scenes && sceneSession.current) {
    applySceneStage(sceneSession.current);
  } else {
    restoreSettingsStage();
  }
  keepsakeSession.bgPrev = '';
  try { await settings.save(); } catch { /* 当场已还原 */ }
}
</script>

<template>
  <n-drawer :show="show" @update:show="onShow" :width="420" placement="right"
            show-mask="transparent" to="body">
    <n-drawer-content title="证物相册" closable :native-scrollbar="false">
      <p class="hint">舞台上截下的剧照和短片。当背景只盖一层，不会改掉今晚这场戏；随时可以取消。</p>
      <div v-if="overlayOn" class="bar">
        <span>证物正在当背景</span>
        <n-button size="tiny" type="primary" secondary @click="clearKeepsakeBg">取消，回到环境</n-button>
      </div>
      <div v-if="!keepsakeSession.items.length" class="empty">还没有证物。对话栏快门可以拍一张或录 8 秒。</div>
      <div class="grid">
        <figure v-for="it in keepsakeSession.items" :key="it.id">
          <video v-if="it.kind === 'clip'" controls playsinline preload="metadata">
            <source :src="mediaUrl(it.url)" :type="it.mime || 'video/mp4'" />
          </video>
          <img v-else :src="mediaUrl(it.url)" :alt="it.caption || '剧照'" />
          <figcaption>
            <span>{{ it.caption || it.quote || (it.kind === 'clip' ? '短片' : '剧照') }}</span>
            <span class="acts">
              <n-button v-if="it.kind !== 'clip' && isCurrentBg(it.url)" size="tiny" quaternary
                        @click="clearKeepsakeBg">取消背景</n-button>
              <n-button v-else-if="it.kind !== 'clip'" size="tiny" quaternary
                        @click="useAsBg(it.url)">当背景</n-button>
              <n-button size="tiny" quaternary @click="drop(it.id)">删除</n-button>
            </span>
          </figcaption>
        </figure>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.hint { font-size: 12px; opacity: 0.5; margin: 0 0 12px; }
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(91, 91, 214, 0.18);
  font-size: 12px;
}
.empty { font-size: 13px; opacity: 0.5; }
.grid { display: flex; flex-direction: column; gap: 14px; }
figure { margin: 0; }
img, video {
  width: 100%;
  border-radius: 12px;
  background: #111;
  display: block;
}
figcaption {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  opacity: 0.75;
}
.acts { display: flex; gap: 4px; }
</style>
