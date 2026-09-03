<script setup lang="ts">
const show = Boolean(window.companionDesktop?.isShell);
</script>

<template>
  <div v-if="show" class="chrome">
    <span class="dot" />
    <span class="name">Companion Studio</span>
  </div>
</template>

<style scoped>
.chrome {
  position: absolute;
  top: 0;
  left: 0;
  right: var(--desk-controls, 0px);
  height: var(--desk-chrome, 36px);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  z-index: 30;
  pointer-events: none;
  -webkit-app-region: drag;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: rgba(232, 232, 240, 0.78);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7a7af0;
  box-shadow: 0 0 10px rgba(91, 91, 214, 0.85);
}
.name {
  opacity: 0.9;
}
</style>
