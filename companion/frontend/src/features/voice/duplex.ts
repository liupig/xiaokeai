/**
 * 小冰 Transaction / ChannelPool 的决策层。
 * 后端给每句打 DuplexCmd + SentenceType；这里根据剩余时长决定 queue / interrupt / skip。
 * 不合成音频，只决定播不播、插不插。
 */

export type DuplexCmd =
  | 'queue'
  | 'interrupt'
  | 'skip'
  | 'silent'
  | 'skip_on_new'
  | 'conditional_queue'
  | 'conditional_interrupt'
  | 'interrupt_or_queue'
  | 'intermediate';

export type SentenceType =
  | 'transition'
  | 'normal'
  | 'continuous'
  | 'welcome'
  | 'goodbye'
  | 'proactive';

export type PlayAction = 'queue' | 'interrupt' | 'skip';

export const DEFAULT_DUPLEX_REMAIN_SEC = 3;
export const DEFAULT_DUPLEX_DELAYED_SEC = 16;
export const DEFAULT_DUPLEX_PROACTIVE_SEC = 45;
export const DEFAULT_DUPLEX_GOODBYE_SEC = 140;
export const DEFAULT_DUPLEX_SESSION_MAX_MIN = 0;

/** 人类对话里的自然沉默，不是固定闹钟。 */
export const SILENCE_RANGE: Record<'delayed' | 'proactive' | 'goodbye', { min: number; max: number }> = {
  delayed: { min: 10, max: 28 },
  proactive: { min: 28, max: 75 },
  goodbye: { min: 90, max: 210 },
};

/** 在区间里抽一次，略偏中间，避免每次都卡在两端。 */
export function humanSilenceSec(
  kind: 'delayed' | 'proactive' | 'goodbye',
  typical?: number,
): number {
  if (typical === 0) return 0;
  const span = SILENCE_RANGE[kind];
  const center = Number.isFinite(typical) && (typical as number) > 0
    ? (typical as number)
    : (span.min + span.max) / 2;
  let lo = span.min;
  let hi = span.max;
  if (center >= span.min * 0.8) {
    lo = Math.max(span.min, center * 0.7);
    hi = Math.max(lo + 5, Math.min(span.max, center * 1.55));
  }
  const n = (Math.random() + Math.random()) / 2;
  return lo + (hi - lo) * n;
}

export interface PlayableUnit {
  text: string;
  duplexCmd: DuplexCmd;
  sentenceType: SentenceType;
  /** 创建时的用户轮次；SkipOnNew 在轮次变化后丢掉 */
  inputGen?: number;
  kind?: string;
  id?: string;
  updateContext?: boolean;
}

const CMDS: DuplexCmd[] = [
  'queue', 'interrupt', 'skip', 'silent', 'skip_on_new',
  'conditional_queue', 'conditional_interrupt', 'interrupt_or_queue', 'intermediate',
];
const TYPES: SentenceType[] = [
  'transition', 'normal', 'continuous', 'welcome', 'goodbye', 'proactive',
];

export function normalizeDuplexCmd(v: unknown): DuplexCmd {
  const s = String(v || '').trim().toLowerCase();
  return (CMDS as string[]).includes(s) ? (s as DuplexCmd) : 'interrupt_or_queue';
}

export function normalizeSentenceType(v: unknown): SentenceType {
  const s = String(v || '').trim().toLowerCase();
  return (TYPES as string[]).includes(s) ? (s as SentenceType) : 'normal';
}

export function resolveDuplex(opts: {
  cmd: DuplexCmd;
  remaining: number;
  threshold: number;
  currentAudible: boolean;
  currentType: SentenceType | null;
  userTurnMoved: boolean;
  /** 同一轮 QA 的 A1/A2/A3：不看剩余，只排队 */
  sameTurn: boolean;
}): PlayAction {
  const { cmd, remaining, threshold, currentAudible, userTurnMoved, sameTurn } = opts;
  if (cmd === 'skip' || cmd === 'silent') return 'skip';
  if (cmd === 'skip_on_new' && userTurnMoved) return 'skip';
  // 一轮回复切成多段音频：A1→A2→A3 永远顺播
  if (sameTurn) return 'queue';

  if (!currentAudible) return 'queue';

  const over = remaining > threshold;
  switch (cmd) {
    case 'queue':
    case 'skip_on_new':
      return 'queue';
    case 'interrupt':
    case 'intermediate':
      return 'interrupt';
    case 'interrupt_or_queue':
      return over ? 'interrupt' : 'queue';
    case 'conditional_queue':
      return remaining < threshold ? 'queue' : 'skip';
    case 'conditional_interrupt':
      return over ? 'interrupt' : 'skip';
    default:
      return 'queue';
  }
}
