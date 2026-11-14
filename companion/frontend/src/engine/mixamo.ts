import * as THREE from 'three';
import type { VRM, VRMHumanBoneName } from '@pixiv/three-vrm';

interface RestBone {
  pos: THREE.Vector3;
  quat: THREE.Quaternion;
  worldPos: THREE.Vector3;
  worldQuat: THREE.Quaternion;
}

interface BonePair {
  source: string;
  target: THREE.Object3D;
  rest: RestBone;
}

export interface MixamoRig {
  format: string;
  root: THREE.Object3D;
  bones: THREE.Object3D[];
  rest: Map<THREE.Object3D, RestBone>;
  pairs: BonePair[];
  hips: BonePair;
}

const VRM_BONES: [string, VRMHumanBoneName][] = [
  ['Hips', 'hips'],
  ['Spine', 'spine'],
  ['Spine1', 'chest'],
  ['Spine2', 'upperChest'],
  ['Neck', 'neck'],
  ['Head', 'head'],
  ['LeftShoulder', 'leftShoulder'],
  ['LeftArm', 'leftUpperArm'],
  ['LeftForeArm', 'leftLowerArm'],
  ['LeftHand', 'leftHand'],
  ['RightShoulder', 'rightShoulder'],
  ['RightArm', 'rightUpperArm'],
  ['RightForeArm', 'rightLowerArm'],
  ['RightHand', 'rightHand'],
  ['LeftUpLeg', 'leftUpperLeg'],
  ['LeftLeg', 'leftLowerLeg'],
  ['LeftFoot', 'leftFoot'],
  ['LeftToeBase', 'leftToes'],
  ['RightUpLeg', 'rightUpperLeg'],
  ['RightLeg', 'rightLowerLeg'],
  ['RightFoot', 'rightFoot'],
  ['RightToeBase', 'rightToes'],
];

const FINGERS: [string, string, string][] = [
  ['Thumb', 'Thumb', '親指'],
  ['Index', 'Index', '人指'],
  ['Middle', 'Middle', '中指'],
  ['Ring', 'Ring', '薬指'],
  ['Pinky', 'Little', '小指'],
];

for (const [side] of [['Left'], ['Right']] as const) {
  for (const [mixamo, vrm] of FINGERS) {
    for (let i = 1; i <= 3; i++) {
      const segment = i === 1 ? 'Metacarpal' : i === 2 ? 'Proximal' : 'Distal';
      VRM_BONES.push([
        `${side}Hand${mixamo}${i}`,
        `${side.toLowerCase()}${vrm}${segment}` as VRMHumanBoneName,
      ]);
    }
  }
}

const PMX_FINGERS: Record<string, string> = {};
const REST_CHILDREN: Record<string, string> = {};
for (const [side, jp] of [['Left', '左'], ['Right', '右']] as const) {
  REST_CHILDREN[`mixamorig${side}Shoulder`] = `mixamorig${side}Arm`;
  REST_CHILDREN[`mixamorig${side}Arm`] = `mixamorig${side}ForeArm`;
  REST_CHILDREN[`mixamorig${side}ForeArm`] = `mixamorig${side}Hand`;
  REST_CHILDREN[`mixamorig${side}Hand`] = `mixamorig${side}HandMiddle1`;
  REST_CHILDREN[`mixamorig${side}UpLeg`] = `mixamorig${side}Leg`;
  REST_CHILDREN[`mixamorig${side}Leg`] = `mixamorig${side}Foot`;
  REST_CHILDREN[`mixamorig${side}Foot`] = `mixamorig${side}ToeBase`;
  for (const [mixamo, , mmd] of FINGERS) {
    for (let i = 1; i <= 3; i++) {
      const joint = mixamo === 'Thumb' ? i - 1 : i;
      PMX_FINGERS[`mixamorig${side}Hand${mixamo}${i}`] = `${jp}${mmd}${['０', '１', '２'][joint]}`;
      if (i < 3) {
        REST_CHILDREN[`mixamorig${side}Hand${mixamo}${i}`] = `mixamorig${side}Hand${mixamo}${i + 1}`;
      }
    }
  }
}

function snapshot(root: THREE.Object3D) {
  root.updateWorldMatrix(true, true);
  const rest = new Map<THREE.Object3D, RestBone>();
  const bones: THREE.Object3D[] = [];
  root.traverse((obj) => {
    if (!(obj as THREE.Bone).isBone) return;
    bones.push(obj);
    rest.set(obj, {
      pos: obj.position.clone(),
      quat: obj.quaternion.clone(),
      worldPos: obj.getWorldPosition(new THREE.Vector3()),
      worldQuat: obj.getWorldQuaternion(new THREE.Quaternion()),
    });
  });
  return { bones, rest };
}

function buildPairs(root: THREE.Object3D, format: string, vrm: VRM | null, rest: Map<THREE.Object3D, RestBone>) {
  const pairs: BonePair[] = [];
  const used = new Set<THREE.Object3D>();
  const add = (source: string, target: THREE.Object3D | null | undefined) => {
    if (!target || used.has(target)) return;
    const initial = rest.get(target);
    if (!initial) return;
    used.add(target);
    pairs.push({ source: `mixamorig${source}`, target, rest: initial });
  };

  if (format === 'vrm' && vrm) {
    for (const [source, humanBone] of VRM_BONES) {
      add(source, vrm.humanoid.getRawBoneNode(humanBone));
    }
  } else if (format === 'pmx') {
    const find = (...names: string[]) => {
      for (const name of names) {
        const bone = root.getObjectByName(name);
        if (bone) return bone;
      }
      return null;
    };
    add('Hips', find('センター', '下半身', '全ての親'));
    if (find('上半身2')) {
      add('Spine1', find('上半身'));
      add('Spine2', find('上半身2'));
    } else {
      add('Spine', find('上半身'));
    }
    add('Neck', find('首'));
    add('Head', find('頭'));
    for (const [side, jp] of [['Left', '左'], ['Right', '右']] as const) {
      add(`${side}Shoulder`, find(`${jp}肩`));
      add(`${side}Arm`, find(`${jp}腕`));
      add(`${side}ForeArm`, find(`${jp}ひじ`));
      add(`${side}Hand`, find(`${jp}手首`));
      add(`${side}UpLeg`, find(`${jp}足`));
      add(`${side}Leg`, find(`${jp}ひざ`));
      add(`${side}Foot`, find(`${jp}足首`));
      add(`${side}ToeBase`, find(`${jp}つま先`));
    }
    for (const [source, name] of Object.entries(PMX_FINGERS)) {
      const target = find(name);
      if (!target) continue;
      const initial = rest.get(target);
      if (initial) pairs.push({ source, target, rest: initial });
    }
  } else {
    root.traverse((target) => {
      if (!(target as THREE.Bone).isBone) return;
      const source = target.name.replace(/^mixamorig(?=[A-Z])/, '');
      if (!/^(?:Hips|Spine|Neck|Head|Left|Right)/.test(source)) return;
      add(source, target);
    });
  }
  return pairs;
}

/** 在角色仍处于绑定姿势时记录骨骼；之后闲置动画放低手臂不会影响重定向基准。 */
export function createMixamoRig(root: THREE.Object3D, format: string, vrm: VRM | null): MixamoRig | null {
  const { bones, rest } = snapshot(root);
  const pairs = buildPairs(root, format, vrm, rest);
  const hips = pairs.find((p) => p.source === 'mixamorigHips');
  if (!hips || pairs.length < 4) return null;
  return { format, root, bones, rest, pairs, hips };
}

function disposeSource(root: THREE.Object3D) {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry?.dispose();
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) material?.dispose();
  });
}

export async function loadMixamoClip(url: string, rig: MixamoRig): Promise<THREE.AnimationClip | null> {
  const { FBXLoader } = await import('three/examples/jsm/loaders/FBXLoader.js');
  const source = await new FBXLoader().loadAsync(url);
  return retargetMixamoClip(source, rig);
}

/** 把 Mixamo 的世界旋转增量换到目标骨骼上，保留骨骼长度并校准 A-pose / T-pose 差异。 */
export async function retargetMixamoClip(source: THREE.Group, rig: MixamoRig): Promise<THREE.AnimationClip | null> {
  const clip = source.animations[0];
  if (!clip) {
    disposeSource(source);
    return null;
  }
  const { rest: sourceRest } = snapshot(source);
  const before = new Map<THREE.Object3D, { pos: THREE.Vector3; quat: THREE.Quaternion }>();
  for (const bone of rig.bones) {
    before.set(bone, { pos: bone.position.clone(), quat: bone.quaternion.clone() });
  }

  try {
    const mixer = new THREE.AnimationMixer(source);
    mixer.clipAction(clip).play();
    const fps = 30;
    const frames = Math.max(2, Math.ceil(clip.duration * fps) + 1);
    const times = new Float32Array(frames);
    const rotations = new Map<THREE.Object3D, Float32Array>();
    for (const pair of rig.pairs) rotations.set(pair.target, new Float32Array(frames * 4));
    const hipPositions = new Float32Array(frames * 3);
    const sourceHip = source.getObjectByName(rig.hips.source);
    const sourceHipRest = sourceHip ? sourceRest.get(sourceHip) : null;
    if (!sourceHip || !sourceHipRest) return null;

    const sourceRootPos = source.getWorldPosition(new THREE.Vector3());
    const targetRootPos = rig.root.getWorldPosition(new THREE.Vector3());
    const sourceHeight = Math.max(0.001, sourceHipRest.worldPos.y - sourceRootPos.y);
    const targetHeight = Math.max(0.001, rig.hips.rest.worldPos.y - targetRootPos.y);
    const hipScale = targetHeight / sourceHeight;
    const pairBySource = new Map(rig.pairs.map((pair) => [pair.source, pair]));
    const restAlignments = new Map<BonePair, THREE.Quaternion>();
    for (const pair of rig.pairs) {
      const childName = REST_CHILDREN[pair.source];
      const childPair = childName ? pairBySource.get(childName) : null;
      const sourceBone = source.getObjectByName(pair.source);
      const sourceChild = childName ? source.getObjectByName(childName) : null;
      const sourceBoneRest = sourceBone ? sourceRest.get(sourceBone) : null;
      const sourceChildRest = sourceChild ? sourceRest.get(sourceChild) : null;
      if (!childPair || !sourceBoneRest || !sourceChildRest) continue;
      const sourceDirection = sourceChildRest.worldPos.clone().sub(sourceBoneRest.worldPos).normalize();
      const targetDirection = childPair.rest.worldPos.clone().sub(pair.rest.worldPos).normalize();
      if (sourceDirection.lengthSq() < 0.5 || targetDirection.lengthSq() < 0.5) continue;
      restAlignments.set(pair, new THREE.Quaternion().setFromUnitVectors(targetDirection, sourceDirection));
    }
    const srcWorldQuat = new THREE.Quaternion();
    const deltaQuat = new THREE.Quaternion();
    const desiredWorldQuat = new THREE.Quaternion();
    const parentWorldQuat = new THREE.Quaternion();
    const srcHipPos = new THREE.Vector3();
    const targetHipPos = new THREE.Vector3();

    for (let frame = 0; frame < frames; frame++) {
      const time = Math.min(clip.duration, frame / fps);
      times[frame] = time;
      mixer.setTime(time);
      source.updateMatrixWorld(true);
      for (const bone of rig.bones) {
        const rest = rig.rest.get(bone)!;
        bone.position.copy(rest.pos);
        bone.quaternion.copy(rest.quat);
      }
      rig.root.updateMatrixWorld(true);

      for (const pair of rig.pairs) {
        const sourceBone = source.getObjectByName(pair.source);
        if (!sourceBone) continue;
        const initialSource = sourceRest.get(sourceBone);
        if (!initialSource) continue;
        sourceBone.getWorldQuaternion(srcWorldQuat);
        deltaQuat.copy(srcWorldQuat).multiply(initialSource.worldQuat.clone().invert());
        desiredWorldQuat.copy(deltaQuat);
        const alignment = restAlignments.get(pair);
        if (alignment) desiredWorldQuat.multiply(alignment);
        desiredWorldQuat.multiply(pair.rest.worldQuat);
        pair.target.parent?.getWorldQuaternion(parentWorldQuat);
        pair.target.quaternion.copy(parentWorldQuat.invert()).multiply(desiredWorldQuat);
        pair.target.updateMatrixWorld(true);
        pair.target.quaternion.toArray(rotations.get(pair.target)!, frame * 4);
      }

      // 水平位移由站位控制器负责，避免走路时人物和舞台走位叠加成双倍速度。
      sourceHip.getWorldPosition(srcHipPos);
      targetHipPos.copy(rig.hips.rest.worldPos);
      targetHipPos.y += (srcHipPos.y - sourceHipRest.worldPos.y) * hipScale;
      if (rig.hips.target.parent) rig.hips.target.parent.worldToLocal(targetHipPos);
      targetHipPos.toArray(hipPositions, frame * 3);
    }

    const tracks: THREE.KeyframeTrack[] = [];
    for (const pair of rig.pairs) {
      if (!source.getObjectByName(pair.source)) continue;
      tracks.push(new THREE.QuaternionKeyframeTrack(
        `${pair.target.name}.quaternion`, times, rotations.get(pair.target)!,
      ));
    }
    tracks.push(new THREE.VectorKeyframeTrack(
      `${rig.hips.target.name}.position`, times, hipPositions,
    ));
    mixer.stopAllAction();
    return new THREE.AnimationClip(clip.name, clip.duration, tracks);
  } finally {
    for (const [bone, pose] of before) {
      bone.position.copy(pose.pos);
      bone.quaternion.copy(pose.quat);
    }
    rig.root.updateMatrixWorld(true);
    disposeSource(source);
  }
}
