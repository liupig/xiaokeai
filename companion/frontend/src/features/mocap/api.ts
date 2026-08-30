import type { Object3D } from 'three';
import type { VRM } from '@pixiv/three-vrm';
import type { Stage } from '../../engine/stage';
import type { Avatar } from '../../engine/types';
import { captureRest, type RestCapture } from './bones';
import { mocap, type MocapTarget } from './session';

/**
 * 模仿动捕模块对外入口：UI 只调这里，舞台通过 installMocap 挂插件。
 */

let rest: RestCapture | null = null;
let target: MocapTarget | null = null;
let stopMotion: () => void = () => {};

export function installMocap(stage: Stage) {
  stopMotion = () => stage.stopMotion();
  stage.use({
    id: 'mocap',
    onTPose(root: Object3D, vrm: VRM | null) {
      rest = captureRest(root, vrm);
    },
    onAvatarReady(root: Object3D, avatar: Avatar, vrm: VRM | null) {
      if (!rest) rest = captureRest(root, vrm);
      target = { root, avatar, vrm, rest };
      if (mocap.active) mocap.attach(target);
    },
    onAvatarUnload() {
      mocap.detach();
      target = null;
      rest = null;
    },
    onMotionWillPlay() {
      if (mocap.active) mocap.stop();
    },
    applyPose() {
      if (!mocap.active) return false;
      mocap.apply();
      return true;
    },
  });
}

export async function startMocap(file?: File) {
  if (!target) throw new Error('请先加载角色');
  stopMotion();
  mocap.attach(target);
  if (file) await mocap.startVideo(file);
  else await mocap.startCamera();
}

export function stopMocap() {
  mocap.stop();
}
