<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, NPopover } from 'naive-ui';
import type { CodewatchSourceId } from '../../api/client';
import {
  codewatchLive, closeCodewatch, installHooks, openCodewatch, setPicked, uninstallHooks,
} from './session';
import { mergeSources } from './sources';
import XkIcon from '../icons/XkIcon.vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';

const open = ref(false);
const hookBusy = ref(false);
const hookHint = ref('');
const settings = useSettingsStore();

const phaseLabel = computed(() => {
  settings.locale.ui;
  if (!codewatchLive.open) return t('code.closed');
  if (codewatchLive.phase === 'started') return t('code.started');
  if (codewatchLive.phase === 'working') return t('code.working');
  if (codewatchLive.phase === 'done') return t('code.donePhase');
  return t('code.idle');
});

const live = computed(() => codewatchLive.open);
const desks = computed(() => mergeSources(codewatchLive.sources, codewatchLive.picked));
const picked = computed(() => new Set(codewatchLive.picked));
const pickedNames = computed(() =>
  desks.value.filter((d) => picked.value.has(d.id)).map((d) => d.short).join(' / ') || 'Cursor',
);
const foundN = computed(() => desks.value.filter((d) => d.found && picked.value.has(d.id)).length);

async function pick(id: CodewatchSourceId) {
  if (codewatchLive.picked.length <= 1 && codewatchLive.picked[0] === id) return;
  await setPicked(id);
}

async function toggle() {
  if (codewatchLive.busy) return;
  if (codewatchLive.open) await closeCodewatch();
  else await openCodewatch();
}

async function hookOn() {
  if (hookBusy.value) return;
  hookBusy.value = true;
  hookHint.value = '';
  try {
    await installHooks();
    hookHint.value = t('code.hookInstalled');
  } catch (e) {
    hookHint.value = String(e);
  } finally {
    hookBusy.value = false;
  }
}

async function hookOff() {
  if (hookBusy.value) return;
  hookBusy.value = true;
  hookHint.value = '';
  try {
    await uninstallHooks();
    hookHint.value = t('code.hookRemoved');
  } catch (e) {
    hookHint.value = String(e);
  } finally {
    hookBusy.value = false;
  }
}
</script>

<template>
  <n-popover trigger="click" placement="top" :show="open" @update:show="(v: boolean) => { open = v; }">
    <template #trigger>
      <n-button quaternary circle size="small"
                :type="live ? 'primary' : 'default'"
                :disabled="codewatchLive.busy"
                :title="t('code.title')">
        <XkIcon name="code" :size="18" />
      </n-button>
    </template>
    <div class="pop">
      <p class="lead">{{ t('code.title') }}</p>
      <p class="hint">
        {{ live ? t('code.hintOn', { names: pickedNames, phase: phaseLabel }) : t('code.hintOff') }}
      </p>
      <div class="desks">
        <button
          v-for="d in desks" :key="d.id"
          type="button"
          class="desk"
          :class="{ found: d.found, on: picked.has(d.id) }"
          @click="pick(d.id)"
        >
          {{ d.short }}
        </button>
      </div>
      <p v-if="live && codewatchLive.title" class="title">{{ codewatchLive.title }}</p>
      <p v-if="live && foundN === 0" class="hint warn">{{ t('code.missing') }}</p>
      <div class="ops">
        <button type="button" :disabled="codewatchLive.busy" @click="toggle">
          <strong>{{ live ? t('code.close') : t('code.open') }}</strong>
          <span>{{ live ? t('code.stopFollow') : t('code.follow', { names: pickedNames }) }}</span>
        </button>
      </div>
      <p class="g">{{ t('code.hooks') }}</p>
      <p class="hint">{{ t('code.hooksHint') }}</p>
      <div class="ops">
        <button v-if="!codewatchLive.hooksInstalled" type="button" :disabled="hookBusy" @click="hookOn">
          <strong>{{ t('code.hookOn') }}</strong>
          <span>{{ t('code.hookOnSub') }}</span>
        </button>
        <button v-else type="button" class="ghost" :disabled="hookBusy" @click="hookOff">
          {{ t('code.hookOff') }}
        </button>
      </div>
      <p v-if="hookHint" class="hint">{{ hookHint }}</p>
    </div>
  </n-popover>
</template>

<style scoped>
.pop {
  width: 280px;
  padding: 2px 2px 4px;
}
.lead {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: #d7d7ff;
}
.hint {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.48);
}
.hint.warn { color: #f0c28a; }
.desks {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: -2px 0 10px;
}
.desk {
  appearance: none;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.32);
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
}
.desk:hover {
  color: rgba(255, 255, 255, 0.72);
  border-color: rgba(255, 255, 255, 0.22);
}
.desk.found {
  color: rgba(232, 232, 248, 0.86);
  border-color: rgba(167, 167, 230, 0.35);
}
.desk.on {
  color: #fff;
  background: rgba(91, 91, 214, 0.28);
  border-color: rgba(154, 154, 255, 0.5);
}
.title {
  margin: -4px 0 10px;
  font-size: 12px;
  color: rgba(232, 232, 240, 0.82);
}
.g {
  margin: 12px 0 4px;
  font-size: 10px;
  letter-spacing: 0.12em;
  color: rgba(167, 167, 230, 0.7);
}
.ops {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ops button {
  appearance: none;
  border: 1px solid rgba(122, 122, 240, 0.4);
  background: rgba(91, 91, 214, 0.16);
  color: #e8e8ff;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ops button span {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.48);
  font-weight: 400;
}
.ops button:hover:not(:disabled) {
  background: rgba(91, 91, 214, 0.28);
}
.ops button.ghost {
  border-color: rgba(255, 255, 255, 0.14);
  background: transparent;
  color: rgba(255, 255, 255, 0.72);
  text-align: center;
  display: block;
}
.ops button:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
