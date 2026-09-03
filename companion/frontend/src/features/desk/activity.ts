import { stage } from '../../engine/stage';
import { caster } from '../performance/caster';
import { tarotLive } from '../tarot/gate';

export type DeskActivity = 'tarot' | 'dance' | 'chat';

export function dancingNow() {
  return !!(caster.holdingDance && stage.motion.active);
}

export function tarotNow() {
  return !!tarotLive.value;
}

/** 台面上正在干什么：看牌局压过舞，舞压过闲聊。 */
export function deskActivity(): DeskActivity {
  if (tarotNow()) return 'tarot';
  if (dancingNow()) return 'dance';
  return 'chat';
}
