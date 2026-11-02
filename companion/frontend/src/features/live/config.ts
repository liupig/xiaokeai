/** 直播配置。和后端 default_live 对齐，缺的键补上，彩排默认关。 */
export const LIVE_FEATURES = [
  'bilibili', 'douyin', 'scheduler', 'reply', 'gifts', 'audience', 'rundown',
  'idle', 'budget', 'watchdog', 'ai_label', 'content_gate', 'ritual', 'rehearsal',
  'commands', 'interrupt',
] as const;

export type LiveFeature = typeof LIVE_FEATURES[number];

export interface LiveConfig {
  douyin: { room: string; push_secret: string; room_id: string };
  bilibili: { access_key_id: string; access_key_secret: string; app_id: number; code: string };
  features: Record<LiveFeature, boolean>;
  compliance: {
    strict: boolean;
    ack_voice: boolean;
    ack_model: boolean;
    ack_bgm: boolean;
    bgm_licensed: boolean;
  };
  budget: {
    cap_cny: number;
    cny_per_1k: number;
    fallback_base_url: string;
    fallback_model: string;
    fallback_api_key: string;
  };
  pace: { batch_sec: number; user_cooldown_sec: number; batch_size: number; idle_sec: number; session_max_min: number; quiet_min: number };
  persona: { catchphrase: string; style: string };
  schedule: { note: string; community: string };
  songs: string;
  block_words: string;
}

export function defaultLive(): LiveConfig {
  const features = {} as Record<LiveFeature, boolean>;
  for (const key of LIVE_FEATURES) features[key] = key !== 'rehearsal';
  return {
    douyin: { room: '', push_secret: '', room_id: '' },
    bilibili: { access_key_id: '', access_key_secret: '', app_id: 0, code: '' },
    features,
    compliance: {
      strict: true, ack_voice: false, ack_model: false, ack_bgm: false, bgm_licensed: false,
    },
    budget: {
      cap_cny: 30, cny_per_1k: 0.004,
      fallback_base_url: '', fallback_model: '', fallback_api_key: '',
    },
    pace: { batch_sec: 20, user_cooldown_sec: 8, batch_size: 6, idle_sec: 45, session_max_min: 0, quiet_min: 0 },
    persona: { catchphrase: '我在呢', style: '' },
    schedule: { note: '', community: '' },
    songs: '',
    block_words: '',
  };
}

function num(value: unknown, fallback: number) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function normalizeLive(raw: unknown): LiveConfig {
  const base = defaultLive();
  const src = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
  const douyin = src.douyin && typeof src.douyin === 'object' ? src.douyin as Record<string, unknown> : {};
  const bili = src.bilibili && typeof src.bilibili === 'object' ? src.bilibili as Record<string, unknown> : {};
  const feats = src.features && typeof src.features === 'object' ? src.features as Record<string, unknown> : {};
  const comp = src.compliance && typeof src.compliance === 'object' ? src.compliance as Record<string, unknown> : {};
  const budget = src.budget && typeof src.budget === 'object' ? src.budget as Record<string, unknown> : {};
  const pace = src.pace && typeof src.pace === 'object' ? src.pace as Record<string, unknown> : {};
  const persona = src.persona && typeof src.persona === 'object' ? src.persona as Record<string, unknown> : {};
  const schedule = src.schedule && typeof src.schedule === 'object' ? src.schedule as Record<string, unknown> : {};
  base.douyin = {
    room: String(douyin.room || ''),
    push_secret: String(douyin.push_secret || ''),
    room_id: String(douyin.room_id || ''),
  };
  base.bilibili = {
    access_key_id: String(bili.access_key_id || ''),
    access_key_secret: String(bili.access_key_secret || ''),
    app_id: Math.max(0, Math.round(num(bili.app_id, 0))),
    code: String(bili.code || ''),
  };
  for (const key of LIVE_FEATURES) {
    base.features[key] = key in feats ? !!feats[key] : key !== 'rehearsal';
  }
  base.compliance = {
    strict: comp.strict !== false && comp.strict !== 0,
    ack_voice: !!comp.ack_voice,
    ack_model: !!comp.ack_model,
    ack_bgm: !!comp.ack_bgm,
    bgm_licensed: !!comp.bgm_licensed,
  };
  if (!('strict' in comp)) base.compliance.strict = true;
  base.budget = {
    cap_cny: num(budget.cap_cny, 30),
    cny_per_1k: num(budget.cny_per_1k, 0.004),
    fallback_base_url: String(budget.fallback_base_url || ''),
    fallback_model: String(budget.fallback_model || ''),
    fallback_api_key: String(budget.fallback_api_key || ''),
  };
  base.pace = {
    batch_sec: num(pace.batch_sec, 20),
    user_cooldown_sec: num(pace.user_cooldown_sec, 8),
    batch_size: num(pace.batch_size, 6),
    idle_sec: num(pace.idle_sec, 45),
    session_max_min: num(pace.session_max_min, 0),
    quiet_min: num(pace.quiet_min, 0),
  };
  base.persona = {
    catchphrase: String(persona.catchphrase || '我在呢'),
    style: String(persona.style || ''),
  };
  base.schedule = {
    note: String(schedule.note || ''),
    community: String(schedule.community || ''),
  };
  base.songs = String(src.songs || '');
  base.block_words = String(src.block_words || '');
  return base;
}
