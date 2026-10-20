<script setup lang="ts">
import { computed, ref } from 'vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';
import { coins, onCoinDelta, openUserCenter } from './session';

const settings = useSettingsStore();
const pulse = ref<'up' | 'down' | ''>('');
const floaters = ref<{ id: number; text: string; dir: 'up' | 'down' }[]>([]);
let floaterId = 0;
let pulseGen = 0;

function trimNum(n: number) {
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function trimCoins(milli: number) {
  const c = milli / 1000;
  if (c >= 100) return String(Math.floor(c));
  return trimNum(Math.floor(c * 10) / 10);
}

function formatDelta(milli: number) {
  const sign = milli > 0 ? '+' : '-';
  const c = Math.abs(milli) / 1000;
  let body: string;
  if (c >= 100) body = String(Math.floor(c));
  else if (c >= 10) body = trimNum(Math.floor(c * 10) / 10);
  else body = (Math.round(c * 100) / 100).toFixed(2).replace(/\.?0+$/, '');
  if (!body || body === '0') body = '0.01';
  return sign + body;
}

function formatDur(sec: number) {
  settings.locale.ui;
  const whole = Math.max(0, Math.floor(sec));
  if (whole < 60) return t('coin.timeS', { s: whole });
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  if (h > 0 && m === 0) return t('coin.timeHours', { h });
  return h > 0 ? t('coin.timeH', { h, m }) : t('coin.timeM', { m });
}

function kick(dir: 'up' | 'down') {
  const gen = ++pulseGen;
  pulse.value = '';
  requestAnimationFrame(() => {
    if (gen === pulseGen) pulse.value = dir;
  });
}

onCoinDelta((delta) => {
  const dir = delta > 0 ? 'up' : 'down';
  kick(dir);
  const id = ++floaterId;
  floaters.value = [...floaters.value.slice(-2), { id, text: formatDelta(delta), dir }];
  window.setTimeout(() => {
    floaters.value = floaters.value.filter((item) => item.id !== id);
  }, 900);
});

const amount = computed(() => trimCoins(coins.balanceMilli));
const label = computed(() => {
  settings.locale.ui;
  return `${amount.value} ${t('user.asset')}`;
});
const title = computed(() => {
  settings.locale.ui;
  return t('user.streak', { time: formatDur(coins.streakSec) });
});
</script>

<template>
  <button v-if="coins.ready" type="button" class="pill glass"
          :title="title" :aria-label="label" @click="openUserCenter">
    <span class="body" :class="pulse">
      <span class="mark" aria-hidden="true" />
      <span class="amt">{{ amount }}</span>
    </span>
    <span v-for="item in floaters" :key="item.id" class="floater" :class="item.dir">{{ item.text }}</span>
  </button>
</template>

<style scoped>
.pill {
  position: relative;
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  padding: 6px 12px 6px 8px;
  border: none;
  font: inherit;
  color: rgba(255, 236, 214, 0.95);
  white-space: nowrap;
  cursor: pointer;
}
.body {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.body.up {
  animation: coin-pop 0.55s ease;
}
.body.down {
  animation: coin-dip 0.45s ease;
}
.body.up .mark {
  animation: coin-glint 0.55s ease;
}
.mark {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 35% 30%, #fff6dc 0%, #f0d48a 38%, #c4923e 72%, #7a4e22 100%);
  box-shadow: inset 0 -1px 1px rgba(60, 30, 0, 0.45), 0 0 0 1px rgba(255, 231, 194, 0.35);
}
.amt {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
.floater {
  position: absolute;
  left: 50%;
  top: 0;
  font-size: 12px;
  font-weight: 700;
  pointer-events: none;
  animation: coin-float 0.85s ease-out forwards;
}
.floater.up {
  color: #ffe7c2;
}
.floater.down {
  color: #f3c2b0;
}
@keyframes coin-pop {
  0% { transform: scale(1); }
  35% { transform: scale(1.14); }
  100% { transform: scale(1); }
}
@keyframes coin-dip {
  0% { transform: scale(1); }
  40% { transform: scale(0.92); }
  100% { transform: scale(1); }
}
@keyframes coin-glint {
  0% { filter: brightness(1); transform: scale(1); }
  40% { filter: brightness(1.45); transform: scale(1.2); }
  100% { filter: brightness(1); transform: scale(1); }
}
@keyframes coin-float {
  0% { opacity: 0; transform: translate(-50%, 4px); }
  18% { opacity: 1; }
  100% { opacity: 0; transform: translate(-50%, -20px); }
}
@media (prefers-reduced-motion: reduce) {
  .body.up,
  .body.down,
  .body.up .mark,
  .floater {
    animation: none;
  }
}
</style>
