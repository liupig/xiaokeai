<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { NDrawer, NDrawerContent, NQrCode, NSlider, useMessage } from 'naive-ui';
import { api, type CoinPreview } from '../../api/client';
import { t } from '../../i18n';
import { useSettingsStore } from '../../stores/settings';
import { coins, onCoinDelta, userCenterOpen } from './session';
import { beginWish, wishUi } from '../wish';

type Tab = 'receive' | 'send' | 'cash';
type PayStep = 'edit' | 'review' | 'done';

const settings = useSettingsStore();
const message = useMessage();
const tab = ref<Tab>('receive');
const payStep = ref<PayStep>('edit');
const hours = ref(0);
const calcOn = ref(false);
const preview = ref<CoinPreview | null>(null);
const payTo = ref('');
const payCoins = ref<number | null>(1);
const useMax = ref(false);
const noteOut = ref('');
const noteIn = ref('');
const busy = ref(false);
const copied = ref('');
let previewToken = 0;
let copyTimer = 0;

function trimNum(n: number) {
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function trimCoins(milli: number) {
  const c = milli / 1000;
  if (c >= 100) return String(Math.floor(c));
  const shown = Math.floor(c * 10) / 10;
  return Number.isInteger(shown) ? String(shown) : shown.toFixed(1);
}

function formatDur(sec: number) {
  settings.locale.ui;
  const whole = Math.max(0, Math.floor(sec));
  if (whole < 60) return t('coin.timeS', { s: whole });
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  if (h > 0 && m === 0) return t('coin.timeHours', { h });
  return h > 0 ? t('coin.timeH', { h, m }) : t('coin.timeM', { m });
}

function shortAddr(addr: string) {
  if (addr.length < 12) return addr || '—';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function grouped(addr: string) {
  return addr.replace(/(.{4})/g, '$1 ').trim();
}

const balanceText = computed(() => trimCoins(coins.balanceMilli));
const payMilli = computed(() => {
  if (useMax.value) return coins.balanceMilli;
  return Math.round(Number(payCoins.value || 0) * 1000);
});
const payAmountText = computed(() => trimCoins(payMilli.value));
const payToClean = computed(() => payTo.value.trim().toLowerCase());

const payBlock = computed(() => {
  settings.locale.ui;
  const to = payToClean.value;
  if (!to) return 'empty';
  if (!/^[0-9a-f]{64}$/.test(to)) return 'bad_address';
  if (to === coins.address) return 'self';
  if (payMilli.value <= 0) return 'bad_amount';
  if (payMilli.value > coins.balanceMilli) return 'funds';
  return '';
});

const streakText = computed(() => {
  settings.locale.ui;
  return t('user.streak', { time: formatDur(coins.streakSec) });
});
const mineText = computed(() => {
  settings.locale.ui;
  const gpu = coins.gpu || 1;
  const vars = {
    m: trimNum(coins.multiplier || 1),
    g: trimNum(gpu),
    p: trimNum(coins.perMin || 2),
  };
  return coins.vramGb > 0 ? t('user.mine', vars) : t('user.mineCpu', vars);
});
const demoText = computed(() => {
  settings.locale.ui;
  const row = preview.value;
  if (!row) return '';
  return t('user.demoResult', {
    time: formatDur(row.sec),
    m: trimNum(row.multiplier),
    g: trimNum(row.gpu || coins.gpu || 1),
    p: trimNum(row.per_min),
    n: trimCoins(row.earned_milli),
  });
});

const wishCast = ref(false);
const wishDrop = ref('');
const balancePulse = ref<'up' | 'down' | ''>('');
let balanceGen = 0;

onCoinDelta((delta) => {
  const dir = delta > 0 ? 'up' : 'down';
  const gen = ++balanceGen;
  balancePulse.value = '';
  requestAnimationFrame(() => {
    if (gen === balanceGen) balancePulse.value = dir;
  });
});

const wishLeftText = computed(() => {
  settings.locale.ui;
  return t('user.wishLeft', { n: coins.wishLeft });
});

async function castWish() {
  if (wishCast.value || wishUi.on || coins.wishLeft <= 0) return;
  wishCast.value = true;
  wishDrop.value = '';
  try {
    const { line, done } = beginWish();
    const { useChatStore } = await import('../../stores/chat');
    void useChatStore().send(line, { hideUser: true, scripted: true, localLine: line });
    const row = await done;
    if (row) wishDrop.value = t('user.wishDrop', { n: trimCoins(row.dropMilli) });
  } catch (error) {
    message.error(errText(error));
  } finally {
    wishCast.value = false;
  }
}

function errText(error: unknown) {
  const code = error instanceof Error ? error.message : '';
  const key = `user.err.${code}`;
  const text = t(key);
  return text === key ? code : text;
}

async function copyText(text: string, which: string) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    return;
  }
  copied.value = which;
  window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => {
    copied.value = '';
  }, 1400);
}

function fillMax() {
  useMax.value = true;
  payCoins.value = Math.floor(coins.balanceMilli / 100) / 10;
}

function onAmountInput() {
  useMax.value = false;
}

function goReview() {
  if (payBlock.value) {
    if (payBlock.value !== 'empty') message.error(t(`user.err.${payBlock.value}`));
    return;
  }
  payStep.value = 'review';
}

async function sendNote() {
  if (busy.value || payBlock.value) return;
  busy.value = true;
  try {
    const row = await api.coinPay(payToClean.value, payMilli.value);
    coins.balanceMilli = row.balance_milli;
    coins.address = row.address || coins.address;
    noteOut.value = row.note;
    payStep.value = 'done';
  } catch (error) {
    message.error(errText(error));
  } finally {
    busy.value = false;
  }
}

function again() {
  payStep.value = 'edit';
  noteOut.value = '';
  payTo.value = '';
  useMax.value = false;
}

async function cashNote() {
  if (busy.value || !noteIn.value.trim()) return;
  busy.value = true;
  try {
    const row = await api.coinRedeem(noteIn.value.trim());
    coins.balanceMilli = row.balance_milli;
    coins.address = row.address || coins.address;
    noteIn.value = '';
    message.success(t('user.redeemOk', { n: trimCoins(row.received_milli) }));
  } catch (error) {
    message.error(errText(error));
  } finally {
    busy.value = false;
  }
}

async function loadPreview() {
  const token = ++previewToken;
  const sec = Math.round(hours.value * 3600);
  try {
    const row = await api.coinPreview(sec);
    if (token !== previewToken) return;
    preview.value = row;
  } catch {
    /* 后端还没起来时抽屉里先空着 */
  }
}

watch(userCenterOpen, (open) => {
  if (!open) return;
  calcOn.value = false;
  tab.value = 'receive';
  payStep.value = 'edit';
  hours.value = Math.min(48, Math.round((coins.streakSec / 3600) * 2) / 2);
  void loadPreview();
});

watch(hours, () => {
  if (userCenterOpen.value) void loadPreview();
});
</script>

<template>
  <n-drawer :show="userCenterOpen" :width="400" placement="right"
            show-mask="transparent" to="body"
            @update:show="(v: boolean) => userCenterOpen = v">
    <n-drawer-content :title="t('user.title')" closable :native-scrollbar="false">
      <header class="hero">
        <div class="asset">{{ t('user.asset') }}</div>
        <div class="balance" :class="balancePulse">{{ balanceText }}</div>
        <div class="streak">{{ streakText }}</div>
        <div class="mine">{{ mineText }}</div>
        <p class="hint">{{ t('user.tokenHint') }}</p>
      </header>

      <section class="wish">
        <div class="wish-title">{{ t('user.wish') }}</div>
        <p class="hint">{{ t('user.wishHint') }}</p>
        <p class="hint">{{ wishLeftText }}</p>
        <button type="button" class="primary" :disabled="wishCast || wishUi.on || coins.wishLeft <= 0"
                @click="castWish">
          {{ wishCast ? t('user.wishCast') : (coins.wishLeft <= 0 ? t('user.wishWait') : t('user.wishGo')) }}
        </button>
        <p v-if="wishDrop" class="result">{{ wishDrop }}</p>
      </section>

      <div class="demo">
        <p class="hint">{{ t('user.demoHint') }}</p>
        <n-slider v-model:value="hours" :min="0" :max="48" :step="0.5" :tooltip="false"
                  @update:value="calcOn = true" />
        <p v-if="calcOn" class="result">{{ demoText }}</p>
      </div>

      <div class="tabs">
        <button type="button" :class="{ on: tab === 'receive' }" @click="tab = 'receive'">{{ t('user.tabReceive') }}</button>
        <button type="button" :class="{ on: tab === 'send' }" @click="tab = 'send'">{{ t('user.tabSend') }}</button>
        <button type="button" :class="{ on: tab === 'cash' }" @click="tab = 'cash'">{{ t('user.tabCash') }}</button>
      </div>

      <section v-if="tab === 'receive'" class="pane">
        <div class="qr-card">
          <n-qr-code v-if="coins.address" :value="coins.address" :size="188"
                     color="#141414" background-color="#ffffff" error-correction-level="H" />
        </div>
        <p class="hint">{{ t('user.receiveHint') }}</p>
        <div class="addr-box">{{ grouped(coins.address) }}</div>
        <button type="button" class="primary" @click="copyText(coins.address, 'addr')">
          {{ copied === 'addr' ? t('user.copied') : t('user.copy') }}
        </button>
      </section>

      <section v-else-if="tab === 'send'" class="pane">
        <template v-if="payStep === 'edit'">
          <label class="field">{{ t('user.to') }}</label>
          <input v-model="payTo" class="line" spellcheck="false" autocomplete="off" placeholder="64 hex" />
          <label class="field">{{ t('user.payAmt') }}</label>
          <div class="amount">
            <input v-model.number="payCoins" class="line grow" type="number" min="0.1" step="0.1"
                   @input="onAmountInput" />
            <span class="unit">{{ t('user.asset') }}</span>
            <button type="button" class="ghost" @click="fillMax">{{ t('user.max') }}</button>
          </div>
          <div class="row">
            <span>{{ t('user.available', { n: balanceText }) }}</span>
            <span>{{ t('user.fee') }} {{ t('user.feeFree') }}</span>
          </div>
          <p v-if="payBlock && payBlock !== 'empty'" class="warn">{{ t(`user.err.${payBlock}`) }}</p>
          <button type="button" class="primary" :disabled="!!payBlock" @click="goReview">{{ t('user.nextStep') }}</button>
        </template>

        <template v-else-if="payStep === 'review'">
          <div class="sheet">
            <div class="sheet-amt">{{ payAmountText }}</div>
            <div class="sheet-asset">{{ t('user.asset') }}</div>
            <div class="kv"><span>{{ t('user.from') }}</span><b>{{ shortAddr(coins.address) }}</b></div>
            <div class="kv"><span>{{ t('user.to') }}</span><b>{{ shortAddr(payToClean) }}</b></div>
            <div class="kv"><span>{{ t('user.fee') }}</span><b>{{ t('user.feeFree') }}</b></div>
            <div class="kv total"><span>{{ t('user.total') }}</span><b>{{ payAmountText }}</b></div>
          </div>
          <button type="button" class="primary" :disabled="busy" @click="sendNote">{{ t('user.sign') }}</button>
          <button type="button" class="text" @click="payStep = 'edit'">{{ t('user.back') }}</button>
        </template>

        <template v-else>
          <div class="done">
            <div class="mark">✓</div>
            <div class="done-title">{{ t('user.signed') }}</div>
            <div class="sheet-amt">{{ payAmountText }}</div>
            <div class="sheet-asset">{{ t('user.asset') }} → {{ shortAddr(payToClean) }}</div>
          </div>
          <div v-if="noteOut" class="qr-card small">
            <n-qr-code :value="noteOut" :size="168" color="#141414" background-color="#ffffff"
                       error-correction-level="L" />
          </div>
          <p class="hint">{{ t('user.signedHint') }}</p>
          <button type="button" class="primary" @click="copyText(noteOut, 'note')">
            {{ copied === 'note' ? t('user.copied') : t('user.copyNote') }}
          </button>
          <button type="button" class="text" @click="again">{{ t('user.again') }}</button>
        </template>
      </section>

      <section v-else class="pane">
        <p class="hint">{{ t('user.redeemHint') }}</p>
        <textarea v-model="noteIn" class="note" spellcheck="false" />
        <button type="button" class="primary" :disabled="busy || !noteIn.trim()" @click="cashNote">
          {{ t('user.redeem') }}
        </button>
      </section>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 14px;
  padding: 16px 16px 14px;
  border-radius: 18px;
  background:
    radial-gradient(90% 80% at 100% 0%, rgba(226, 181, 106, 0.28), transparent 58%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.025));
  border: 1px solid rgba(255, 231, 194, 0.16);
}
.streak {
  margin-top: 8px;
  font-size: 12px;
  color: rgba(232, 232, 240, 0.72);
}
.mine {
  margin-top: 4px;
  font-size: 12px;
  color: #ffe7c2;
}
.wish {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 231, 194, 0.12);
}
.wish-title {
  font-weight: 700;
  color: #ffe7c2;
}
.wish .primary {
  margin-top: 8px;
}
.wish .primary:disabled {
  opacity: 0.45;
}
.asset {
  font-size: 12px;
  letter-spacing: 0.16em;
  color: rgba(255, 236, 214, 0.62);
}
.balance {
  margin-top: 4px;
  font-size: 42px;
  font-weight: 750;
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  color: #ffe7c2;
}
.balance.up {
  animation: bal-pop 0.45s ease;
}
.balance.down {
  animation: bal-dip 0.4s ease;
}
@keyframes bal-pop {
  40% { transform: scale(1.06); color: #fff6dc; }
}
@keyframes bal-dip {
  40% { transform: scale(0.96); color: #f3c2b0; }
}
.demo {
  margin-bottom: 16px;
  padding: 10px 12px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
}
.tabs button {
  border: none;
  border-radius: 9px;
  padding: 8px 0;
  background: transparent;
  color: rgba(232, 232, 240, 0.72);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}
.tabs button.on {
  background: #ffe7c2;
  color: #1a140c;
}
.pane {
  padding-top: 18px;
}
.qr-card {
  width: fit-content;
  margin: 4px auto 14px;
  padding: 12px;
  border-radius: 22px;
  background:
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(160deg, #fff6dc, #e2b56a 42%, #8a6230) border-box;
  border: 2px solid transparent;
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.28);
}
.qr-card.small {
  margin-top: 8px;
}
.hint {
  margin: 0 0 12px;
  text-align: center;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(232, 232, 240, 0.68);
}
.addr-box {
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
  letter-spacing: 0.04em;
  text-align: center;
  word-break: break-all;
  color: rgba(255, 231, 194, 0.92);
}
.primary, .text, .ghost {
  font: inherit;
  cursor: pointer;
}
.primary {
  display: block;
  width: 100%;
  margin-top: 14px;
  border: none;
  border-radius: 12px;
  padding: 13px 16px;
  background: #ffe7c2;
  color: #1a140c;
  font-size: 15px;
  font-weight: 700;
}
.primary:disabled {
  opacity: 0.4;
  cursor: default;
}
.text {
  display: block;
  width: 100%;
  margin-top: 8px;
  border: none;
  background: transparent;
  color: rgba(232, 232, 240, 0.72);
  padding: 8px;
}
.field {
  display: block;
  margin: 0 0 6px;
  font-size: 12px;
  color: rgba(232, 232, 240, 0.62);
}
.line {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.22);
  color: #ffe7c2;
  font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}
.amount {
  display: flex;
  align-items: center;
  gap: 8px;
}
.amount .grow {
  flex: 1;
}
.unit {
  color: rgba(255, 231, 194, 0.8);
  font-size: 13px;
  font-weight: 650;
}
.ghost {
  border: none;
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(255, 231, 194, 0.14);
  color: #ffe7c2;
  font-size: 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 12px;
  color: rgba(232, 232, 240, 0.55);
}
.warn {
  margin: 8px 0 0;
  font-size: 12px;
  color: #ffb4b4;
}
.sheet {
  padding: 16px 14px 6px;
  border-radius: 16px;
  text-align: center;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 231, 194, 0.1);
}
.sheet-amt {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  color: #ffe7c2;
}
.sheet-asset {
  margin: 6px 0 16px;
  color: rgba(232, 232, 240, 0.7);
  font-size: 13px;
}
.kv {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 13px;
  color: rgba(232, 232, 240, 0.62);
}
.kv b {
  color: rgba(255, 231, 194, 0.95);
  font-weight: 650;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.kv.total b {
  color: #ffe7c2;
}
.done {
  text-align: center;
}
.mark {
  width: 52px;
  height: 52px;
  margin: 0 auto 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(120, 196, 140, 0.18);
  color: #9be7a8;
  font-size: 26px;
}
.done-title {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 700;
}
.note {
  width: 100%;
  min-height: 120px;
  box-sizing: border-box;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.22);
  color: rgba(255, 231, 194, 0.92);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  padding: 12px;
  resize: vertical;
}
.result {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: #ffe7c2;
}
.demo :deep(.n-slider-rail__fill) {
  background: linear-gradient(90deg, #a87432, #ffe7c2);
}
</style>
