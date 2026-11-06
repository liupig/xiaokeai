<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { live2dStage } from './index';

const host = ref<HTMLDivElement | null>(null);

onMounted(() => {
  if (host.value) live2dStage.init(host.value);
});

onBeforeUnmount(() => {
  live2dStage.dispose();
});
</script>

<template>
  <div ref="host" class="live2d-layer" />
</template>

<style scoped>
.live2d-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}
</style>
