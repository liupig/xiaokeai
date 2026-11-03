<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, ref, computed } from 'vue';
import { NConfigProvider, NMessageProvider, NModal, NSpace, darkTheme, zhCN, dateZhCN, enUS, dateEnUS, jaJP, dateJaJP, koKR, dateKoKR } from 'naive-ui';
import { i18n } from './i18n';
import StageView from './features/stage/StageView.vue';
import TopBar from './features/hud/TopBar.vue';
import DeskChrome from './features/hud/DeskChrome.vue';
import BrandLogo from './components/BrandLogo.vue';
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
import { startCoins } from './features/coins/session';
import { availableRelease, checkUpdate, CURRENT_VERSION, DEFAULT_DOWNLOADS, ignore, UPDATE_URL } from './features/update/updateService';
import type { ReleaseInfo } from './features/update/updateService';

const QuickPanel = defineAsyncComponent(() => import('./features/hud/QuickPanel.vue'));
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
  bindLiveHost();
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
onUnmounted(() => window.removeEventListener('xiaokeai:update', onUpdate));
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="naiveLocale" :date-locale="naiveDate">
    <n-message-provider placement="top">
      <n-modal :show="!!update" @update:show="(v: boolean) => { if (!v) dismissUpdate(); }" preset="card" class="update-modal" :bordered="false" :segmented="{ content: true, footer: true }" style="width: min(470px, calc(100vw - 32px))">
        <template #header>
          <div class="update-header"><div class="update-orb"><BrandLogo :size="28" /></div><div><div class="update-kicker">XIAOKE.AI</div><div class="update-title">发现新版本</div></div></div>
        </template>
        <div class="update-body">
          <div class="update-lead">让陪伴，再近一步。</div>
          <span class="update-version">v{{ update?.version }}</span>
          <div v-if="update?.notes?.zh" class="update-notes">{{ update.notes.zh }}</div>
          <div class="update-section-label">下载安装包 <span>选择你习惯的下载方式</span></div>
          <div class="update-downloads">
            <button type="button" @click="openDownload(update?.downloads?.baidu || DEFAULT_DOWNLOADS.baidu)"><span>百度网盘</span><small>提取码 {{ update?.baidu_password || 'xkai' }}</small></button>
            <button type="button" @click="openDownload(update?.downloads?.huggingface || DEFAULT_DOWNLOADS.huggingface)"><span>Hugging Face</span></button>
            <button type="button" @click="openDownload(update?.downloads?.google_drive || DEFAULT_DOWNLOADS.google_drive)"><span>Google Drive</span></button>
          </div>
        </div>
        <template #footer>
          <div class="update-actions"><button type="button" class="update-primary" @click="openUpdate">前往官网更新 <span>↗</span></button><div class="update-secondary"><button type="button" @click="dismissUpdate">下次提醒</button><button type="button" @click="neverUpdate">不再提醒此版本</button></div></div>
        </template>
      </n-modal>
      <div class="layout">
        <button v-if="isPetShell && availableRelease" type="button" data-pet-hit class="update-badge update-badge-pet" @click="showUpdateEntry"><span></span>有新版本</button>
        <StageView />
        <DrawCard />
        <DeskChrome v-if="!isPetShell && !tavernUi.on" />
        <CoinPill v-if="isPetShell" class="pet-coin" />
        <UserCenter />
        <ContentSetup />
        <TopBar v-if="!isPetShell && !tavernUi.on" :active="activePanel" :update-available="!!availableRelease" :update-label="updateCheckLabel" @check-update="showUpdateEntry" @toggle="togglePanel" />
        <LiveBeatHud v-if="!isPetShell && !tavernUi.on && !tarotLayerOn && !wishUi.on && (!activePanel || activePanel === 'characters')" />
        <MocapOverlay v-if="!isPetShell" />
        <SpeechCaption />
        <TarotLayer v-if="tarotLayerOn" />
        <TavernLayer v-if="settings.modules.tavern && tavernUi.on" />
        <WishLayer v-if="wishUi.on" />
        <CodewatchHud v-if="!isPetShell && settings.modules.codewatch" />
        <LiveDesk v-if="!isPetShell && settings.modules.live" />
        <DanmakuStage v-if="!isPetShell && (settings.modules.live || settings.modules.live_douyin)" />
        <QuickPanel :show="activePanel === 'quick'"
                    @update:show="(v: boolean) => setPanel('quick', v)" />
        <ChatBar v-if="!isPetShell && !tavernUi.on" />
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
  overflow: hidden;
  border: 1px solid rgba(167, 139, 250, 0.28);
  border-radius: 26px;
  background: linear-gradient(145deg, rgba(30, 27, 51, 0.985), rgba(18, 21, 38, 0.985));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.48), 0 0 36px rgba(124, 92, 224, 0.16);
}
:global(.n-modal-mask) { background: rgba(5, 7, 18, .58) !important; backdrop-filter: blur(5px); }
:global(.update-modal .n-card-header) { padding: 26px 30px 22px; }
:global(.update-modal .n-card__content) { padding: 28px 30px 30px; }
:global(.update-modal .n-card__footer) { padding: 20px 30px 24px; }
.update-header { display: flex; align-items: center; gap: 12px; }
.update-orb { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 15px; background: linear-gradient(145deg, #8b6cf6, #4f66d8); box-shadow: 0 8px 22px rgba(112, 91, 224, .35); }
.update-kicker { color: #a99afb; font-size: 10px; font-weight: 800; letter-spacing: .18em; }
.update-title { margin-top: 4px; color: #f8f6ff; font-size: 24px; font-weight: 800; letter-spacing: -.03em; }
.update-body { position: relative; padding: 2px 0 4px; }
.update-lead { color: rgba(245, 243, 255, .92); font-size: 16px; font-weight: 650; }
.update-version { display: inline-block; margin-top: 14px; padding: 5px 10px; border: 1px solid rgba(167, 139, 250, .35); border-radius: 999px; background: rgba(139, 108, 246, .14); color: #c6b8ff; font-size: 12px; font-weight: 700; letter-spacing: .04em; }
.update-notes { margin-top: 16px; padding: 15px 16px; border: 1px solid rgba(255, 255, 255, .07); border-radius: 14px; background: rgba(255, 255, 255, .055); color: rgba(235, 232, 248, .76); font-size: 14px; line-height: 1.65; }
.update-downloads { display: grid; gap: 7px; margin-top: 14px; }
.update-downloads button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px; border: 1px solid rgba(167, 139, 250, .16); border-radius: 11px; background: rgba(116, 96, 190, .09); color: rgba(245, 243, 255, .88); font: inherit; text-align: left; cursor: pointer; transition: background .15s, border-color .15s, transform .15s; }
.update-downloads button:hover { border-color: rgba(167, 139, 250, .5); background: rgba(139, 108, 246, .18); transform: translateY(-1px); }
.update-downloads small { color: rgba(214, 205, 250, .58); font-size: 11px; }
.update-actions { display: flex; flex-direction: column; gap: 10px; }
.update-primary { width: 100%; height: 44px; border: 0 !important; border-radius: 13px; background: linear-gradient(135deg, #9073ff, #6379ea) !important; box-shadow: 0 8px 22px rgba(105, 92, 224, .32); font-size: 15px; font-weight: 700; }
.update-secondary { display: flex; justify-content: center; gap: 4px; }
.update-secondary button { flex: 1; height: 38px; border: 1px solid #ffffff14; border-radius: 10px; background: #ffffff05; color: #a6a3b8; font: inherit; font-size: 12px; cursor: pointer; }
.update-secondary button:hover { background: #ffffff0d; color: #eeeaff; }
.update-primary { color: white; cursor: pointer; font-family: inherit; display: flex; justify-content: center; align-items: center; gap: 12px; }
.update-primary:hover { filter: brightness(1.12); }
.update-secondary { gap: 10px; }
.update-section-label { display: flex; justify-content: space-between; margin-top: 24px; font-size: 12px; font-weight: 600; color: #d5cee8; }
.update-section-label span { font-weight: 400; color: #858196; font-size: 11px; }
.update-downloads { margin-top: 10px; }
.update-downloads button { min-height: 48px; padding: 12px 16px; background: #ffffff04; border-color: #ffffff12; justify-content: center; text-align: center; }
.update-downloads button:first-child { background: #9c82ff0c; border-color: #a68aff30; }
.update-lead { font-size: 22px; font-weight: 600; letter-spacing: .02em; }
.update-version { font-family: ui-monospace, monospace; font-weight: 400; font-size: 11px; }
.update-notes { white-space: pre-wrap; max-height: 140px; overflow-y: auto; border: 0; border-left: 2px solid #a68aff70; border-radius: 0; background: transparent; padding: 2px 0 2px 14px; }
.update-primary span { margin-left: 3px; font-size: 16px; }
</style>
