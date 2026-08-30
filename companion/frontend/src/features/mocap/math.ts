import { Quaternion, Vector3 } from 'three';

/** One-Euro 滤波（Casiez 2012）：静止时压抖动，快速动作时放宽截止。 */
export class OneEuroFilter {
  private prev: number | null = null;
  private prevDeriv = 0;
  private prevTs: number | null = null;

  constructor(
    private minCutoff: number,
    private beta: number,
    private dCutoff: number,
  ) {}

  filter(value: number, ts: number): number {
    if (this.prev === null || this.prevTs === null) {
      this.prev = value;
      this.prevTs = ts;
      return value;
    }
    const dt = (ts - this.prevTs) / 1000;
    if (dt <= 0 || dt > 1) {
      this.prev = value;
      this.prevDeriv = 0;
      this.prevTs = ts;
      return value;
    }
    const rawDeriv = (value - this.prev) / dt;
    const aD = OneEuroFilter.alpha(this.dCutoff, dt);
    const filteredDeriv = aD * rawDeriv + (1 - aD) * this.prevDeriv;
    const cutoff = this.minCutoff + this.beta * Math.abs(filteredDeriv);
    const a = OneEuroFilter.alpha(cutoff, dt);
    const filtered = a * value + (1 - a) * this.prev;
    this.prev = filtered;
    this.prevDeriv = filteredDeriv;
    this.prevTs = ts;
    return filtered;
  }

  reset() {
    this.prev = null;
    this.prevDeriv = 0;
    this.prevTs = null;
  }

  private static alpha(cutoff: number, dt: number): number {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }
}

/** 用真实角速度驱动的四元数 One-Euro，避免按分量滤波。 */
export class QuaternionOneEuroFilter {
  private prev = new Quaternion();
  private hasPrev = false;
  private prevTs = 0;
  private prevSpeed = 0;
  private speedFilter: OneEuroFilter;
  maxSpeed = 30;
  maxAccel = 450;

  constructor(
    private minCutoff: number,
    private beta: number,
    dCutoff: number,
  ) {
    this.speedFilter = new OneEuroFilter(dCutoff, 0, dCutoff);
  }

  filterInto(q: Quaternion, ts: number, out: Quaternion): Quaternion {
    const aligned = _q.copy(q);
    if (this.hasPrev && this.prev.dot(aligned) < 0) aligned.x *= -1, aligned.y *= -1, aligned.z *= -1, aligned.w *= -1;
    if (!this.hasPrev) {
      this.prev.copy(aligned);
      this.hasPrev = true;
      this.prevTs = ts;
      return out.copy(aligned);
    }
    const dt = (ts - this.prevTs) / 1000;
    if (dt <= 0 || dt > 1) {
      this.prev.copy(aligned);
      this.prevTs = ts;
      this.prevSpeed = 0;
      return out.copy(aligned);
    }
    let speed = this.prev.angleTo(aligned) / dt;
    const maxStep = this.prevSpeed + this.maxAccel * dt;
    speed = Math.min(speed, Math.min(this.maxSpeed, maxStep));
    speed = this.speedFilter.filter(speed, ts);
    this.prevSpeed = speed;
    const cutoff = this.minCutoff + this.beta * speed;
    const tau = 1 / (2 * Math.PI * cutoff);
    const a = 1 / (1 + tau / dt);
    out.copy(this.prev).slerp(aligned, a);
    this.prev.copy(out);
    this.prevTs = ts;
    return out;
  }

  reset() {
    this.hasPrev = false;
    this.prevSpeed = 0;
    this.prevTs = 0;
    this.speedFilter.reset();
  }
}

export class Vec3OneEuroFilter {
  private x: OneEuroFilter;
  private y: OneEuroFilter;
  private z: OneEuroFilter;

  constructor(minCutoff: number, beta: number, dCutoff: number) {
    this.x = new OneEuroFilter(minCutoff, beta, dCutoff);
    this.y = new OneEuroFilter(minCutoff, beta, dCutoff);
    this.z = new OneEuroFilter(minCutoff, beta, dCutoff);
  }

  filterInto(v: Vector3, ts: number, out: Vector3): Vector3 {
    out.set(this.x.filter(v.x, ts), this.y.filter(v.y, ts), this.z.filter(v.z, ts));
    return out;
  }

  reset() {
    this.x.reset();
    this.y.reset();
    this.z.reset();
  }
}

const _q = new Quaternion();

export function rotateVec(q: Quaternion, v: Vector3, out: Vector3): Vector3 {
  return out.copy(v).applyQuaternion(q);
}

export function rotateVecInv(q: Quaternion, v: Vector3, out: Vector3): Vector3 {
  return out.copy(v).applyQuaternion(_inv.copy(q).conjugate());
}

const _inv = new Quaternion();
const _mX = new Vector3();
const _mY = new Vector3();
const _mZ = new Vector3();

/** 由正交基构造四元数（列向量 = X, Y, Z）。 */
export function quatFromBasis(x: Vector3, y: Vector3, z: Vector3, out: Quaternion): Quaternion {
  // 旋转矩阵列向量为基，用 setFromRotationMatrix 需要 Matrix4
  // 这里用标准公式避免额外分配
  const m00 = x.x, m01 = y.x, m02 = z.x;
  const m10 = x.y, m11 = y.y, m12 = z.y;
  const m20 = x.z, m21 = y.z, m22 = z.z;
  const trace = m00 + m11 + m22;
  if (trace > 0) {
    const s = 0.5 / Math.sqrt(trace + 1);
    out.set((m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s);
  } else if (m00 > m11 && m00 > m22) {
    const s = 2 * Math.sqrt(1 + m00 - m11 - m22);
    out.set(0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s);
  } else if (m11 > m22) {
    const s = 2 * Math.sqrt(1 + m11 - m00 - m22);
    out.set((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s);
  } else {
    const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
    out.set((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s);
  }
  return out.normalize();
}

/** 由躯干 Y 与原始 X 正交化：X ⊥ Y，Z = X × Y。 */
export function basisFromYAndX(y: Vector3, rawX: Vector3, out: Quaternion): Quaternion {
  const d = rawX.dot(y);
  _mX.copy(rawX).addScaledVector(y, -d);
  if (_mX.lengthSq() < 1e-10) return out.identity();
  _mX.normalize();
  _mY.copy(y).normalize();
  _mZ.crossVectors(_mX, _mY).normalize();
  return quatFromBasis(_mX, _mY, _mZ, out);
}

export function nlerp(a: Quaternion, b: Quaternion, t: number, out: Quaternion): Quaternion {
  let bx = b.x, by = b.y, bz = b.z, bw = b.w;
  if (a.x * bx + a.y * by + a.z * bz + a.w * bw < 0) {
    bx = -bx; by = -by; bz = -bz; bw = -bw;
  }
  out.set(
    a.x + (bx - a.x) * t,
    a.y + (by - a.y) * t,
    a.z + (bz - a.z) * t,
    a.w + (bw - a.w) * t,
  );
  return out.normalize();
}
