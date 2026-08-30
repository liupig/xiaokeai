import * as THREE from 'three';
import type { ArmRig, Axis } from '../types';

/** 记录骨骼初始欧拉角，动画时在其基础上叠加 */
export function makeBaseTracker() {
  const map = new Map<THREE.Object3D, THREE.Euler>();
  return (obj: THREE.Object3D) => {
    if (!map.has(obj)) map.set(obj, obj.rotation.clone());
    return map.get(obj)!;
  };
}

/** 自动测量：绕哪个轴、哪个方向旋转上臂能让手臂放下，以及当前手臂下垂角度 */
export function measureArm(
  root: THREE.Object3D,
  upper: THREE.Object3D,
  lower: THREE.Object3D
): ArmRig {
  const armDir = () => {
    root.updateMatrixWorld(true);
    return lower.getWorldPosition(new THREE.Vector3())
      .sub(upper.getWorldPosition(new THREE.Vector3()))
      .normalize();
  };
  const dir0 = armDir();
  const drop0 = Math.asin(THREE.MathUtils.clamp(-dir0.y, -1, 1)); // 当前低于水平的角度

  let best: { axis: Axis; sign: number; dy: number } = { axis: 'z', sign: 1, dy: 0 };
  for (const axis of ['x', 'y', 'z'] as Axis[]) {
    const orig = upper.rotation[axis];
    upper.rotation[axis] = orig + 0.15;
    const dy = armDir().y - dir0.y;
    upper.rotation[axis] = orig;
    if (Math.abs(dy) > Math.abs(best.dy)) best = { axis, sign: dy < 0 ? 1 : -1, dy };
  }
  root.updateMatrixWorld(true);

  const targetDrop = 1.15; // 目标下垂约 66°
  const down = best.sign * Math.max(0, targetDrop - drop0);
  const up = best.sign * -(drop0 + 0.35); // 抬到水平以上约 20°
  return { axis: best.axis, down, up };
}
