import type { CamShotId } from './types';

const sizes: CamShotId[] = ['close', 'bust', 'half', 'threeQ', 'full', 'long'];

export function isSideProfile(move?: CamShotId) {
  return move === 'yawL90' || move === 'yawR90';
}

export function isAdvancedShot(move?: CamShotId) {
  return move === 'high45' || isSideProfile(move);
}

export function minimumShotSize(move?: CamShotId): CamShotId | undefined {
  if (isSideProfile(move)) return 'full';
  if (move === 'high45') return 'threeQ';
  if (move === 'tilt12' || move === 'yawL45' || move === 'yawR45') return 'half';
}

export function acceptsShot(size: CamShotId, move?: CamShotId) {
  const minimum = minimumShotSize(move);
  return !minimum || sizes.indexOf(size) >= sizes.indexOf(minimum);
}

export function safeAutomaticShot(move: CamShotId): CamShotId {
  if (move === 'high45') return 'tilt12';
  if (move === 'yawL90') return 'yawL45';
  if (move === 'yawR90') return 'yawR45';
  return move;
}
