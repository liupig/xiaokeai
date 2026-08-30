/**
 * 角色情绪映射：在内置情绪预设之上，叠加角色自定义的形态键组合。
 * emotion_map 格式：{ happy: ["にっこり", "頬染め"], sad: [...] }
 */
import { stage } from '../../engine/stage';
import type { EmotionKey } from '../../engine/types';

let appliedMorphs: string[] = [];

export function parseEmotionMap(json: string): Record<string, string[]> {
  try {
    const obj = JSON.parse(json || '{}');
    return typeof obj === 'object' && obj ? obj : {};
  } catch {
    return {};
  }
}

/** 切换情绪：内置预设 + 角色自定义形态键，自动清掉上一个情绪的叠加 */
export function applyEmotion(emo: EmotionKey, map: Record<string, string[]>, intensity = 0.85) {
  stage.setEmotion(emo, intensity);
  for (const name of appliedMorphs) stage.setMorph(name, false);
  appliedMorphs = emo === 'neutral' ? [] : (map[emo] ?? []);
  for (const name of appliedMorphs) stage.setMorph(name, true);
}
