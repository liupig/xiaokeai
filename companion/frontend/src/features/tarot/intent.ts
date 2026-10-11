/** 口头进 / 出 / 仪式。正则在 locales 的 intents.json，和后端同一份。 */

import { intentRe } from '../../i18n';

export function normTarotText(text: string) {
  return (text || '')
    .replace(/[「」『』“”"'']/g, '')
    .replace(/[。！？、,.!?;；…~～\s]/g, '')
    .trim();
}

export function maybeTarotPhrase(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  return intentRe('tarot.hint').test(t) || intentRe('tarot.hint').test(n)
    || intentRe('tarot.exit').test(t) || intentRe('tarot.exit').test(n);
}

/** 没在看牌时，只有明确「看牌」才能开局。换一个 / 再来一次不算。 */
export function canWakeTarot(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  return intentRe('tarot.hint').test(t) || intentRe('tarot.hint').test(n);
}

export function isTarotRitualAllow(text: string, phase = '') {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  if (intentRe('tarot.ritual').test(t) || intentRe('tarot.ritual').test(n)) return true;
  if (intentRe('tarot.exit').test(t) || intentRe('tarot.exit').test(n)) return true;
  if ((phase === 'shuffle' || phase === 'cut') && (intentRe('tarot.soft_ok').test(n) || intentRe('tarot.stop').test(t))) return true;
  if ((phase === 'linger' || phase === 'synth') && (intentRe('tarot.soft_ok').test(n) || intentRe('tarot.thanks').test(t) || intentRe('tarot.linger').test(n))) return true;
  return false;
}

export function isTarotCut(text: string, phase = '') {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (intentRe('tarot.cut').test(t) || intentRe('tarot.cut').test(n) || n === '切' || n === 'cut') return true;
  if (phase === 'shuffle' || phase === 'cut') {
    if (intentRe('tarot.soft_ok').test(n) || intentRe('tarot.stop').test(t) || n === '停' || n === 'stop') return true;
  }
  return false;
}

export function isTarotRedeal(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  return intentRe('tarot.redeal').test(t) || intentRe('tarot.redeal').test(n);
}

/** 看牌口令：不能当回声丢掉，也不能在她说话时被 hold。 */
export function isTarotVoiceCommand(text: string, phase = '') {
  const inGame = !!phase && phase !== 'off' && phase !== 'leaving';
  if (!inGame) return canWakeTarot(text);
  if (phase === 'intent') return true;
  if (isTarotCut(text, phase) || isTarotExit(text, phase) || isTarotRedeal(text)) return true;
  return isTarotRitualAllow(text, phase);
}

export function isTarotExit(text: string, phase = '') {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  if (t === '算了' || t === '算啦' || t === '算了吧' || n === '算了' || n === '算啦' || n === '算了吧') return false;
  if (intentRe('tarot.exit').test(t) || intentRe('tarot.exit').test(n)) return true;
  if (phase === 'shuffle' || phase === 'cut') {
    if (isTarotCut(t, phase)) return false;
  }
  if (phase === 'linger' || phase === 'synth') {
    if (intentRe('tarot.soft_ok').test(n) || intentRe('tarot.thanks').test(t)
      || intentRe('tarot.stop').test(t) || intentRe('tarot.linger').test(n)) {
      return true;
    }
  }
  if (phase && phase !== 'shuffle' && phase !== 'cut' && intentRe('tarot.stop').test(t) && /不看|收|结束|关掉/.test(n)) {
    return true;
  }
  return false;
}
