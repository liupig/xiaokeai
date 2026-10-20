// One wish, in order: open the pool, ask the box for three throws and a coin
// amount, fly those props in, pause, rain coins on the opposite side, then
// speak. The spoken line is the model's sentence when it keeps the integer
// amount; otherwise the local result line. If memory is on, the fact list
// refreshes after the ritual. The opening line is spoken by the caller, so
// the model cannot invent the coin count before the box answers.
import { reactive } from 'vue';
import { api } from '../../api/client';
import { t } from '../../i18n';
import { stage } from '../../engine/stage';
import { coins } from '../coins/session';
import { refreshMemory } from '../memory/session';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { canWakeWish } from './intent';
import { installWish } from './plugin';

export { canWakeWish };

export const wishUi = reactive({
  on: false,
  caption: '',
});

let running = false;

export function wishBusy() {
  return running;
}

function trimCoins(milli: number) {
  const c = Math.abs(milli) / 1000;
  if (c >= 100) return String(Math.floor(c));
  const shown = Math.floor(c * 10) / 10;
  return Number.isInteger(shown) ? String(shown) : shown.toFixed(1);
}

function takeRow(row: { balance_milli: number; multiplier: number; gpu?: number; vram_gb?: number; per_min: number; streak_sec: number; wish_sec?: number; wish_left?: number }) {
  coins.balanceMilli = row.balance_milli;
  coins.multiplier = row.multiplier;
  coins.gpu = row.gpu ?? coins.gpu;
  coins.vramGb = row.vram_gb ?? coins.vramGb;
  coins.perMin = row.per_min;
  coins.streakSec = row.streak_sec;
  coins.wishSec = row.wish_sec ?? 0;
  if (row.wish_left != null) coins.wishLeft = row.wish_left;
}

async function waitIdle() {
  const { useChatStore } = await import('../../stores/chat');
  const { speechPlayer } = await import('../voice/tts');
  for (let i = 0; i < 80; i += 1) {
    if (!useChatStore().sending && !speechPlayer.isSpeaking()) return;
    await new Promise((resolve) => window.setTimeout(resolve, 100));
  }
}

async function speak(line: string) {
  const { useChatStore } = await import('../../stores/chat');
  await useChatStore().send(line, { hideUser: true, scripted: true, localLine: line });
}

export function beginWish(): { line: string; done: Promise<{ dropMilli: number } | null> } {
  if (running) return { line: t('wish.busy'), done: Promise.resolve(null) };
  if (coins.ready && coins.wishLeft <= 0) return { line: t('wish.none'), done: Promise.resolve(null) };
  running = true;
  wishUi.on = true;
  wishUi.caption = t('wish.caption');
  const done = ritual().finally(() => {
    running = false;
    wishUi.on = false;
    wishUi.caption = '';
  });
  return { line: t('wish.open'), done };
}

async function ritual(): Promise<{ dropMilli: number } | null> {
  const plugin = installWish(stage);
  await plugin.start();
  const ready = plugin.whenReady();
  const characterId = useCharacterStore().currentId || 0;
  let row: Awaited<ReturnType<typeof api.coinWish>> | null = null;
  try {
    row = await api.coinWish(characterId);
  } catch {
    row = null;
  }
  await ready;
  if (!row) {
    wishUi.caption = t('wish.fail');
    await waitIdle();
    void speak(t('wish.fail'));
    await plugin.finish();
    return null;
  }
  takeRow(row);
  const thrown = Array.isArray(row.throws) ? row.throws : [];
  if (thrown.length) {
    wishUi.caption = thrown.map((item) => t(`wish.item.${item.id}`)).join(' · ');
  }
  await plugin.toss(thrown);
  const n = trimCoins(row.drop_milli);
  const line = (row.line || '').trim()
    || (row.drop_milli >= 30_000 ? t('wish.jackpot', { n }) : t('wish.result', { n }));
  wishUi.caption = t('wish.drop', { n, left: coins.wishLeft });
  plugin.reveal(n);
  await waitIdle();
  void speak(line);
  await new Promise((resolve) => window.setTimeout(resolve, 7200));
  if (characterId && useSettingsStore().modules.memory) void refreshMemory(characterId);
  await plugin.finish();
  return { dropMilli: row.drop_milli };
}
