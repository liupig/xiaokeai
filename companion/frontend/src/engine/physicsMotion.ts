import * as THREE from 'three';

const identityRotation = new THREE.Quaternion();

export function isSmallPhysicsPart(name: string) {
  return /(?:^|[左右])ear(?=[_.\d]|$)|earring|zanzi|liusu|daimao|耳饰|耳飾|耳环|耳環|簪|流苏|流蘇|吊坠|吊墜|飾り/i.test(name);
}

/** 只限制相对于动画骨骼的余摆。父骨转头、抬手时不受限速拖拽。 */
export class PhysicsMotion {
  readonly previousRotation = new THREE.Quaternion();
  readonly rotation = new THREE.Quaternion();
  readonly previousOffset = new THREE.Vector3();
  readonly offset = new THREE.Vector3();
  private readonly targetRotation = new THREE.Quaternion();
  private readonly targetOffset = new THREE.Vector3();
  private readonly maxOffset: number;
  private readonly maxAngle: number;
  private readonly maxSpeed: number;

  constructor(private readonly small: boolean, length: number, smallAncestors = 0) {
    const chainScale = 1 + 0.55 * smallAncestors;
    this.maxOffset = small ? 0 : Math.min(0.15, length * 0.12);
    this.maxAngle = small ? 0.20 / chainScale : 0.48;
    this.maxSpeed = small ? 1.6 / chainScale : 3.8;
  }

  reset() {
    this.previousRotation.identity();
    this.rotation.identity();
    this.previousOffset.set(0, 0, 0);
    this.offset.set(0, 0, 0);
  }

  sample(bone: THREE.Object3D, animatedRotation: THREE.Quaternion, animatedPosition: THREE.Vector3, dt: number) {
    this.previousRotation.copy(this.rotation);
    this.previousOffset.copy(this.offset);
    const reference = this.targetRotation.copy(animatedRotation).invert().multiply(bone.quaternion).normalize();
    const angle = 2 * Math.acos(Math.min(1, Math.abs(reference.w)));
    const knee = this.maxAngle * 0.55;
    if (!Number.isFinite(angle)) reference.identity();
    else if (angle > knee) {
      const range = this.maxAngle - knee;
      const shaped = knee + range * -Math.expm1(-(angle - knee) / range);
      reference.slerp(identityRotation, 1 - shaped / angle);
    }
    // 甩开稍快，回落稍慢，让惯性保留一点尾巴。
    const returning = Math.abs(this.rotation.w) < Math.abs(reference.w);
    const rate = this.small ? (returning ? 6.5 : 10) : (returning ? 9 : 14);
    const response = 1 - Math.exp(-rate * dt);
    const gap = this.rotation.angleTo(reference);
    const maxStep = this.maxSpeed * dt;
    this.rotation.slerp(reference, gap > maxStep ? Math.min(response, maxStep / gap) : response).normalize();

    this.targetOffset.subVectors(bone.position, animatedPosition);
    if (!Number.isFinite(this.targetOffset.lengthSq())) this.targetOffset.set(0, 0, 0);
    this.offset.lerp(this.targetOffset.clampLength(0, this.maxOffset), response);
  }
}
