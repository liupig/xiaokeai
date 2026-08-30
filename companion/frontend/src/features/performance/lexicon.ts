/**
 * 表演总表：每个情绪 / 表情种类 / 动作卡片的含义、触发条件、切换规则。
 * 选角器只认这张表，不再拿文件名做关键词碰运气。
 */
import type { AssetItem } from '../../api/client';
import type { EmotionKey } from '../../engine/types';
import { parseMotionCat } from '../assets/motionMeta';

export type Intent =
  | 'greet' | 'nod' | 'shake' | 'think' | 'shy' | 'heart'
  | 'kiss' | 'bow' | 'sit' | 'talk' | 'stretch' | 'cute'
  | 'look' | 'clap' | 'comfort' | 'tease' | 'idle' | 'dance' | 'walk';

export type ExprKind =
  | 'blush' | 'wink' | 'sparkle' | 'smile' | 'sadEye' | 'tear'
  | 'angry' | 'relax' | 'surprise' | 'heartEye';

export type SwitchRule = 'cut' | 'blend' | 'hold';
export type Stance = 'stand' | 'sit' | 'locomote' | 'dance';
export type Grade = 'S' | 'A' | 'B';
/** 景别：特写 / 1/4 / 1/2 / 3/4 / 全身 / 远景 */
export type Distance = 'ecu' | 'bust' | 'half' | 'threeQ' | 'full' | 'long';
export type MotionScale = Distance;

export const DIST_RANK: Record<Distance, number> = {
  ecu: 0, bust: 1, half: 2, threeQ: 3, full: 4, long: 5,
};

export const DIST_MAX: Record<Distance, Distance> = {
  ecu: 'bust',
  bust: 'threeQ',
  half: 'full',
  threeQ: 'full',
  full: 'long',
  long: 'long',
};

export interface EmotionCard {
  key: EmotionKey;
  meaning: string;
  when: string;
  expr: ExprKind[];
  motion: Intent[];
}

export interface ExprCard {
  kind: ExprKind;
  meaning: string;
  when: string;
  moods: EmotionKey[];
  exclusive: ExprKind[];
  speakOk: boolean;
  nameRe: RegExp;
}

export interface MotionCard {
  name: string;
  label: string;
  meaning: string;
  tags: Intent[];
  when: string;
  speakSafe: boolean;
  chainable: boolean;
  switchRule: SwitchRule;
  stance: Stance;
  loop: boolean;
  grade: Grade;
  minDist: Distance;
  maxDist: Distance;
  /** @deprecated 等同 minDist，给旧调用留着 */
  scale: MotionScale;
}

export const EMOTIONS: EmotionCard[] = [
  { key: 'neutral', meaning: '平静、没有明显情绪', when: '默认 / 情绪衰减完毕', expr: [], motion: ['idle', 'talk'] },
  { key: 'happy', meaning: '开心、轻快、亲近', when: '打招呼、夸奖、玩笑、喜欢', expr: ['smile', 'sparkle', 'wink'], motion: ['greet', 'cute', 'talk', 'heart'] },
  { key: 'sad', meaning: '难过、心疼、安慰', when: '伤心、抱歉、安慰对方', expr: ['sadEye', 'tear'], motion: ['sit', 'think', 'nod'] },
  { key: 'angry', meaning: '嗔怪、不满、娇嗔', when: '被逗急、否定、哼', expr: ['angry'], motion: ['shake', 'look'] },
  { key: 'relaxed', meaning: '放松、听着、慵懒', when: '闲聊、嗯嗯、听你说', expr: ['relax', 'smile'], motion: ['talk', 'idle', 'look'] },
];

export const EXPRESSIONS: ExprCard[] = [
  { kind: 'smile', meaning: '微笑、嘴角上扬', when: '开心、打招呼、感谢、肯定', moods: ['happy', 'relaxed'], exclusive: ['angry', 'tear'], speakOk: true, nameRe: /にっこり|にこり|笑い|微笑|笑/ },
  { kind: 'sparkle', meaning: '星星眼、亮晶晶', when: '哈哈、太好了、惊喜的开心', moods: ['happy'], exclusive: ['angry', 'sadEye', 'tear'], speakOk: true, nameRe: /星目|キラ|sparkle|星/ },
  { kind: 'wink', meaning: '眨单眼、俏皮', when: '调侃、卖萌、坏笑', moods: ['happy'], exclusive: ['angry', 'tear'], speakOk: true, nameRe: /ウィンク|wink|眨/ },
  { kind: 'blush', meaning: '脸红、害羞', when: '被夸、喜欢、讨厌啦', moods: ['happy', 'relaxed'], exclusive: ['angry'], speakOk: true, nameRe: /照れ|頬|赤面|てれ|blush/ },
  { kind: 'heartEye', meaning: '爱心眼', when: '比心、爱你、心动', moods: ['happy'], exclusive: ['angry', 'sadEye'], speakOk: true, nameRe: /ハート|爱心目|heart/i },
  { kind: 'sadEye', meaning: '柔和的难过眼神', when: '安慰、唉、心疼', moods: ['sad'], exclusive: ['sparkle', 'wink', 'angry'], speakOk: true, nameRe: /悲しい|困る|うるうる|じと|悲伤/ },
  { kind: 'tear', meaning: '含泪', when: '很伤心、快哭了', moods: ['sad'], exclusive: ['smile', 'sparkle', 'wink', 'angry'], speakOk: true, nameRe: /涙|泪|なみだ|cry/ },
  { kind: 'angry', meaning: '皱眉、嗔怒', when: '哼、讨厌、生气', moods: ['angry'], exclusive: ['smile', 'sparkle', 'wink', 'blush'], speakOk: true, nameRe: /怒り|キリッ|むっ|怒/ },
  { kind: 'relax', meaning: '软软的放松脸', when: '闲聊、听着、否定但不凶', moods: ['relaxed', 'neutral'], exclusive: ['angry', 'tear'], speakOk: true, nameRe: /なごみ|ほほえ|リラックス|穏やか/ },
  { kind: 'surprise', meaning: '惊讶、眼睛睁大', when: '真的吗、诶、问句', moods: ['happy', 'relaxed', 'neutral'], exclusive: ['angry'], speakOk: true, nameRe: /びっくり|驚|あせ|汗/ },
];

const SKIP_MORPH = /^(あ|い|う|え|お|ん|ワ|まばたき|瞬き|瞳[LR]|目[0-9])/i;

export const INTENTS: Intent[] = [
  'greet', 'nod', 'shake', 'think', 'shy', 'heart',
  'kiss', 'bow', 'sit', 'talk', 'stretch', 'cute',
  'look', 'clap', 'comfort', 'tease', 'idle', 'dance', 'walk',
];

function textOf(m: { name: string; label: string }) {
  return `${m.label} ${m.name}`;
}

/** 把一条动作资产编成卡片：含义 + 何时用 + 最小/最大景别 */
export function classifyMotion(m: AssetItem): MotionCard {
  const name = m.name;
  const label = m.label || name;
  const t = textOf(m).replace(/^\[(?:待机|打招呼|互动|舞蹈)\]\s*/, '');
  let fromVpd = false;
  try { fromVpd = !!JSON.parse(m.meta || '{}').from_vpd; } catch { /* */ }
  const cat = parseMotionCat(m);

  const gradeOf = (opts: {
    speakSafe: boolean;
    chainable: boolean;
    stance: Stance;
    tags: Intent[];
  }): Grade => {
    if (opts.stance === 'dance') return 'S';
    if (fromVpd) return 'B';
    if (opts.speakSafe && opts.chainable) return 'S';
    if (opts.tags.some((x) => x === 'greet' || x === 'bow' || x === 'idle' || x === 'cute' || x === 'think' || x === 'shy')) return 'A';
    return 'B';
  };

  const base = (over: Partial<MotionCard>): MotionCard => {
    const tags = over.tags || [];
    const speakSafe = over.speakSafe ?? false;
    const chainable = over.chainable ?? false;
    const stance = over.stance ?? 'stand';
    const minDist: Distance = over.minDist
      ?? (stance === 'dance' || stance === 'locomote' ? 'full'
        : stance === 'sit' ? 'full'
          : 'half');
    const maxDist: Distance = over.maxDist ?? DIST_MAX[minDist];
    return {
      name, label,
      meaning: over.meaning || label,
      tags,
      when: over.when || '',
      speakSafe,
      chainable,
      switchRule: over.switchRule ?? 'cut',
      stance,
      loop: over.loop ?? false,
      minDist,
      maxDist,
      scale: minDist,
      grade: over.grade ?? gradeOf({ speakSafe, chainable, stance, tags }),
    };
  };

  if (/走路|walk\.vmd/i.test(t) && !/挥手|wave/i.test(t)) {
    return base({
      meaning: '走路循环', tags: ['walk'], when: '走位、展示走路',
      stance: 'locomote', minDist: 'full', maxDist: 'long', switchRule: 'cut',
    });
  }
  if (/Walk cutely|一边走.*挥手/i.test(t)) {
    return base({
      meaning: '边走边挥手打招呼', tags: ['greet', 'walk'], when: '见面打招呼（会换站位）',
      stance: 'locomote', minDist: 'full', maxDist: 'long', switchRule: 'cut',
    });
  }
  if (/摆手/.test(t) && !/舞蹈/.test(t)) {
    return base({
      meaning: '摆手打招呼', tags: ['greet', 'talk'], when: '嗨、在呢、唤人',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'full', switchRule: 'blend',
    });
  }
  if (/挥手|打招呼|挨拶|偶像在跟你打招呼/.test(t)) {
    return base({
      meaning: fromVpd ? '打招呼定格' : '挥手打招呼',
      tags: ['greet'],
      when: '你好、嗨、见面',
      speakSafe: !fromVpd, chainable: !fromVpd,
      minDist: 'half', maxDist: 'full',
      switchRule: fromVpd ? 'hold' : 'blend',
    });
  }
  if (/举手/.test(t)) {
    return base({
      meaning: '举手示意', tags: ['talk', 'greet'], when: '唤人、回答、打招呼',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'full', switchRule: 'blend',
    });
  }
  if (/盘腿|坐姿|坐下/.test(t)) {
    return base({
      meaning: /望向窗外|思考|眺望/.test(t) ? '坐着眺望思考' : '坐下 / 坐姿',
      tags: ['sit', /思考|眺望|凝视/.test(t) ? 'think' : 'look'],
      when: '休息、出神、一个人待着',
      stance: 'sit', minDist: 'full', maxDist: 'long', switchRule: 'cut',
    });
  }
  if (/凝视|眺望|望向窗外|偷看|看向/.test(t)) {
    return base({
      meaning: /偷看/.test(t) ? '偷看' : '凝视 / 眺望',
      tags: ['look', 'idle'],
      when: '出神、看向别处、一个人待着',
      speakSafe: true, chainable: true,
      minDist: 'bust', maxDist: 'full', switchRule: 'blend', grade: 'S',
    });
  }
  if (/伸懒腰|伸展|stretch/i.test(t)) {
    return base({
      meaning: '伸懒腰',
      tags: ['stretch', 'idle'],
      when: '闲着、刚说完、一个人待着',
      speakSafe: false, minDist: 'threeQ', maxDist: 'full', switchRule: 'blend', grade: 'A',
    });
  }
  if (/鞠躬|お辞儀/.test(t)) {
    return base({
      meaning: /yeah|比/.test(t) ? '比耶后鞠躬' : /旋转/.test(t) ? '旋转鞠躬' : '鞠躬致谢',
      tags: ['bow'], when: '谢谢、再见、致意',
      minDist: 'threeQ', maxDist: 'full', switchRule: 'cut',
    });
  }
  if (/比心|ハート|手势舞比心|万有引力/.test(t)) {
    return base({
      meaning: fromVpd ? '比心定格' : '比心手势',
      tags: ['heart', 'cute'],
      when: '喜欢、爱你、比心',
      speakSafe: false,
      minDist: 'half', maxDist: 'full',
      switchRule: fromVpd ? 'hold' : 'cut',
    });
  }
  if (/叉腰|插腰/.test(t)) {
    return base({
      meaning: '叉腰俏皮站姿', tags: ['cute', 'tease'], when: '卖萌、逞强、开心',
      minDist: 'half', maxDist: 'full',
      switchRule: fromVpd ? 'hold' : 'blend', speakSafe: false, grade: fromVpd ? 'B' : 'A',
    });
  }
  if (/拥抱/.test(t)) {
    return base({
      meaning: '拥抱', tags: ['comfort', 'kiss'], when: '不舍、安慰、告别',
      minDist: 'threeQ', maxDist: 'full', switchRule: 'cut',
    });
  }
  if (/思考|托腮|抱胸/.test(t)) {
    return base({
      meaning: /抱胸/.test(t) ? '抱胸思考' : '思考',
      tags: ['think'], when: '问句、让我想想',
      speakSafe: true, chainable: true, minDist: 'bust', maxDist: 'threeQ', switchRule: 'blend', grade: 'S',
    });
  }
  if (/害羞|低头害羞|表白害羞/.test(t)) {
    return base({
      meaning: /摇/.test(t) ? '害羞摇' : /舞/.test(t) ? '害羞表白' : '害羞',
      tags: ['shy', 'cute'], when: '被夸、不好意思、心动',
      speakSafe: !/舞/.test(t), chainable: !/舞/.test(t),
      minDist: /舞/.test(t) ? 'threeQ' : 'bust', maxDist: 'full',
      switchRule: 'blend', grade: 'A',
    });
  }
  if (/点头|摇头/.test(t)) {
    return base({
      meaning: '点头 / 摇头', tags: ['nod', 'shake'], when: '肯定、否定',
      speakSafe: true, chainable: true, minDist: 'ecu', maxDist: 'half', switchRule: 'blend', grade: 'S',
    });
  }
  if (/拒绝|格挡|后仰拒绝/.test(t)) {
    return base({
      meaning: '拒绝 / 格挡', tags: ['shake'], when: '不要、才不是',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'A',
    });
  }
  if (/摊手|叽里呱啦/.test(t)) {
    return base({
      meaning: /摊手/.test(t) ? '摊手说话' : '说话比划',
      tags: ['talk'], when: '解释、聊天、无奈',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'S',
    });
  }
  if (/捂胸口|捂胸/.test(t)) {
    return base({
      meaning: '手捂胸口', tags: ['shy', 'heart'], when: '心动、被说中',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'threeQ', switchRule: 'blend', grade: 'A',
    });
  }
  if (/郁闷|低头郁闷/.test(t)) {
    return base({
      meaning: '低头郁闷', tags: ['comfort', 'think'], when: '唉、难过',
      speakSafe: true, chainable: true, minDist: 'bust', maxDist: 'threeQ', switchRule: 'blend', grade: 'A',
    });
  }
  if (/握拳|前倾|惊/.test(t) && /原神/.test(t)) {
    return base({
      meaning: '吃惊前倾', tags: ['look', 'talk'], when: '诶、真的吗',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'threeQ', switchRule: 'blend', grade: 'A',
    });
  }
  if (/比耶|yeah/i.test(t) && !/鞠躬/.test(t)) {
    return base({
      meaning: '比耶', tags: ['cute', 'tease'], when: '开心、卖萌',
      speakSafe: false, minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'A',
    });
  }
  if (/眨眼/.test(t)) {
    return base({
      meaning: '眨眼卖萌', tags: ['look', 'cute'], when: '俏皮、调侃',
      speakSafe: true, chainable: true, minDist: 'ecu', maxDist: 'bust', switchRule: 'blend', grade: 'S',
    });
  }
  if (/轻拍/.test(t)) {
    return base({
      meaning: '轻拍', tags: ['tease', 'talk'], when: '调侃、提醒',
      speakSafe: true, chainable: true, minDist: 'half', maxDist: 'threeQ', switchRule: 'blend', grade: 'A',
    });
  }
  if (/转身/.test(t)) {
    return base({
      meaning: '转身看', tags: ['look'], when: '看那边、回神',
      speakSafe: false, minDist: 'threeQ', maxDist: 'full', switchRule: 'cut', grade: 'B',
    });
  }
  if (/病娇/.test(t)) {
    return base({
      meaning: '病娇俏皮', tags: ['tease', 'cute'], when: '调侃、撒娇',
      minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'A',
    });
  }
  if (/多幸运|手势舞/.test(t)) {
    return base({
      meaning: '手势舞', tags: ['cute', 'heart'], when: '开心、卖萌、比心',
      minDist: 'half', maxDist: 'full', switchRule: 'cut', grade: 'A',
    });
  }
  if (/丘丘摇/.test(t)) {
    return base({
      meaning: '轻快待机摇摆', tags: ['idle', 'cute'], when: '开心闲时',
      loop: true, minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'S',
    });
  }
  if (/云堇待机|待机动作/.test(t)) {
    return base({
      meaning: '角色待机律动', tags: ['idle'], when: '闲时保持活着',
      loop: true, minDist: 'half', maxDist: 'full', switchRule: 'blend', grade: 'S',
    });
  }
  if (/站姿|姿势 Pose|艾尔海森姿势/.test(t)) {
    return base({
      meaning: /可爱/.test(t) ? '可爱站姿' : /领导/.test(t) ? '端正站姿' : '自然站姿',
      tags: ['idle'], when: '闲时换一个站法',
      minDist: 'threeQ', maxDist: 'full', switchRule: 'hold', grade: fromVpd ? 'B' : 'A',
    });
  }

  if (cat === 'dance') {
    const named = label.replace(/^\[舞蹈\]\s*/, '') || name;
    return base({
      meaning: `完整舞蹈：${named}`,
      tags: ['dance'],
      when: '仅当用户明确要求跳舞 / 点名这支舞',
      stance: 'dance', loop: true, minDist: 'full', maxDist: 'long', switchRule: 'cut', grade: 'S',
    });
  }
  if (cat === 'greet') {
    return base({
      meaning: '打招呼动作', tags: ['greet'], when: '见面',
      speakSafe: !fromVpd, chainable: !fromVpd,
      minDist: 'half', maxDist: 'full',
      switchRule: fromVpd ? 'hold' : 'blend',
    });
  }
  if (cat === 'idle') {
    return base({
      meaning: '待机动作', tags: ['idle'], when: '闲时',
      loop: !fromVpd, minDist: 'half', maxDist: 'full',
      switchRule: fromVpd ? 'hold' : 'blend',
    });
  }
  return base({
    meaning: label.replace(/^\[互动\]\s*/, ''),
    tags: ['talk', 'cute'],
    when: '聊天点缀',
    speakSafe: !fromVpd, chainable: !fromVpd,
    minDist: 'half', maxDist: 'full',
    switchRule: fromVpd ? 'hold' : 'blend',
    grade: fromVpd ? 'B' : 'A',
  });
}

export function classifyMorph(name: string): ExprCard | null {
  if (SKIP_MORPH.test(name)) return null;
  return EXPRESSIONS.find((e) => e.nameRe.test(name)) ?? null;
}

export function buildMotionCards(motions: AssetItem[]): MotionCard[] {
  return motions.map(classifyMotion);
}

export function groupMorphs(names: string[]): Map<ExprKind, string[]> {
  const map = new Map<ExprKind, string[]>();
  for (const e of EXPRESSIONS) map.set(e.kind, []);
  for (const name of names) {
    const card = classifyMorph(name);
    if (card) map.get(card.kind)!.push(name);
  }
  return map;
}

export function cardsByTag(cards: MotionCard[], tag: Intent): MotionCard[] {
  return cards.filter((c) => c.tags.includes(tag));
}

export function speakCards(cards: MotionCard[], tag: Intent): MotionCard[] {
  return cards.filter((c) => c.tags.includes(tag) && c.speakSafe && c.chainable);
}

export function idleCards(cards: MotionCard[], sad: boolean): MotionCard[] {
  return cards.filter((c) => {
    if (c.tags.includes('dance') || c.stance === 'dance' || c.stance === 'locomote') return false;
    if (c.stance === 'sit') return sad;
    return c.tags.includes('idle') || (c.stance === 'stand' && c.switchRule === 'hold');
  });
}

export function compatibleExpr(kinds: ExprKind[]): ExprKind[] {
  const out: ExprKind[] = [];
  for (const k of kinds) {
    const card = EXPRESSIONS.find((e) => e.kind === k);
    if (!card) continue;
    if (out.some((x) => card.exclusive.includes(x))) continue;
    out.push(k);
  }
  return out;
}
