/** 正式直播和彩排共用的舞台播放入口。 */
import { orchestrator } from '../performance/orchestrator';
import { speechPlayer } from '../voice/tts';

export interface LiveTurn {
  id: string; text: string; cue: string; act?: string; interrupt?: boolean;
  sources?: Array<{ msg_id: string; nickname: string; content: string; kind: string }>;
}

export type PlaybackOutcome = 'completed' | 'displayed' | 'interrupted' | 'failed';

export async function playLiveTurn(turn: LiveTurn, signal?: AbortSignal): Promise<PlaybackOutcome> {
  const text = turn.text.trim();
  if (!text || signal?.aborted) return 'interrupted';
  if (turn.interrupt) speechPlayer.onUserBargeIn();
  const wantsDance = turn.cue === 'dance' || turn.act === 'dance';
  if (wantsDance) {
    // 把原始弹幕交给选舞器：这样“跳个极乐净土”能按名字命中，而不是只说话不跳。
    const ask = turn.sources?.map((source) => source.content).filter(Boolean).join('；')
      || turn.text || '跳一支舞';
    orchestrator.beginTurn(ask);
    orchestrator.handle({ type: 'dance', value: '' });
  } else if (turn.act) orchestrator.beginTurn(text);
  else orchestrator.beginContinue('proactive');
  orchestrator.allowLocalSpeech();
  const ticket = speechPlayer.playbackTicket();
  const cancelOwnedSpeech = () => {
    const current = speechPlayer.playbackTicket();
    if (current.generation === ticket.generation && current.token === ticket.token && current.inputGen === ticket.inputGen) {
      speechPlayer.onUserBargeIn();
    }
  };
  signal?.addEventListener('abort', cancelOwnedSpeech, { once: true });
  if (turn.act && turn.act !== 'dance') orchestrator.handle({ type: 'intent', value: turn.act });
  orchestrator.handle({ type: 'text', delta: text });
  orchestrator.handle({ type: 'done', full_text: text });
  try { return await speechPlayer.playbackResult(ticket, signal); }
  finally { signal?.removeEventListener('abort', cancelOwnedSpeech); }
}
