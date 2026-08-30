/** 站台左右站位：直径 1/4 / 1/2 / 3/4 三档，角色根节点缓动走动。 */

export type StandSlot = 'left' | 'center' | 'right';

const SLOT_FRAC: Record<StandSlot, number> = {
  // 相对站台直径：从左缘起 1/4、1/2、3/4 → 相对圆心为 -R/2、0、+R/2
  left: -0.5,
  center: 0,
  right: 0.5,
};

function smootherstep(t: number) {
  const u = Math.min(1, Math.max(0, t));
  return u * u * u * (u * (u * 6 - 15) + 10);
}

export class StandController {
  slot: StandSlot = 'center';
  x = 0;
  radius = 1.6;
  /** 到位回调（用于停掉走路动作） */
  onArrive: (() => void) | null = null;

  private targetX = 0;
  private fromX = 0;
  private travelT = 0;
  private travelDur = 0;
  private moving = false;
  private dir = 0;
  private facing = 0;

  get isMoving() {
    return this.moving;
  }

  slotX(slot: StandSlot) {
    return this.radius * SLOT_FRAC[slot];
  }

  setRadius(r: number) {
    this.radius = Math.max(0.6, r);
    this.targetX = this.slotX(this.slot);
    if (!this.moving) this.x = this.targetX;
  }

  /** 走到指定档位；已在该档则 noop。返回是否开始移动。 */
  goTo(slot: StandSlot): boolean {
    this.slot = slot;
    this.targetX = this.slotX(slot);
    const dist = Math.abs(this.targetX - this.x);
    if (dist < 0.008) {
      this.x = this.targetX;
      this.moving = false;
      this.facing = 0;
      return false;
    }
    this.fromX = this.x;
    this.dir = Math.sign(this.targetX - this.fromX);
    // 平均约 0.5 m/s，近档稍慢、远档略快，避免匀速滑过去
    this.travelDur = Math.min(2.4, Math.max(0.9, dist / 0.5));
    this.travelT = 0;
    this.moving = true;
    return true;
  }

  step(dir: -1 | 1): boolean {
    const order: StandSlot[] = ['left', 'center', 'right'];
    const i = order.indexOf(this.slot);
    const next = order[Math.max(0, Math.min(2, i + dir))];
    return this.goTo(next);
  }

  reset() {
    this.slot = 'center';
    this.x = 0;
    this.targetX = 0;
    this.fromX = 0;
    this.travelT = 0;
    this.travelDur = 0;
    this.moving = false;
    this.dir = 0;
    this.facing = 0;
    this.onArrive = null;
  }

  /**
   * 推进走动：smootherstep 位移 + 中途朝向行走方向的轻微转身。
   * 身体步态交给走路 VMD，这里不再做机械颠簸。
   */
  update(dt: number, root: {
    position: { x: number; y: number };
    rotation: { y: number };
  } | null) {
    if (this.moving) {
      this.travelT += dt;
      const u = Math.min(1, this.travelT / Math.max(this.travelDur, 1e-4));
      const e = smootherstep(u);
      this.x = this.fromX + (this.targetX - this.fromX) * e;
      // 起步/收步时朝向更正，中途略侧身，到位回正对镜头
      this.facing = this.dir * 0.42 * Math.sin(Math.PI * e);

      if (u >= 1) {
        this.x = this.targetX;
        this.facing = 0;
        this.moving = false;
        const cb = this.onArrive;
        this.onArrive = null;
        cb?.();
      }
    }
    if (!root) return;
    root.position.x = this.x;
    root.position.y = 0;
    root.rotation.y = this.facing;
  }
}
