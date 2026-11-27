<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import StagePanel from '../hud/StagePanel.vue';
import PanelGroup from '../hud/PanelGroup.vue';
import { NButton, NInput, NInputNumber, NSelect, NSwitch, useMessage } from 'naive-ui';
import { api } from '../../api/client';
import { t } from '../../i18n';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { speechPlayer } from '../voice/tts';
import { LIVE_FEATURES, normalizeLive } from './config';
import { liveDesk, pullLiveDesk, stopLiveLoop } from './session';
import { douyinFeed, resetDouyinFeed, startDouyinFeed, stopDouyinFeed } from './douyinFeed';

defineProps<{ show: boolean }>();
const emit = defineEmits<{ 'update:show': [show: boolean] }>();
const settings = useSettingsStore();
const characters = useCharacterStore();
const message = useMessage();
const busy = ref(false);
const changingModule = ref(false);
const rehearsalText = ref('');
const audit = ref<null | {
  events: number; turns: number; acks: Record<string, number>;
  source_to_turn_avg_sec: number; source_to_turn_max_sec: number; model_failures: number;
}>(null);
const qrBusy = ref(false);
const qrImage = ref('');
const qrState = ref('');
let qrKey = '';
let qrTimer = 0;

const live = computed(() => settings.live);
const biliModeOptions = computed(() => [
  { label: t('live.desk.biliOpen'), value: 'open' },
  { label: t('live.desk.biliWeb'), value: 'web' },
]);
const missingText = computed(() => liveDesk.missing.map((key) => t(`live.block.${key}`)).join('、'));
const showBadge = computed(() => settings.modules.live && liveDesk.aiLabel && liveDesk.onAir);
const segmentLabel = computed(() => t(`live.seg.${liveDesk.segment.id}`));
const healthText = computed(() => {
  if (liveDesk.health.degraded) return liveDesk.health.last_error || t('live.health.degraded');
  if (liveDesk.health.last_error) return liveDesk.health.last_error;
  return t('live.health.ok');
});

async function save() {
  await settings.save();
}

async function toggleFeature(key: typeof LIVE_FEATURES[number], on: boolean) {
  live.value.features[key] = on;
  try {
    await save();
  } catch (err) {
    message.error(String(err));
  }
}

async function toggleAck(key: 'strict' | 'ack_voice' | 'ack_model' | 'ack_bgm' | 'bgm_licensed', on: boolean) {
  live.value.compliance[key] = on;
  try {
    await save();
  } catch (err) {
    message.error(String(err));
  }
}

async function air(on: boolean) {
  busy.value = true;
  try {
    await save();
    if (!on) {
      await api.liveOff();
    } else {
      // 模式切换只中止当前个人语音，不清空个人聊天、记忆或角色设置。
      useChatStore().cancelStream();
      speechPlayer.onUserBargeIn();
      const data = await api.liveOn(characters.currentId || 0);
      if (data.ok === false) {
        message.warning(missingText.value || t('live.desk.needAck'));
      }
    }
    await pullLiveDesk();
  } catch (err) {
    message.error(String(err));
  } finally {
    busy.value = false;
  }
}

async function bili(on: boolean) {
  busy.value = true;
  try {
    await save();
    if (on) await api.liveBiliStart();
    else await api.liveBiliStop();
    await pullLiveDesk();
  } catch (err) {
    message.error(String(err));
  } finally {
    busy.value = false;
  }
}

async function pollBiliQr() {
  if (!qrKey || !qrBusy.value) return;
  try {
    const data = await api.liveBiliQrPoll(qrKey);
    qrState.value = data.state;
    if (data.state === 'done') {
      if (data.live) settings.live = normalizeLive(data.live);
      qrBusy.value = false;
      qrKey = '';
      message.success(t('live.desk.biliLoginDone'));
      await bili(true);
      return;
    }
    if (data.state === 'expired') {
      qrBusy.value = false;
      qrKey = '';
      return;
    }
    qrTimer = window.setTimeout(pollBiliQr, 2000);
  } catch (err) {
    qrBusy.value = false;
    qrKey = '';
    message.error(String(err));
  }
}

async function startBiliQr() {
  if (qrBusy.value) return;
  qrBusy.value = true;
  qrState.value = 'waiting';
  qrImage.value = '';
  try {
    const data = await api.liveBiliQrCreate();
    qrKey = data.qrcode_key;
    qrImage.value = data.image;
    qrTimer = window.setTimeout(pollBiliQr, 1000);
  } catch (err) {
    qrBusy.value = false;
    message.error(String(err));
  }
}

onBeforeUnmount(() => {
  qrBusy.value = false;
  window.clearTimeout(qrTimer);
});

async function toggleModule(key: 'live' | 'live_douyin', enabled: boolean) {
  if (changingModule.value) return;
  changingModule.value = true;
  const previous = settings.modules[key];
  settings.modules[key] = enabled;
  try {
    await save();
    if (!enabled && key === 'live') {
      stopLiveLoop();
      await api.liveOff().catch(() => {});
    }
    if (!enabled && key === 'live_douyin' && !settings.modules.live) {
      stopDouyinFeed();
      await api.liveDouyinStop().catch(() => {});
      douyinFeed.listening = false;
    }
  } catch (err) {
    settings.modules[key] = previous;
    message.error(String(err));
  } finally {
    changingModule.value = false;
  }
}

async function saveDouyinOptions() {
  try {
    await save();
  } catch (err) {
    message.error(String(err));
  }
}

async function douyin() {
  const room = live.value.douyin.room.trim();
  if (!douyinFeed.listening && !room) {
    message.warning(t('live.douyin.roomPh'));
    return;
  }
  busy.value = true;
  try {
    await save();
    if (!douyinFeed.listening) resetDouyinFeed();
    const data = douyinFeed.listening ? await api.liveDouyinStop() : await api.liveDouyinListen(room);
    douyinFeed.listening = !!data.listening;
    douyinFeed.error = data.error || '';
    startDouyinFeed();
  } catch (err) {
    message.error(String(err));
  } finally {
    busy.value = false;
  }
}

async function inject() {
  const content = rehearsalText.value.trim();
  if (!content) return;
  try {
    await save();
    await api.liveRehearsal(content);
    rehearsalText.value = '';
    await pullLiveDesk();
  } catch (err) {
    message.error(String(err));
  }
}

async function loadAudit() {
  if (!liveDesk.sessionId) return;
  try { audit.value = await api.liveMetrics(liveDesk.sessionId); }
  catch (err) { message.error(String(err)); }
}

const biliUp = computed(() => (
  liveDesk.bilibili.state === 'live'
  || liveDesk.bilibili.state === 'connecting'
  || liveDesk.bilibili.state === 'reconnecting'
));

async function cue(act: string) {
  try {
    await api.liveCue(act);
    await pullLiveDesk();
  } catch (err) {
    message.error(String(err));
  }
}

function yuan(n: number) {
  return n.toFixed(n >= 1 ? 2 : 4);
}
</script>

<template>
  <div v-if="showBadge" class="badge">{{ t('live.badge') }}</div>
  <StagePanel :show="show" :title="t('set.group.live')"
              @update:show="emit('update:show', $event)">
    <div class="live-panel-content">
      <PanelGroup tone="amber" :title="t('set.group.live')">
        <div class="module">
          <div><strong>{{ t('mod.live') }}</strong><p class="hint">{{ t('set.mod.liveHost') }}</p></div>
          <NSwitch :aria-label="t('mod.live')" :value="settings.modules.live" :disabled="changingModule"
                   @update:value="toggleModule('live', $event)" />
        </div>
        <div class="module">
          <div><strong>{{ t('mod.liveDouyin') }}</strong><p class="hint">{{ t('set.mod.liveDouyin') }}</p></div>
          <NSwitch :aria-label="t('mod.liveDouyin')" :value="settings.modules.live_douyin" :disabled="changingModule"
                   @update:value="toggleModule('live_douyin', $event)" />
        </div>
      </PanelGroup>
      <PanelGroup v-if="settings.modules.live_douyin || settings.modules.live"
                  tone="teal" :title="t('live.desk.douyin')">
        <div class="row douyin-room">
          <NInput v-model:value="live.douyin.room" :placeholder="t('live.douyin.roomPh')" size="small" />
          <NButton size="small" :loading="busy" @click="douyin">
            {{ douyinFeed.listening ? t('live.douyin.stop') : t('live.douyin.start') }}
          </NButton>
        </div>
        <p class="hint" role="status">{{ douyinFeed.error || (douyinFeed.listening ? t('live.douyin.waiting') : t('live.douyin.idle')) }}</p>
        <label v-if="settings.modules.live" class="label">{{ t('live.desk.roomId') }}
          <NInput v-model:value="live.douyin.room_id" size="small" @blur="saveDouyinOptions" />
        </label>
        <label class="label">{{ t('live.douyin.secret') }}
          <NInput v-model:value="live.douyin.push_secret" type="password" show-password-on="click"
                  :placeholder="t('live.douyin.secretPh')" size="small" @blur="saveDouyinOptions" />
        </label>
        <p v-if="settings.modules.live" class="hint">{{ t('live.desk.callback') }} {{ liveDesk.douyin.callback }}</p>
        <ul v-if="douyinFeed.lines.length" class="danmaku">
          <li v-for="item in douyinFeed.lines" :key="item.seq"><b>{{ item.nickname || '…' }}</b> {{ item.content }}</li>
        </ul>
      </PanelGroup>
      <PanelGroup v-if="settings.modules.live" tone="violet" :title="t('live.desk.title')">
        <p class="status">
          {{ liveDesk.onAir ? segmentLabel : t('live.desk.offAir') }}
          <template v-if="liveDesk.onAir"> · {{ liveDesk.segment.left }}s</template>
          · {{ t('live.desk.spent') }} {{ yuan(liveDesk.budget.spent_cny) }}
          <template v-if="liveDesk.budget.cap_cny"> / {{ liveDesk.budget.cap_cny }}</template>
        </p>
        <p v-if="missingText && !liveDesk.onAir" class="warn">{{ missingText }}</p>
        <p class="hint">{{ healthText }}</p>
        <details>
          <summary>弹幕处理状态{{ liveDesk.processing.generating ? ' · 正在组织回应' : '' }}</summary>
          <p class="hint">
            已接收 {{ liveDesk.processing.accepted }} · 重复过滤 {{ liveDesk.processing.duplicate }}
            · 过期 {{ liveDesk.processing.expired }} · 队列溢出 {{ liveDesk.processing.overflow }}
            · 播放失败 {{ liveDesk.processing.playbackFailures }}
          </p>
        </details>
        <details v-if="liveDesk.sessionId" @toggle="loadAudit">
          <summary>{{ t('live.audit.title') }}</summary>
          <p class="hint">{{ liveDesk.sessionId }}</p>
          <template v-if="audit">
            <p class="hint">{{ t('live.audit.latency', {
              events: audit.events, turns: audit.turns,
              avg: audit.source_to_turn_avg_sec, max: audit.source_to_turn_max_sec,
            }) }}</p>
            <p class="hint">{{ t('live.audit.receipts', {
              completed: audit.acks.completed || 0, failed: audit.acks.failed || 0, models: audit.model_failures,
            }) }}</p>
          </template>
        </details>
        <div v-if="live.features.commands" class="cues">
          <button v-for="act in ['nod', 'heart', 'greet', 'bow', 'stretch']" :key="act" type="button" @click="cue(act)">
            {{ t(`live.act.${act}`) }}
          </button>
        </div>
        <div class="row">
          <NButton size="small" type="primary" :loading="busy" @click="air(!liveDesk.onAir)">
            {{ liveDesk.onAir ? t('live.desk.off') : t('live.desk.on') }}
          </NButton>
          <span class="meta">{{ t('live.desk.queue', { n: liveDesk.queue, r: liveDesk.regulars }) }}</span>
        </div>

        <details open>
          <summary>{{ t('live.desk.platforms') }}</summary>
          <p class="label">{{ t('live.desk.bili') }}</p>
          <NSelect v-model:value="live.bilibili.mode" :options="biliModeOptions" size="small" />
          <template v-if="live.bilibili.mode === 'web'">
            <NInput v-model:value="live.bilibili.room_id" :placeholder="t('live.desk.biliRoom')" size="small" />
            <NInput v-model:value="live.bilibili.cookie" type="password" show-password-on="click"
                    :placeholder="t('live.desk.biliCookie')" size="small" />
            <p class="hint">{{ t('live.desk.biliCookieHint') }}</p>
            <NButton size="tiny" :loading="qrBusy" @click="startBiliQr">{{ t('live.desk.biliLogin') }}</NButton>
            <div v-if="qrImage" class="qr-login">
              <img :src="qrImage" :alt="t('live.desk.biliLogin')" />
              <p class="hint">{{ t(`live.desk.biliQr.${qrState}`) }}</p>
            </div>
          </template>
          <template v-else>
            <NInput v-model:value="live.bilibili.access_key_id" :placeholder="t('live.desk.biliId')" size="small" />
            <NInput v-model:value="live.bilibili.access_key_secret" type="password" show-password-on="click"
                    :placeholder="t('live.desk.biliSecret')" size="small" />
            <NInputNumber v-model:value="live.bilibili.app_id" :min="0" size="small" :placeholder="t('live.desk.biliApp')" />
            <NInput v-model:value="live.bilibili.code" :placeholder="t('live.desk.biliCode')" size="small" />
          </template>
          <p class="hint">{{ liveDesk.bilibili.error || liveDesk.bilibili.anchor || t(`live.bili.${liveDesk.bilibili.state}`) }}</p>
          <NButton size="tiny" :loading="busy" @click="bili(!biliUp)">
            {{ biliUp ? t('live.desk.biliStop') : t('live.desk.biliStart') }}
          </NButton>
        </details>

        <details>
          <summary>{{ t('live.desk.switches') }}</summary>
          <label v-for="key in LIVE_FEATURES" :key="key" class="switch">
            <span>{{ t(`live.feat.${key}`) }}</span>
            <NSwitch :value="!!live.features[key]" size="small" @update:value="(v: boolean) => toggleFeature(key, v)" />
          </label>
        </details>

        <details>
          <summary>{{ t('live.desk.compliance') }}</summary>
          <label class="switch"><span>{{ t('live.desk.strict') }}</span>
            <NSwitch :value="live.compliance.strict" size="small" @update:value="(v: boolean) => toggleAck('strict', v)" />
          </label>
          <label class="switch"><span>{{ t('live.desk.ackVoice') }}</span>
            <NSwitch :value="live.compliance.ack_voice" size="small" @update:value="(v: boolean) => toggleAck('ack_voice', v)" />
          </label>
          <label class="switch"><span>{{ t('live.desk.ackModel') }}</span>
            <NSwitch :value="live.compliance.ack_model" size="small" @update:value="(v: boolean) => toggleAck('ack_model', v)" />
          </label>
          <label class="switch"><span>{{ t('live.desk.ackBgm') }}</span>
            <NSwitch :value="live.compliance.ack_bgm" size="small" @update:value="(v: boolean) => toggleAck('ack_bgm', v)" />
          </label>
          <label class="switch"><span>{{ t('live.desk.bgm') }}</span>
            <NSwitch :value="live.compliance.bgm_licensed" size="small" @update:value="(v: boolean) => toggleAck('bgm_licensed', v)" />
          </label>
          <p class="hint">{{ t('live.desk.filing') }}</p>
        </details>

        <details>
          <summary>{{ t('live.desk.budget') }}</summary>
          <label class="label">{{ t('live.desk.cap') }}</label>
          <NInputNumber v-model:value="live.budget.cap_cny" :min="0" :step="1" size="small" />
          <label class="label">{{ t('live.desk.price') }}</label>
          <NInputNumber v-model:value="live.budget.cny_per_1k" :min="0" :step="0.001" size="small" />
          <NInput v-model:value="live.budget.fallback_base_url" :placeholder="t('live.desk.fallbackUrl')" size="small" />
          <NInput v-model:value="live.budget.fallback_model" :placeholder="t('live.desk.fallbackModel')" size="small" />
          <NInput v-model:value="live.budget.fallback_api_key" type="password" show-password-on="click"
                  :placeholder="t('live.desk.fallbackKey')" size="small" />
          <label class="label">{{ t('live.desk.pace') }}</label>
          <NInputNumber v-model:value="live.pace.batch_sec" :min="1" :max="120" size="small" />
          <label class="label">{{ t('live.desk.cooldown') }}</label>
          <NInputNumber v-model:value="live.pace.user_cooldown_sec" :min="1" :max="120" size="small" />
          <label class="label">{{ t('live.desk.idle') }}</label>
          <NInputNumber v-model:value="live.pace.idle_sec" :min="15" :max="600" size="small" />
          <label class="label">{{ t('live.desk.sessionMax') }}</label>
          <NInputNumber v-model:value="live.pace.session_max_min" :min="0" :max="720" size="small" />
          <label class="label">{{ t('live.desk.quiet') }}</label>
          <NInputNumber v-model:value="live.pace.quiet_min" :min="0" :max="180" size="small" />
          <p class="hint">{{ t('live.desk.guardHint') }}</p>
        </details>

        <details>
          <summary>{{ t('live.desk.show') }}</summary>
          <NInput v-model:value="live.persona.catchphrase" :placeholder="t('live.desk.phrase')" size="small" />
          <NInput v-model:value="live.persona.style" type="textarea" :placeholder="t('live.desk.style')" :autosize="{ minRows: 2, maxRows: 4 }" />
          <NInput v-model:value="live.songs" type="textarea" :placeholder="t('live.desk.songs')" :autosize="{ minRows: 2, maxRows: 4 }" />
          <NInput v-model:value="live.block_words" type="textarea" :placeholder="t('live.desk.block')" :autosize="{ minRows: 2, maxRows: 4 }" />
          <NInput v-model:value="live.schedule.note" :placeholder="t('live.desk.schedule')" size="small" />
          <NInput v-model:value="live.schedule.community" :placeholder="t('live.desk.community')" size="small" />
        </details>

        <details v-if="live.features.rehearsal">
          <summary>{{ t('live.desk.rehearsal') }}</summary>
          <div class="row">
            <NInput v-model:value="rehearsalText" :placeholder="t('live.desk.injectPh')" size="small" @keyup.enter="inject" />
            <NButton size="small" @click="inject">{{ t('live.desk.inject') }}</NButton>
          </div>
        </details>

        <p class="hint">{{ t('live.desk.obs') }}</p>
        <NButton size="small" :loading="busy" @click="save">{{ t('live.desk.save') }}</NButton>
      </PanelGroup>
    </div>
  </StagePanel>
</template>

<style scoped>
.badge {
  position: absolute;
  left: 50%;
  top: calc(12px + var(--desk-chrome, 0px));
  transform: translateX(-50%);
  z-index: 16;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 13px;
  letter-spacing: 0.12em;
  pointer-events: none;
}

.live-panel-content { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.module { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 10px; }
.module + .module { padding-top: 8px; border-top: 1px solid var(--panel-line); }
.module strong { font-size: 13px; }
.module .hint { margin-top: 3px; }
.douyin-room { flex-wrap: wrap; }
.douyin-room :deep(.n-input) { flex: 1 1 148px; }
.danmaku { list-style: none; max-height: 180px; overflow: auto; font-size: 12px; }
.danmaku li { padding: 4px 0; border-top: 1px solid var(--panel-line); overflow-wrap: anywhere; }

.row, .switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch {
  justify-content: space-between;
  margin: 6px 0;
  font-size: 13px;
}

.status, .hint, .warn, .label, .meta {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
}

.hint, .meta { opacity: 0.72; }
.warn { color: #ffd27a; }
.label { margin-top: 8px; }

.qr-login {
  width: 190px;
  padding: 8px;
  border-radius: 10px;
  background: #fff;
  color: #222;
  text-align: center;
}

.qr-login img { display: block; width: 174px; height: 174px; }

summary {
  cursor: pointer;
  font-size: 13px;
  letter-spacing: 0.06em;
}

details { display: flex; flex-direction: column; gap: 6px; }

.cues {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cues button {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  border-radius: 999px;
  padding: 2px 8px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
</style>
