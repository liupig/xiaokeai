<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, NColorPicker, NSelect, NSlider, NSwitch } from 'naive-ui';
import { stage } from '../../engine/stage';
import { t } from '../../i18n';
import {
  lightingPresets, readLighting, saveLighting,
  type LightingPreset, type LightingProfile, type LightingSettings,
} from './preferences';

const lighting = ref(readLighting());
const presetOptions = computed(() => (Object.keys(lightingPresets) as LightingPreset[]).map(
  (value) => ({ value, label: t('lighting.' + value) }),
));
const customized = computed(() => {
  const { preset, profile } = lighting.value;
  const base = lightingPresets[preset];
  return (Object.keys(base) as (keyof LightingProfile)[]).some((key) => base[key] !== profile[key]);
});

function update(next: LightingSettings) {
  lighting.value = next;
  stage.setCharacterLighting(next);
  saveLighting(next);
}

function selectPreset(preset: LightingPreset) {
  update({ ...lighting.value, preset, profile: { ...lightingPresets[preset] } });
}

function patchProfile(patch: Partial<LightingProfile>) {
  update({ ...lighting.value, profile: { ...lighting.value.profile, ...patch } });
}
</script>

<template>
  <section class="lighting-controls" :aria-label="t('lighting.title')">
    <div class="lighting-row">
      <label for="character-lighting-enabled">{{ t('lighting.title') }}</label>
      <n-switch id="character-lighting-enabled" :value="lighting.enabled"
                @update:value="(enabled) => update({ ...lighting, enabled })" />
    </div>
    <template v-if="lighting.enabled">
      <n-select :aria-label="t('lighting.preset')" :value="lighting.preset"
                :options="presetOptions" @update:value="selectPreset" />
      <div v-if="customized" class="lighting-row">
        <span>{{ t('lighting.custom') }}</span>
        <n-button size="small" @click="selectPreset(lighting.preset)">{{ t('lighting.reset') }}</n-button>
      </div>
      <label>{{ t('lighting.direction') }}</label>
      <n-slider :aria-label="t('lighting.direction')" :value="lighting.profile.direction"
                :min="-180" :max="180"
                @update:value="(direction: number) => patchProfile({ direction })" />
      <label>{{ t('lighting.contrast') }}</label>
      <n-slider :aria-label="t('lighting.contrast')" :value="lighting.profile.contrast"
                :min="-100" :max="100"
                @update:value="(contrast: number) => patchProfile({ contrast })" />
      <label>{{ t('lighting.color') }}</label>
      <n-color-picker :aria-label="t('lighting.color')" :value="lighting.profile.color"
                      :modes="['hex']" :show-alpha="false"
                      @update:value="(color) => patchProfile({ color })" />
      <div class="lighting-row">
        <label for="character-lighting-toon">{{ t('lighting.toon') }}</label>
        <n-switch id="character-lighting-toon" :value="lighting.profile.toon"
                  @update:value="(toon) => patchProfile({ toon })" />
      </div>
      <div class="lighting-row">
        <label for="character-lighting-outline">{{ t('lighting.outline') }}</label>
        <n-switch id="character-lighting-outline" :value="lighting.profile.outline"
                  @update:value="(outline) => patchProfile({ outline })" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.lighting-controls {
  display: grid;
  gap: 8px;
}
.lighting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
