import { Vector3, type PerspectiveCamera } from 'three';

export const FRAME_SAFE_LIMIT = 0.9;

export function outsideSafeFrame(camera: PerspectiveCamera, points: readonly Vector3[], projected = new Vector3()) {
  return points.some(point => {
    projected.copy(point).project(camera);
    return Math.abs(projected.x) > FRAME_SAFE_LIMIT
      || Math.abs(projected.y) > FRAME_SAFE_LIMIT
      || Math.abs(projected.z) > 1;
  });
}

export function predictFraming(current: Vector3[], previous: Vector3[], elapsed: number, lookAhead = 0.45) {
  if (elapsed <= 0 || current.length !== previous.length) return current;
  return current.flatMap((point, index) => {
    const delta = point.clone().sub(previous[index]).multiplyScalar(lookAhead / elapsed).clampLength(0, 0.35);
    return [point, point.clone().add(delta)];
  });
}
