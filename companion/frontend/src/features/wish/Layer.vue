<script setup lang="ts">
import { wishUi } from './session';
</script>

<template>
  <div v-if="wishUi.on" class="wish-layer" aria-live="polite">
    <p class="note">{{ wishUi.caption }}</p>
  </div>
</template>

<style scoped>
.wish-layer {
  position: absolute;
  inset: 0;
  z-index: 8;
  pointer-events: none;
}
.note {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(72px + var(--desk-chrome, 0px));
  margin: 0 auto;
  width: fit-content;
  padding: 6px 16px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  text-align: center;
  font-size: 13px;
  color: rgba(245, 228, 186, 0.9);
  background: rgba(10, 8, 16, 0.42);
  border: 1px solid rgba(212, 176, 106, 0.28);
}
</style>
