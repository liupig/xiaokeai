<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, NInput, NInputNumber, NSwitch, useMessage } from 'naive-ui';
import { api } from '../../api/client';
import { t } from '../../i18n';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { LIVE_FEATURES } from './config';
import { liveDesk, pullLiveDesk } from './session';

const settings = useSettingsStore();
const characters = useCharacterStore();
const message = useMessage();
const busy = ref(false);
const rehearsalText = ref('');

const live = computed(() => settings.live);
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
  <button v-if="!liveDesk.deskOpen" type="button" class="pill" @click="liveDesk.deskOpen = true">
    <span class="lamp" :class="{ on: liveDesk.onAir, bad: liveDesk.health.degraded }" />
    {{ t('live.desk.open') }}
  </button>
  <section v-else class="desk">
    <header>
      <span class="lamp" :class="{ on: liveDesk.onAir, bad: liveDesk.health.degraded }" />
      <strong>{{ t('live.desk.title') }}</strong>
      <button type="button" class="text" @click="liveDesk.deskOpen = false">{{ t('live.desk.close') }}</button>
    </header>
    <p class="status">
      {{ liveDesk.onAir ? segmentLabel : t('live.desk.offAir') }}
      <template v-if="liveDesk.onAir"> · {{ liveDesk.segment.left }}s</template>
      · {{ t('live.desk.spent') }} {{ yuan(liveDesk.budget.spent_cny) }}
      <template v-if="liveDesk.budget.cap_cny"> / {{ liveDesk.budget.cap_cny }}</template>
    </p>
    <p v-if="missingText && !liveDesk.onAir" class="warn">{{ missingText }}</p>
    <p class="hint">{{ healthText }}</p>
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
      <NInput v-model:value="live.bilibili.access_key_id" :placeholder="t('live.desk.biliId')" size="small" />
      <NInput v-model:value="live.bilibili.access_key_secret" type="password" show-password-on="click"
              :placeholder="t('live.desk.biliSecret')" size="small" />
      <NInputNumber v-model:value="live.bilibili.app_id" :min="0" size="small" :placeholder="t('live.desk.biliApp')" />
      <NInput v-model:value="live.bilibili.code" :placeholder="t('live.desk.biliCode')" size="small" />
      <p class="hint">{{ liveDesk.bilibili.error || liveDesk.bilibili.anchor || t(`live.bili.${liveDesk.bilibili.state}`) }}</p>
      <NButton size="tiny" :loading="busy" @click="bili(!biliUp)">
        {{ biliUp ? t('live.desk.biliStop') : t('live.desk.biliStart') }}
      </NButton>
      <p class="label">{{ t('live.desk.douyin') }}</p>
      <NInput v-model:value="live.douyin.room_id" :placeholder="t('live.desk.roomId')" size="small" />
      <NInput v-model:value="live.douyin.push_secret" type="password" show-password-on="click"
              :placeholder="t('live.douyin.secretPh')" size="small" />
      <p class="hint">{{ t('live.desk.callback') }} {{ liveDesk.douyin.callback }}</p>
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
      <NInputNumber v-model:value="live.pace.batch_sec" :min="5" :max="120" size="small" />
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
  </section>
</template>

<style scoped>
.badge {
  position: absolute;
  left: 50%;
  top: 18px;
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

.pill,
.desk {
  position: absolute;
  left: 12px;
  top: 64px;
  z-index: 16;
  color: rgba(255, 255, 255, 0.92);
}

.pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(12, 12, 20, 0.55);
  font: inherit;
  font-size: 12px;
  letter-spacing: 0.08em;
  cursor: pointer;
}

.desk {
  width: min(320px, calc(100vw - 28px));
  max-height: calc(100vh - 96px);
  overflow: auto;
  padding: 12px;
  border-radius: 16px;
  background: rgba(12, 12, 20, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.16);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

header, .row, .switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch {
  justify-content: space-between;
  margin: 6px 0;
  font-size: 13px;
}

.lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.35);
}

.lamp.on { background: #7dffa1; box-shadow: 0 0 8px rgba(125, 255, 161, 0.8); }
.lamp.bad { background: #ffb020; }

.text {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.status, .hint, .warn, .label, .meta {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
}

.hint, .meta { opacity: 0.72; }
.warn { color: #ffd27a; }
.label { margin-top: 8px; }

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
