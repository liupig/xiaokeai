import * as THREE from 'three';
import { retargetMixamoClip, type MixamoRig } from './mixamo';

export const XK_MOTION_FORMAT = 'xiaoke-motion';
export const XK_MOTION_VERSION = 1;

interface TransformJson {
  position: number[];
  quaternion: number[];
  scale: number[];
}

interface BoneJson extends TransformJson {
  name: string;
  parent: number;
}

export interface XkMotionDocument {
  format: typeof XK_MOTION_FORMAT;
  version: typeof XK_MOTION_VERSION;
  rig: 'mixamo';
  name: string;
  source: string;
  root: TransformJson;
  bones: BoneJson[];
  clip: ReturnType<THREE.AnimationClip['toJSON']>;
}

function transformOf(obj: THREE.Object3D): TransformJson {
  return {
    position: obj.position.toArray(),
    quaternion: obj.quaternion.toArray(),
    scale: obj.scale.toArray(),
  };
}

function applyTransform(obj: THREE.Object3D, json: TransformJson) {
  obj.position.fromArray(json.position);
  obj.quaternion.fromArray(json.quaternion);
  obj.scale.fromArray(json.scale);
}

export function createXkMotionDocument(
  sourceRoot: THREE.Group,
  name: string,
  source: string,
): XkMotionDocument {
  const clip = sourceRoot.animations[0];
  if (!clip) throw new Error(`${name} 没有动画轨道`);
  const bones: THREE.Bone[] = [];
  sourceRoot.traverse((obj) => {
    if ((obj as THREE.Bone).isBone) bones.push(obj as THREE.Bone);
  });
  const indices = new Map(bones.map((bone, index) => [bone, index]));
  return {
    format: XK_MOTION_FORMAT,
    version: XK_MOTION_VERSION,
    rig: 'mixamo',
    name,
    source,
    root: transformOf(sourceRoot),
    bones: bones.map((bone) => ({
      name: bone.name,
      parent: bone.parent ? indices.get(bone.parent as THREE.Bone) ?? -1 : -1,
      ...transformOf(bone),
    })),
    clip: clip.toJSON(),
  };
}

export async function parseXkMotionDocument(doc: XkMotionDocument, rig: MixamoRig): Promise<THREE.AnimationClip> {
  if (doc?.format !== XK_MOTION_FORMAT || doc.version !== XK_MOTION_VERSION
      || doc.rig !== 'mixamo' || !doc.clip || !Array.isArray(doc.bones)) {
    throw new Error('不是受支持的 xiaoke-motion 动作文件');
  }
  const source = new THREE.Group();
  applyTransform(source, doc.root);
  const bones = doc.bones.map((json) => {
    const bone = new THREE.Bone();
    bone.name = json.name;
    applyTransform(bone, json);
    return bone;
  });
  doc.bones.forEach((json, index) => {
    if (json.parent >= 0) bones[json.parent].add(bones[index]);
    else source.add(bones[index]);
  });
  source.animations = [THREE.AnimationClip.parse(doc.clip)];
  source.updateMatrixWorld(true);
  const clip = await retargetMixamoClip(source, rig);
  if (!clip) throw new Error(`${doc.name} 没有可转换的动画轨道`);
  return clip;
}

export async function loadXkMotion(url: string, rig: MixamoRig): Promise<THREE.AnimationClip> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`动作下载失败：HTTP ${response.status}`);
  return parseXkMotionDocument(await response.json(), rig);
}

export function stringifyXkMotion(doc: XkMotionDocument): string {
  return JSON.stringify(doc, (_key, value) =>
    typeof value === 'number' && Number.isFinite(value) ? Number(value.toFixed(6)) : value);
}
