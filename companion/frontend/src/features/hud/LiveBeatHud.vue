<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue';
import { lightTheme, NButton, NConfigProvider, useMessage } from 'naive-ui';
import {
  liveNow,
  liveCamera,
  liveRecent,
  repertoire,
  type ApprovedBeat,
} from '../performance/repertoire';
import { banApprovedCombo } from '../review/camReview';
import { motionTitle, t } from '../../i18n';
import { useAssetsStore } from '../../stores/assets';
import { useSettingsStore } from '../../stores/settings';
import { stripCatPrefix } from '../assets/motionMeta';

const open = ref(false);
const hoverBlocked = ref(false);
const trigger = ref<HTMLButtonElement>();
const closeButton = ref<HTMLButtonElement>();
const headingId = useId();
const panelId = useId();

function activate(event: MouseEvent) {
  open.value = true;
  if (event.detail === 0) void nextTick(() => closeButton.value?.focus());
}

function close(event: Event) {
  hoverBlocked.value = true;
  open.value = false;
  if (event instanceof KeyboardEvent || (event.currentTarget instanceof HTMLElement && event.currentTarget.matches(':focus-visible'))) {
    void nextTick(() => trigger.value?.focus());
  }
}
const message = useMessage();
const settings = useSettingsStore();
const assets = useAssetsStore();
const banning = ref(false);
const banned = ref(new Set<string>());
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

const labels = computed(() => {
  if (!now.value) return null;
  const action = labelsOf(now.value.beat);
  const actual = liveCamera.value ? labelsOf(liveCamera.value) : null;
  return { ...action, size: actual?.size, cam: actual?.cam };
});
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
  <div class="beat-monitor" @pointerleave="hoverBlocked = false">
    <div class="beat-hotspot" @pointerenter="(event) => { if (!open && !hoverBlocked && event.pointerType === 'mouse') open = true; }">
      <button v-show="!open" ref="trigger" type="button" class="beat-trigger stage-cue"
              :aria-label="t('beat.title')" :title="t('beat.title')" :aria-expanded="open"
              :aria-controls="open ? panelId : undefined" @click="activate">
        <span class="stage-cue__wave" aria-hidden="true"></span>
      </button>
    </div>
    <section v-if="open" :id="panelId" class="beat-panel" :aria-labelledby="headingId" @keydown.esc.stop="close">
      <header class="beat-header">
        <h2 :id="headingId">{{ t('beat.title') }}</h2>
        <button ref="closeButton" type="button" class="beat-close" :aria-label="t('common.close')"
                :title="t('common.close')" @click="close">×</button>
      </header>
      <n-config-provider :theme="lightTheme" class="beat-body">
        <template v-if="now && labels">
          <div class="chips">
            <span v-if="labels.size" class="chip"><em>{{ t('beat.size') }}</em>{{ labels.size }}</span>
            <span v-if="labels.cam" class="chip"><em>{{ t('beat.cam') }}</em>{{ labels.cam }}</span>
            <span class="chip"><em>{{ t('beat.stand') }}</em>{{ labels.stand }}</span>
            <span class="chip" :class="{ dim: !now.motion }">
              <em>{{ t('beat.act') }}</em>{{ actionText }}
            </span>
          </div>
          <n-button size="tiny" type="error" ghost
                    :disabled="banning || currentBanned || !now.appliedApprovedCam"
                    :loading="banning && !currentBanned"
                    @click="ban(now.beat.id)">
            {{ currentBanned ? t('beat.gone') : t('beat.bad') }}
          </n-button>
        </template>
        <p v-else class="empty">{{ t('beat.empty') }}</p>
        <div v-if="recent.length" class="recent">
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
      </n-config-provider>
    </section>
  </div>
</template>

<style scoped>
.beat-monitor {
  --beat-top: max(16.6667%, calc(var(--desk-chrome, 0px) + 10px));
  --panel-muted: #514653;
  --panel-line: #79647752;
  position: absolute;
  top: var(--beat-top);
  right: 12px;
  bottom: var(--beat-bottom, 18px);
  width: min(314px, calc(100% - 24px));
  z-index: 12;
  pointer-events: none;
  -webkit-app-region: no-drag;
}
.beat-hotspot { position: absolute; top: 0; right: 0; width: 52px; }
.beat-trigger {
  width: 52px;
  height: 52px;
  pointer-events: auto;
  --cue-accent: #c9e7ff;
  --cue-halo: #9f9aff;
  --cue-delay: 1.5s;
}
.beat-close:focus-visible { outline: 2px solid #775278; outline-offset: -3px; }
.beat-panel {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  border: 1px solid var(--panel-line);
  border-radius: 15px;
  background: #faf3f7;
  color: #302533;
  box-shadow: 0 6px 20px #2b183422;
  pointer-events: auto;
}
.beat-header { display: flex; flex: none; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--panel-line); }
.beat-header h2 { margin: 0; color: #50374f; font-size: 14px; font-weight: 650; }
.beat-close { flex: none; width: 30px; height: 30px; border: 1px solid var(--panel-line); border-radius: 8px; background: transparent; color: var(--panel-muted); font: 20px/1 system-ui; cursor: pointer; }
.beat-close:hover { background: #eadbe7; color: #302533; }
.beat-body { overflow: auto; min-height: 0; padding: 12px; scrollbar-width: thin; }
.sub {
  font-size: 13px;
  font-weight: 600;
  color: var(--panel-muted);
  margin: 16px 0 8px;
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
  background: #f0e5ee;
  border: 1px solid #e5d6e2;
  font-size: 13px;
  font-weight: 600;
}
.chip em {
  font-style: normal;
  font-weight: 500;
  font-size: 10px;
  color: var(--panel-muted);
}
.chip.dim { color: var(--panel-muted); }
.empty {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--panel-muted);
  padding: 24px 12px;
  border: 1px dashed var(--panel-line);
  border-radius: 12px;
  text-align: center;
}
.row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 0;
  border-top: 1px solid var(--panel-line);
}
.line {
  flex: 1;
  font-size: 11px;
  line-height: 1.4;
  color: var(--panel-muted);
}
</style>
