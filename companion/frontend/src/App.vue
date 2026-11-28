<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, ref, computed, watch } from 'vue';
import { NConfigProvider, NMessageProvider, NModal, NSpace, darkTheme, zhCN, dateZhCN, enUS, dateEnUS, jaJP, dateJaJP, koKR, dateKoKR } from 'naive-ui';
import { i18n } from './i18n';
import StageView from './features/stage/StageView.vue';
import StageWelcome from './features/stage/StageWelcome.vue';
import type { ReplyLang } from './i18n';
import TopBar from './features/hud/TopBar.vue';
import DeskChrome from './features/hud/DeskChrome.vue';
import BrandLogo from './components/BrandLogo.vue';
import { MocapOverlay } from './features/mocap';
import ChatBar from './features/chat/ChatBar.vue';
import SpeechCaption from './features/chat/SpeechCaption.vue';
import LiveBeatHud from './features/hud/LiveBeatHud.vue';
import { stage } from './engine/stage';
import { live2dStage } from './engine/live2d';
import { caster } from './features/performance/caster';
import { shots } from './features/performance/shotConductor';
import { repertoire } from './features/performance/repertoire';
import { speechPlayer } from './features/voice/tts';
import { useAssetsStore } from './stores/assets';
import { useCharacterStore } from './stores/character';
import { useChatStore } from './stores/chat';
import { useSettingsStore } from './stores/settings';
import { tarotLayerOn } from './features/tarot/gate';
import { tavernUi } from './features/tavern/session';
import { wishUi } from './features/wish';
import { featureOn } from './i18n';
import { isPetShell } from './features/shell/mode';
import { bindLiveHost } from './features/live/session';
import { installPetPointer } from './features/shell/petPointer';
import { installPetWander } from './features/shell/petWander';
import { installTouch } from './features/touch';
import PetBar from './features/shell/PetBar.vue';
import CoinPill from './features/coins/CoinPill.vue';
import UserCenter from './features/coins/UserCenter.vue';
import DrawCard from './features/draw/DrawCard.vue';
import { lifePanelOpen, startCoins, userCenterOpen } from './features/coins/session';
import { availableRelease, checkUpdate, CURRENT_VERSION, DEFAULT_DOWNLOADS, ignore, UPDATE_URL } from './features/update/updateService';
import type { ReleaseInfo } from './features/update/updateService';
import JourneyToasts from './features/journey/JourneyToasts.vue';

const QuickPanel = defineAsyncComponent(() => import('./features/hud/QuickPanel.vue'));
const MusicPanel = defineAsyncComponent(() => import('./features/hud/MusicPanel.vue'));
const update = ref<ReleaseInfo | null>(null);
const onUpdate = (event: Event) => { update.value = (event as CustomEvent<ReleaseInfo>).detail; };
const openUpdate = () => window.open(UPDATE_URL, '_blank', 'noopener');
const updateCheckLabel = ref('检查更新');
async function showUpdateEntry() {
  if (availableRelease.value) { update.value = availableRelease.value; return; }
  updateCheckLabel.value = '正在检查…';
  try {
    const info = await checkUpdate();
    if (info.update_available) update.value = info;
    updateCheckLabel.value = info.update_available ? '有新版本' : CURRENT_VERSION === 'dev' ? `线上版本 ${info.version}` : '已是最新版本';
  } catch { updateCheckLabel.value = '检查失败，点击重试'; }
}
const openDownload = (url: string) => window.open(url, '_blank', 'noopener');
const dismissUpdate = () => { update.value = null; };
const neverUpdate = () => { if (update.value) ignore(update.value.version); dismissUpdate(); };
const AssetCenter = defineAsyncComponent(() => import('./features/assets/AssetCenter.vue'));
const CharacterPanel = defineAsyncComponent(() => import('./features/character/CharacterPanel.vue'));
const SettingsPanel = defineAsyncComponent(() => import('./features/settings/SettingsPanel.vue'));
const ContentSetup = defineAsyncComponent(() => import('./features/settings/ContentSetup.vue'));
const CamReviewPanel = defineAsyncComponent(() => import('./features/review/CamReviewPanel.vue'));
const KeepsakeGallery = defineAsyncComponent(() => import('./features/keepsake/KeepsakeGallery.vue'));
const TranscriptPanel = defineAsyncComponent(() => import('./features/chat/TranscriptPanel.vue'));
const TarotLayer = defineAsyncComponent(() => import('./features/tarot/Layer.vue'));
const TavernLayer = defineAsyncComponent(() => import('./features/tavern/Layer.vue'));
const WishLayer = defineAsyncComponent(() => import('./features/wish/Layer.vue'));
const CodewatchHud = defineAsyncComponent(() => import('./features/codewatch/Hud.vue'));
const DanmakuStage = defineAsyncComponent(() => import('./features/live/DanmakuStage.vue'));
const LiveDesk = defineAsyncComponent(() => import('./features/live/LiveDesk.vue'));

// 舞台工作区同一时间只显示一个面板。
type PanelKey = 'quick' | 'assets' | 'characters' | 'settings' | 'review' | 'keepsake' | 'log' | 'live' | 'music';
const activePanel = ref<PanelKey | null>(null);
const chatDockHeight = ref(0);
function updateChatDock(_width: number, height: number) {
  chatDockHeight.value = height;
}

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

watch(lifePanelOpen, (open) => {
  if (!open) return;
  userCenterOpen.value = false;
  activePanel.value = null;
}, { flush: 'sync' });
watch(userCenterOpen, (open) => {
  if (!open) return;
  lifePanelOpen.value = false;
  activePanel.value = null;
}, { flush: 'sync' });

function togglePanel(p: PanelKey) {
  lifePanelOpen.value = false;
  userCenterOpen.value = false;
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
const stageMounted = ref(isPetShell);
const stageEntered = ref(isPetShell);
const needsLanguage = ref(false);
const savingLanguage = ref(false);
const languageFailed = ref(false);
const preparingCharacter = ref(false);
let warmCharacter: Promise<void> = Promise.resolve();
let continueStartup: (() => void) | undefined;
let stageWarmupStarted = false;

function preloadStage() {
  if (stageWarmupStarted) return;
  stageWarmupStarted = true;
  stageMounted.value = true;
  warmCharacter = loadStartupCharacter();
}

async function loadStartupCharacter() {
  if (preparingCharacter.value) return;
  preparingCharacter.value = true;
  characters.modelError = '';
  try {
    await Promise.all([assets.refresh(), characters.loadList()]);
    if (!characters.currentId) throw new Error(t('top.none'));
    await characters.switchTo(characters.currentId);
  } catch (error) {
    characters.modelError = error instanceof Error ? error.message : String(error);
  } finally {
    preparingCharacter.value = false;
  }
}

function isModeSwitch() {
  const url = new URL(window.location.href);
  if (!window.companionDesktop?.isShell || url.searchParams.get('entry') !== 'mode-switch') return false;
  url.searchParams.delete('entry');
  window.history.replaceState(window.history.state, '', url);
  return true;
}

async function enterStage(language: ReplyLang) {
  if (savingLanguage.value || stageEntered.value) return;
  savingLanguage.value = true;
  const retryLanguage = languageFailed.value;
  languageFailed.value = false;
  try {
    if (retryLanguage || !settings.locale_set || settings.locale.ui !== language) {
      await settings.setLocale({ ui: language, reply: language });
      settings.locale_set = true;
    }
    continueStartup?.();
  } catch {
    languageFailed.value = true;
  } finally {
    savingLanguage.value = false;
  }
}

onMounted(async () => {
  window.addEventListener('xiaokeai:update', onUpdate);
  // 开发环境可通过设置页按钮预览；正式版本启动时自动检查。
  if (!import.meta.env.DEV) void checkUpdate().catch(() => {});
  startCoins();
  installTouch();
  if (isPetShell) {
    installPetPointer();
    installPetWander();
  }
  await settings.load().catch(() => {});
  const showWelcome = !isPetShell && !isModeSwitch();
  window.companionDesktop?.setStartupWindow?.(showWelcome);
  stage.setPresentationPaused(showWelcome);
  live2dStage.setPresentationPaused(showWelcome);
  if (showWelcome) {
    await new Promise<void>((resolve) => {
      continueStartup = resolve;
      needsLanguage.value = true;
    });
    continueStartup = undefined;
  }
  preloadStage();
  stageEntered.value = true;
  needsLanguage.value = false;
  if (showWelcome) {
    window.companionDesktop?.setStartupWindow?.(false);
    stage.setPresentationPaused(false);
    live2dStage.setPresentationPaused(false);
  }
  bindLiveHost();
  await warmCharacter;
  await chat.loadHistory().catch(() => {});
  const sceneP = (settings.modules.scenes && characters.currentId)
    ? import('./features/scenes/session').then((m) => m.restoreOrRotateScene({
        characterId: characters.currentId,
        lastChatAt: chat.lastUserChatAt(),
      })).catch(() => {})
    : Promise.resolve();
  await sceneP;
  const along = await import('./features/glance/along');
  along.installAlong();
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
  stage.use({ id: "playing-motion-framing", onFrame: () => shots.reframePlayingMotion() });
  shots.beginIdle();
  speechPlayer.onSentence = (text, allowAutoMotion) => {
    caster.onSpeakSentence(text, allowAutoMotion);
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
onUnmounted(() => {
  stage.unuse('playing-motion-framing');
  window.removeEventListener('xiaokeai:update', onUpdate);
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="naiveLocale" :date-locale="naiveDate">
    <n-message-provider placement="top">
      <n-modal :show="!!update" @update:show="(v: boolean) => { if (!v) dismissUpdate(); }" preset="card" class="update-modal" :bordered="false" :segmented="{ content: true, footer: true }" style="width: min(470px, calc(100vw - 32px))">
        <template #header>
          <div class="update-header"><div class="update-orb"><BrandLogo :size="28" /></div><div><div class="update-title">发现新版本</div><span class="update-version">v{{ update?.version }}</span></div></div>
        </template>
        <div class="update-body">
          <div v-if="update?.notes?.zh" class="update-notes">{{ update.notes.zh }}</div>
          <h3 class="update-section-label">下载安装包</h3>
          <div class="update-downloads">
            <button type="button" @click="openDownload(update?.downloads?.baidu || DEFAULT_DOWNLOADS.baidu)"><span>百度网盘</span><small>中国 · 提取码 {{ update?.baidu_password || 'xkai' }}</small></button>
            <button type="button" @click="openDownload(update?.downloads?.modelscope || DEFAULT_DOWNLOADS.modelscope)"><span>ModelScope 魔塔</span><small>中国</small></button>
            <button type="button" @click="openDownload(update?.downloads?.huggingface || DEFAULT_DOWNLOADS.huggingface)"><span>Hugging Face</span><small>国外</small></button>
            <button type="button" @click="openDownload(update?.downloads?.google_drive || DEFAULT_DOWNLOADS.google_drive)"><span>Google Drive</span><small>国外</small></button>
          </div>
        </div>
        <template #footer>
          <div class="update-actions"><button type="button" class="update-primary" @click="openUpdate">前往官网更新 <span>↗</span></button><div class="update-secondary"><button type="button" @click="dismissUpdate">下次提醒</button><button type="button" @click="neverUpdate">不再提醒此版本</button></div></div>
        </template>
      </n-modal>
        <StageWelcome v-if="needsLanguage" :language="settings.locale.ui"
                      :saving="savingLanguage"
                      :failed="languageFailed" @preload-stage="preloadStage" @continue="enterStage" />
      <div v-if="!stageEntered && !needsLanguage" class="stage-boot" aria-busy="true"><BrandLogo :size="42" /></div>
      <div v-if="stageMounted" class="layout" :inert="!stageEntered"
           :class="{ 'has-stage-nav': !isPetShell && !tavernUi.on }"
           :style="{ '--chat-dock-height': chatDockHeight + 'px' }">
        <div class="stage-viewport"><StageView :starting-model="preparingCharacter" @retry-model="loadStartupCharacter" /></div>
        <template v-if="stageEntered">
        <button v-if="isPetShell && availableRelease" type="button" data-pet-hit class="update-badge update-badge-pet" @click="showUpdateEntry"><span></span>有新版本</button>
        <DrawCard />
        <DeskChrome v-if="!isPetShell && !tavernUi.on" />
        <CoinPill v-if="isPetShell" class="pet-coin" data-pet-hit />
        <UserCenter />
        <ContentSetup />
        <TopBar v-if="!isPetShell && !tavernUi.on" :active="activePanel" :update-available="!!availableRelease" :update-label="updateCheckLabel" @check-update="showUpdateEntry" @toggle="togglePanel" />
        <LiveBeatHud v-if="!isPetShell" v-show="!tavernUi.on" />
        <MocapOverlay v-if="!isPetShell" />
        <SpeechCaption />
        <TarotLayer v-if="tarotLayerOn" />
        <TavernLayer v-if="settings.modules.tavern && tavernUi.on" />
        <WishLayer v-if="wishUi.on" />
        <CodewatchHud v-if="!isPetShell && settings.modules.codewatch" />
        <LiveDesk v-if="!isPetShell" :show="!tavernUi.on && activePanel === 'live'"
                  @update:show="(v: boolean) => setPanel('live', v)" />
        <DanmakuStage v-if="!isPetShell && (settings.modules.live || settings.modules.live_douyin)" />
        <QuickPanel :show="activePanel === 'quick'"
                    @update:show="(v: boolean) => setPanel('quick', v)" />
        <MusicPanel v-if="!isPetShell" :show="activePanel === 'music' && !tavernUi.on"
                    @update:show="(v: boolean) => setPanel('music', v)" />
        <ChatBar v-if="!isPetShell && !tavernUi.on" @dock-size="updateChatDock" />
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
        <JourneyToasts v-if="settings.modules.journey !== false" />
        </template>
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
.stage-boot {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: #161229;
}
.stage-viewport { position: absolute; inset: 0; }
.has-stage-nav {
  background: #211b28;
  --stage-panel-span: min(492px, 52vw);
  --stage-nav-width: 160px;
  --stage-nav-compact-width: 70px;
  --stage-nav-clearance: 12px;
  --stage-chat-span: min(390px, 36vw);
}
.has-stage-nav .stage-viewport {
  inset: 0 0 0 var(--stage-content-left, 0px);
  overflow: hidden;
  background: radial-gradient(ellipse at 50% 20%, #3f3258, #292037);
}
.has-stage-nav:has(.stage-panel--small) { --stage-panel-span: min(366px, 52vw); }
.has-stage-nav:has(.stage-panel--large) { --stage-panel-span: min(702px, 52vw); }
.has-stage-nav:has(.review-current) :deep(.chat-corner),
.has-stage-nav:has(.review-current) :deep(.caption-layer) { display: none; }
.has-stage-nav:has(.chat-corner--open):not(:has(.review-current)) :deep(.beat-monitor) {
  --beat-bottom: calc(var(--chat-dock-height) + 24px);
}
@media (min-width: 700px) {
  .has-stage-nav:has(.chat-corner--open):not(:has(.review-current)) {
    --stage-content-right: calc(var(--stage-chat-span) + 24px);
  }
}
@media (max-width: 699px) {
  .has-stage-nav { --stage-chat-span: calc(100vw - 24px); }
  .has-stage-nav:has(.chat-corner--open):not(:has(.review-current)) {
    --stage-content-bottom: calc(var(--chat-dock-height) + 18px);
  }
}
@media (min-width: 960px) {
  .has-stage-nav:has(.stage-panel) {
    --stage-content-left: calc(var(--stage-nav-clearance) + var(--stage-panel-span) + 12px);
  }
}
@media (max-width: 959px) {
  .has-stage-nav:has(.stage-panel) { --stage-panel-span: 100%; }
  .has-stage-nav:has(.stage-panel) :deep(.chat-corner) { display: none; }
  .has-stage-nav:has(.stage-panel) { --stage-content-right: 0px; --stage-content-bottom: 0px; }
}
@media (min-width: 700px) and (max-width: 959px) {
  .has-stage-nav:has(.review-current) {
    --stage-panel-span: min(380px, 46vw);
    --stage-content-left: calc(var(--stage-nav-clearance) + var(--stage-panel-span) + 12px);
  }
}
@media (max-width: 640px) {
  .has-stage-nav { --stage-nav-width: var(--stage-nav-compact-width); }
}
.has-stage-nav:has(.stage-panel) {
  --stage-nav-clearance: calc(var(--stage-nav-width) + 24px);
}
.has-stage-nav:has(.stage-panel):has(.stage-nav.compact) {
  --stage-nav-clearance: calc(var(--stage-nav-compact-width) + 24px);
}
.update-badge { position: absolute; top: 72px; right: 24px; z-index: 40; display: flex; align-items: center; gap: 8px; padding: 9px 14px; border: 1px solid #b8a3ff55; border-radius: 999px; background: #252039ed; color: #ddd3ff; box-shadow: 0 4px 18px #0003; font: inherit; font-size: 12px; cursor: pointer; -webkit-app-region: no-drag; }
.update-badge:hover { background: #393052; }
.update-badge span { width: 6px; height: 6px; border-radius: 50%; background: #bc9fff; box-shadow: 0 0 8px #b59aff88; }
.update-badge-pet { top: 52px; right: 12px; }

.pet-coin {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
}

:global(.update-modal.n-card) {
  border: 1px solid #e8c5d035;
  border-radius: 20px;
  background: radial-gradient(ellipse at top left, #483444, transparent 60%), #231e2a;
  box-shadow: 0 24px 70px #0f0b18a8;
}
:global(.n-modal-mask) { background: rgba(5, 7, 18, .58) !important; backdrop-filter: blur(5px); }
:global(.update-modal .n-card-header),
:global(.update-modal .n-card__content),
:global(.update-modal .n-card__footer) { padding: 18px clamp(16px, 4vw, 26px); }
.update-header { display: flex; align-items: center; gap: 12px; }
.update-orb { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 13px; background: #e8bd9830; }
.update-title { color: #f6ece9; font-size: 20px; font-weight: 650; }
.update-version { color: #ebc5a1; font: 12px/1.4 ui-monospace, monospace; }
.update-section-label { font-size: 13px; font-weight: 600; color: #f6ece9; }
.update-notes { white-space: pre-wrap; max-height: 140px; overflow-y: auto; margin-bottom: 16px; padding: 6px 12px; border-left: 2px solid #ebc5a16b; color: #bcb0ba; font-size: 13px; line-height: 1.65; }
.update-downloads { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.update-downloads button {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid #e8c5d021;
  border-radius: 11px;
  background: #ffffff08;
  color: #f6ece9;
  text-align: start;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}
.update-downloads button:hover { background: #ebc5a118; border-color: #ebc5a168; }
.update-downloads small { color: #bcb0ba; font-size: 11px; }
.update-actions { display: grid; gap: 8px; }
.update-primary { min-height: 42px; border: 0; border-radius: 10px; background: #ebc5a1; color: #2b1e25; font: inherit; font-weight: 650; cursor: pointer; }
.update-primary:hover { background: #f8d8b9; }
.update-primary span { margin-left: 5px; }
.update-secondary { display: flex; gap: 8px; }
.update-secondary button { flex: 1; min-height: 36px; border: 1px solid #e8c5d021; border-radius: 9px; background: transparent; color: #bcb0ba; font: inherit; font-size: 12px; cursor: pointer; }
.update-secondary button:hover { background: #ffffff0d; color: #f6ece9; }
</style>
