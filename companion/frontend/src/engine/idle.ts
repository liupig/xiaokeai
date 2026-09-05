import type { ActionKey, Avatar } from './types';

/** 动作的淡入淡出包络，避免姿势突变 */
function envelope(p: number) {
  const fadeIn = Math.min(1, p / 0.15);
  const fadeOut = Math.min(1, (1 - p) / 0.15);
  return Math.min(fadeIn, fadeOut);
}

const DURATIONS: Record<ActionKey, number> = { nod: 1.4, shake: 1.6 };

/** 程序化闲置动画：呼吸、身体摆动、头部微动、手臂下垂 + 点头/摇头 */
export class IdleAnimator {
  private action: { name: ActionKey; time: number; duration: number } | null = null;

  trigger(name: ActionKey) {
    this.action = { name, time: 0, duration: DURATIONS[name] ?? 1.5 };
  }

  update(av: Avatar, dt: number, t: number) {
    const spine = av.bone('spine');
    const chest = av.bone('chest');
    const hips = av.bone('hips');
    if (spine) spine.rotation.x = av.base(spine).x + 0.015 * Math.sin(t * 1.5);
    if (chest) chest.rotation.x = av.base(chest).x + 0.02 * Math.sin(t * 1.5 + 0.4);
    if (hips) hips.rotation.y = av.base(hips).y + 0.03 * Math.sin(t * 0.5);

    const head = av.bone('head');
    let headRx = 0.02 * Math.sin(t * 0.7 + 1);
    let headRy = 0.04 * Math.sin(t * 0.5);

    const la = av.bone('leftUpperArm');
    const ra = av.bone('rightUpperArm');
    const rl = av.bone('rightLowerArm');
    const raOffset = av.armR.down;
    if (la) {
      la.rotation[av.armL.axis] =
        av.base(la)[av.armL.axis] + av.armL.down + 0.02 * Math.sin(t * 1.5 + 0.4);
    }

    if (this.action) {
      this.action.time += dt;
      const p = Math.min(this.action.time / this.action.duration, 1);
      const e = envelope(p);
      if (this.action.name === 'nod') {
        headRx += e * 0.3 * Math.sin(p * Math.PI * 4);
      } else if (this.action.name === 'shake') {
        headRy += e * 0.4 * Math.sin(p * Math.PI * 4);
      }
      if (p >= 1) this.action = null;
    }

    if (ra) {
      ra.rotation[av.armR.axis] =
        av.base(ra)[av.armR.axis] + raOffset + 0.02 * Math.sin(t * 1.5);
    }
    if (rl) {
      rl.rotation[av.armR.axis] = av.base(rl)[av.armR.axis];
    }
    if (head) {
      const hb = av.base(head);
      head.rotation.set(hb.x + headRx, hb.y + headRy, hb.z);
    }
  }
}
