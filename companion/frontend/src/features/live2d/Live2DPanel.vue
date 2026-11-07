<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  NButton, NEmpty, NInput, NSlider, NSwitch, NTabPane, NTabs,
} from 'naive-ui';
import { live2dStage } from '../../engine/live2d';
import { t } from '../../i18n';
import { useCharacterStore } from '../../stores/character';

const characters = useCharacterStore();
const activeExpressions = ref<string[]>([]);
const currentMotion = ref('');
const parameterSearch = ref('');
const showAllParameters = ref(false);
const parameterValues = ref<Record<string, number>>({});
const gaze = ref(true);
const zoom = ref(1);
const error = ref('');
const busyExpression = ref('');
const presetName = ref('');
const presetNames = ref<string[]>([]);

const OUTFIT_RE = /glasses|cloth|sticker|whale|claw|phone|omurice|parfait|brush|eraser|headband|ponytail|paw|order|board|squeeze|flowers/i;
const BASE_PARAMETER_RE = /Param(Angle|BodyAngle|Eye|Brow|Mouth|Cheek)/;

const motionGroups = computed(() => {
  void characters.modelInfo?.url;
  return live2dStage.motionGroups;
});
const expressions = computed(() => {
  void characters.modelInfo?.url;
  return live2dStage.expressionNames;
});
const outfitExpressions = computed(() => expressions.value.filter((name) => OUTFIT_RE.test(name)));
const emotionExpressions = computed(() => expressions.value.filter((name) => !OUTFIT_RE.test(name)));
const parameters = computed(() => {
  void characters.modelInfo?.url;
  return live2dStage.parameterMeta();
});
const filteredParameters = computed(() => {
  const query = parameterSearch.value.trim().toLowerCase();
  return parameters.value.filter((parameter) => {
    if (!showAllParameters.value && !BASE_PARAMETER_RE.test(parameter.id)) return false;
    return !query || parameter.id.toLowerCase().includes(query)
      || parameter.name.toLowerCase().includes(query);
  });
});

function label(name: string) {
  return name.replaceAll('_', ' ');
}

function refresh() {
  activeExpressions.value = [...live2dStage.activeExpressions];
  parameterValues.value = Object.fromEntries(parameters.value.map((item) => [item.id, item.value]));
  gaze.value = live2dStage.view.gaze;
  zoom.value = live2dStage.view.zoom;
  currentMotion.value = '';
  presetNames.value = [...live2dStage.presets];
  error.value = '';
}

watch(() => characters.modelInfo?.url, refresh, { immediate: true });

function savePreset() {
  if (!live2dStage.savePreset(presetName.value)) return;
  presetNames.value = [...live2dStage.presets];
  presetName.value = '';
}

async function applyPreset(name: string) {
  await live2dStage.applyPreset(name);
  refresh();
}

function deletePreset(name: string) {
  live2dStage.deletePreset(name);
  presetNames.value = [...live2dStage.presets];
}

function playMotion(group: string, index: number) {
  if (live2dStage.playMotion(group, index)) currentMotion.value = `${group}:${index}`;
}

function stopMotion() {
  live2dStage.stopMotion();
  currentMotion.value = '';
}

async function toggleExpression(name: string) {
  if (busyExpression.value) return;
  busyExpression.value = name;
  error.value = '';
  try {
    const enabled = !activeExpressions.value.includes(name);
    await live2dStage.setExpressionEnabled(name, enabled);
    activeExpressions.value = [...live2dStage.activeExpressions];
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busyExpression.value = '';
  }
}

function setGaze(value: boolean) {
  gaze.value = value;
  live2dStage.setGazeEnabled(value);
}

function setZoom(value: number) {
  zoom.value = value;
  live2dStage.setZoom(value);
}

function setParameter(id: string, value: number) {
  parameterValues.value[id] = value;
  live2dStage.setParameter(id, value);
}

function resetParameter(id: string) {
  live2dStage.resetParameter(id);
  const value = parameters.value.find((item) => item.id === id)?.defaultValue ?? 0;
  parameterValues.value[id] = value;
}

function resetParameters() {
  live2dStage.resetParameters();
  parameterValues.value = Object.fromEntries(parameters.value.map((item) => [item.id, item.defaultValue]));
}
</script>

<template>
  <div class="live2d-panel">
    <n-tabs type="segment" size="small" animated>
      <n-tab-pane name="interaction" :tab="t('live2d.interaction')">
        <div class="section">
          <div class="switch-row">
            <span>{{ t('live2d.gaze') }}</span>
            <n-switch :value="gaze" @update:value="setGaze" />
          </div>
          <p class="hint">{{ t('live2d.gazeHint') }}</p>
        </div>
        <div class="section">
          <div class="section-head"><span>{{ t('live2d.size') }}</span><span>{{ Math.round(zoom * 100) }}%</span></div>
          <n-slider :value="zoom" :min="0.1" :max="3" :step="0.01" @update:value="setZoom" />
          <p class="hint">{{ t('live2d.sizeHint') }}</p>
          <n-button size="small" secondary @click="live2dStage.resetView(); zoom = 0.3">{{ t('live2d.resetView') }}</n-button>
        </div>
        <div class="section">
          <div class="section-head"><span>{{ t('live2d.nativeMotions') }}</span>
            <n-button size="tiny" quaternary @click="stopMotion">{{ t('live2d.stop') }}</n-button>
          </div>
          <n-empty v-if="!motionGroups.length" :description="t('live2d.noMotions')" size="small" />
          <div v-for="group in motionGroups" :key="group.group" class="motion-group">
            <div class="group-name">{{ group.group }} · {{ group.count }}</div>
            <div class="button-grid">
              <n-button v-for="index in group.count" :key="index" size="tiny"
                        :type="currentMotion === `${group.group}:${index - 1}` ? 'primary' : 'default'"
                        :quaternary="currentMotion !== `${group.group}:${index - 1}`"
                        @click="playMotion(group.group, index - 1)">
                {{ group.group }}_{{ index - 1 }}
              </n-button>
            </div>
          </div>
        </div>
        <div class="section">
          <div class="section-head"><span>{{ t('live2d.presets') }}</span></div>
          <div class="preset-save">
            <n-input v-model:value="presetName" size="small" :placeholder="t('live2d.presetPlaceholder')" maxlength="32" />
            <n-button size="small" :disabled="!presetName.trim()" @click="savePreset">{{ t('live2d.save') }}</n-button>
          </div>
          <p class="hint">{{ t('live2d.presetHint') }}</p>
          <div v-for="name in presetNames" :key="name" class="preset-row">
            <n-button size="tiny" secondary @click="applyPreset(name)">{{ name }}</n-button>
            <n-button size="tiny" quaternary @click="deletePreset(name)">{{ t('live2d.delete') }}</n-button>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="outfits" :tab="t('live2d.outfits')">
        <p class="hint">{{ t('live2d.outfitHint') }}</p>
        <n-empty v-if="!outfitExpressions.length" :description="t('live2d.noOutfits')" size="small" />
        <div class="button-grid expressions">
          <n-button v-for="name in outfitExpressions" :key="name" size="small"
                    :type="activeExpressions.includes(name) ? 'primary' : 'default'"
                    :quaternary="!activeExpressions.includes(name)"
                    :loading="busyExpression === name" @click="toggleExpression(name)">
            {{ label(name) }}
          </n-button>
        </div>
        <div class="section-head emotion-title"><span>{{ t('live2d.emotionEffects') }}</span></div>
        <div class="button-grid expressions">
          <n-button v-for="name in emotionExpressions" :key="name" size="small"
                    :type="activeExpressions.includes(name) ? 'primary' : 'default'"
                    :quaternary="!activeExpressions.includes(name)"
                    :loading="busyExpression === name" @click="toggleExpression(name)">
            {{ label(name) }}
          </n-button>
        </div>
      </n-tab-pane>

      <n-tab-pane name="parameters" :tab="t('live2d.parameters')">
        <div class="tools">
          <n-input v-model:value="parameterSearch" size="small" :placeholder="t('live2d.searchParameters')" clearable />
          <n-button size="small" quaternary @click="showAllParameters = !showAllParameters">
            {{ showAllParameters ? t('live2d.baseParameters') : t('live2d.allParameters') }}
          </n-button>
          <n-button size="small" quaternary @click="resetParameters">{{ t('live2d.resetAll') }}</n-button>
        </div>
        <p class="hint">{{ t('live2d.parameterHint') }}</p>
        <div v-for="parameter in filteredParameters" :key="parameter.id" class="parameter">
          <div class="parameter-head">
            <span :title="parameter.id">{{ parameter.name }}</span>
            <button class="reset" @click="resetParameter(parameter.id)">{{ t('live2d.reset') }}</button>
          </div>
          <div class="parameter-editor">
            <n-slider :value="parameterValues[parameter.id] ?? parameter.defaultValue"
                      :min="parameter.min" :max="parameter.max"
                      :step="(parameter.max - parameter.min) / 100"
                      @update:value="(value: number) => setParameter(parameter.id, value)" />
            <span class="value">{{ (parameterValues[parameter.id] ?? parameter.defaultValue).toFixed(2) }}</span>
          </div>
        </div>
        <n-empty v-if="!filteredParameters.length" :description="t('live2d.noMatching')" size="small" />
      </n-tab-pane>
    </n-tabs>
    <div v-if="error" class="error">{{ error }}</div>
  </div>
</template>

<style scoped>
.live2d-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.section {
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}

.switch-row,
.section-head,
.parameter-head,
.parameter-editor,
.tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-row,
.section-head,
.parameter-head {
  justify-content: space-between;
}

.section-head {
  margin: 8px 0;
  font-size: 12px;
  font-weight: 600;
}

.hint {
  margin: 6px 0;
  font-size: 11px;
  line-height: 1.55;
  opacity: 0.58;
}

.button-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.expressions {
  padding: 8px 0;
}

.motion-group {
  margin: 8px 0;
}

.group-name {
  margin-bottom: 6px;
  font-size: 11px;
  opacity: 0.65;
}

.emotion-title {
  margin-top: 14px;
}

.tools {
  flex-wrap: wrap;
}

.tools :deep(.n-input) {
  flex: 1;
  min-width: 120px;
}

.parameter {
  padding: 7px 0;
}

.parameter-head {
  margin-bottom: 2px;
  font-size: 11px;
}

.parameter-head span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reset {
  padding: 0;
  border: 0;
  color: #8b8bd6;
  background: transparent;
  font-size: 10px;
  cursor: pointer;
}

.parameter-editor :deep(.n-slider) {
  flex: 1;
}

.value {
  width: 44px;
  text-align: right;
  font-size: 10px;
  opacity: 0.65;
}

.preset-save,
.preset-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0;
}

.error {
  color: #ff8a8a;
  font-size: 11px;
}
</style>
