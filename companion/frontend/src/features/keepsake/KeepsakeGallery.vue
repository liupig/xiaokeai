<script setup lang="ts">
import StagePanel from '../hud/StagePanel.vue';
import { computed, ref, watch } from 'vue';
import { NButton, NModal } from 'naive-ui';
import { api } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { leaveLifeStage } from '../life/stageLife';
import { t } from '../../i18n';
import { applySceneStage, restoreSettingsStage, sceneSession } from '../scenes/session';
import {
  isKeepsakeBgUrl, keepsakeSession, refreshKeepsakes,
} from './session';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const characters = useCharacterStore();
const settings = useSettingsStore();

const overlayOn = computed(() =>
  !!keepsakeSession.bgOverride || isKeepsakeBgUrl(settings.quality.background_image));
const zoom = ref('');

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

watch(() => props.show, (show) => {
  if (show && characters.currentId) void refreshKeepsakes(characters.currentId);
});

async function drop(id: number) {
  await api.deleteKeepsake(id);
  if (characters.currentId) await refreshKeepsakes(characters.currentId);
}

function useAsBg(url: string) {
  const u = mediaUrl(url);
  if (!u) return;
  leaveLifeStage();
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
  <StagePanel :show="show" :title="t('top.keepsake')" size="medium"
              @update:show="(v: boolean) => emit('update:show', v)">
      <p v-if="keepsakeSession.items.length" class="hint">{{ t('keep.hint') }}</p>
      <div v-if="overlayOn" class="bar">
        <span>{{ t('keep.asBg') }}</span>
        <n-button size="tiny" type="primary" secondary @click="clearKeepsakeBg">{{ t('keep.back') }}</n-button>
      </div>
      <div v-if="!keepsakeSession.items.length" class="empty">{{ t('keep.empty') }}</div>
      <div class="grid">
        <figure v-for="it in keepsakeSession.items" :key="it.id">
          <video v-if="it.kind === 'clip'" controls playsinline preload="metadata">
            <source :src="mediaUrl(it.url)" :type="it.mime || 'video/mp4'" />
          </video>
          <button v-else class="still" type="button" @click="zoom = mediaUrl(it.url)">
            <img :src="mediaUrl(it.url)" :alt="it.caption || t('keep.still')" loading="lazy" />
          </button>
          <figcaption>
            <span>{{ it.caption || it.quote || (it.kind === 'clip' ? t('keep.clipWord') : t('keep.still')) }}</span>
            <span class="acts">
              <n-button v-if="it.kind !== 'clip' && isCurrentBg(it.url)" size="tiny" quaternary
                        @click="clearKeepsakeBg">{{ t('keep.clearBg') }}</n-button>
              <n-button v-else-if="it.kind !== 'clip'" size="tiny" quaternary
                        @click="useAsBg(it.url)">{{ t('keep.useBg') }}</n-button>
              <n-button size="tiny" quaternary @click="drop(it.id)">{{ t('keep.delete') }}</n-button>
            </span>
          </figcaption>
        </figure>
      </div>
  </StagePanel>
  <n-modal :show="!!zoom" @update:show="(open) => { if (!open) zoom = ''; }">
    <div class="zoom-view">
      <button type="button" class="zoom-close" :aria-label="t('common.close')" @click="zoom = ''">×</button>
      <img v-if="zoom" class="zoom-image" :src="zoom" :alt="t('keep.still')" />
    </div>
  </n-modal>
</template>

<style scoped>
.hint { font-size: 13px; color: var(--panel-muted); margin: 0 0 14px; }
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #ebc5a118;
  font-size: 12px;
}
.empty { font-size: 13px; color: var(--panel-muted); padding: 28px 14px; text-align: center; border: 1px dashed var(--panel-line); border-radius: 12px; }
.grid { display: flex; flex-direction: column; gap: 14px; }
figure { margin: 0; border: 1px solid var(--panel-line); border-radius: 14px; overflow: hidden; background: var(--panel-card); }
img, video {
  width: 100%;
  background: #1a161d;
  display: block;
}
.still {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  cursor: zoom-in;
}
.still:focus-visible { outline: 2px solid var(--panel-accent); outline-offset: -3px; }
.zoom-view { position: relative; width: fit-content; margin-inline: auto; }
.zoom-close {
  position: absolute;
  inset: 8px 8px auto auto;
  width: 36px;
  height: 36px;
  border: 1px solid #ffffff55;
  border-radius: 10px;
  background: #231e2ae8;
  color: #f6ece9;
  font-size: 23px;
  cursor: pointer;
}
.zoom-image {
  width: auto;
  max-width: min(920px, 88vw);
  max-height: 88vh;
  object-fit: contain;
  border-radius: 12px;
}
figcaption {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 9px 12px;
  font-size: 12px;
  opacity: 0.75;
}
.acts { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
