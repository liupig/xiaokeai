import { stage } from '../../engine/stage';

export async function captureStill(maxW = 1280): Promise<Blob> {
  return stage.captureStill(maxW);
}

export async function captureClip(seconds = 8, onTick?: (sec: number) => void): Promise<Blob> {
  const sec = Math.min(60, Math.max(1, Math.round(seconds) || 8));
  return stage.captureClip(sec, onTick);
}
