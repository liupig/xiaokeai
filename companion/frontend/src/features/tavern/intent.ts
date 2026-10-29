/** 聊天里点名魅影酒馆。正则在 locales 的 intents.json。 */

import { intentRe } from '../../i18n';

function folded(text: string) {
  return (text || '').replace(/[「」『』“”"'']/g, '').replace(/[。！？、,.!?;；…~～\s]/g, '').trim();
}

export function isTavernExit(text: string) {
  const t = (text || '').trim();
  const n = folded(t);
  if (!t) return false;
  return intentRe('tavern.close').test(t) || intentRe('tavern.close').test(n);
}

/** 没开着牌桌时，只有点名酒馆才打开。看牌、许愿不算。 */
export function canWakeTavern(text: string) {
  const t = (text || '').trim();
  const n = folded(t);
  if (!t || isTavernExit(t)) return false;
  return intentRe('tavern.open').test(t) || intentRe('tavern.open').test(n);
}
