<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { NButton, NInput, NTabPane, NTabs } from 'naive-ui';
import { CAM_SHOTS } from '../../engine/camera';
import { stage, type StandSlot } from '../../engine/stage';
import type { ActionKey, CamShotId, EmotionKey } from '../../engine/types';
import Live2DPanel from '../live2d/Live2DPanel.vue';
import { applyEmotion, parseEmotionMap } from '../performance/emotionMap';
import { isFramingCam } from '../performance/camLexicon';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import {
  MOTION_CATS, isMotionRejected, motionReviewStatus, parseMotionCat, playAssetMotion, stripCatPrefix, type MotionCat,
} from '../assets/motionMeta';
import { api } from '../../api/client';
import { motionTitle, t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';

defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const assets = useAssetsStore();
const characters = useCharacterStore();
const settings = useSettingsStore();

const sizeShots = computed(() => CAM_SHOTS.filter((c) =>
  ['close', 'bust', 'half', 'threeQ', 'full', 'long'].includes(c.id)));
const moveShots = computed(() => CAM_SHOTS.filter((c) =>
  !['close', 'bust', 'half', 'threeQ', 'full', 'long'].includes(c.id)));
const libraryCams = computed(() => assets.cameras.filter((c) => !isFramingCam(c)));
const currentShot = ref<CamShotId>('full');
const currentCamera = ref('');
const emotions = computed(() => {
  settings.locale.ui;
  return (['neutral', 'happy', 'angry', 'sad', 'relaxed'] as EmotionKey[])
    .map((key) => ({ key, label: t(`emo.${key}`) }));
});
const actions = computed(() => {
  settings.locale.ui;
  return (['nod', 'shake'] as ActionKey[]).map((key) => ({ key, label: t(`act.${key}`) }));
});
const stands = computed(() => {
  settings.locale.ui;
  return (['left', 'center', 'right'] as StandSlot[]).map((key) => ({ key, label: t(`stand.${key}`) }));
});

const currentEmotion = ref<EmotionKey>('neutral');
const standSlot = ref<StandSlot>(stage.standSlot);
const morphSearch = ref('');
const motionSearch = ref('');
const motionCat = ref<MotionCat>('idle');
const activeMorphs = ref(new Set<string>());
const currentMotion = ref('');

const morphNames = computed(() => characters.modelInfo?.morphNames ?? []);
const filteredMorphs = computed(() =>
  morphSearch.value
    ? morphNames.value.filter((n) => n.includes(morphSearch.value.trim()))
    : morphNames.value
);
const supportsMotions = computed(() => characters.modelInfo?.supportsVmd ?? false);
const isLive2D = computed(() => characters.modelInfo?.format === 'live2d');
const activeTab = ref('motions');
watch(isLive2D, (enabled) => {
  activeTab.value = enabled ? 'live2d' : 'motions';
}, { immediate: true });

const groupedMotions = computed(() => {
  const q = motionSearch.value.trim();
  return assets.motions.filter((m) => {
    if (parseMotionCat(m) !== motionCat.value) return false;
    if (!q) return true;
    return m.label.includes(q) || m.name.includes(q) || stripCatPrefix(m.label).includes(q);
  });
});

const catCounts = computed(() => {
  const c: Record<MotionCat, number> = { idle: 0, greet: 0, interact: 0, dance: 0 };
  for (const m of assets.motions) c[parseMotionCat(m)] += 1;
  return c;
});
const motionIndex = computed(() => groupedMotions.value.findIndex((m) => m.name === currentMotion.value));
const reviewPosition = computed(() => `${motionIndex.value < 0 ? 0 : motionIndex.value + 1} / ${groupedMotions.value.length}`);

async function playMotionOffset(offset: number) {
  const list = groupedMotions.value;
  if (!list.length) return;
  const current = motionIndex.value;
  const index = current < 0 ? (offset > 0 ? 0 : list.length - 1) : current + offset;
  if (index < 0 || index >= list.length) return;
  await playMotion(list[index].name);
}

function setCam(id: CamShotId) {
  currentShot.value = id;
  currentCamera.value = '';
  stage.playShot(id);
}

function goStand(slot: StandSlot) {
  standSlot.value = slot;
  stage.goToStand(slot);
}

async function playCamera(name: string) {
  const cam = assets.cameras.find((c) => c.name === name);
  if (!cam) return;
  currentCamera.value = name;
  await stage.playCameraVmd(api.assetUrl(cam));
}

function stopCamera() {
  currentCamera.value = '';
  stage.stopCamera();
}

function setEmotion(e: EmotionKey) {
  currentEmotion.value = e;
  applyEmotion(e, parseEmotionMap(characters.current?.emotion_map ?? '{}'));
}

function toggleMorph(name: string) {
  const on = !activeMorphs.value.has(name);
  if (on) activeMorphs.value.add(name);
  else activeMorphs.value.delete(name);
  activeMorphs.value = new Set(activeMorphs.value);
  stage.setMorph(name, on);
}

function resetMorphs() {
  activeMorphs.value = new Set();
  stage.resetMorphs();
}

async function playMotion(name: string) {
  const motion = assets.motionByName(name);
  if (!motion) return;
  currentMotion.value = name;
  await playAssetMotion(motion);
}

function stopMotion() {
  currentMotion.value = '';
  stage.stopMotion();
}

async function setReview(m: { id: number; name: string }, status: 'pending' | 'approved' | 'rejected') {
  await assets.setMotionReviewStatus(m.id, status);
  if (status === 'rejected' && currentMotion.value === m.name) stopMotion();
}

async function removeMotion(m: { id: number; name: string; label: string }) {
  if (!window.confirm(`确定删除动作“${m.label}”及其文件吗？此操作不可撤销。`)) return;
  if (currentMotion.value === m.name) stopMotion();
  await assets.remove(m.id, true);
}
</script>

<template>
  <transition name="slide">
    <div v-if="show" class="panel glass">
      <div class="head">
        <span class="title">{{ t('top.quick') }}</span>
        <n-button size="tiny" quaternary @click="emit('update:show', false)">{{ t('common.close') }} ›</n-button>
      </div>
      <div class="rows">
        <div v-if="!isLive2D" class="row">
          <span class="row-label">{{ t('quick.shot') }}</span>
          <n-button v-for="c in sizeShots" :key="c.id" size="small" quaternary
                    :type="currentShot === c.id && !currentCamera ? 'primary' : 'default'"
                    @click="setCam(c.id)">{{ t('cam.' + c.id) }}</n-button>
        </div>
        <div v-if="!isLive2D" class="row">
          <span class="row-label">{{ t('quick.move') }}</span>
          <n-button v-for="c in moveShots" :key="c.id" size="small" quaternary
                    :type="currentShot === c.id && !currentCamera ? 'primary' : 'default'"
                    @click="setCam(c.id)">{{ t('cam.' + c.id) }}</n-button>
        </div>
        <div class="row">
          <span class="row-label">{{ t('quick.face') }}</span>
          <n-button v-for="e in emotions" :key="e.key" size="small"
                    :type="currentEmotion === e.key ? 'primary' : 'default'"
                    :quaternary="currentEmotion !== e.key"
                    @click="setEmotion(e.key)">{{ e.label }}</n-button>
        </div>
        <div v-if="!isLive2D" class="row">
          <span class="row-label">{{ t('quick.stand') }}</span>
          <n-button v-for="s in stands" :key="s.key" size="small"
                    :type="standSlot === s.key ? 'primary' : 'default'"
                    :quaternary="standSlot !== s.key"
                    @click="goStand(s.key)">{{ s.label }}</n-button>
        </div>
        <div class="row">
          <span class="row-label">{{ t('quick.act') }}</span>
          <n-button v-for="a in actions" :key="a.key" size="small" quaternary
                    @click="stage.triggerAction(a.key)">{{ a.label }}</n-button>
        </div>
      </div>

      <n-tabs v-model:value="activeTab" type="segment" size="small" class="tabs">
        <n-tab-pane v-if="isLive2D" name="live2d" tab="Live2D 高级互动">
          <Live2DPanel />
        </n-tab-pane>
        <n-tab-pane name="motions" :tab="`${t('quick.motions')} (${assets.motions.length})`" :disabled="!supportsMotions">
          <div v-if="!supportsMotions" class="empty">{{ t('quick.noVmd') }}</div>
          <template v-else>
            <div class="cat-row">
              <n-button v-for="c in MOTION_CATS" :key="c.key" size="tiny"
                        :type="motionCat === c.key ? 'primary' : 'default'"
                        :quaternary="motionCat !== c.key"
                        @click="motionCat = c.key">
                {{ t('cat.' + c.key) }} {{ catCounts[c.key] }}
              </n-button>
            </div>
            <div class="morph-tools">
              <n-input v-model:value="motionSearch" size="small" :placeholder="t('quick.searchMotion')" clearable />
              <n-button size="small" type="warning" secondary @click="stopMotion">{{ t('quick.stop') }}</n-button>
            </div>
            <div v-if="groupedMotions.length" class="review-nav">
              <n-button size="tiny" :disabled="motionIndex <= 0" @click="playMotionOffset(-1)">‹ 上一个</n-button>
              <span>{{ reviewPosition }}</span>
              <n-button size="tiny" :disabled="motionIndex >= groupedMotions.length - 1" @click="playMotionOffset(1)">下一个 ›</n-button>
            </div>
            <div v-if="!groupedMotions.length" class="empty">{{ t('quick.emptyMotion') }}</div>
            <div v-else class="grid">
              <div v-for="m in groupedMotions" :key="m.id" class="motion-item" :class="{ rejected: isMotionRejected(m) }">
                <n-button size="small" :disabled="isMotionRejected(m)"
                          :type="currentMotion === m.name ? 'primary' : 'default'"
                          :quaternary="currentMotion !== m.name"
                          @click="playMotion(m.name)">{{ settings.locale.reply === 'zh-CN' ? stripCatPrefix(m.label) : motionTitle(m.name, m.label) }}</n-button>
                <n-button size="tiny" quaternary :type="motionReviewStatus(m) === 'approved' ? 'success' : 'default'"
                          @click="setReview(m, 'approved')">可用</n-button>
                <n-button size="tiny" quaternary :type="isMotionRejected(m) ? 'error' : 'default'"
                          @click="setReview(m, 'rejected')">不可用</n-button>
                <n-button v-if="isMotionRejected(m)" size="tiny" quaternary type="warning"
                          @click="removeMotion(m)">删除</n-button>
              </div>
            </div>
          </template>
        </n-tab-pane>
        <n-tab-pane name="cameras" :tab="`${t('quick.cameras')} (${libraryCams.length})`" :disabled="isLive2D">
          <div class="morph-tools">
            <span class="hint-inline">内置运镜点上面「镜头」；这里是镜头 VMD</span>
            <n-button size="small" type="warning" secondary @click="stopCamera">复位</n-button>
          </div>
          <div v-if="!libraryCams.length" class="empty">{{ t('quick.emptyCam') }}</div>
          <div v-else class="grid">
            <n-button v-for="c in libraryCams" :key="c.id" size="small"
                      :type="currentCamera === c.name ? 'primary' : 'default'"
                      :quaternary="currentCamera !== c.name"
                      @click="playCamera(c.name)">{{ stripCatPrefix(c.label) }}</n-button>
          </div>
        </n-tab-pane>
        <n-tab-pane name="morphs" :tab="`${t('quick.morphs')} (${morphNames.length})`">
          <div class="morph-tools">
            <n-input v-model:value="morphSearch" size="small" :placeholder="t('quick.searchMorph')" clearable />
            <n-button size="small" quaternary @click="resetMorphs">{{ t('quick.reset') }}</n-button>
          </div>
          <div class="grid morphs">
            <n-button v-for="name in filteredMorphs" :key="name" size="tiny"
                      :type="activeMorphs.has(name) ? 'primary' : 'default'"
                      :quaternary="!activeMorphs.has(name)"
                      @click="toggleMorph(name)">{{ name }}</n-button>
          </div>
        </n-tab-pane>
      </n-tabs>
    </div>
  </transition>
</template>

<style scoped>
.panel {
  position: absolute;
  top: calc(70px + var(--desk-chrome, 0px));
  right: 16px;
  bottom: 20px;
  width: 330px;
  z-index: 9;
  padding: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 16px;
  background: rgba(15, 15, 26, 0.72);
  backdrop-filter: blur(18px);
  box-shadow: 0 14px 44px rgba(0, 0, 0, 0.4);
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.title {
  font-size: 14px;
  font-weight: 600;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.row-label {
  font-size: 12px;
  opacity: 0.6;
  width: 32px;
  flex-shrink: 0;
}

.tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tabs :deep(.n-tab-pane) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
}

.motion-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: 6px;
}

.motion-item.rejected {
  background: rgba(255, 100, 100, 0.1);
}

.motion-item.rejected > :first-child {
  opacity: 0.5;
  text-decoration: line-through;
}

.morph-tools {
  display: flex;
  gap: 6px;
  padding-top: 8px;
}

.review-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  font-size: 12px;
  opacity: 0.8;
}

.cat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-top: 8px;
}

.hint-inline {
  font-size: 11px;
  opacity: 0.55;
  flex: 1;
}

.empty {
  padding: 20px 6px;
  font-size: 13px;
  opacity: 0.55;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(30px);
  opacity: 0;
}
</style>
