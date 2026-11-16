import { reactive } from 'vue';
import type { JourneyState } from '../../api/client';
import { api } from '../../api/client';

export const journeyToasts = reactive([] as { id: number; title: string; lines: string[] }[]);
let sequence = 0;
let snapshot: JourneyState | null = null;
let refreshTimer = 0;

function pushToast(lines: string[]) {
  if (!lines.length) return;
  const id = ++sequence;
  journeyToasts.push({ id, title: '共同时光有了新的收获', lines });
  if (journeyToasts.length > 3) journeyToasts.shift();
  window.setTimeout(() => {
    const index = journeyToasts.findIndex(row => row.id === id);
    if (index >= 0) journeyToasts.splice(index, 1);
  }, 4600);
}

export function notifyJourney(state: JourneyState) {
  snapshot = state;
  if (!state.recorded || !state.reward) return;
  const reward = state.reward;
  const lines = [
    `好感 +${reward.affection_gained} · 陪伴经验 +${reward.ai_xp_gained}`,
  ];
  if (reward.level_up) lines.push(`AI 陪伴等级提升 · Lv.${reward.new_level}`);
  if (reward.affection_stage_up) lines.push(`关系进阶 · ${reward.affection_stage}`);
  for (const name of reward.inner_unlocked) lines.push(`内心档案解锁 · ${name}`);
  for (const row of state.coin_granted_now || []) lines.push(`${row.title} · +${row.coin} 金币`);
  pushToast(lines);
}

/** Poll once after a completed reply and turn persistent changes into the same reward language as gifts. */
export function refreshJourneySoon(characterId: number) {
  if (!characterId) return;
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(async () => {
    try {
      const next = await api.journeyState(characterId);
      const previous = snapshot;
      snapshot = next;
      if (!previous || previous.character_id !== characterId) return;
      const reward = {
        affection_gained: next.affection.value - previous.affection.value,
        ai_xp_gained: next.ai_level.xp - previous.ai_level.xp,
        level_up: next.ai_level.level > previous.ai_level.level,
        new_level: next.ai_level.level,
        affection_stage_up: next.affection.number > previous.affection.number,
        affection_stage: next.affection.stage,
        inner_unlocked: next.inner_story.entries.filter(row => row.unlocked && !previous.inner_story.entries.some(old => old.id === row.id && old.unlocked)).map(row => row.title),
      };
      if (reward.ai_xp_gained || reward.affection_gained || next.coin_granted_now.length || next.returns.length > previous.returns.length) {
        notifyJourney({ ...next, recorded: true, reward });
        if (next.returns.length > previous.returns.length) pushToast(['她也为你准备了一份新的回礼']);
      }
    } catch { /* chat remains independent from growth UI */ }
  }, 1400);
}
