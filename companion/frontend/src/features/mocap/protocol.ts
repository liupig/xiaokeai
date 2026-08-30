/** 主线程 ↔ 动捕 Worker 消息协议（与 MediaPipe 运行时解耦，避免 Worker 被打成 ESM）。 */

export type PoseWorkerRequest =
  | { type: 'init' }
  | { type: 'video'; bitmap: ImageBitmap; ts: number; mediaTs: number }
  | { type: 'reset' };

export interface PoseWorkerResult {
  poseWorldLandmarks?: { x: number; y: number; z: number; visibility?: number }[][];
  leftHandWorldLandmarks?: { x: number; y: number; z: number }[][];
  rightHandWorldLandmarks?: { x: number; y: number; z: number }[][];
  faceLandmarks?: { x: number; y: number; z: number }[][];
  poseLandmarks?: { x: number; y: number; z: number; visibility?: number }[][];
  imageAspect: number;
  inferenceMs: number;
}

export type PoseWorkerResponse =
  | { type: 'ready' }
  | { type: 'result'; result: PoseWorkerResult; mediaTs: number }
  | { type: 'error'; message: string };
