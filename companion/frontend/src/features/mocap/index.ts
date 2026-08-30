/** 实时模仿动捕：摄像头 / 本地视频 → MediaPipe Holistic → 当前角色骨骼。 */

export { mocap, mocapState } from './session';
export type { MocapSource, MocapStatus, MocapTarget } from './session';
export { installMocap, startMocap, stopMocap } from './api';
export { default as MocapOverlay } from './Overlay.vue';
export { default as MocapToolbar } from './Toolbar.vue';
