import type { TouchZone } from '../../engine/types';
import type { ReplyLang } from '../../i18n';
import type { TouchTone } from './decide';

const LINES: Record<ReplyLang, Record<string, string[]>> = {
  'zh-CN': {
    'head.fond': ['[emo:relaxed]嗯，这里可以。', '[emo:happy]轻一点也行。', '[emo:relaxed]头发会乱。'],
    'head.shy': ['[emo:relaxed]摸头就摸头。', '[emo:happy]……嗯。'],
    'head.play': ['[emo:happy]又摸。', '[emo:relaxed]发旋在这儿。'],
    'head.bored': ['[emo:relaxed]摸平了。', '[emo:relaxed]知道了。'],
    'head.disdain': ['[emo:angry]手拿开。', '[emo:relaxed]我当没看见。'],
    'face.fond': ['[emo:happy]……就一下。', '[emo:relaxed]别盯着看。'],
    'face.shy': ['[emo:relaxed]脸不行。', '[emo:happy]手。'],
    'face.play': ['[emo:happy]躲什么躲。', '[emo:relaxed]戳到了。'],
    'face.dodge': ['[emo:relaxed]别戳脸。', '[emo:angry]往旁边。'],
    'face.bored': ['[emo:relaxed]没劲。', '[emo:relaxed]还摸。'],
    'face.disdain': ['[emo:angry]有完没完。', '[emo:relaxed]自己玩吧。'],
    'chest.fond': ['[emo:happy]……轻点。', '[emo:relaxed]今天就这样。'],
    'chest.shy': ['[emo:relaxed]你认真的？', '[emo:happy]手往哪放。'],
    'chest.play': ['[emo:happy]想什么呢。', '[emo:relaxed]正经点。'],
    'chest.cover': ['[emo:relaxed]这个不行。', '[emo:angry]手拿开。', '[emo:relaxed]往上，不是这里。'],
    'chest.dodge': ['[emo:relaxed]别。', '[emo:angry]躲开了哦。'],
    'chest.bored': ['[emo:relaxed]没意思了。', '[emo:relaxed]你自己玩吧。'],
    'chest.disdain': ['[emo:angry]有完没完。', '[emo:relaxed]当我空气？', '[emo:angry]再摸我就不理你。'],
    'waist.shy': ['[emo:relaxed]腰不行。', '[emo:happy]痒。'],
    'waist.cover': ['[emo:relaxed]手拿开。', '[emo:angry]别搂。'],
    'waist.dodge': ['[emo:relaxed]往旁边。'],
    'waist.bored': ['[emo:relaxed]又来。'],
    'waist.disdain': ['[emo:angry]适可而止。'],
    'hand.fond': ['[emo:happy]手可以牵。', '[emo:relaxed]握一下就行。'],
    'hand.shy': ['[emo:relaxed]干嘛突然抓。'],
    'hand.play': ['[emo:happy]放开也行。'],
    'hand.bored': ['[emo:relaxed]松开。'],
  },
  en: {
    'head.fond': ['[emo:relaxed]Mm. Here is fine.', '[emo:happy]Gently.'],
    'head.shy': ['[emo:relaxed]Just the head.'],
    'head.bored': ['[emo:relaxed]You will flatten it.'],
    'head.disdain': ['[emo:angry]Hand off.'],
    'face.shy': ['[emo:relaxed]Not the face.'],
    'face.dodge': ['[emo:relaxed]Don\'t poke.'],
    'face.disdain': ['[emo:angry]Enough.'],
    'chest.shy': ['[emo:relaxed]Seriously?'],
    'chest.cover': ['[emo:angry]Hands off.', '[emo:relaxed]Not there.'],
    'chest.dodge': ['[emo:relaxed]No.'],
    'chest.bored': ['[emo:relaxed]This is dull.'],
    'chest.disdain': ['[emo:angry]Are you done.'],
    'chest.fond': ['[emo:happy]...Easy.'],
    'waist.cover': ['[emo:relaxed]Hands off.'],
    'hand.fond': ['[emo:happy]You can hold that.'],
  },
  ja: {
    'head.fond': ['[emo:relaxed]うん、そこはいい。', '[emo:happy]優しく。'],
    'head.shy': ['[emo:relaxed]頭だけ。'],
    'head.bored': ['[emo:relaxed]ぺたんこになる。'],
    'head.disdain': ['[emo:angry]手、どいて。'],
    'face.shy': ['[emo:relaxed]顔はだめ。'],
    'face.dodge': ['[emo:relaxed]突かないで。'],
    'face.disdain': ['[emo:angry]もういい。'],
    'chest.shy': ['[emo:relaxed]本気？'],
    'chest.cover': ['[emo:angry]手、どいて。', '[emo:relaxed]そこじゃない。'],
    'chest.dodge': ['[emo:relaxed]やだ。'],
    'chest.bored': ['[emo:relaxed]つまんない。'],
    'chest.disdain': ['[emo:angry]まだやるの。'],
    'chest.fond': ['[emo:happy]…優しく。'],
    'waist.cover': ['[emo:relaxed]手、どいて。'],
    'hand.fond': ['[emo:happy]手ならいい。'],
  },
  ko: {
    'head.fond': ['[emo:relaxed]응, 거긴 돼.', '[emo:happy]살살.'],
    'head.shy': ['[emo:relaxed]머리는 괜찮아.'],
    'head.bored': ['[emo:relaxed]납작해지겠다.'],
    'head.disdain': ['[emo:angry]손 치워.'],
    'face.shy': ['[emo:relaxed]얼굴은 안 돼.'],
    'face.dodge': ['[emo:relaxed]찌르지 마.'],
    'face.disdain': ['[emo:angry]그만.'],
    'chest.shy': ['[emo:relaxed]진심이야?'],
    'chest.cover': ['[emo:angry]손 치워.', '[emo:relaxed]거긴 아니야.'],
    'chest.dodge': ['[emo:relaxed]싫어.'],
    'chest.bored': ['[emo:relaxed]재미없어.'],
    'chest.disdain': ['[emo:angry]아직이야?'],
    'chest.fond': ['[emo:happy]…살살.'],
    'waist.cover': ['[emo:relaxed]손 치워.'],
    'hand.fond': ['[emo:happy]손은 잡아도 돼.'],
  },
};

const ZONE_NAME: Record<ReplyLang, Record<TouchZone, string>> = {
  'zh-CN': { head: '头', face: '脸', chest: '胸', waist: '腰', hand: '手' },
  en: { head: 'head', face: 'face', chest: 'chest', waist: 'waist', hand: 'hand' },
  ja: { head: '頭', face: '顔', chest: '胸', waist: '腰', hand: '手' },
  ko: { head: '머리', face: '얼굴', chest: '가슴', waist: '허리', hand: '손' },
};

const TONE_NAME: Record<ReplyLang, Record<TouchTone, string>> = {
  'zh-CN': {
    fond: '亲昵', shy: '害羞', dodge: '躲开', cover: '护住', play: '闹着玩',
    bored: '腻了', numb: '麻了', ignore: '当没看见', disdain: '冷淡',
  },
  en: {
    fond: 'fond', shy: 'shy', dodge: 'pulling away', cover: 'covering up', play: 'teasing',
    bored: 'bored', numb: 'numb', ignore: 'ignoring', disdain: 'cold',
  },
  ja: {
    fond: '甘い', shy: '恥ずかしい', dodge: '避ける', cover: '隠す', play: 'からかう',
    bored: '飽きた', numb: '麻痺', ignore: '見て見ぬふり', disdain: '冷たい',
  },
  ko: {
    fond: '다정', shy: '수줍음', dodge: '피함', cover: '가림', play: '장난',
    bored: '질림', numb: '무딤', ignore: '못 본 척', disdain: '차가움',
  },
};

function pool(lang: ReplyLang, zone: TouchZone, tone: TouchTone) {
  const bag = LINES[lang] || LINES['zh-CN'];
  return bag[`${zone}.${tone}`]
    || bag[`${zone}.shy`]
    || bag[`${zone}.cover`]
    || LINES['zh-CN'][`${zone}.${tone}`]
    || ['[emo:relaxed]……'];
}

export function pickLine(lang: ReplyLang, zone: TouchZone, tone: TouchTone, last: string, rng = Math.random) {
  const all = pool(lang, zone, tone);
  const fresh = all.filter((s) => s !== last);
  const src = fresh.length ? fresh : all;
  return src[Math.floor(rng() * src.length)] ?? all[0];
}

function span(ms: number, lang: ReplyLang) {
  const min = Math.round(ms / 60000);
  if (lang === 'en') {
    if (min < 2) return 'just now';
    if (min < 60) return `${min} min`;
    const h = Math.round(min / 60);
    if (h < 36) return `${h} h`;
    return `${Math.round(h / 24)} days`;
  }
  if (lang === 'ja') {
    if (min < 2) return 'たった今';
    if (min < 60) return `${min}分`;
    const h = Math.round(min / 60);
    if (h < 36) return `${h}時間`;
    return `${Math.round(h / 24)}日`;
  }
  if (lang === 'ko') {
    if (min < 2) return '방금';
    if (min < 60) return `${min}분`;
    const h = Math.round(min / 60);
    if (h < 36) return `${h}시간`;
    return `${Math.round(h / 24)}일`;
  }
  if (min < 2) return '刚刚';
  if (min < 60) return `${min}分钟`;
  const h = Math.round(min / 60);
  if (h < 36) return `${h}小时`;
  return `${Math.round(h / 24)}天`;
}

function hourName(hour: number, lang: ReplyLang) {
  const late = hour < 5 || hour >= 23;
  const morning = hour >= 6 && hour < 11;
  const noon = hour >= 11 && hour < 14;
  const afternoon = hour >= 14 && hour < 18;
  if (lang === 'en') {
    if (late) return 'late night';
    if (morning) return 'morning';
    if (noon) return 'noon';
    if (afternoon) return 'afternoon';
    return 'evening';
  }
  if (lang === 'ja') {
    if (late) return '深夜';
    if (morning) return '朝';
    if (noon) return '昼';
    if (afternoon) return '午後';
    return '夜';
  }
  if (lang === 'ko') {
    if (late) return '깊은 밤';
    if (morning) return '아침';
    if (noon) return '한낮';
    if (afternoon) return '오후';
    return '저녁';
  }
  if (late) return '深夜';
  if (morning) return '早上';
  if (noon) return '中午';
  if (afternoon) return '下午';
  return '晚上';
}

export function touchBrief(lang: ReplyLang, fact: {
  zone: TouchZone;
  tone: TouchTone;
  bond: number;
  knownMs: number;
  idleMs: number;
  sessionMs: number;
  hour: number;
  streak: number;
  boundary: string;
  lastSpoken: string;
}) {
  const zone = ZONE_NAME[lang][fact.zone];
  const tone = TONE_NAME[lang][fact.tone];
  const bond = Math.round(fact.bond * 100);
  const last = fact.lastSpoken.replace(/\[[^\]]+\]/g, '').trim();
  if (lang === 'en') {
    return [
      `Touched: ${zone}. Attitude now: ${tone}. Do not change this attitude.`,
      `Closeness ${bond}/100. Known for ${span(fact.knownMs, lang)}. Idle ${span(fact.idleMs, lang)}. This sitting ${span(fact.sessionMs, lang)}.`,
      `Time: ${hourName(fact.hour, lang)}. This is touch ${fact.streak} on the same spot. Boundary: ${fact.boundary || 'free'}.`,
      last ? `Do not repeat: ${last}` : '',
    ].filter(Boolean).join('\n');
  }
  if (lang === 'ja') {
    return [
      `触られた場所：${zone}。今の態度：${tone}。態度は変えない。`,
      `親密度 ${bond}/100。知り合って ${span(fact.knownMs, lang)}。空いて ${span(fact.idleMs, lang)}。この回 ${span(fact.sessionMs, lang)}。`,
      `時間帯：${hourName(fact.hour, lang)}。同じ場所の ${fact.streak} 回目。尺度：${fact.boundary || 'free'}。`,
      last ? `繰り返さない：${last}` : '',
    ].filter(Boolean).join('\n');
  }
  if (lang === 'ko') {
    return [
      `닿은 곳: ${zone}. 지금의 태도: ${tone}. 태도를 바꾸지 마.`,
      `친밀 ${bond}/100. 안 지 ${span(fact.knownMs, lang)}. 비운 시간 ${span(fact.idleMs, lang)}. 이번 자리 ${span(fact.sessionMs, lang)}.`,
      `시간: ${hourName(fact.hour, lang)}. 같은 곳을 ${fact.streak}번째. 선: ${fact.boundary || 'free'}.`,
      last ? `반복하지 마: ${last}` : '',
    ].filter(Boolean).join('\n');
  }
  return [
    `碰到的位置：${zone}。现在的态度：${tone}。不要改这个态度。`,
    `亲疏 ${bond}/100。认识了 ${span(fact.knownMs, lang)}。空了 ${span(fact.idleMs, lang)}。这轮坐了 ${span(fact.sessionMs, lang)}。`,
    `时段：${hourName(fact.hour, lang)}。同一处第 ${fact.streak} 下。尺度：${fact.boundary || 'free'}。`,
    last ? `不要重复上一句：${last}` : '',
  ].filter(Boolean).join('\n');
}
