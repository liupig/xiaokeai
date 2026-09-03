<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from 'vue';
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN } from 'naive-ui';
import StageView from './features/stage/StageView.vue';
import TopBar from './features/hud/TopBar.vue';
import DeskChrome from './features/hud/DeskChrome.vue';
import { MocapOverlay } from './features/mocap';
import ChatBar from './features/chat/ChatBar.vue';
import SpeechCaption from './features/chat/SpeechCaption.vue';
import LiveBeatHud from './features/hud/LiveBeatHud.vue';
import { stage } from './engine/stage';
import { caster } from './features/performance/caster';
import { shots } from './features/performance/shotConductor';
import { repertoire } from './features/performance/repertoire';
import { speechPlayer } from './features/voice/tts';
import { useAssetsStore } from './stores/assets';
import { useCharacterStore } from './stores/character';
import { useChatStore } from './stores/chat';
import { useSettingsStore } from './stores/settings';
import { tarotLayerOn } from './features/tarot/gate';

const QuickPanel = defineAsyncComponent(() => import('./features/hud/QuickPanel.vue'));
const AssetCenter = defineAsyncComponent(() => import('./features/assets/AssetCenter.vue'));
const CharacterPanel = defineAsyncComponent(() => import('./features/character/CharacterPanel.vue'));
const SettingsPanel = defineAsyncComponent(() => import('./features/settings/SettingsPanel.vue'));
const CamReviewPanel = defineAsyncComponent(() => import('./features/review/CamReviewPanel.vue'));
const KeepsakeGallery = defineAsyncComponent(() => import('./features/keepsake/KeepsakeGallery.vue'));
const TranscriptPanel = defineAsyncComponent(() => import('./features/chat/TranscriptPanel.vue'));
const TarotLayer = defineAsyncComponent(() => import('./features/tarot/Layer.vue'));

/** 右侧面板互斥：同一时间只显示一个 */
type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log';
const activePanel = ref<PanelKey | null>(null);

function togglePanel(p: PanelKey) {
  activePanel.value = activePanel.value === p ? null : p;
}

function setPanel(p: PanelKey, v: boolean) {
  if (v) activePanel.value = p;
  else if (activePanel.value === p) activePanel.value = null;
}

const assets = useAssetsStore();
const characters = useCharacterStore();
const settings = useSettingsStore();
const chat = useChatStore();

onMounted(async () => {
  await settings.load().catch(() => {});
  await assets.refresh().catch(() => {});
  await characters.loadList().catch(() => {});
  await chat.loadHistory().catch(() => {});
  const sceneP = (settings.modules.scenes && characters.currentId)
    ? import('./features/scenes/session').then((m) => m.restoreOrRotateScene({
        characterId: characters.currentId,
        lastChatAt: chat.lastUserChatAt(),
      })).catch(() => {})
    : Promise.resolve();
  const modelP = characters.currentId
    ? characters.switchTo(characters.currentId).catch(() => {})
    : Promise.resolve();
  await Promise.all([sceneP, modelP]);
  caster.indexFrom(assets.motions, characters.modelInfo?.morphNames ?? []);
  shots.indexFrom(assets.cameras);
  await repertoire.load().catch(() => {});
  stage.director.idlePicker = () => caster.pickIdleUrl();
  stage.director.onSpeakBeat = () => caster.onSpeakBeat();
  stage.director.onIdleBeat = () => caster.onIdleBeat();
  stage.director.onIdleCam = () => shots.idleLive();
  shots.beginIdle();
  speechPlayer.onSentence = (text) => {
    caster.onSpeakSentence(text);
    chat.markSpeaking(text);
  };
  speechPlayer.onAllEnded = () => {
    chat.markSpokenAll();
    chat.scheduleDelayed();
  };
  settings.applyTts();
  window.addEventListener('pointerdown', () => speechPlayer.unlock(), { once: true });
  await chat.beginVisit();
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider placement="top">
      <div class="layout">
        <StageView />
        <DeskChrome />
        <TopBar :active="activePanel" @toggle="togglePanel" />
        <LiveBeatHud v-if="!tarotLayerOn && (!activePanel || activePanel === 'characters')" />
        <MocapOverlay />
        <SpeechCaption />
        <TarotLayer v-if="tarotLayerOn" />
        <QuickPanel :show="activePanel === 'quick'"
                    @update:show="(v: boolean) => setPanel('quick', v)" />
        <ChatBar />
        <AssetCenter :show="activePanel === 'assets'"
                     @update:show="(v: boolean) => setPanel('assets', v)" />
        <CharacterPanel :show="activePanel === 'characters'"
                        @update:show="(v: boolean) => setPanel('characters', v)" />
        <SettingsPanel :show="activePanel === 'settings'"
                       @update:show="(v: boolean) => setPanel('settings', v)" />
        <CamReviewPanel :show="activePanel === 'review'"
                        @update:show="(v: boolean) => setPanel('review', v)" />
        <KeepsakeGallery :show="activePanel === 'keepsake'"
                         @update:show="(v: boolean) => setPanel('keepsake', v)" />
        <TranscriptPanel :show="activePanel === 'log'"
                         @update:show="(v: boolean) => setPanel('log', v)" />
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.layout {
  /* provider 包裹层无高度，直接铺满视口 */
  position: fixed;
  inset: 0;
}
</style>
