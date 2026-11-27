<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { NSpin } from 'naive-ui';
import { stage } from '../../engine/stage';
import Live2DLayer from '../../engine/live2d/Live2DLayer.vue';
import { installMocap } from '../mocap';
import { useCharacterStore } from '../../stores/character';
import { endLifeActivity, endLifePreview, leaveLifeStage, refreshLifeStage, returnLifeHome, stageLife } from '../life/stageLife';
import { lifePanelOpen } from '../coins/session';
import { installLifeVehicles } from '../life/vehicles';
import { t } from '../../i18n';

defineProps<{ startingModel?: boolean }>();
const emit = defineEmits<{ 'retry-model': [] }>();
const container = ref<HTMLDivElement | null>(null);
const rendererError = ref('');
const characters = useCharacterStore();
let releaseVehicles: (() => void) | null = null;
const MOMENT_NAMES: Record<string, string> = { tea:'一起喝茶', noodles:'一起吃面', hotpot:'一起吃火锅', cake:'一起吃蛋糕', home_dish:'一起吃家常饭', dessert:'一起吃甜点', coffee:'一起喝咖啡', milk_tea:'一起喝奶茶', fruit_tea:'一起喝果茶', bicycle:'一起看看自行车', scooter:'一起看看踏板车', car:'一起看看电动小车', fuel_car:'一起看看燃油轿车', camper:'一起看看厢式车' };
function rememberMoment() {
  const label = MOMENT_NAMES[stageLife.activity] || (stageLife.activityCategory === 'meal' ? '一起品尝餐点' : stageLife.activityCategory === 'vehicle' ? '一起看看车' : '');
  if (!label) return;
  stageLife.memoryDraft = label;
  lifePanelOpen.value = true;
}

onMounted(() => {
  installMocap(stage);
  if (!container.value) return;
  let rebuilt: boolean;
  try {
    rebuilt = stage.init(container.value);
  } catch (error) {
    rendererError.value = error instanceof Error ? error.message : String(error);
    return;
  }
  refreshLifeStage();
  releaseVehicles = installLifeVehicles();
  if (rebuilt && characters.currentId) void characters.switchTo(characters.currentId);
});

function retryStage() {
  if (rendererError.value) window.location.reload();
  else emit('retry-model');
}
onBeforeUnmount(() => {
  releaseVehicles?.();
  stage.dispose();
});
</script>

<template>
  <div ref="container" class="stage"></div>
  <div v-if="stageLife.active && !stageLife.destination" class="life-props" aria-hidden="true">
    <img v-if="stageLife.placed.includes('lamp') || stageLife.preview === 'lamp'" :src="'/assets/life/lamp.png'" class="life-lamp" alt="" />
    <img v-if="stageLife.placed.includes('picture') || stageLife.preview === 'picture'" :src="'/assets/life/picture.png'" class="life-picture" alt="" />
    <img v-if="stageLife.placed.includes('plant') || stageLife.preview === 'plant'" :src="'/assets/life/plant.png'" class="life-plant" alt="" />
    <div v-if="stageLife.preview === 'rain' || (stageLife.preview !== 'stars' && stageLife.placed.includes('rain'))" class="life-rain"></div>
    <div v-if="stageLife.preview === 'stars' || (stageLife.preview !== 'rain' && stageLife.placed.includes('stars'))" class="life-stars"></div>
  </div>
  <Live2DLayer />
  <div v-if="stageLife.active && stageLife.activityCategory === 'meal'" class="tea-scene" aria-label="餐桌上的食物">
    <span v-if="['tea','noodles','hotpot','home_dish','coffee'].includes(stageLife.activityArt)" class="tea-steam" aria-hidden="true"></span><img :src="`/assets/life/${stageLife.activityArt}.png`" alt="餐桌上的食物" />
  </div>
  <div v-if="stageLife.active && stageLife.activityCategory === 'vehicle'" class="ride-scene"><img :src="`/assets/life/${stageLife.activityArt}.png`" alt="交通工具插画" /></div>
  <div v-if="stageLife.active" class="life-controls">
    <div v-if="stageLife.activity || stageLife.preview || stageLife.previewHome" class="life-moment-actions">
      <button v-if="stageLife.activity" @click="rememberMoment">记录这一刻</button>
      <button v-if="stageLife.activity" @click="endLifeActivity">结束这段时光</button>
      <button v-if="stageLife.preview || stageLife.previewHome" @click="endLifePreview">结束预览</button>
    </div>
    <div class="life-navigation" aria-label="共同空间导航">
      <button v-if="stageLife.destination" class="home-action" @click="returnLifeHome">回到家</button>
      <button class="stage-action" @click="leaveLifeStage">返回舞台</button>
    </div>
  </div>
  <div v-if="!rendererError && (characters.modelLoading || (startingModel && !characters.modelInfo))" class="loading glass">
    <n-spin size="small" />
    <span>模型加载中…</span>
  </div>
  <div v-if="rendererError || characters.modelError" class="loading glass error" role="alert">
    <span>{{ rendererError || characters.modelError }}</span>
    <button type="button" class="retry-stage" @click="retryStage">{{ t('char.journal.retry') }}</button>
  </div>
</template>

<style scoped>
.stage {
  position: absolute;
  inset: 0;
}
.retry-stage { flex: none; padding: 5px 9px; border: 1px solid #ffffff38; border-radius: 7px; background: #ffffff19; color: inherit; font: inherit; cursor: pointer; }

.stage.review-safe-area::after {
  content: '';
  position: absolute;
  inset: 5%;
  z-index: 1;
  border: 1px dashed rgba(255, 255, 255, 0.65);
  pointer-events: none;
}
.stage :deep(canvas) {
  display: block;
}
.life-props { position:absolute; inset:0; pointer-events:none; z-index:1; }
.life-props img { position:absolute; object-fit:contain; filter:drop-shadow(0 5px 10px #24171077); }
.life-lamp { width:clamp(80px,10vw,150px); right:12%; bottom:12%; }
.life-picture { width:clamp(65px,8vw,110px); right:8%; top:24%; }
.life-plant { width:clamp(80px,10vw,150px); left:10%; bottom:14%; }
.life-rain { position:absolute; inset:-100%; opacity:.20; background:repeating-linear-gradient(105deg,transparent 0 28px,#c9e9ff 29px 30px,transparent 31px 60px); animation:life-rainfall .8s linear infinite; }
.life-stars { position:absolute; top:10%; right:10%; width:32%; height:28%; background:radial-gradient(circle at 12% 24%,#ffe7a7 0 2px,transparent 3px),radial-gradient(circle at 46% 13%,#fff3c8 0 1.5px,transparent 2.5px),radial-gradient(circle at 72% 42%,#ffe7a7 0 2px,transparent 3px),radial-gradient(circle at 31% 76%,#fff3c8 0 1px,transparent 2px),radial-gradient(circle at 91% 68%,#ffe7a7 0 1.5px,transparent 2.5px); animation:life-twinkle 3s ease-in-out infinite; }
@keyframes life-rainfall { to { transform:translate(-20px,50px); } }
@keyframes life-twinkle { 50% { opacity:.3; } }
@media (prefers-reduced-motion:reduce) { .life-rain,.life-stars { animation:none; } }
.life-controls { position:absolute; z-index:12; top:50%; right:max(16px,env(safe-area-inset-right)); transform:translateY(-50%); display:flex; align-items:flex-end; flex-direction:column; gap:9px; pointer-events:none; }
.life-controls button { pointer-events:auto; border:1px solid #f3debc45; background:#29221fe8; color:#fbe8d0; border-radius:12px; padding:8px 12px; cursor:pointer; font:inherit; font-size:12px; box-shadow:0 8px 24px #120b0838; backdrop-filter:blur(14px); transition:transform .18s ease,background .18s ease; }
.life-controls button:hover { transform:translateY(-1px); background:#4b3830ef; }
.life-moment-actions { display:flex; max-width:min(430px,calc(100vw - 90px)); gap:7px; }
.life-navigation { display:flex; flex-direction:column; overflow:hidden; padding:4px; gap:2px; border:1px solid #f3debc2e; border-radius:15px; background:#1d1715a8; box-shadow:0 12px 35px #10090755; backdrop-filter:blur(18px); pointer-events:auto; }
.life-navigation button { display:flex; align-items:center; justify-content:center; min-width:104px; margin:0; border:0; box-shadow:none; background:transparent; }
.life-navigation button+button { border-top:1px solid #ffffff16; border-left:0; border-radius:0 0 10px 10px; }
.life-navigation .home-action { background:#d9bd94; color:#2d211b; }
.life-motion-error { position:absolute; z-index:12; left:18px; bottom:145px; padding:8px 12px; background:#29221fdc; color:#fbe8d0; border-radius:10px; }
.tea-scene { pointer-events:none; position:absolute; z-index:4; right:12%; bottom:15%; width:clamp(120px,18vw,240px); filter:drop-shadow(0 8px 15px #211a1688); animation:tea-arrive .5s ease-out; }
.tea-scene img { width:100%; display:block; }.tea-steam { position:absolute; top:-12%; left:44%; width:22px; height:38px; opacity:.7; background:radial-gradient(ellipse at 40% 75%,#fff7e699 0 18%,transparent 45%),radial-gradient(ellipse at 65% 35%,#fff7e677 0 14%,transparent 42%); filter:blur(3px); animation:tea-steam 2.4s ease-in-out infinite; }
.ride-scene { pointer-events:none; position:absolute; z-index:4; right:5%; bottom:10%; width:clamp(150px,24vw,320px); filter:drop-shadow(0 8px 12px #211a1688); animation:ride-arrive 1.2s ease-out; }.ride-scene img{display:block;width:100%}@keyframes ride-arrive { from { opacity:0; transform:translateX(100px); } to { opacity:1; transform:none; } }
@keyframes tea-arrive { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:none} }
@keyframes tea-steam { 50%{opacity:.25;transform:translateY(-10px)} }
@media (prefers-reduced-motion:reduce) { .tea-scene,.tea-steam,.ride-scene { animation:none; } }
@media (max-width:640px) {
  .life-controls { top:46%; right:max(8px,env(safe-area-inset-right)); }
  .life-moment-actions { max-width:calc(100vw - 80px); overflow:auto; }
  .life-navigation button { padding:7px 9px; }
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
