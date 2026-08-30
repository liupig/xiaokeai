import * as THREE from 'three';
import type { Avatar, EmotionKey, ExprKey } from './types';

const EMOTIONS: ExprKey[] = ['happy', 'angry', 'sad', 'relaxed'];

/** 表情控制：情绪预设平滑过渡 + 眨眼 + 口型 + 手动形态键叠加 */
export class ExpressionController {
  emotion: EmotionKey = 'neutral';
  /** 当前情绪的目标强度 0~1（由表演导演每帧驱动，含衰减） */
  emotionIntensity = 0.85;
  /** 每帧由 Lipsync 写入的口型开合值 0~1 */
  mouthValue = 0;

  private weights: Record<string, number> = { happy: 0, angry: 0, sad: 0, relaxed: 0 };
  private manualTargets = new Map<string, number>();
  private manualCurrent = new Map<string, number>();
  private blinkTimer = 2.5;
  private blinkProgress = -1;

  setEmotion(e: EmotionKey, intensity = 0.85) {
    this.emotion = e;
    this.emotionIntensity = intensity;
  }

  /** 手动开关任意形态键（表情库），动画循环里平滑过渡；可传 0~1 强度 */
  setMorphTarget(name: string, on: boolean | number) {
    const v = typeof on === 'number' ? Math.min(1, Math.max(0, on)) : (on ? 1 : 0);
    this.manualTargets.set(name, v);
    if (!this.manualCurrent.has(name)) this.manualCurrent.set(name, 0);
  }

  activeMorphs(): string[] {
    return [...this.manualTargets.entries()].filter(([, v]) => v > 0).map(([k]) => k);
  }

  resetMorphs() {
    for (const name of this.manualTargets.keys()) this.manualTargets.set(name, 0);
  }

  reset() {
    this.emotion = 'neutral';
    this.manualTargets.clear();
    this.manualCurrent.clear();
    this.mouthValue = 0;
  }

  update(av: Avatar, dt: number) {
    av.setExpr('aa', this.mouthValue);

    // 眨眼
    this.blinkTimer -= dt;
    if (this.blinkTimer <= 0 && this.blinkProgress < 0) {
      this.blinkProgress = 0;
      this.blinkTimer = 2 + Math.random() * 4;
    }
    if (this.blinkProgress >= 0) {
      this.blinkProgress += dt;
      const v = this.blinkProgress < 0.08
        ? this.blinkProgress / 0.08
        : Math.max(0, 1 - (this.blinkProgress - 0.08) / 0.12);
      av.setExpr('blink', v);
      if (this.blinkProgress > 0.22) {
        this.blinkProgress = -1;
        av.setExpr('blink', 0);
      }
    }

    // 情绪平滑过渡（目标权重 = 导演给出的连续强度）
    for (const e of EMOTIONS) {
      const target = this.emotion === e ? this.emotionIntensity : 0;
      this.weights[e] = THREE.MathUtils.lerp(this.weights[e], target, 1 - Math.exp(-8 * dt));
      av.setExpr(e, this.weights[e]);
    }

    // 手动形态键叠加（平滑淡入淡出，可任意组合）
    for (const [name, target] of this.manualTargets) {
      const cur = this.manualCurrent.get(name) ?? 0;
      const nv = THREE.MathUtils.lerp(cur, target, 1 - Math.exp(-10 * dt));
      if (target === 0 && nv < 0.01) {
        this.manualTargets.delete(name);
        this.manualCurrent.delete(name);
        av.setMorph(name, 0);
      } else {
        this.manualCurrent.set(name, nv);
        av.setMorph(name, nv);
      }
    }
  }
}
