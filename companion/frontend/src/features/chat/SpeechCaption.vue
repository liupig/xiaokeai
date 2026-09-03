<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import { speechPlayer } from '../voice/tts';

const line = ref('');
const said = ref('');
const now = ref('');
const wait = ref('');
const waiting = ref(false);
let raf = 0;

function paint(text: string, p: number) {
  const chars = Array.from(text);
  waiting.value = p <= 0;
  let n = Math.floor(chars.length * p);
  if (p > 0 && n < 1) n = 1;
  if (p >= 0.995) n = chars.length;
  if (n <= 0) {
    said.value = '';
    now.value = chars[0] || '';
    wait.value = chars.slice(1).join('');
  } else {
    said.value = chars.slice(0, n - 1).join('');
    now.value = chars[n - 1] || '';
    wait.value = chars.slice(n).join('');
  }
}

function tick() {
  const cap = speechPlayer.liveCaption();
  if (!cap) {
    line.value = '';
    said.value = '';
    now.value = '';
    wait.value = '';
    waiting.value = false;
  } else {
    line.value = cap.text;
    paint(cap.text, cap.progress);
  }
  raf = requestAnimationFrame(tick);
}

raf = requestAnimationFrame(tick);
onUnmounted(() => cancelAnimationFrame(raf));
</script>

<template>
  <transition name="cap">
    <div v-if="line" class="caption-layer" aria-live="polite">
      <p class="caption">
        <span class="said">{{ said }}</span><span class="now" :class="{ waiting }">{{ now }}</span><span class="wait">{{ wait }}</span>
      </p>
    </div>
  </transition>
</template>

<style scoped>
.caption-layer {
  position: absolute;
  left: calc(20px + min(372px, 100vw - 40px) + 16px);
  right: 24px;
  bottom: 8vh;
  z-index: 9;
  pointer-events: none;
  display: flex;
  justify-content: center;
}

.caption {
  margin: 0;
  max-width: 36em;
  padding: 6px 18px 8px;
  border-radius: 12px;
  background: rgba(6, 6, 14, 0.32);
  text-align: center;
  font-size: clamp(16px, 1.7vw, 22px);
  font-weight: 500;
  line-height: 1.65;
  letter-spacing: 0.04em;
  white-space: pre-wrap;
  word-break: break-word;
}

.said {
  color: rgba(255, 255, 255, 0.94);
  text-shadow:
    0 0 3px rgba(0, 0, 0, 0.95),
    0 2px 12px rgba(0, 0, 0, 0.8);
}

.now {
  color: #fff;
  text-shadow:
    0 0 3px rgba(0, 0, 0, 0.95),
    0 0 14px rgba(196, 181, 253, 0.85);
}

.now.waiting {
  animation: cap-pulse 0.9s ease-in-out infinite;
}

@keyframes cap-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}

.wait {
  color: rgba(255, 255, 255, 0.34);
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.75);
}

.cap-enter-active,
.cap-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}

.cap-enter-from,
.cap-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
