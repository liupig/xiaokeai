import { stage } from '../../engine/stage';
import { useChatStore } from '../../stores/chat';
import { speechPlayer } from '../voice/tts';

/** 桌宠在画面里随意走一走。说话、回复、拖动时先站着。 */
export function installPetWander() {
  let timer = 0;
  let stopped = false;

  const arm = (ms: number) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(tick, ms);
  };

  const busy = () => {
    const chat = useChatStore();
    return chat.sending || speechPlayer.isSpeaking();
  };

  const tick = () => {
    if (stopped) return;
    if (!busy() && stage.canPetWander()) {
      stage.petWanderOnce();
      arm(7000 + Math.random() * 8000);
      return;
    }
    arm(1600);
  };

  arm(4500);
  return () => {
    stopped = true;
    window.clearTimeout(timer);
  };
}
