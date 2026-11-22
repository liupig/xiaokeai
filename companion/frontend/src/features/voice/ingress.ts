import { asksForDance, stopsCurrentDance } from '../performance/dancePick';
import { canWakeTavern } from '../tavern/intent';
import { isTarotVoiceCommand } from '../tarot/intent';
import { deskActivity } from '../desk/activity';
import { tarotUi } from '../tarot/session';
import { intentRe, replyLang } from '../../i18n';

export type IngressAct = 'drop' | 'hold' | 'cut';
export type IngressBusy = 'dance' | 'speech' | 'generate';

function cutRe() { return intentRe('ingress.cut'); }
function askRe() { return intentRe('ingress.ask'); }
function dropRe() { return intentRe('ingress.drop'); }
function backRe() { return intentRe('ingress.backchannel'); }
function holdTailRe() { return intentRe('ingress.hold_tail'); }
function holdHeadRe() { return intentRe('ingress.hold_head'); }

function norm(text: string) {
  return (text || '').replace(/\s+/g, '').trim();
}

/** 本地能定的立刻定。拿不准返回 null，交给模型。 */
export function localIngress(text: string, busy: IngressBusy): IngressAct | null {
  const t = norm(text);
  if (!t) return 'drop';
  if (canWakeTavern(text)) return 'cut';
  const act = deskActivity();
  if (act === 'tarot' && isTarotVoiceCommand(t, tarotUi.phase || '')) return 'cut';
  if (act === 'dance') {
    if (stopsCurrentDance(text) || isExplicitSpeechStop(text) || askRe().test(t) || asksForDance(text)) return 'cut';
    if (backRe().test(t) || dropRe().test(t)
      || /^(?:跳得?真好|跳的真好|跳得?好棒|好棒|太棒了|好看|跳得真不错|继续跳|接着跳)[呀啊哦。！!]*$/i.test(t)) return 'drop';
    if (t.length <= 2) return 'drop';
    return 'cut';
  }
  if (cutRe().test(t) || askRe().test(t)) return 'cut';
  const latin = !/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(t);
  if (latin && t.length <= 16 && replyLang() === 'zh-CN') return 'drop';
  if (backRe().test(t) || dropRe().test(t)) return 'drop';
  if (t.length <= 2) return busy === 'dance' ? 'drop' : 'hold';
  if ((holdTailRe().test(t) || holdHeadRe().test(t)) && t.length <= 8) return 'hold';
  if (busy === 'speech' || busy === 'generate') return 'cut';
  return null;
}

/** 麦克风 interim：只有明确制止/提问才提前切开，夸奖等终稿。 */
export function peekIngressCut(text: string): boolean {
  const t = norm(text);
  if (canWakeTavern(text)) return true;
  if (t.length < 2) return false;
  if (deskActivity() === 'tarot' && isTarotVoiceCommand(t, tarotUi.phase || '')) return true;
  return cutRe().test(t) || askRe().test(t);
}

export function isExplicitSpeechStop(text: string) {
  return /^(?:停|停下|停一下|别说了|先别说|不要说了|暂停|stop(?:talking)?|pause|やめて|待って|그만|стоп)[。！？!?]*$/i.test(norm(text));
}

export function fallbackIngress(busy: IngressBusy): IngressAct {
  if (busy === 'dance') return 'drop';
  return 'cut';
}

export function mergeHold(prev: string, next: string) {
  const a = (prev || '').trim();
  const b = (next || '').trim();
  if (!a) return b;
  if (!b) return a;
  if (b.startsWith(a)) return b;
  if (a.startsWith(b)) return a;
  const glue = /[，。！？、,.!?]$/.test(a) ? '' : '，';
  return `${a}${glue}${b}`;
}
