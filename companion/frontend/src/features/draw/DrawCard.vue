<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';
import { dismissDrawnCard, drawnCard } from './card';

function onKey(ev: KeyboardEvent) {
  if (ev.key !== 'Escape') return;
  if (drawnCard.zoom) {
    drawnCard.zoom = false;
    return;
  }
  if (drawnCard.url || drawnCard.waiting) dismissDrawnCard();
}

onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<template>
  <div
    v-if="(drawnCard.url || drawnCard.waiting) && !drawnCard.zoom"
    class="card"
    :class="{ wait: drawnCard.waiting }"
    data-pet-hit
  >
    <button
      type="button"
      class="face"
      :aria-label="drawnCard.waiting ? '在画' : (drawnCard.name || '画')"
      @click="drawnCard.url && (drawnCard.zoom = true)"
    >
      <img v-if="drawnCard.url" :src="drawnCard.url" alt="" />
      <span v-else class="wash" />
      <span v-if="drawnCard.name" class="name">{{ drawnCard.name }}</span>
    </button>
    <button type="button" class="x" aria-label="关闭" @click="dismissDrawnCard">×</button>
  </div>
  <Teleport to="body">
    <div v-if="drawnCard.url && drawnCard.zoom" class="zoom" data-pet-hit @click="drawnCard.zoom = false">
      <button type="button" class="x zoom-x" aria-label="关闭" @click.stop="dismissDrawnCard">×</button>
      <img :src="drawnCard.url" :alt="drawnCard.name || '画'" />
    </div>
  </Teleport>
</template>

<style scoped>
.card {
  position: fixed;
  right: 36px;
  top: 50%;
  z-index: 12;
  width: min(220px, 24vw);
  aspect-ratio: 2 / 3;
  margin: 0;
  padding: 0;
  border: 2px solid rgba(212, 176, 106, 0.92);
  border-radius: 14px;
  overflow: hidden;
  transform: translateY(-50%);
  background: #0c0a12;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.face {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: zoom-in;
}
.card.wait .face { cursor: default; }
.card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.x {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(8, 6, 14, 0.72);
  color: rgba(245, 228, 186, 0.96);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
.zoom-x {
  top: 18px;
  right: 18px;
  width: 36px;
  height: 36px;
  font-size: 22px;
}
.wash {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(110deg, transparent 30%, rgba(245, 228, 186, 0.18) 48%, transparent 62%),
    #16131c;
  background-size: 220% 100%, auto;
  animation: wash 1.6s ease-in-out infinite;
}
@keyframes wash {
  from { background-position: 120% 0, 0 0; }
  to { background-position: -20% 0, 0 0; }
}
.name {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 10px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(8, 6, 14, 0.55);
  color: rgba(245, 228, 186, 0.96);
  font-size: 13px;
  line-height: 1.2;
  text-align: center;
}
.zoom {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.72);
  cursor: zoom-out;
}
.zoom img {
  max-width: min(920px, 88vw);
  max-height: 88vh;
  object-fit: contain;
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
}
</style>
