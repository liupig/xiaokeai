import * as THREE from 'three';
import type { VRM } from '@pixiv/three-vrm';
import type { VRMHumanBoneName } from '@pixiv/three-vrm';

/** 求解器需要的静止骨骼世界坐标（按 MMD 名）。 */
export const REST_BONE_NAMES = [
  '左足', '右足', '左ひざ', '右ひざ', '左足首', '右足首',
  '左つま先', '右つま先',
  '首', '頭', '左肩', '右肩', '左目', '右目',
  '上半身', '上半身2', '下半身', 'センター',
  '左腕', '右腕', '左ひじ', '右ひじ', '左手首', '右手首',
  '左腕捩', '右腕捩', '左手捩', '右手捩',
  '左中指１', '右中指１',
  '左親指１', '左親指２', '右親指１', '右親指２',
  '左人指１', '左人指２', '右人指１', '右人指２',
  '左中指２', '右中指２',
  '左薬指１', '左薬指２', '右薬指１', '右薬指２',
  '左小指１', '左小指２', '右小指１', '右小指２',
] as const;

/** MMD 名 → VRM humanoid 名 */
export const MMD_TO_VRM: Record<string, VRMHumanBoneName | undefined> = {
  センター: 'hips',
  下半身: 'hips',
  上半身: 'spine',
  上半身2: 'chest',
  首: 'neck',
  頭: 'head',
  左肩: 'leftShoulder',
  右肩: 'rightShoulder',
  左腕: 'leftUpperArm',
  右腕: 'rightUpperArm',
  左ひじ: 'leftLowerArm',
  右ひじ: 'rightLowerArm',
  左手首: 'leftHand',
  右手首: 'rightHand',
  左足: 'leftUpperLeg',
  右足: 'rightUpperLeg',
  左ひざ: 'leftLowerLeg',
  右ひざ: 'rightLowerLeg',
  左足首: 'leftFoot',
  右足首: 'rightFoot',
  左つま先: 'leftToes',
  右つま先: 'rightToes',
  左目: 'leftEye',
  右目: 'rightEye',
  左親指１: 'leftThumbMetacarpal',
  左親指２: 'leftThumbProximal',
  右親指１: 'rightThumbMetacarpal',
  右親指２: 'rightThumbProximal',
  左人指１: 'leftIndexProximal',
  左人指２: 'leftIndexIntermediate',
  左人指３: 'leftIndexDistal',
  右人指１: 'rightIndexProximal',
  右人指２: 'rightIndexIntermediate',
  右人指３: 'rightIndexDistal',
  左中指１: 'leftMiddleProximal',
  左中指２: 'leftMiddleIntermediate',
  左中指３: 'leftMiddleDistal',
  右中指１: 'rightMiddleProximal',
  右中指２: 'rightMiddleIntermediate',
  右中指３: 'rightMiddleDistal',
  左薬指１: 'leftRingProximal',
  左薬指２: 'leftRingIntermediate',
  左薬指３: 'leftRingDistal',
  右薬指１: 'rightRingProximal',
  右薬指２: 'rightRingIntermediate',
  右薬指３: 'rightRingDistal',
  左小指１: 'leftLittleProximal',
  左小指２: 'leftLittleIntermediate',
  左小指３: 'leftLittleDistal',
  右小指１: 'rightLittleProximal',
  右小指２: 'rightLittleIntermediate',
  右小指３: 'rightLittleDistal',
};

const GLB_ALIASES: Record<string, string[]> = {
  下半身: ['Hips', 'mixamorigHips'],
  上半身: ['Spine', 'mixamorigSpine'],
  上半身2: ['Spine2', 'mixamorigSpine2', 'Spine1', 'mixamorigSpine1'],
  首: ['Neck', 'mixamorigNeck'],
  頭: ['Head', 'mixamorigHead'],
  左肩: ['LeftShoulder', 'mixamorigLeftShoulder'],
  右肩: ['RightShoulder', 'mixamorigRightShoulder'],
  左腕: ['LeftArm', 'mixamorigLeftArm'],
  右腕: ['RightArm', 'mixamorigRightArm'],
  左ひじ: ['LeftForeArm', 'mixamorigLeftForeArm'],
  右ひじ: ['RightForeArm', 'mixamorigRightForeArm'],
  左手首: ['LeftHand', 'mixamorigLeftHand'],
  右手首: ['RightHand', 'mixamorigRightHand'],
  左足: ['LeftUpLeg', 'mixamorigLeftUpLeg'],
  右足: ['RightUpLeg', 'mixamorigRightUpLeg'],
  左ひざ: ['LeftLeg', 'mixamorigLeftLeg'],
  右ひざ: ['RightLeg', 'mixamorigRightLeg'],
  左足首: ['LeftFoot', 'mixamorigLeftFoot'],
  右足首: ['RightFoot', 'mixamorigRightFoot'],
  左つま先: ['LeftToeBase', 'mixamorigLeftToeBase'],
  右つま先: ['RightToeBase', 'mixamorigRightToeBase'],
};

export function findBone(
  root: THREE.Object3D,
  mmdName: string,
  vrm?: VRM | null,
): THREE.Object3D | null {
  if (vrm) {
    const human = MMD_TO_VRM[mmdName];
    if (human) {
      const node = vrm.humanoid.getNormalizedBoneNode(human)
        ?? vrm.humanoid.getRawBoneNode(human);
      if (node) return node;
    }
  }
  const exact = root.getObjectByName(mmdName);
  if (exact) return exact;
  for (const alias of GLB_ALIASES[mmdName] ?? []) {
    const found = root.getObjectByName(alias);
    if (found) return found;
  }
  return null;
}

export interface RestCapture {
  worldPos: Record<string, { x: number; y: number; z: number }>;
  restQuat: Map<string, THREE.Quaternion>;
  restPos: Map<string, THREE.Vector3>;
  bones: Map<string, THREE.Object3D>;
}

const _wp = new THREE.Vector3();

/** 在模型静止姿势下采集骨骼世界坐标与局部位姿。须在程序化摆臂之前调用。 */
export function captureRest(root: THREE.Object3D, vrm?: VRM | null): RestCapture {
  root.updateMatrixWorld(true);
  const worldPos: RestCapture['worldPos'] = {};
  const restQuat = new Map<string, THREE.Quaternion>();
  const restPos = new Map<string, THREE.Vector3>();
  const bones = new Map<string, THREE.Object3D>();
  const names = new Set<string>(REST_BONE_NAMES);
  for (const extra of ['左人指３', '右人指３', '左中指３', '右中指３', '左薬指３', '右薬指３', '左小指３', '右小指３']) {
    names.add(extra);
  }
  for (const name of names) {
    const bone = findBone(root, name, vrm);
    if (!bone) continue;
    bones.set(name, bone);
    bone.getWorldPosition(_wp);
    worldPos[name] = { x: _wp.x, y: _wp.y, z: _wp.z };
    restQuat.set(name, bone.quaternion.clone());
    restPos.set(name, bone.position.clone());
  }
  return { worldPos, restQuat, restPos, bones };
}
