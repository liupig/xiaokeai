/** 口头许愿。正则在 locales 的 intents.json。 */

import { intentRe } from '../../i18n';

function norm(text: string) {
  return (text || '')
    .replace(/[「」『』“”"'']/g, '')
    .replace(/[。！？、,.!?;；…~～\s]/g, '')
    .trim();
}

const AGREE = /^(?:可以|可以啊|可以呀|好|好啊|好呀|好的|好吧|行|行啊|行吧|来|来吧|来呀|要|玩|玩吧|那就玩|就这个|嗯|嗯嗯|ok|okay|yes|sure)$/i;

function offeredWish(prior: string) {
  const text = prior || '';
  if (/落下|枚金币|coins fell|コインが落ち|코인이 떨어/.test(text)) return false;
  return /许愿池|许个愿|许愿|wishing well|make a wish|願いの池|소원 연못/i.test(text);
}

export function canWakeWish(text: string, prior = '') {
  const raw = (text || '').trim();
  const folded = norm(raw);
  if (!raw) return false;
  if (folded === '许愿' || folded.toLowerCase() === 'wish') return true;
  if (intentRe('wish.hint').test(raw) || intentRe('wish.hint').test(folded)) return true;
  return offeredWish(prior) && AGREE.test(folded);
}
