// Local coin readout. The pill next to the character name shows the balance
// from the box. After the first load, every change plays a small bump on
// that pill. The wallet drawer is separate; this module only opens the
// personal center. Heartbeats keep the idle streak alive.
import { onScopeDispose, reactive, ref, watch } from 'vue';
import { api, type CoinState } from '../../api/client';
import { t } from '../../i18n';

export const coins = reactive({
  balanceMilli: 0,
  multiplier: 1,
  gpu: 1,
  vramGb: 0,
  perMin: 2,
  streakSec: 0,
  wishSec: 0,
  wishLeft: 50,
  address: '',
  ready: false,
});

export const userCenterOpen = ref(false);

export function openUserCenter() {
  userCenterOpen.value = true;
}

let timer = 0;
const deltaListeners = new Set<(deltaMilli: number) => void>();
let deltaArmed = false;

function armDelta() {
  if (deltaArmed) return;
  deltaArmed = true;
  let last = coins.balanceMilli;
  let primed = false;
  watch(() => coins.balanceMilli, (next) => {
    if (!primed) {
      primed = true;
      last = next;
      return;
    }
    const delta = next - last;
    last = next;
    if (!delta) return;
    for (const fn of deltaListeners) fn(delta);
  });
}

export function onCoinDelta(fn: (deltaMilli: number) => void) {
  deltaListeners.add(fn);
  onScopeDispose(() => deltaListeners.delete(fn));
}

function apply(row: CoinState) {
  coins.balanceMilli = row.balance_milli;
  coins.multiplier = row.multiplier;
  coins.gpu = row.gpu ?? 1;
  coins.vramGb = row.vram_gb ?? 0;
  coins.perMin = row.per_min;
  coins.streakSec = row.streak_sec;
  coins.wishSec = row.wish_sec ?? 0;
  if (row.wish_left != null) coins.wishLeft = row.wish_left;
  coins.address = row.address || '';
  coins.ready = true;
}

async function beat() {
  try {
    apply(await api.coinHeartbeat());
  } catch {
    /* 后端还没起来时下一次心跳再试 */
  }
}

export function startCoins() {
  if (timer) return;
  armDelta();
  void beat();
  timer = window.setInterval(() => void beat(), 10 * 60 * 1000);
}

let refreshTimer = 0;

/** 对话入账是异步的。这一轮说完再读一次余额，不跟心跳绑在一起。 */
export function refreshCoinsSoon() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    void api.coinBalance().then((row) => {
      coins.balanceMilli = row.balance_milli;
      coins.ready = true;
    }).catch(() => {});
  }, 1200);
}

function trimCoins(milli: number) {
  const c = Math.abs(milli) / 1000;
  if (c >= 100) return String(Math.floor(c));
  const shown = Math.floor(c * 10) / 10;
  return Number.isInteger(shown) ? String(shown) : shown.toFixed(1);
}

const PAY_NOTE = /XKTX3\.[A-Za-z0-9_-]{16,}/;

export function payNote(text: string) {
  const found = (text || '').match(PAY_NOTE);
  return found ? found[0] : '';
}

const NOT_PURSE = /股价|金价|房价|物价|多少钱一|卖多少/;

export function asksPurse(text: string) {
  const raw = (text || '').replace(/[\s?？!！。，,~～]/g, '');
  if (!raw || raw.length > 40) return false;
  if (NOT_PURSE.test(raw)) return false;
  if (raw.includes('落下') && !/一共|所有|余额|钱包|总共/.test(raw)) return false;
  if (/你(?:现在|目前|到底|究竟)?有多少(?:钱|金币)/.test(raw)) return true;
  const mine = /我|咱|余额|钱包/.test(raw)
    || (/金币/.test(raw) && /所有|一共|总共|余额|还有|现在/.test(raw));
  return mine && /多少|几枚|几个|总共|一共|所有|全部/.test(raw);
}

export async function purseSpeech(): Promise<string> {
  const row = await api.coinBalance();
  coins.balanceMilli = row.balance_milli;
  return t('user.purseSpeak', { n: trimCoins(row.balance_milli) });
}

export async function collectNote(text: string): Promise<string> {
  const note = payNote(text);
  if (!note) return '';
  try {
    const row = await api.coinRedeem(note);
    coins.balanceMilli = row.balance_milli;
    if (row.address) coins.address = row.address;
    return t('user.cashSpeak', { n: trimCoins(row.received_milli) });
  } catch (error) {
    const code = error instanceof Error ? error.message : '';
    const key = `user.err.${code}`;
    const spoken = t(key);
    return spoken === key ? t('user.cashMiss') : spoken;
  }
}
