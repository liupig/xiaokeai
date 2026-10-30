/** 酒馆音色。XiaO 女声，AI 男声。KE 看牌组：萝莉少女御姐用男声，犬系正太爹系用女声。裁判用角色的声音。 */

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

type Gender = 'f' | 'm';

const FEMALE: Record<string, CastPick[]> = {
  'zh-CN': [
    { engine: 'qwen', voice: 'Vivian' },
    { engine: 'qwen', voice: 'Serena' },
    { engine: 'edge', voice: 'zh-CN-XiaoxiaoNeural' },
    { engine: 'edge', voice: 'zh-CN-XiaoyiNeural' },
    { engine: 'edge', voice: 'zh-CN-liaoning-XiaobeiNeural' },
    { engine: 'edge', voice: 'zh-TW-HsiaoChenNeural' },
  ],
  en: [
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
    { engine: 'qwen', voice: 'Dylan' },
    { engine: 'qwen', voice: 'Eric' },
    { engine: 'qwen', voice: 'Uncle_Fu' },
    { engine: 'edge', voice: 'zh-CN-YunjianNeural' },
    { engine: 'edge', voice: 'zh-CN-YunxiNeural' },
    { engine: 'edge', voice: 'zh-CN-YunyangNeural' },
  ],
  en: [
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

const GENDER = new Map<string, Gender>();
for (const rows of Object.values(FEMALE)) {
  for (const row of rows) GENDER.set(row.voice, 'f');
}
for (const rows of Object.values(MALE)) {
  for (const row of rows) GENDER.set(row.voice, 'm');
}

function langOf(raw: string) {
  if (raw === 'en' || raw === 'ja' || raw === 'ko' || raw === 'zh-CN') return raw;
  if (raw.startsWith('en')) return 'en';
  if (raw.startsWith('ja')) return 'ja';
  if (raw.startsWith('ko')) return 'ko';
  return 'zh-CN';
}

function genderOf(voice: string): Gender | '' {
  return GENDER.get(voice) || '';
}

function engineOf(voice: string, fallback: string) {
  if (['Vivian', 'Serena', 'Dylan', 'Eric', 'Uncle_Fu', 'Ryan', 'Aiden', 'Ono_Anna', 'Sohee'].includes(voice)) {
    return 'qwen';
  }
  if (voice.includes('Neural')) return 'edge';
  return fallback;
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
  if (primary === 'off' || primary === 'browser') {
    return { her: blank, host: blank, qin: blank, bar: blank, you: blank };
  }

  const order = (rows: CastPick[]) => {
    const localFirst = rows.some((row) => row.engine === 'qwen');
    return [...rows].sort((a, b) => {
      const score = (row: CastPick) => {
        if (localFirst) return row.engine === 'qwen' ? 0 : row.engine === 'edge' ? 1 : 2;
        return row.engine === primary ? 0 : row.engine === 'edge' ? 1 : 2;
      };
      return score(a) - score(b);
    });
  };
  const females = order(FEMALE[lang] || FEMALE['zh-CN']);
  const males = order(MALE[lang] || MALE['zh-CN']);
  const used = new Set<string>();

  function fits(role: string, pick: CastPick) {
    const need = role === 'qin' ? 'f' : role === 'bar' ? 'm' : role === 'you' ? (keMale ? 'm' : 'f') : '';
    if (!need) return true;
    const got = genderOf(pick.voice);
    return !got || got === need;
  }

  function claim(pick: CastPick, unique: boolean) {
    if (unique) used.add(pick.voice);
    return pick;
  }

  function take(role: string, pool: CastPick[], unique: boolean): CastPick {
    const picked = saved[role];
    const localFirst = pool.some((row) => row.engine === 'qwen');
    if (
      picked?.engine && picked.voice && fits(role, picked)
      && (!localFirst || picked.engine === 'qwen')
      && (!unique || !used.has(picked.voice))
    ) {
      return claim({ engine: picked.engine, voice: picked.voice }, unique);
    }
    for (const row of pool) {
      if (unique && used.has(row.voice)) continue;
      return claim(row, unique);
    }
    return blank;
  }

  const characterPick: CastPick | null = character
    ? { engine: engineOf(character, primary), voice: character }
    : null;
  const femaleLocal = females.some((row) => row.engine === 'qwen');
  const characterOk = !!characterPick && (!femaleLocal || characterPick.engine === 'qwen');
  const herSaved = saved.her;
  const her = herSaved?.engine && herSaved.voice && (!femaleLocal || herSaved.engine === 'qwen')
    ? claim({ engine: herSaved.engine, voice: herSaved.voice }, true)
    : characterOk && characterPick
      ? claim(characterPick, true)
      : take('her', females, true);
  const hostSaved = saved.host;
  const host = hostSaved?.engine && hostSaved.voice && (!femaleLocal || hostSaved.engine === 'qwen')
    ? { engine: hostSaved.engine, voice: hostSaved.voice }
    : characterOk && characterPick
      ? { ...characterPick }
      : take('host', females, false);
  const qin = take('qin', females, true);
  const bar = take('bar', males, true);
  const you = take('you', keMale ? males : females, true);
  return { her, host, qin, bar, you };
}
