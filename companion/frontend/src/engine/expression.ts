import * as THREE from 'three';
import type { Avatar, EmotionKey, ExprKey } from './types';

export const WINK_MORPH = /wink|biyan[_. -]?[lr]$|^EL_Happy_[lr]_CLO$|^(?:[左右][ _+.-]*)?(?:笑い目|なごみ|じと目|笑い)(?:[ _+.-]*[左右lr])$|^[左右][ _+.-]*(?:笑い目|なごみ|じと目|笑い)$|ｳｨﾝｸ|ウ[ィイ]ンク|眨[单單]眼|[单單]眼眨|眨[左右]眼|[左右]眼眨|眨眼[左右]|(?:[单單左右]眼[闭閉]|[闭閉][左右]眼)|(?:eye[_. -]?)?blink[_. -]?(?:left|right|l|r)\b/i;
const WINK_CLOSE = 0.07;
const WINK_OPEN = 0.14;
const WINK_INTERVAL_MS = 650;

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
  private cues = new Map<string, { target: number; value: number; remaining: number }>();
  private written = new Set<string>();
  private wink: { name: string; strength: number; start: number; elapsed: number } | null = null;
  private nextWinkAt = 0;

  private triggerWink(name: string, strength: number) {
    if (strength <= 0 || !Number.isFinite(strength)) return;
    const now = performance.now();
    if (this.wink || now < this.nextWinkAt) return;
    this.wink = { name, strength: Math.min(1, strength), start: now, elapsed: 0 };
    this.nextWinkAt = now + WINK_INTERVAL_MS;
    this.blinkProgress = -1;
    this.blinkTimer = Math.max(this.blinkTimer, 0.42);
  }

  setCue(name: string, weight: number, seconds: number) {
    if (WINK_MORPH.test(name)) {
      this.triggerWink(name, weight);
      return;
    }
    this.cues.set(name, { target: weight, value: this.cues.get(name)?.value ?? 0, remaining: seconds });
  }

  releaseCues() {
    for (const cue of this.cues.values()) cue.remaining = 0;
  }
  private blinkTimer = 2.5;
  private blinkProgress = -1;

  setEmotion(e: EmotionKey, intensity = 0.85) {
    this.emotion = e;
    this.emotionIntensity = intensity;
  }

  /** 手动开关任意形态键（表情库），动画循环里平滑过渡；可传 0~1 强度 */
  setMorphTarget(name: string, on: boolean | number) {
    const v = typeof on === 'number' ? Math.min(1, Math.max(0, on)) : (on ? 1 : 0);
    if (WINK_MORPH.test(name)) {
      this.triggerWink(name, v);
      return;
    }
    this.manualTargets.set(name, v);
    if (!this.manualCurrent.has(name)) this.manualCurrent.set(name, 0);
  }

  activeMorphs(): string[] {
    return [...this.manualTargets.entries()].filter(([, v]) => v > 0).map(([k]) => k);
  }

  resetMorphs() {
    this.wink = null;
    for (const name of this.manualTargets.keys()) this.manualTargets.set(name, 0);
  }

  /** 被碰到的这一下，补一次眨眼，不另开表情系统 */
  blinkNow() {
    if (!this.wink && this.blinkProgress < 0) {
      this.blinkProgress = 0;
      this.blinkTimer = 2.2 + Math.random() * 2;
    }
  }

  reset() {
    this.emotion = 'neutral';
    this.manualTargets.clear();
    this.manualCurrent.clear();
    this.cues.clear();
    this.written.clear();
    this.wink = null;
    this.nextWinkAt = 0;
    this.blinkProgress = -1;
    this.blinkTimer = 2.5;
    for (const key of EMOTIONS) this.weights[key] = 0;
    this.mouthValue = 0;
  }

  update(av: Avatar, dt: number) {
    const named = new Map<string, number>();
    for (const [name, target] of this.manualTargets) {
      const value = THREE.MathUtils.lerp(this.manualCurrent.get(name) ?? 0, target, 1 - Math.exp(-10 * dt));
      if (target === 0 && value < 0.01) {
        this.manualTargets.delete(name);
        this.manualCurrent.delete(name);
      } else {
        this.manualCurrent.set(name, value);
        named.set(name, value);
      }
    }
    for (const [name, cue] of this.cues) {
      cue.remaining -= dt;
      const target = cue.remaining > 0 ? cue.target : 0;
      cue.value = THREE.MathUtils.lerp(cue.value, target, 1 - Math.exp(-(target > cue.value ? 15 : 7) * dt));
      if (target === 0 && cue.value < 0.01) this.cues.delete(name);
      else named.set(name, Math.max(named.get(name) ?? 0, cue.value));
    }
    if (this.wink) {
      const wink = this.wink;
      wink.elapsed = Math.max(wink.elapsed + dt, (performance.now() - wink.start) / 1000);
      if (wink.elapsed >= WINK_CLOSE + WINK_OPEN) {
        this.wink = null;
      } else {
        const progress = wink.elapsed < WINK_CLOSE
          ? wink.elapsed / WINK_CLOSE
          : 1 - (wink.elapsed - WINK_CLOSE) / WINK_OPEN;
        named.set(wink.name, wink.strength * progress);
      }
    }
    for (const name of this.written) if (!named.has(name)) av.setMorph(name, 0);
    this.written = new Set(named.keys());
    av.setExpr('aa', this.mouthValue);

    // 眨眼
    this.blinkTimer -= dt;
    if (this.wink) av.setExpr('blink', 0);
    if (!this.wink && this.blinkTimer <= 0 && this.blinkProgress < 0) {
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

    for (const [name, value] of named) {
      const base = av.isVRM ? this.weights[name] ?? 0 : 0;
      av.setMorph(name, Math.max(base, value), true);
    }
  }
}
