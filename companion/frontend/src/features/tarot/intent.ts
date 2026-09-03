/** 口头进 / 出 / 仪式，和后端 modules/tarot/service 对齐。默认不 import 3D。 */

export function normTarotText(text: string) {
  return (text || '')
    .replace(/[「」『』“”"'']/g, '')
    .replace(/[。！？、,.!?;；…~～\s]/g, '')
    .trim();
}

/** 游戏前：能把牌局唤起来。 */
export const TAROT_HINT_RE =
  /抽一张|抽三张|抽张牌|抽个牌|来一张|来三张|日抽|今日牌|抽牌|看看牌|帮我抽|给我抽|看看这张牌|三张阵|三张牌|三张塔罗|时间线|过去.{0,8}未来|现状.{0,8}建议|建议阵|行动阵|行动三张|身心|心身体|是否一张|抽一张看是否|二选一|两个选择|选A还是|左右为难|两条路|关系阵|感情阵|事业阵|工作阵|职场|凯尔特|十字阵|大十字|十张|深度看|塔罗|看个牌|来看牌|算一卦|玩塔罗|看牌|帮我看|给我看|来局牌|玩牌/;

/** 游戏中：切 / 抽 / 翻 / 问 / 换，不被当成闲聊拦下。 */
const TAROT_RITUAL_RE =
  /切牌|我切|切一下|切了|切吧|好了切|可以切|给我切|帮我切|你来抽|你抽|帮我选|给我选|随便抽|你定|你帮我抽|你挑|抽吧|选牌|再抽|换牌|重新抽|再来一轮|再来一局|换一张|不要这张|再翻一张|补一张|clarifier|看清楚点|综合|总结|串起来|收线|翻开|翻转|翻牌|翻面|翻这|翻第|翻一下|打开|正面|什么意思|怎么解|怎么看|解释|这张|那张|左边|右边|中间|最左|最右|当中|过去|现在|未来|第[一二三四五六七八九十0-9]+[张个种]?|好了|好啦|可以了|行了|停下|停一下|随便|都可以|都行|随机|你看着办|日抽|是否一张|时间线|行动三张|身心|二选一|关系五张|关系五章|四页五章|四页五张|事业五张|事业五章|凯尔特|十字阵/;

const TAROT_REDEAL_RE =
  /再抽|换牌|重新抽|再来一轮|再来一局|换三张|换一张|不要这张|重新来/;

/** 明确收摊。 */
export const TAROT_EXIT_RE =
  /收起来|不看了|收牌|把牌收|牌收起来|不看牌了|看完了|不玩了|不完了|不玩啦|关掉牌|可以收了|好了收|收了吧|收吧|收掉|收摊|结束看牌|不想看了|关掉|退出|不想玩|不玩游戏|结束游戏|退出游戏/;

const TAROT_STOP_RE = /停下|别说了|不要讲了|停一下/;
const TAROT_SOFT_OK_RE = /^(好了|好了哦|好啦|可以了|行了|行啦|嗯好|好的|好)$/;
const TAROT_THANKS_RE = /谢谢|多谢|感谢/;
const TAROT_CUT_RE = /切牌|我切|切一下|切了|好了切|可以切|切吧|给我切|帮我切/;
const TAROT_LINGER_DONE_RE = /够了|明白了|知道了|了解了|嗯好的/;

export function maybeTarotPhrase(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  return TAROT_HINT_RE.test(t) || TAROT_HINT_RE.test(n)
    || TAROT_EXIT_RE.test(t) || TAROT_EXIT_RE.test(n);
}

/** 没在看牌时，只有明确「看牌」才能开局。换一个 / 再来一次不算。 */
export function canWakeTarot(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  return TAROT_HINT_RE.test(t) || TAROT_HINT_RE.test(n);
}

export function isTarotRitualAllow(text: string, phase = '') {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (!t) return false;
  if (TAROT_RITUAL_RE.test(t) || TAROT_RITUAL_RE.test(n)) return true;
  if (TAROT_EXIT_RE.test(t) || TAROT_EXIT_RE.test(n)) return true;
  if ((phase === 'shuffle' || phase === 'cut') && (TAROT_SOFT_OK_RE.test(n) || TAROT_STOP_RE.test(t))) return true;
  if ((phase === 'linger' || phase === 'synth') && (TAROT_SOFT_OK_RE.test(n) || TAROT_THANKS_RE.test(t) || TAROT_LINGER_DONE_RE.test(n))) return true;
  return false;
}

export function isTarotCut(text: string, phase = '') {
  const t = (text || '').trim();
  const n = normTarotText(t);
  if (TAROT_CUT_RE.test(t) || TAROT_CUT_RE.test(n) || n === '切') return true;
  if (phase === 'shuffle' || phase === 'cut') {
    if (TAROT_SOFT_OK_RE.test(n) || TAROT_STOP_RE.test(t) || n === '停') return true;
  }
  return false;
}

export function isTarotRedeal(text: string) {
  const t = (text || '').trim();
  const n = normTarotText(t);
  return TAROT_REDEAL_RE.test(t) || TAROT_REDEAL_RE.test(n);
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
  if (TAROT_EXIT_RE.test(t) || TAROT_EXIT_RE.test(n)) return true;
  if (phase === 'shuffle' || phase === 'cut') {
    if (isTarotCut(t, phase)) return false;
  }
  if (phase === 'linger' || phase === 'synth') {
    if (TAROT_SOFT_OK_RE.test(n) || TAROT_THANKS_RE.test(t) || TAROT_STOP_RE.test(t) || TAROT_LINGER_DONE_RE.test(n)) {
      return true;
    }
  }
  if (phase && phase !== 'shuffle' && phase !== 'cut' && TAROT_STOP_RE.test(t) && /不看|收|结束|关掉/.test(n)) {
    return true;
  }
  return false;
}
