<script setup lang="ts">
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 22 });

const files = import.meta.glob('../../assets/icons/*.png', {
  eager: true,
  import: 'default',
}) as Record<string, string>;

const src = Object.entries(files).find(([path]) => path.endsWith(`/${props.name}.png`))?.[1] ?? '';
</script>

<template>
  <img class="xk-icon" :src="src" :width="size" :height="size" alt="" draggable="false" />
</template>

<style scoped>
.xk-icon {
  display: block;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}
</style>
