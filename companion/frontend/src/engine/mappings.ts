import type { BoneMap, MorphMap } from './types';

/** 写实 GLB（RPM / Avaturn / MetaPerson 等）的 ARKit 形态键映射 */
export const GLB_MORPHS: MorphMap = {
  aa: [
    { name: 'viseme_aa', scale: 1 },
    { name: 'jawOpen', scale: 0.6 },
    { name: 'mouthOpen', scale: 0.8 },
  ],
  blink: [
    { name: 'eyeBlinkLeft', scale: 1 },
    { name: 'eyeBlinkRight', scale: 1 },
    { name: 'eyesClosed', scale: 1 },
  ],
  happy: [
    { name: 'mouthSmileLeft', scale: 1 },
    { name: 'mouthSmileRight', scale: 1 },
    { name: 'mouthSmile', scale: 1 },
    { name: 'cheekSquintLeft', scale: 0.5 },
    { name: 'cheekSquintRight', scale: 0.5 },
  ],
  angry: [
    { name: 'browDownLeft', scale: 1 },
    { name: 'browDownRight', scale: 1 },
    { name: 'mouthFrownLeft', scale: 0.4 },
    { name: 'mouthFrownRight', scale: 0.4 },
    { name: 'noseSneerLeft', scale: 0.4 },
    { name: 'noseSneerRight', scale: 0.4 },
  ],
  sad: [
    { name: 'mouthFrownLeft', scale: 0.8 },
    { name: 'mouthFrownRight', scale: 0.8 },
    { name: 'browInnerUp', scale: 1 },
    { name: 'eyeSquintLeft', scale: 0.3 },
    { name: 'eyeSquintRight', scale: 0.3 },
  ],
  relaxed: [
    { name: 'mouthSmileLeft', scale: 0.35 },
    { name: 'mouthSmileRight', scale: 0.35 },
    { name: 'eyeSquintLeft', scale: 0.4 },
    { name: 'eyeSquintRight', scale: 0.4 },
  ],
};

/** GLB（Mixamo/RPM 命名）骨骼映射 */
export const GLB_BONES: BoneMap = {
  hips: ['Hips', 'mixamorigHips'],
  spine: ['Spine', 'mixamorigSpine'],
  chest: ['Spine2', 'mixamorigSpine2', 'Spine1'],
  head: ['Head', 'mixamorigHead'],
  leftUpperArm: ['LeftArm', 'mixamorigLeftArm'],
  rightUpperArm: ['RightArm', 'mixamorigRightArm'],
  leftLowerArm: ['LeftForeArm', 'mixamorigLeftForeArm'],
  rightLowerArm: ['RightForeArm', 'mixamorigRightForeArm'],
};

/** MMD（PMX，日文标准命名）形态键映射 */
export const MMD_MORPHS: MorphMap = {
  aa: [{ name: 'あ', scale: 1 }],
  blink: [{ name: 'まばたき', scale: 1 }, { name: '瞬き', scale: 1 }],
  happy: [
    { name: 'にこり', scale: 0.6 },
    { name: '笑い目', scale: 0.8 },
    { name: 'にっこり', scale: 1 },
    { name: '口角上げ左', scale: 1 },
    { name: '口角上げ右', scale: 1 },
  ],
  angry: [
    { name: '怒り', scale: 1 },
    { name: 'キリッ', scale: 0.6 },
    { name: '口角下げ左', scale: 0.7 },
    { name: '口角下げ右', scale: 0.7 },
  ],
  sad: [
    { name: '困る', scale: 1 },
    { name: '悲しい目', scale: 0.8 },
    { name: '悲しい', scale: 0.8 },
    { name: '口角下げ左', scale: 0.5 },
    { name: '口角下げ右', scale: 0.5 },
  ],
  relaxed: [
    { name: 'なごみ', scale: 1 },
    { name: 'じと目', scale: 0.5 },
    { name: '笑い目', scale: 0.4 },
    { name: '口角上げ左', scale: 0.3 },
    { name: '口角上げ右', scale: 0.3 },
  ],
};

/** MMD（PMX）骨骼映射 */
export const MMD_BONES: BoneMap = {
  hips: ['下半身'],
  spine: ['上半身'],
  chest: ['上半身2', '上半身'],
  head: ['頭'],
  leftUpperArm: ['左腕'],
  rightUpperArm: ['右腕'],
  leftLowerArm: ['左ひじ'],
  rightLowerArm: ['右ひじ'],
};
