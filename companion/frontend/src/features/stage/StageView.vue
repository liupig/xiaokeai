<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { NSpin } from 'naive-ui';
import { stage } from '../../engine/stage';
import { installMocap } from '../mocap';
import { useCharacterStore } from '../../stores/character';

const container = ref<HTMLDivElement | null>(null);
const characters = useCharacterStore();

onMounted(() => {
  installMocap(stage);
  if (container.value) stage.init(container.value);
});
</script>

<template>
  <div ref="container" class="stage"></div>
  <div v-if="characters.modelLoading" class="loading glass">
    <n-spin size="small" />
    <span>模型加载中…</span>
  </div>
  <div v-if="characters.modelError" class="loading glass error">
    {{ characters.modelError }}
  </div>
</template>

<style scoped>
.stage {
  position: absolute;
  inset: 0;
}

.stage :deep(canvas) {
  display: block;
}

.loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 14px 26px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  z-index: 5;
}

.error {
  color: #ff8a8a;
  max-width: 60vw;
}
</style>
