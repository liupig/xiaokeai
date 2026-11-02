<script setup lang="ts">
import { getLogoUrl, type LogoVariant } from '../branding';

defineProps<{ variant?: LogoVariant; size?: number | string }>();
</script>

<template>
  <img :src="getLogoUrl(variant)" alt="xiaoke.ai" :width="size ?? 24" :height="size ?? 24" class="brand-logo" draggable="false" />
</template>

<style scoped>
.brand-logo { display: inline-block; flex: none; object-fit: contain; vertical-align: middle; }
</style>
