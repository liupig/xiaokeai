<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { NButton } from 'naive-ui';
import { startMocap, stopMocap } from './api';
import { mocap, mocapState } from './session';

const wrap = ref<HTMLDivElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

onMounted(() => {
  mountVideo();
});

watch(() => mocapState.status, () => mountVideo());

function mountVideo() {
  if (wrap.value && mocap.video.parentElement !== wrap.value) {
    wrap.value.appendChild(mocap.video);
  }
}

onBeforeUnmount(() => {
  mocap.video.remove();
});

function stop() {
  stopMocap();
}

async function onFile(e: Event) {
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

function pickVideo() {
  fileInput.value?.click();
}

function toggleLoop() {
  mocap.setLoop(!mocapState.loop);
}
</script>

<template>
  <transition name="fade">
    <div v-if="mocapState.status !== 'idle'" class="overlay">
      <div class="preview glass">
        <div ref="wrap" class="video-wrap" :class="{ mirror: mocapState.source === 'camera' }">
          <div v-if="mocapState.status === 'starting'" class="hint">
            {{ mocapState.source === 'video' ? '正在加载视频与检测模型…' : '正在启动摄像头与检测模型…' }}
          </div>
        </div>
        <div class="meta">
          <span class="dot" :class="{ on: mocapState.tracking, wait: mocapState.status === 'starting' }" />
          <span v-if="mocapState.status === 'starting'">初始化</span>
          <span v-else-if="mocapState.status === 'error'">启动失败</span>
          <span v-else-if="mocapState.tracking">
            {{ mocapState.source === 'video' ? '视频' : '摄像头' }} · {{ mocapState.fps }} FPS
          </span>
          <span v-else>未检测到人</span>
          <span v-if="mocapState.inferenceMs" class="ms">{{ mocapState.inferenceMs }}ms</span>
        </div>
        <p v-if="mocapState.error" class="err">{{ mocapState.error }}</p>
        <div class="actions">
          <input ref="fileInput" type="file" accept="video/*" hidden @change="onFile" />
          <n-button size="tiny" secondary @click="pickVideo">打开视频</n-button>
          <n-button v-if="mocapState.source === 'video'" size="tiny" secondary
                    :type="mocapState.loop ? 'primary' : 'default'"
                    @click="toggleLoop">循环</n-button>
          <n-button size="tiny" type="warning" secondary @click="stop">停止</n-button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.overlay {
  position: absolute;
  left: 408px;
  bottom: 20px;
  z-index: 10;
  pointer-events: none;
}

.preview {
  pointer-events: auto;
  padding: 8px;
  width: 240px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.video-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  border-radius: 10px;
  background: #0a0a14;
}

.video-wrap :deep(video) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.video-wrap.mirror :deep(video) {
  transform: scaleX(-1);
}

.hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  opacity: 0.7;
  padding: 8px;
  text-align: center;
  z-index: 1;
}

.meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  opacity: 0.9;
}

.ms {
  margin-left: auto;
  opacity: 0.55;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #666;
  flex-shrink: 0;
}

.dot.wait {
  background: #e6b84d;
  animation: pulse 1s ease infinite;
}

.dot.on {
  background: #5dca7a;
  box-shadow: 0 0 8px #5dca7a;
}

.err {
  font-size: 12px;
  color: #ff8a8a;
  line-height: 1.4;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@keyframes pulse {
  50% { opacity: 0.4; }
}
</style>
