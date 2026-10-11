<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, useMessage } from 'naive-ui';
import {
  liveNow,
  liveRecent,
  repertoire,
  type ApprovedBeat,
} from '../performance/repertoire';
import { banApprovedCombo } from '../review/camReview';
import { motionTitle, t } from '../../i18n';
import { useAssetsStore } from '../../stores/assets';
import { useSettingsStore } from '../../stores/settings';
import { stripCatPrefix } from '../assets/motionMeta';

const OPEN_KEY = 'xiaoke.livebeat.open';
const message = useMessage();
const settings = useSettingsStore();
const assets = useAssetsStore();
const banning = ref(false);
const banned = ref(new Set<string>());
const open = ref(false);
try {
  open.value = localStorage.getItem(OPEN_KEY) === '1';
} catch { /* */ }

function toggle() {
  open.value = !open.value;
  try {
    localStorage.setItem(OPEN_KEY, open.value ? '1' : '0');
  } catch { /* */ }
}

const now = computed(() => liveNow.value);

function labelsOf(beat: ApprovedBeat) {
  settings.locale.ui;
  const size = t(`cam.${beat.size}`);
  let cam = t('beat.hold');
  if (beat.idleMove) cam = t(`idle.${beat.idleMove}`);
  else if (beat.camKind === 'move' && beat.camMove) cam = t(`cam.${beat.camMove}`);
  else if (beat.camKind === 'vmd' && beat.vmdName) {
    const raw = assets.cameras.find((c) => c.name === beat.vmdName);
    cam = stripCatPrefix(raw?.label || '') || beat.vmdName;
  }
  let action = t('beat.none');
  let group = '';
  if (beat.actionKind === 'builtin' && beat.builtin) {
    action = t(`act.${beat.builtin}`);
    group = action;
  } else if (beat.actionKind === 'asset' && beat.assetName) {
    const raw = assets.motions.find((m) => m.name === beat.assetName);
    action = motionTitle(beat.assetName, stripCatPrefix(raw?.label || ''));
    const tag = beat.intents[0];
    group = tag ? t(`intent.${tag}`) : '';
  }
  return { size, cam, stand: t(`stand.${beat.stand}`), action, group };
}

const labels = computed(() => (now.value ? labelsOf(now.value.beat) : null));
const actionText = computed(() => {
  if (!labels.value) return '';
  const { group, action } = labels.value;
  if (action === t('beat.none')) return action;
  return group && group !== action ? `${group} · ${action}` : action;
});
const recent = computed(() => {
  const cur = now.value?.beat.id;
  return liveRecent.value.filter((b) => b.id !== cur).slice(0, 3);
});
const currentBanned = computed(() => !!now.value && banned.value.has(now.value.beat.id));

function lineOf(beat: ApprovedBeat) {
  const d = labelsOf(beat);
  const act = d.action === t('beat.none') || !d.group || d.group === d.action
    ? d.action
    : `${d.group} · ${d.action}`;
  return `${d.size} × ${d.cam} × ${d.stand} × ${act}`;
}

async function ban(id: string) {
  if (banning.value || banned.value.has(id)) return;
  banning.value = true;
  try {
    repertoire.drop(id);
    await banApprovedCombo(id);
    banned.value = new Set([...banned.value, id]);
    message.success(t('beat.banned'));
  } catch {
    message.error(t('beat.banFail'));
  } finally {
    banning.value = false;
  }
}
</script>

<template>
  <div class="hud glass" :class="{ shut: !open }">
    <button type="button" class="cap" @click="toggle">
      {{ t('beat.title') }}
      <span class="fold">{{ open ? t('common.close') : t('beat.expand') }}</span>
    </button>
    <template v-if="open && now && labels">
      <div class="chips">
        <span class="chip"><em>{{ t('beat.size') }}</em>{{ labels.size }}</span>
        <span class="chip"><em>{{ t('beat.cam') }}</em>{{ labels.cam }}</span>
        <span class="chip"><em>{{ t('beat.stand') }}</em>{{ labels.stand }}</span>
        <span class="chip" :class="{ dim: !now.motion }">
          <em>{{ t('beat.act') }}</em>{{ actionText }}
        </span>
      </div>
      <n-button size="tiny" type="error" ghost
                :disabled="banning || currentBanned"
                :loading="banning && !currentBanned"
                @click="ban(now.beat.id)">
        {{ currentBanned ? t('beat.gone') : t('beat.bad') }}
      </n-button>
    </template>
    <p v-else-if="open" class="empty">{{ t('beat.empty') }}</p>
    <div v-if="open && recent.length" class="recent">
      <div class="sub">{{ t('beat.recent') }}</div>
      <div v-for="b in recent" :key="b.id" class="row">
        <span class="line">{{ lineOf(b) }}</span>
        <n-button size="tiny" quaternary type="error"
                  :disabled="banning || banned.has(b.id)"
                  @click="ban(b.id)">
          {{ banned.has(b.id) ? t('beat.gone') : t('beat.drop') }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hud {
  position: absolute;
  top: calc(68px + var(--desk-chrome, 0px));
  right: 16px;
  z-index: 8;
  width: min(340px, calc(100vw - 32px));
  padding: 10px 12px 12px;
  pointer-events: none;
}
.hud.shut {
  width: auto;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(16, 16, 28, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(16px);
}
.hud :deep(.n-button),
.hud .cap {
  pointer-events: auto;
}
.cap {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0 0 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 11px;
  letter-spacing: 0.08em;
  opacity: 0.55;
  cursor: pointer;
  text-align: left;
}
.shut .cap { margin: 0; }
.fold {
  margin-left: auto;
  letter-spacing: 0.04em;
  opacity: 0.7;
}
.sub {
  font-size: 11px;
  letter-spacing: 0.08em;
  opacity: 0.45;
  margin: 10px 0 4px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.chip {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 13px;
  font-weight: 600;
}
.chip em {
  font-style: normal;
  font-weight: 500;
  font-size: 10px;
  opacity: 0.5;
}
.chip.dim { opacity: 0.45; }
.empty {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  opacity: 0.5;
}
.row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
}
.line {
  flex: 1;
  font-size: 11px;
  line-height: 1.4;
  opacity: 0.72;
}
</style>
