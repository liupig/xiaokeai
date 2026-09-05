<script setup lang="ts">
import { computed } from 'vue';
import { codewatchLive } from './live';
import { mergeSources } from './sources';

const show = computed(() => codewatchLive.open);
const phase = computed(() => codewatchLive.hudPhase || codewatchLive.phase || 'idle');
const label = computed(() => {
  if (phase.value === 'started') return '开工';
  if (phase.value === 'working') return '进行中';
  if (phase.value === 'done') return '完成';
  return '空闲';
});
const waiting = computed(() => codewatchLive.waiting && (phase.value === 'started' || phase.value === 'done'));
const picked = computed(() => (
  codewatchLive.picked.length ? codewatchLive.picked : ['cursor']
));
const desks = computed(() => {
  const ids = picked.value;
  return mergeSources(codewatchLive.sources, ids)
    .filter((row) => ids.includes(row.id))
    .map((row) => ({
      ...row,
      on: row.active || (phase.value !== 'idle' && codewatchLive.source === row.id),
    }));
});
const many = computed(() => desks.value.length > 3);
const title = computed(() => {
  if (phase.value === 'idle') return '';
  if (phase.value === 'working') return (codewatchLive.title || '').trim();
  return (codewatchLive.line || codewatchLive.title || '').trim();
});
const line = computed(() => {
  if (title.value) return title.value;
  if (phase.value === 'idle') return '看着，有活再开口';
  return '';
});
</script>

<template>
  <div v-if="show" class="hud" :class="[phase, { wait: waiting }]">
    <div class="top">
      <div class="brand">
        <span class="lamp" />
        <span class="name">码伴</span>
      </div>
      <span class="pill">{{ label }}</span>
    </div>
    <div class="desks" :class="{ many }">
      <span v-for="d in desks" :key="d.id"
            class="desk" :class="[d.id, { on: d.on, found: d.found }]">
        <i />{{ d.short }}
      </span>
    </div>
    <p class="line" :class="{ mute: !title }">{{ line }}</p>
  </div>
</template>

<style scoped>
.hud {
  position: absolute;
  left: 16px;
  top: calc(68px + var(--desk-chrome, 0px));
  z-index: 8;
  width: min(312px, calc(100vw - 32px));
  padding: 12px 14px 13px;
  pointer-events: none;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(28, 26, 40, 0.62), rgba(12, 12, 20, 0.5));
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(22px) saturate(1.25);
  color: #f6f5fb;
}
.top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.28);
}
.started .lamp,
.wait .lamp {
  background: #b4b4ff;
  box-shadow: 0 0 12px rgba(180, 180, 255, 0.9);
}
.working .lamp {
  background: #7ad4a6;
  box-shadow: 0 0 12px rgba(122, 212, 166, 0.85);
}
.done .lamp {
  background: #efc28a;
  box-shadow: 0 0 12px rgba(239, 194, 138, 0.8);
}
.name {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  opacity: 0.72;
}
.pill {
  margin-left: auto;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.started .pill { color: #d8d8ff; background: rgba(122, 122, 240, 0.18); }
.working .pill { color: #c8f3dc; background: rgba(76, 186, 134, 0.16); }
.done .pill { color: #f8e0b8; background: rgba(224, 168, 90, 0.16); }
.desks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.desks.many {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.desk {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 26px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgba(246, 245, 251, 0.32);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.desk i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.55;
}
.desk.found {
  color: rgba(246, 245, 251, 0.78);
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}
.desk.on {
  color: #fff;
}
.desk.cursor.on {
  background: rgba(122, 122, 240, 0.28);
  border-color: rgba(168, 168, 255, 0.45);
}
.desk.codex.on {
  background: rgba(16, 163, 127, 0.26);
  border-color: rgba(80, 210, 170, 0.45);
}
.desk.cc.on {
  background: rgba(217, 119, 87, 0.28);
  border-color: rgba(240, 170, 140, 0.5);
}
.desk.lingma.on {
  background: rgba(22, 119, 255, 0.26);
  border-color: rgba(120, 176, 255, 0.5);
}
.desk.trae.on {
  background: rgba(45, 212, 191, 0.22);
  border-color: rgba(120, 240, 220, 0.45);
}
.desk.comate.on {
  background: rgba(41, 50, 225, 0.28);
  border-color: rgba(140, 150, 255, 0.5);
}
.desk.on i {
  opacity: 1;
  box-shadow: 0 0 8px currentColor;
}
.line {
  margin: 9px 0 0;
  font-size: 13px;
  line-height: 1.45;
  opacity: 0.86;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line.mute {
  opacity: 0.46;
  font-size: 12px;
}
.working .line {
  -webkit-line-clamp: 1;
  opacity: 0.66;
}
</style>
