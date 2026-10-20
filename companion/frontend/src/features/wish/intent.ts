/** 口头许愿。正则在 locales 的 intents.json。 */

import { intentRe } from '../../i18n';

function norm(text: string) {
  return (text || '')
    .replace(/[「」『』“”"'']/g, '')
    .replace(/[。！？、,.!?;；…~～\s]/g, '')
    .trim();
}

export function canWakeWish(text: string) {
  const raw = (text || '').trim();
  const folded = norm(raw);
  if (!raw) return false;
  if (folded === '许愿' || folded.toLowerCase() === 'wish') return true;
  return intentRe('wish.hint').test(raw) || intentRe('wish.hint').test(folded);
}
