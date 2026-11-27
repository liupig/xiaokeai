<script setup lang="ts">
import { useId } from 'vue';
import { NConfigProvider } from 'naive-ui';
import { t } from '../../i18n';

const props = withDefaults(defineProps<{
  show: boolean;
  title: string;
  size?: 'small' | 'medium' | 'large';
  fixedBody?: boolean;
}>(), { size: 'medium' });
const emit = defineEmits<{ 'update:show': [show: boolean] }>();
const headingId = useId();
const theme = {
  common: {
    primaryColor: '#ebc5a1',
    primaryColorHover: '#f8d8b9',
    primaryColorPressed: '#d9aa80',
    primaryColorSuppl: '#f8d8b9',
    borderRadius: '9px',
  },
};

function close() {
  emit('update:show', false);
}
</script>

<template>
  <NConfigProvider :theme-overrides="theme">
    <section v-if="props.show" class="stage-panel" data-pet-hit :class="`stage-panel--${size}`"
             :aria-labelledby="headingId" @keydown.esc.stop="close">
      <header class="stage-panel__header">
        <h2 :id="headingId">{{ title }}</h2>
        <button type="button" class="stage-panel__close" :aria-label="t('common.close')"
                :title="t('common.close')" @click="close">
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <div class="stage-panel__body" :class="{ 'stage-panel__body--fixed': fixedBody }">
        <slot />
      </div>
      <footer v-if="$slots.footer" class="stage-panel__footer">
        <slot name="footer" />
      </footer>
    </section>
  </NConfigProvider>
</template>

<style>
.stage-panel {
  --panel-width: 492px;
  --panel-ink: #f6ece9;
  --panel-muted: #bcb0ba;
  --panel-accent: #ebc5a1;
  --panel-line: #e8c5d021;
  --panel-card: #ffffff08;
  --panel-pad: clamp(14px, 2vw, 24px);
  position: absolute;
  z-index: 15;
  inset: calc(12px + var(--desk-chrome, 0px)) 12px 12px auto;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(var(--panel-width), calc(100% - 24px));
  border: 1px solid var(--panel-line);
  border-radius: 20px;
  background: radial-gradient(ellipse at top left, #483444 0, transparent 60%), #231e2a;
  box-shadow: 0 18px 52px #140f1b54, inset 0 1px #ffffff0e;
  color: var(--panel-ink);
  box-sizing: border-box;
  -webkit-app-region: no-drag;
}
.stage-panel--small { --panel-width: 366px; }
.stage-panel--large { --panel-width: 702px; }
.has-stage-nav .stage-panel {
  left: var(--stage-nav-clearance);
  right: auto;
  width: min(var(--stage-panel-span), calc(100% - var(--stage-nav-clearance) - 12px));
}
.stage-panel__header,
.stage-panel__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px var(--panel-pad);
}
.stage-panel__header { border-bottom: 1px solid var(--panel-line); }
.stage-panel__header h2 {
  margin: 0;
  font-size: clamp(18px, 2vw, 23px);
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.stage-panel__close {
  display: grid;
  place-items: center;
  flex: none;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--panel-line);
  border-radius: 10px;
  color: var(--panel-muted);
  background: var(--panel-card);
  font: 23px/1 system-ui, sans-serif;
  cursor: pointer;
}
.stage-panel__close:hover { background: #ffffff16; color: var(--panel-ink); }
.stage-panel__close:focus-visible { outline: 2px solid var(--panel-accent); outline-offset: 3px; }
.stage-panel__body {
  min-width: 0;
  overflow: auto;
  padding: var(--panel-pad);
  scrollbar-width: thin;
  scrollbar-color: #795e74 transparent;
}
.stage-panel__body--fixed {
  container: stage-panel / inline-size;
  overflow: hidden;
  padding: 0;
}
.stage-panel__footer {
  border-top: 1px solid var(--panel-line);
  justify-content: flex-end;
  background: #1b172340;
  border-radius: 0 0 20px 20px;
}
</style>
