<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { artUrl } from './copy';

const props = defineProps<{
  face: string;
  art?: string;
  name: string;
  role?: string;
  back?: boolean;
  on?: boolean;
  large?: boolean;
  hero?: boolean;
  slim?: boolean;
}>();

const emit = defineEmits<{ click: []; preview: [] }>();
const broken = ref(false);
const src = computed(() => artUrl(props.back ? 'back' : (props.art || props.face)));
watch(src, () => { broken.value = false; });
</script>

<template>
  <button type="button"
          class="card"
          :class="[back ? 'is-back' : `face-${face}`, { on, large, hero, slim }]"
          @click="emit('click')"
          @contextmenu.prevent="emit('preview')"
          @dblclick.stop="emit('preview')">
    <span class="slab">
      <img v-if="!broken"
           :src="src"
           alt=""
           draggable="false"
           @error="broken = true" />
      <span v-if="!back" class="plate">
        <small v-if="role">{{ role }}</small>
        <b>{{ name }}</b>
      </span>
    </span>
  </button>
</template>

<style scoped>
.card {
  position: relative;
  width: 108px;
  aspect-ratio: 2 / 3;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  flex: 0 0 auto;
  color: inherit;
  perspective: 800px;
  overflow: visible;
}
.card.slim { width: 72px; }
.card.large { width: 148px; }
.card.hero { width: min(320px, 72vw); }
.slab {
  position: relative;
  display: block;
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  transform: rotateX(7deg) rotateY(-13deg);
  transform-style: preserve-3d;
  transition: transform 0.2s ease;
  box-shadow:
    2px 2px 0 #e6d3b4,
    4px 4px 0 #b08958,
    6px 6px 0 #6e5430,
    12px 16px 22px rgba(0, 0, 0, 0.42);
}
.slab::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  box-shadow:
    inset 0 0 0 1px rgba(255, 236, 210, 0.55),
    inset 0 12px 18px rgba(255, 255, 255, 0.14);
}
.card:hover .slab { transform: rotateX(3deg) rotateY(-6deg) translateY(-8px); }
.card.on .slab,
.card.on:hover .slab { transform: translateY(-16px) rotateX(2deg) rotateY(-4deg); }
.card.hero .slab { transform: rotateX(4deg) rotateY(-8deg); border-radius: 16px; }
.card.hero:hover .slab { transform: rotateY(-3deg) translateY(-6px); }
.card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 16%;
  display: block;
}
.face-loli .slab {
  background: radial-gradient(circle at 50% 28%, #ffe8f1, #f0a9c4 55%, #e7c4a4);
  box-shadow:
    2px 2px 0 #ffd6e8,
    4px 4px 0 #e7a0bf,
    6px 6px 0 #a85d86,
    12px 16px 22px rgba(0, 0, 0, 0.42);
}
.face-girl .slab {
  background: linear-gradient(160deg, #fff4c4, #8fd0ff 70%, #ffe08a);
  box-shadow:
    2px 2px 0 #ffe7a0,
    4px 4px 0 #f0c14b,
    6px 6px 0 #8a6a22,
    12px 16px 22px rgba(0, 0, 0, 0.42);
}
.face-lady .slab {
  background: linear-gradient(180deg, #d5e6f5, #6d86a8 42%, #1c2c40);
  box-shadow:
    2px 2px 0 #d5e4f2,
    4px 4px 0 #8aa4c4,
    6px 6px 0 #3d5570,
    12px 16px 22px rgba(0, 0, 0, 0.42);
}
.face-mei .slab { background: radial-gradient(circle at 50% 30%, #6a3d78, #241228 62%, #c6a15a); }
.face-ying .slab { background: linear-gradient(200deg, #d5dde6, #1a2430 45%, #070b10); }
.is-back .slab { background: #1b2744; }
.plate {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 22px 6px 8px;
  background: linear-gradient(transparent, rgba(12, 8, 14, 0.82));
  pointer-events: none;
}
.plate small {
  font-size: 10px;
  letter-spacing: 0.22em;
  color: #f0d48a;
}
.plate b {
  font-weight: 500;
  font-size: 15px;
  letter-spacing: 0.18em;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}
.slim .plate { padding: 14px 4px 5px; }
.slim .plate b { font-size: 12px; letter-spacing: 0.08em; }
.face-loli .plate b { color: #fff7fb; }
.face-girl .plate b { color: #fffdf5; }
.face-lady .plate b { color: #eef4fb; }
.face-mei .plate b { color: #ffe7a8; }
.face-ying .plate b { color: #e7eef5; }
</style>
