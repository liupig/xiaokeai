// Local coin readout. The pill next to the character name shows the balance
// from the box. After the first load, every change plays a small bump on
// that pill. The wallet drawer is separate; this module only opens the
// personal center. Heartbeats keep the idle streak alive.
import { onScopeDispose, reactive, ref, watch } from 'vue';
import { api, type CoinState } from '../../api/client';

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
  timer = window.setInterval(() => void beat(), 20_000);
}
