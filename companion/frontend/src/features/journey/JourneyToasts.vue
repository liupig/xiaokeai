<script setup lang="ts">
import { journeyToasts } from './session';
</script>

<template>
  <div class="journey-toasts" aria-live="polite">
    <article v-for="toast in journeyToasts" :key="toast.id">
      <strong>{{ toast.title }}</strong>
      <p v-for="line in toast.lines" :key="line">{{ line }}</p>
    </article>
  </div>
</template>

<style scoped>
.journey-toasts{position:fixed;z-index:90;right:24px;top:82px;display:grid;gap:10px;width:min(330px,calc(100vw - 32px));pointer-events:none}.journey-toasts article{padding:15px 18px;background:#302724f2;border:1px solid #d4b47a66;border-radius:12px;animation:arrive .22s ease-out}.journey-toasts strong{color:#f0cf9d}.journey-toasts p{margin:6px 0 0;color:#dfcdbb;font-size:12px}@keyframes arrive{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}@media(max-width:600px){.journey-toasts{right:16px;top:68px}}
</style>
