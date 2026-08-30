/** 用户插话分流：正在跳/正在说时，新文本是附和、先记下，还是立刻开新一轮。 */

export type IngressAct = 'drop' | 'hold' | 'cut';
export type IngressBusy = 'dance' | 'speech' | 'generate';

const CUT_RE = /停(下|一下|止)?|别说了|别跳|不要跳|别唱|闭嘴|换(一)?支|换(一)?个|换个故事|跳别的|再来(一)?(支|首|个)|过来|听我说|坐下|站起来|往左|往右/;
const ASK_RE = /[？?]|为什么|怎么(办|了|样)?|什么意思|叫什么|哪支|哪首|几点/;
const DROP_RE = /真好|好看|好漂亮|好美|好帅|好厉害|太棒|太美|爱了|牛逼?|666|跳[得的]?真好|跳[得的]?好看|舞跳得好|不错|加油/;
const BACKCHANNEL_RE = /^(嗯+|啊+|哦+|噢+|额+|唔+|哈+|嘿+|哇+|好|对|是|可以|行|继续|是的|对对)[啊呀哦噢哈嗯！!。.~～…]*$/;
const HOLD_TAIL_RE = /(那个|就是|然后|还有|对了|我想想|就是说)$/;
const HOLD_HEAD_RE = /^(那个|就是|然后|还有|对了|我想)/;

function norm(text: string) {
  return (text || '').replace(/\s+/g, '').trim();
}

/** 本地能定的立刻定。拿不准返回 null，交给模型。 */
export function localIngress(text: string, busy: IngressBusy): IngressAct | null {
  const t = norm(text);
  if (!t) return 'drop';
  if (t.length <= 16 && !/[\u4e00-\u9fff]/.test(t)) return 'drop';
  if (CUT_RE.test(t) || ASK_RE.test(t)) return 'cut';
  if (BACKCHANNEL_RE.test(t) || DROP_RE.test(t)) return 'drop';
  if (t.length <= 2) return busy === 'dance' ? 'drop' : 'hold';
  if ((HOLD_TAIL_RE.test(t) || HOLD_HEAD_RE.test(t)) && t.length <= 8) return 'hold';
  if (busy === 'speech' || busy === 'generate') return 'cut';
  return null;
}

/** 麦克风 interim：只有明确制止/提问才提前切开，夸奖等终稿。 */
export function peekIngressCut(text: string): boolean {
  const t = norm(text);
  if (t.length < 2) return false;
  return CUT_RE.test(t) || ASK_RE.test(t);
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
