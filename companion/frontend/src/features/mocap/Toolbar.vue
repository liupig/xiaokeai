<script setup lang="ts">
import { computed, ref } from 'vue';
import { NTooltip } from 'naive-ui';
import { startMocap, stopMocap } from './api';
import { mocapState } from './session';

const fileInput = ref<HTMLInputElement | null>(null);
const mocapOn = computed(() => mocapState.status === 'running' || mocapState.status === 'starting');

async function toggleCamera() {
  if (mocapOn.value && mocapState.source === 'camera') {
    stopMocap();
    return;
  }
  try {
    await startMocap();
  } catch (e) {
    mocapState.status = 'error';
    mocapState.error = e instanceof Error ? e.message : String(e);
  }
}

async function onVideoFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  try {
    await startMocap(file);
  } catch (err) {
    mocapState.status = 'error';
    mocapState.error = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <n-tooltip :delay="300">
    <template #trigger>
      <button class="tool" :class="{
                active: mocapOn && mocapState.source === 'camera',
                rec: mocapState.status === 'running' && mocapState.source === 'camera',
              }"
              @click="toggleCamera">
        <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
             stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M23 7l-7 5 7 5V7z" />
          <rect x="1" y="5" width="15" height="14" rx="2" />
        </svg>
      </button>
    </template>
    {{ mocapOn && mocapState.source === 'camera' ? '停止摄像头动捕' : '摄像头动捕（全身 / 手 / 脸）' }}
  </n-tooltip>
  <n-tooltip :delay="300">
    <template #trigger>
      <button class="tool" :class="{
                active: mocapOn && mocapState.source === 'video',
                rec: mocapState.status === 'running' && mocapState.source === 'video',
              }"
              @click="fileInput?.click()">
        <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
             stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <polygon points="10 9 16 12 10 15" fill="currentColor" stroke="none" />
        </svg>
      </button>
    </template>
    用视频文件测试动捕
  </n-tooltip>
  <input ref="fileInput" type="file" accept="video/*" hidden @change="onVideoFile" />
</template>

<style scoped>
.tool {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tool:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.tool.active {
  background: #5b5bd6;
  color: #fff;
}

.tool.rec {
  background: #c44545;
}
</style>
