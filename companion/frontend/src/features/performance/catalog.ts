/**
 * 文本 → 意图 / 单句选角。资产卡片见 lexicon.ts。
 */
import type { CamShotId, EmotionKey } from '../../engine/types';
import type { ExprKind, Intent } from './lexicon';
import { compatibleExpr } from './lexicon';

export type { ExprKind, Intent };
export { INTENTS } from './lexicon';

export function motionText(m: { name: string; label: string }) {
  return `${m.label} ${m.name}`;
}

/** 从用户话 + 回复正文推断表演意图（可多个，按优先级） */
export function inferIntents(user: string, assistant: string): Intent[] {
  const t = `${user}\n${assistant}`;
  const hit: Intent[] = [];
  const add = (i: Intent) => { if (!hit.includes(i)) hit.push(i); };

  if (/你好|您好|早上好|晚上好|嗨|哈喽|hello|hi\b|在吗|见面/i.test(t)) add('greet');
  if (/谢谢|感谢|好棒|厉害|优秀/.test(t)) add('bow');
  if (/比心|爱你|喜欢你|心动/.test(t)) add('heart');
  if (/亲|飞吻|mua/i.test(t)) add('kiss');
  if (/害羞|不好意思|脸红/.test(t)) add('shy');
  if (/俏皮|坏笑|逗你|调皮/.test(t)) add('tease');
  if (/难过|伤心|不开心|哭|委屈|安慰/.test(t)) add('comfort');
  if (/坐|坐下|休息一下/.test(t)) add('sit');
  if (/为什么|怎么|吗[？?]|呢[？?]|想一想|让我想/.test(t)) add('think');
  if (/点头|对的|嗯嗯|好的|可以/.test(assistant) && hit.length === 0) add('nod');
  if (/不是|不要|不行/.test(assistant)) add('shake');
  if (/卖萌|可爱吧|好看吗/.test(t)) add('cute');

  return hit;
}

export function inferEmotion(user: string, assistant: string): { key: EmotionKey; intensity: number } | null {
  const t = `${user}\n${assistant}`;
  if (/难过|伤心|哭|委屈|心疼/.test(t)) return { key: 'sad', intensity: 0.75 };
  if (/生气|讨厌|烦|气死/.test(t)) return { key: 'angry', intensity: 0.7 };
  if (/害羞|喜欢你|好看|漂亮|心动/.test(t)) return { key: 'happy', intensity: 0.7 };
  if (/你好|哈喽|嗨|哈哈|开心|太好了|喜欢/i.test(t)) return { key: 'happy', intensity: 0.8 };
  if (/累|困|放松|嗯嗯|听着呢/.test(t)) return { key: 'relaxed', intensity: 0.6 };
  return null;
}

/** 情绪 + 意图 → 该叠哪些表情种类（按强度取前几个） */
export function exprKindsFor(mood: EmotionKey, intensity: number, intents: Intent[]): ExprKind[] {
  const kinds: ExprKind[] = [];
  const add = (k: ExprKind) => { if (!kinds.includes(k)) kinds.push(k); };

  if (mood === 'happy') {
    add('smile');
    if (intensity >= 0.7) add('sparkle');
  } else if (mood === 'sad') {
    add('sadEye');
    if (intensity >= 0.7) add('tear');
  } else if (mood === 'angry') {
    add('angry');
  } else if (mood === 'relaxed') {
    add('relax');
    add('smile');
  }

  if (intents.includes('shy') || intents.includes('heart') || intents.includes('kiss')) add('blush');
  if (intents.includes('tease') || intents.includes('cute')) add('wink');
  if (intents.includes('heart')) add('heartEye');
  if (intents.includes('comfort')) add('sadEye');
  if (intents.includes('greet') && intensity >= 0.6) add('smile');

  return compatibleExpr(kinds);
}

/** 说话中允许的手势：幅度小、不换站位，才不会和口型打架 */
export const SPEAK_SAFE: Intent[] = [
  'nod', 'shake', 'think', 'look', 'talk', 'tease', 'shy', 'cute', 'greet',
];

export function isSpeakSafeMotion(m: { name: string; label: string }) {
  return !/走路|walk|坐下|坐姿|蹲|抱膝|伸懒腰|舞|dance|jump|跑/i.test(motionText(m));
}

export type LineCast = {
  kinds: ExprKind[];
  motion: Intent | null;
  intensity: number;
  mood?: EmotionKey;
  special?: boolean;
  cam?: CamShotId;
};

export type LineBeat = LineCast & { text: string };

export type TurnPlan = {
  narrative: boolean;
  baseKinds: ExprKind[];
  baseMood: EmotionKey;
  baseIntensity: number;
  beats: LineBeat[];
};

export function splitLines(text: string): string[] {
  return text
    .split(/(?<=[。！？!?；;～~\n])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function isNarrative(text: string, lines: string[]): boolean {
  if (lines.length >= 4 || text.replace(/\s/g, '').length >= 72) return true;
  return /笑话|故事|说是有个|有个书生|结果|然后呢|路过|没想到|谁知/.test(text);
}

const SPECIAL_LINE = /小声|悄悄话|飞吻|mua|比心|亲一个|亲亲/i;
const TWIST_LINE = /结果|没想到|居然|谁知|哪知|原来是|脸都黑/;

/** 单句选角：根据这一句的语气，而不是整段心情乱叠 */
export function analyzeLine(text: string, mood: EmotionKey): LineCast {
  const t = text.trim();
  const bang = /[！!]/.test(t);
  const kinds: ExprKind[] = [];
  const add = (k: ExprKind) => { if (!kinds.includes(k)) kinds.push(k); };
  let motion: Intent | null = null;
  let lineMood: EmotionKey | undefined;
  let intensity = bang ? 0.82 : 0.62;

  if (/哈哈|呵呵|嘿嘿|咯咯/.test(t)) {
    add('smile'); add('sparkle'); motion = 'cute'; lineMood = 'happy'; intensity = 0.88;
  } else if (/害羞|不好意思|脸红|讨厌啦|才不告诉/.test(t)) {
    add('blush'); add('wink'); motion = 'shy'; lineMood = 'happy'; intensity = 0.78;
  } else   if (/喜欢你|爱你|想你|心动|比心/.test(t)) {
    add('blush'); add('heartEye'); motion = 'heart'; lineMood = 'happy';
  } else if (/别难过|没事|我陪|心疼|委屈/.test(t)) {
    add('sadEye'); motion = 'comfort'; lineMood = 'sad'; intensity = 0.7;
  } else if (/唉|可惜|难过|伤心/.test(t)) {
    add('sadEye'); add('tear'); motion = 'think'; lineMood = 'sad';
  } else if (/不是|没有|不要|不行|才不是/.test(t)) {
    add('relax'); motion = 'shake'; intensity = 0.7;
  } else if (/嗯嗯|好的|对的|可以|当然|没问题|是啊/.test(t)) {
    add(mood === 'sad' ? 'sadEye' : 'smile'); motion = 'nod';
  } else if (/为什么|怎么|吗[？?]|呢[？?]|什么意思/.test(t)) {
    add('surprise'); motion = 'think'; intensity = 0.55;
  } else if (/诶|真的吗|不会吧|啊[？?]/.test(t)) {
    add('surprise'); motion = 'look'; intensity = 0.75;
  } else if (/哼|讨厌|生气/.test(t)) {
    add('angry'); motion = 'shake'; lineMood = 'angry';
  } else if (/你好|哈喽|嗨|早上好|晚上好/i.test(t)) {
    add('smile'); motion = 'greet'; lineMood = 'happy';
  } else if (/谢谢|感谢/.test(t)) {
    add('smile'); motion = 'bow';
  } else if (/卖萌|可爱吧|好看吗/.test(t)) {
    add('wink'); add('smile'); motion = 'cute'; lineMood = 'happy';
  } else {
    if (mood === 'happy') add('smile');
    else if (mood === 'sad') add('sadEye');
    else if (mood === 'angry') add('angry');
    else if (mood === 'relaxed') add('relax');
    motion = bang || t.length > 8 ? 'talk' : 'look';
    intensity = bang ? 0.7 : 0.58;
  }

  const special = SPECIAL_LINE.test(t);
  if (/小声|悄悄/.test(t)) {
    add('blush');
    return { kinds: compatibleExpr(kinds), motion: 'shy', intensity: 0.7, mood: lineMood, special: true, cam: 'close' };
  }
  if (/飞吻|mua|亲一个/.test(t)) {
    add('blush'); add('wink');
    return { kinds: compatibleExpr(kinds), motion: 'kiss', intensity: 0.8, mood: 'happy', special: true, cam: 'close' };
  }

  return { kinds: compatibleExpr(kinds), motion, intensity, mood: lineMood, special };
}

/** 整段回复编排：长叙述只铺一条主情绪，节拍句才加动作 */
export function planTurn(full: string, mood: EmotionKey): TurnPlan {
  const lines = splitLines(full);
  const narrative = isNarrative(full, lines);
  const guessed = inferEmotion('', full);
  const baseMood = guessed?.key ?? (narrative ? 'happy' : mood);
  const baseIntensity = narrative ? 0.55 : (guessed?.intensity ?? 0.65);
  const baseKinds = exprKindsFor(baseMood, baseIntensity, inferIntents('', full)).slice(0, 1);
  const beats: LineBeat[] = [];

  for (let i = 0; i < lines.length; i++) {
    const text = lines[i];
    const last = i === lines.length - 1;
    const twist = TWIST_LINE.test(text);
    const cast = analyzeLine(text, baseMood);

    if (narrative && !cast.special && !twist && !last) {
      beats.push({
        text,
        kinds: cast.kinds.slice(0, 1),
        motion: cast.motion || 'talk',
        intensity: baseIntensity,
        mood: baseMood,
      });
      continue;
    }

    if (narrative && (twist || last)) {
      if (last && i > 0 && TWIST_LINE.test(lines[i - 1]) && !/哈哈|嘿嘿/.test(text)) {
        beats.push({ text, kinds: ['smile'], motion: null, intensity: 0.72, mood: 'happy' });
        continue;
      }
      const laugh = /哈哈|嘿嘿|好玩|笑死/.test(text);
      beats.push({
        text,
        kinds: compatibleExpr(laugh ? ['smile', 'sparkle'] : ['surprise', 'smile']),
        motion: laugh ? 'cute' : (cast.motion || 'talk'),
        intensity: 0.86,
        mood: 'happy',
        special: true,
      });
      continue;
    }

    beats.push({
      text,
      kinds: cast.kinds,
      motion: (narrative && !cast.special) ? null : cast.motion,
      intensity: cast.intensity,
      mood: cast.mood,
      special: cast.special,
      cam: cast.cam,
    });
  }

  return { narrative, baseKinds, baseMood, baseIntensity, beats };
}

/** 意图 → 优先用哪个动作桶（没有则回退 nod / cute / talk） */
export function motionIntentOrder(intents: Intent[], mood: EmotionKey): Intent[] {
  const order = [...intents];
  if (mood === 'sad' && !order.includes('comfort') && !order.includes('sit')) order.push('sit', 'think');
  if (mood === 'happy' && !order.length) order.push('cute', 'talk');
  if (mood === 'relaxed' && !order.length) order.push('talk', 'stretch');
  if (!order.includes('nod')) order.push('nod');
  if (!order.includes('talk')) order.push('talk');
  if (!order.includes('cute')) order.push('cute');
  return order;
}
