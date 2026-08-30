import * as THREE from 'three';
import type { Avatar, Axis, BoneKey, BoneMap, MorphMap } from '../types';
import { makeBaseTracker, measureArm } from './common';

/** 通用网格适配器：GLB（ARKit）和 MMD（PMX）共用，传入各自的骨骼/形态键映射表 */
export function makeMeshAvatar(
  root: THREE.Object3D,
  BONES: BoneMap,
  MORPHS: MorphMap
): Avatar {
  const base = makeBaseTracker();
  const morphMeshes: THREE.Mesh[] = [];
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.isMesh && mesh.morphTargetDictionary) morphMeshes.push(mesh);
  });
  const findBone = (names: string[]) => {
    for (const name of names) {
      const found = root.getObjectByName(name);
      if (found) return found;
    }
    return null;
  };
  const boneCache = new Map<BoneKey, THREE.Object3D | null>();
  const la = findBone(BONES.leftUpperArm);
  const ll = findBone(BONES.leftLowerArm);
  const ra = findBone(BONES.rightUpperArm);
  const rl = findBone(BONES.rightLowerArm);
  const armL = la && ll ? measureArm(root, la, ll) : { axis: 'z' as Axis, down: 0, up: -1 };
  const armR = ra && rl ? measureArm(root, ra, rl) : { axis: 'z' as Axis, down: 0, up: 1 };
  // 收集所有会被表情系统触碰的形态键索引，每帧统一清零后按最大值合成，
  // 避免多个表情共用同一形态键时相互覆盖
  const usedIndices: { mesh: THREE.Mesh; idx: number }[] = [];
  for (const entries of Object.values(MORPHS)) {
    for (const { name } of entries) {
      for (const mesh of morphMeshes) {
        const idx = mesh.morphTargetDictionary![name];
        if (idx !== undefined) usedIndices.push({ mesh, idx });
      }
    }
  }
  return {
    isVRM: false,
    bone: (key) => {
      if (!boneCache.has(key)) boneCache.set(key, findBone(BONES[key]));
      return boneCache.get(key)!;
    },
    beginFrame: () => {
      for (const { mesh, idx } of usedIndices) mesh.morphTargetInfluences![idx] = 0;
    },
    setExpr: (key, v) => {
      for (const { name, scale } of MORPHS[key]) {
        for (const mesh of morphMeshes) {
          const idx = mesh.morphTargetDictionary![name];
          if (idx !== undefined) {
            mesh.morphTargetInfluences![idx] = Math.max(mesh.morphTargetInfluences![idx], v * scale);
          }
        }
      }
    },
    morphNames: () => {
      const names = new Set<string>();
      for (const mesh of morphMeshes) {
        for (const name of Object.keys(mesh.morphTargetDictionary!)) names.add(name);
      }
      return [...names];
    },
    setMorph: (name, v) => {
      for (const mesh of morphMeshes) {
        const idx = mesh.morphTargetDictionary![name];
        if (idx !== undefined) mesh.morphTargetInfluences![idx] = v;
      }
    },
    update: () => {},
    base,
    armL,
    armR,
  };
}
