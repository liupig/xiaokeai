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
  private resume = 0;

  pause() {
    this.resume = 0;
  }

  trigger(name: ActionKey) {
    this.action = { name, time: 0, duration: DURATIONS[name] ?? 1.5 };
  }

  /** 停止动作和常驻待机共用同一个放松姿势，避免交接时弹回直立。 */
  placeRest(av: Avatar) {
    const hips = av.bone('hips');
    const spine = av.bone('spine');
    const chest = av.bone('chest');
    const head = av.bone('head');
    if (hips) {
      hips.rotation.copy(av.base(hips));
      hips.rotation.y -= 0.06;
    }
    if (spine) {
      spine.rotation.copy(av.base(spine));
      spine.rotation.z += 0.039;
    }
    if (chest && chest !== spine) {
      chest.rotation.copy(av.base(chest));
      chest.rotation.y += 0.032;
      chest.rotation.z -= 0.023;
    }
    if (head) {
      head.rotation.copy(av.base(head));
      head.rotation.x -= 0.018;
      head.rotation.z -= 0.028;
    }
    for (const [upperKey, lowerKey, rig, easeOut, bend] of [
      ['leftUpperArm', 'leftLowerArm', av.armL, 0, 0.085],
      ['rightUpperArm', 'rightLowerArm', av.armR, 0.065, 0.14],
    ] as const) {
      const upper = av.bone(upperKey);
      const lower = av.bone(lowerKey);
      const lift = Math.sign(rig.up);
      if (upper) {
        upper.rotation.copy(av.base(upper));
        upper.rotation[rig.axis] += rig.down + lift * easeOut;
      }
      if (lower) {
        lower.rotation.copy(av.base(lower));
        lower.rotation[rig.axis] += lift * bend;
      }
    }
  }

  update(av: Avatar, dt: number, t: number) {
    this.placeRest(av);
    this.resume = Math.min(1, this.resume + dt / 0.45);
    const ease = this.resume * this.resume * (3 - 2 * this.resume);
    const breathPhase = t * 1.32 + 0.2 * Math.sin(t * 0.27);
    const breath = ease * Math.sin(breathPhase);
    const shift = ease * (0.72 * Math.sin(t * 0.57) + 0.28 * Math.sin(t * 0.31 + 0.9));
    const spine = av.bone('spine');
    const chest = av.bone('chest');
    const hips = av.bone('hips');
    if (hips) hips.rotation.y += 0.033 * shift;
    if (spine) {
      spine.rotation.x += 0.012 * breath;
      spine.rotation.z += 0.016 * shift;
    }
    if (chest) {
      chest.rotation.x += 0.017 * ease * Math.sin(breathPhase - 0.35);
      chest.rotation.y -= 0.021 * shift;
    }

    const head = av.bone('head');
    let headRx = 0.016 * breath;
    let headRy = -0.026 * shift;

    const la = av.bone('leftUpperArm');
    const ra = av.bone('rightUpperArm');
    if (la) {
      la.rotation[av.armL.axis] += 0.012 * breath + 0.014 * shift;
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
      ra.rotation[av.armR.axis] += -0.01 * breath + 0.01 * shift;
    }
    if (head) {
      head.rotation.x += headRx;
      head.rotation.y += headRy;
      head.rotation.z -= 0.012 * shift;
    }
  }
}
