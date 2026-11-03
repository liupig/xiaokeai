/** 酒馆音色。XiaO 女声，AI 男声。KE 看牌组：萝莉少女御姐用男声，犬系正太爹系用女声。
 * 空着的座位跟着当前合成引擎走。小米用冰糖、茉莉、苏打、白桦。角色音色和当前引擎一致时，裁判才用角色的声音。
 */

export interface CastVoice {
  id: string;
  engine?: string;
  lang?: string;
}

export interface CastPick {
  engine: string;
  voice: string;
}

export interface CastSaved {
  engine: string;
  voice: string;
}

const FEMALE: Record<string, CastPick[]> = {
  'zh-CN': [
    { engine: 'mimo', voice: '冰糖' },
    { engine: 'mimo', voice: '茉莉' },
    { engine: 'qwen', voice: 'Vivian' },
    { engine: 'qwen', voice: 'Serena' },
    { engine: 'edge', voice: 'zh-CN-XiaoxiaoNeural' },
    { engine: 'edge', voice: 'zh-CN-XiaoyiNeural' },
    { engine: 'edge', voice: 'zh-CN-liaoning-XiaobeiNeural' },
    { engine: 'edge', voice: 'zh-TW-HsiaoChenNeural' },
  ],
  en: [
    { engine: 'mimo', voice: 'Mia' },
    { engine: 'mimo', voice: 'Chloe' },
    { engine: 'edge', voice: 'en-US-AriaNeural' },
    { engine: 'edge', voice: 'en-US-JennyNeural' },
    { engine: 'edge', voice: 'en-US-MichelleNeural' },
  ],
  ja: [
    { engine: 'qwen', voice: 'Ono_Anna' },
    { engine: 'edge', voice: 'ja-JP-NanamiNeural' },
    { engine: 'edge', voice: 'ja-JP-AoiNeural' },
    { engine: 'edge', voice: 'ja-JP-MayuNeural' },
  ],
  ko: [
    { engine: 'qwen', voice: 'Sohee' },
    { engine: 'edge', voice: 'ko-KR-SunHiNeural' },
    { engine: 'edge', voice: 'ko-KR-YuJinNeural' },
    { engine: 'edge', voice: 'ko-KR-SoonBokNeural' },
  ],
};

const MALE: Record<string, CastPick[]> = {
  'zh-CN': [
    { engine: 'mimo', voice: '苏打' },
    { engine: 'mimo', voice: '白桦' },
    { engine: 'qwen', voice: 'Dylan' },
    { engine: 'qwen', voice: 'Eric' },
    { engine: 'qwen', voice: 'Uncle_Fu' },
    { engine: 'edge', voice: 'zh-CN-YunjianNeural' },
    { engine: 'edge', voice: 'zh-CN-YunxiNeural' },
    { engine: 'edge', voice: 'zh-CN-YunyangNeural' },
  ],
  en: [
    { engine: 'mimo', voice: 'Milo' },
    { engine: 'mimo', voice: 'Dean' },
    { engine: 'qwen', voice: 'Ryan' },
    { engine: 'qwen', voice: 'Aiden' },
    { engine: 'edge', voice: 'en-US-GuyNeural' },
    { engine: 'edge', voice: 'en-US-DavisNeural' },
  ],
  ja: [
    { engine: 'edge', voice: 'ja-JP-KeitaNeural' },
    { engine: 'edge', voice: 'ja-JP-DaichiNeural' },
  ],
  ko: [
    { engine: 'edge', voice: 'ko-KR-InJoonNeural' },
    { engine: 'edge', voice: 'ko-KR-HyunsuNeural' },
  ],
};

function langOf(raw: string) {
  if (raw === 'en' || raw === 'ja' || raw === 'ko' || raw === 'zh-CN') return raw;
  if (raw.startsWith('en')) return 'en';
  if (raw.startsWith('ja')) return 'ja';
  if (raw.startsWith('ko')) return 'ko';
  return 'zh-CN';
}

const QWEN_IDS = ['Vivian', 'Serena', 'Dylan', 'Eric', 'Uncle_Fu', 'Ryan', 'Aiden', 'Ono_Anna', 'Sohee'];
const MIMO_IDS = ['冰糖', '茉莉', '苏打', '白桦', 'mimo_default', 'Mia', 'Chloe', 'Milo', 'Dean'];

function engineOf(voice: string, fallback: string) {
  if (QWEN_IDS.includes(voice)) return 'qwen';
  if (MIMO_IDS.includes(voice)) return 'mimo';
  if (voice.includes('Neural')) return 'edge';
  return fallback;
}

function rank(primary: string, row: CastPick) {
  if (row.engine === primary) return 0;
  if (row.engine === 'qwen') return 1;
  if (row.engine === 'edge') return 2;
  return 3;
}

export function resolveCast(input: {
  lang: string;
  engine: string;
  characterVoice: string;
  deck?: string;
  saved?: Record<string, Record<string, CastSaved>>;
  voices?: CastVoice[];
}): Record<string, CastPick> {
  const lang = langOf(input.lang || 'zh-CN');
  const primary = input.engine || 'browser';
  const saved = input.saved?.[lang] || {};
  const character = (input.characterVoice || '').trim();
  const keMale = (input.deck || 'rose') !== 'ink';
  const blank = { engine: primary === 'off' ? 'off' : 'browser', voice: '' };
  if (primary === 'off') {
    return { her: blank, host: blank, qin: blank, bar: blank, you: blank };
  }

  const order = (rows: CastPick[]) => [...rows].sort((a, b) => rank(primary, a) - rank(primary, b));
  const females = order(FEMALE[lang] || FEMALE['zh-CN']);
  const males = order(MALE[lang] || MALE['zh-CN']);
  const used = new Set<string>();

  function claim(pick: CastPick, unique: boolean) {
    if (unique) used.add(pick.voice);
    return pick;
  }

  function savedPick(role: string, unique: boolean): CastPick | null {
    const picked = saved[role];
    if (!picked?.engine || !picked.voice) return null;
    if (unique && used.has(picked.voice)) return null;
    return claim({ engine: picked.engine, voice: picked.voice }, unique);
  }

  function take(role: string, pool: CastPick[], unique: boolean): CastPick {
    const picked = savedPick(role, unique);
    if (picked) return picked;
    if (primary === 'browser') return blank;
    for (const row of pool) {
      if (unique && used.has(row.voice)) continue;
      return claim(row, unique);
    }
    return blank;
  }

  const characterPick: CastPick | null = character
    ? { engine: engineOf(character, primary), voice: character }
    : null;
  const characterOk = !!characterPick && characterPick.engine === primary;
  const her = savedPick('her', true)
    || (characterOk && characterPick ? claim(characterPick, true) : take('her', females, true));
  const host = savedPick('host', false)
    || (characterOk && characterPick ? { ...characterPick } : take('host', females, false));
  const qin = take('qin', females, true);
  const bar = take('bar', males, true);
  const you = take('you', keMale ? males : females, true);
  return { her, host, qin, bar, you };
}
