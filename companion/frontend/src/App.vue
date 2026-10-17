<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref, computed } from 'vue';
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN, enUS, dateEnUS, jaJP, dateJaJP, koKR, dateKoKR } from 'naive-ui';
import { i18n } from './i18n';
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
import { featureOn } from './i18n';
import { isPetShell } from './features/shell/mode';
import { installPetPointer } from './features/shell/petPointer';
import { installPetWander } from './features/shell/petWander';
import { installTouch } from './features/touch';
import PetBar from './features/shell/PetBar.vue';

const QuickPanel = defineAsyncComponent(() => import('./features/hud/QuickPanel.vue'));
const AssetCenter = defineAsyncComponent(() => import('./features/assets/AssetCenter.vue'));
const CharacterPanel = defineAsyncComponent(() => import('./features/character/CharacterPanel.vue'));
const SettingsPanel = defineAsyncComponent(() => import('./features/settings/SettingsPanel.vue'));
const ContentSetup = defineAsyncComponent(() => import('./features/settings/ContentSetup.vue'));
const CamReviewPanel = defineAsyncComponent(() => import('./features/review/CamReviewPanel.vue'));
const KeepsakeGallery = defineAsyncComponent(() => import('./features/keepsake/KeepsakeGallery.vue'));
const TranscriptPanel = defineAsyncComponent(() => import('./features/chat/TranscriptPanel.vue'));
const TarotLayer = defineAsyncComponent(() => import('./features/tarot/Layer.vue'));
const CodewatchHud = defineAsyncComponent(() => import('./features/codewatch/Hud.vue'));

/** 右侧面板互斥：同一时间只显示一个 */
type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log';
const activePanel = ref<PanelKey | null>(null);

const naiveLocale = computed(() => {
  const ui = String((i18n.global.locale as { value?: string }).value || 'zh-CN');
  if (ui === 'en') return enUS;
  if (ui === 'ja') return jaJP;
  if (ui === 'ko') return koKR;
  return zhCN;
});
const naiveDate = computed(() => {
  const ui = String((i18n.global.locale as { value?: string }).value || 'zh-CN');
  if (ui === 'en') return dateEnUS;
  if (ui === 'ja') return dateJaJP;
  if (ui === 'ko') return dateKoKR;
  return dateZhCN;
});

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
  installTouch();
  if (isPetShell) {
    installPetPointer();
    installPetWander();
  }
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
  if (settings.modules.codewatch) {
    const codewatch = await import('./features/codewatch');
    await codewatch.restoreCodewatch().catch(() => {});
  }
  if (settings.modules.tarot && featureOn('tarot', settings.locale.reply) && characters.currentId) {
    const tarot = await import('./features/tarot');
    await tarot.reconcileTarot(characters.currentId).catch(() => {});
    const onShow = () => {
      if (document.visibilityState !== 'visible' || !characters.currentId) return;
      void tarot.reconcileTarot(characters.currentId).catch(() => {});
    };
    document.addEventListener('visibilitychange', onShow);
  }
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
  const armVoice = () => speechPlayer.unlock();
  window.addEventListener('pointerdown', armVoice);
  window.addEventListener('keydown', armVoice);
  window.addEventListener('focus', armVoice);
  await chat.beginVisit();
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="naiveLocale" :date-locale="naiveDate">
    <n-message-provider placement="top">
      <div class="layout">
        <StageView />
        <DeskChrome v-if="!isPetShell" />
        <ContentSetup />
        <TopBar v-if="!isPetShell" :active="activePanel" @toggle="togglePanel" />
        <LiveBeatHud v-if="!isPetShell && !tarotLayerOn && (!activePanel || activePanel === 'characters')" />
        <MocapOverlay v-if="!isPetShell" />
        <SpeechCaption />
        <TarotLayer v-if="tarotLayerOn" />
        <CodewatchHud v-if="!isPetShell && settings.modules.codewatch" />
        <QuickPanel :show="activePanel === 'quick'"
                    @update:show="(v: boolean) => setPanel('quick', v)" />
        <ChatBar v-if="!isPetShell" />
        <PetBar v-if="isPetShell" />
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
