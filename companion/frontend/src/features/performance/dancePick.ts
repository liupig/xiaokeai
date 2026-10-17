/**
 * 点舞避让。用户没点名时，近期跳过的舞权重变低，让没露过面的有机会。
 * 「再跳一次」留刚才那支；「换一个」不许留。
 */

export type DanceIntent = 'repeat' | 'switch' | 'open';

const RECENT_KEY = 'companion.dance.recent';
const RECENT_CAP = 8;
/** 下标 0 是刚跳完的。越近越难再被抽到。 */
const RECENT_WEIGHT = [0.06, 0.16, 0.32, 0.5, 0.68, 0.82, 0.92];

const REPEAT_RE = /再跳一次|再跳一遍|再来一次|再来一遍|再跳这|这支再|刚才那|同样的|一样的|\bagain\b|one more time|same one/i;
const SWITCH_RE = /换一|换支|另一|别的舞|不一样|不要这|跳个别|下一支|再跳一个|再来一个|再来一支|再跳支|\banother\b|\bdifferent\b/i;
const OPEN_RE = /跳.{0,6}舞|来一段|来一支|跳呀|跳起来|跳一个|dance/i;
const YES_RE = /^(好的|好呀|好啊|好吧|可以|行呀|行吧|来吧|跳吧|就这个|要这个|就它|嗯好|对)[呀啊吧呢哦哇～!！。.\s]*$/;

let recent: string[] = loadRecent();

function norm(name: string) {
  return (name || '').replace(/\.vmd$/i, '').trim().toLowerCase();
}

function loadRecent(): string[] {
  try {
    const raw = sessionStorage.getItem(RECENT_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.map((x) => norm(String(x))).filter(Boolean).slice(0, RECENT_CAP) : [];
  } catch {
    return [];
  }
}

function saveRecent() {
  try { sessionStorage.setItem(RECENT_KEY, JSON.stringify(recent)); } catch { /* 隐私模式 */ }
}

export function noteDancePlayed(name: string) {
  const n = norm(name);
  if (!n) return;
  recent = [n, ...recent.filter((x) => x !== n)].slice(0, RECENT_CAP);
  saveRecent();
}

export function danceIntent(ask: string): DanceIntent {
  const t = ask || '';
  if (REPEAT_RE.test(t)) return 'repeat';
  if (SWITCH_RE.test(t)) return 'switch';
  return 'open';
}

/** 这句话本身就是在要舞，不等模型补标记。 */
export function asksForDance(text: string) {
  const t = text || '';
  return OPEN_RE.test(t) || REPEAT_RE.test(t) || SWITCH_RE.test(t);
}

/** 短句答应。上一句若点了舞名，才当成要跳那支。 */
export function isDanceYes(text: string) {
  return YES_RE.test((text || '').trim());
}

/** 1 是没跳过。越接近 0 越是刚跳完的。 */
export function danceWeight(name: string) {
  const idx = recent.indexOf(norm(name));
  if (idx < 0) return 1;
  return RECENT_WEIGHT[idx] ?? 1;
}

function weightOf(name: string, banLast: boolean) {
  const idx = recent.indexOf(norm(name));
  if (banLast && idx === 0) return 0;
  if (idx < 0) return 1;
  return RECENT_WEIGHT[idx] ?? 1;
}

/** 点名优先由调用方处理。这里只处理再跳一次 / 换一个 / 没点名。 */
export function sampleDance<T>(items: T[], nameOf: (item: T) => string, intent: DanceIntent): T | null {
  if (!items.length) return null;
  if (intent === 'repeat' && recent[0]) {
    const again = items.find((item) => norm(nameOf(item)) === recent[0]);
    if (again) return again;
  }
  const banLast = intent === 'switch';
  const bag = items.map((item) => ({ item, w: weightOf(nameOf(item), banLast) }));
  const sum = bag.reduce((s, x) => s + x.w, 0);
  if (sum <= 0) return items[Math.floor(Math.random() * items.length)];
  let roll = Math.random() * sum;
  for (const x of bag) {
    roll -= x.w;
    if (roll <= 0) return x.item;
  }
  return bag[bag.length - 1].item;
}
