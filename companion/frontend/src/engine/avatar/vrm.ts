import type { VRM } from '@pixiv/three-vrm';
import type { Avatar, Axis } from '../types';
import { makeBaseTracker, measureArm } from './common';

export function makeVRMAvatar(vrm: VRM): Avatar {
  const base = makeBaseTracker();
  const la = vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
  const ll = vrm.humanoid.getNormalizedBoneNode('leftLowerArm');
  const ra = vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
  const rl = vrm.humanoid.getNormalizedBoneNode('rightLowerArm');
  const armL = la && ll ? measureArm(vrm.scene, la, ll) : { axis: 'z' as Axis, down: 1.15, up: -0.35 };
  const armR = ra && rl ? measureArm(vrm.scene, ra, rl) : { axis: 'z' as Axis, down: -1.15, up: 0.35 };
  return {
    isVRM: true,
    bone: (key) => vrm.humanoid.getNormalizedBoneNode(key),
    beginFrame: () => {},
    setExpr: (key, v) => vrm.expressionManager?.setValue(key, v),
    morphNames: () =>
      vrm.expressionManager?.expressions.map((e) => e.expressionName) ?? [],
    setMorph: (name, v) => vrm.expressionManager?.setValue(name, v),
    update: (dt) => vrm.update(dt),
    base,
    armL,
    armR,
  };
}
