<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';
import {
  closeDanmakuPanel, douyinFeed, showDanmakuPanel, startDouyinFeed, stopDouyinFeed,
} from './douyinFeed';
import { liveDesk } from './session';

const settings = useSettingsStore();
const scroller = ref<HTMLElement | null>(null);
const liveOn = computed(() => settings.modules.live);
const lines = computed(() => (
  liveOn.value ? liveDesk.events.slice(-6) : douyinFeed.lines.slice(-6)
));
const listening = computed(() => (
  liveOn.value
    ? liveDesk.onAir || liveDesk.bilibili.state !== 'idle' || liveDesk.events.length > 0
    : douyinFeed.listening
));
const boardOpen = computed(() => (liveOn.value ? liveDesk.boardOpen : douyinFeed.open));
const showPanel = computed(() => listening.value && boardOpen.value);
const showReopen = computed(() => listening.value && !boardOpen.value);
let actionTimer = 0;

watch(() => liveDesk.action, (act) => {
  window.clearTimeout(actionTimer);
  if (!act) return;
  actionTimer = window.setTimeout(() => {
    if (liveDesk.action === act) liveDesk.action = '';
  }, 4000);
});

function closeBoard() {
  if (liveOn.value) liveDesk.boardOpen = false;
  else closeDanmakuPanel();
}

function openBoard() {
  if (liveOn.value) liveDesk.boardOpen = true;
  else showDanmakuPanel();
}

watch(() => settings.modules.live_douyin && !settings.modules.live, (on) => {
  if (on) startDouyinFeed();
  else if (!settings.modules.live_douyin) {
    stopDouyinFeed();
    douyinFeed.listening = false;
  }
}, { immediate: true });

watch(() => lines.value.length, async () => {
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
});

onUnmounted(() => {
  window.clearTimeout(actionTimer);
  if (!settings.modules.live) stopDouyinFeed();
});
</script>

<template>
  <button v-if="showReopen" type="button" class="reopen" @click="openBoard">
    {{ t('live.douyin.show') }}
  </button>
  <section v-else-if="showPanel" class="board">
    <header>
      <span class="lamp" />
      <span class="title">{{ t('live.douyin.board') }}</span>
      <button type="button" class="close" :aria-label="t('live.douyin.close')" @click="closeBoard">×</button>
    </header>
    <p v-if="liveOn && liveDesk.action" class="chip">{{ t(`live.act.${liveDesk.action}`) }}</p>
    <div ref="scroller" class="list">
      <p v-if="!lines.length" class="empty">{{ douyinFeed.error || t('live.douyin.waiting') }}</p>
      <p v-for="item in lines" :key="item.seq" class="row" :class="item.kind">
        <b>{{ item.nickname || '…' }}</b>
        <span>{{ item.content }}</span>
      </p>
    </div>
  </section>
</template>

<style scoped>
.board,
.reopen {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 15;
  pointer-events: auto;
}

.reopen {
  right: 8px;
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
  font: inherit;
  font-size: 12px;
  letter-spacing: 0.12em;
  cursor: pointer;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
}

.board {
  width: min(196px, calc(100vw - 36px));
  display: flex;
  flex-direction: column;
  padding: 6px 8px 7px;
  border-radius: 12px 0 0 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.22);
  box-shadow: none;
  color: rgba(255, 255, 255, 0.96);
}

header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.lamp {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #ff8eae;
  box-shadow: 0 0 8px rgba(255, 142, 174, 0.9);
}

.title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.22em;
  opacity: 0.62;
}

.close {
  margin-left: auto;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.close:hover {
  color: #fff;
}

.list {
  overflow: hidden;
}

.chip {
  margin: 6px 0 0;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #ffe7a3;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.55);
}

.list::-webkit-scrollbar {
  display: none;
}

.empty {
  margin: 8px 0 4px;
  font-size: 12px;
  opacity: 0.72;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.55);
}

.row {
  margin: 0;
  padding: 3px 0;
  font-size: 12.5px;
  line-height: 1.4;
  word-break: break-word;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.65);
}

.row b {
  margin-right: 6px;
  font-weight: 600;
  font-size: 11px;
  color: rgba(190, 224, 255, 0.95);
}

.row.gift b { color: #ffe0a3; }
.row.like b { color: #ffc0d6; }
.row.follow b { color: #b7efd0; }
</style>
