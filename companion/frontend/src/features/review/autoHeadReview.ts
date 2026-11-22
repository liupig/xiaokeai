import * as THREE from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { api, encodeAssetPath, type AssetItem } from '../../api/client';
import { outsideSafeFrame } from '../../engine/framing';
import { acceptsShot } from '../../engine/shotRules';
import { CameraRig } from '../../engine/camera';
import { stage } from '../../engine/stage';
import type { CamShotId } from '../../engine/types';
import type { StandSlot } from '../../engine/stage';
import { useAssetsStore } from '../../stores/assets';
import { parseMotionCat } from '../assets/motionMeta';
import {
  SIZES, STANDS, comboId,
  type ActionPick, type CamPick, type Verdict,
} from './camReview';

interface AuditContext {
  cam: CamPick;
  stand: StandSlot;
  size?: CamShotId;
  rig: CameraRig;
  camera: THREE.PerspectiveCamera;
  projected: THREE.Vector3;
  outside: number;
  firstOutside?: number;
  headOutside?: number;
  limbsOutside?: number;
  duration: number;
  failed: boolean;
  loaded: boolean;
}

export interface HeadAuditSample {
  combo_id: string;
  ratio: number;
  verdict: Verdict;
  firstOutside?: number;
  headOutside?: number;
  limbsOutside?: number;
}

export interface MotionAuditResult {
  ok: boolean;
  verdicts: Record<string, Verdict>;
  samples: HeadAuditSample[];
  remove: string[];
  skipped: number;
}

function makeContext(cam: CamPick, stand: StandSlot, standX: number, size?: CamShotId): AuditContext {
  const camera = stage.threeCamera.clone();
  camera.aspect = stage.threeCamera.aspect;
  camera.updateProjectionMatrix();
  const controls = { target: new THREE.Vector3(), enabled: true } as OrbitControls;
  const rig = new CameraRig(camera, controls);
  rig.headY = stage.cameraHeadY;
  rig.focusX = standX;
  rig.playFramedShot(size ?? 'close', undefined, true);
  return {
    cam, stand, size, rig, camera, projected: new THREE.Vector3(),
    outside: 0, duration: 0, failed: false, loaded: true,
  };
}

function cameraPath(name: string) {
  return name.includes('/') ? name.replace(/^assets\//, '') : `cameras/${name}`;
}

function boundCameraPath(asset: AssetItem) {
  try {
    const bound = JSON.parse(asset.meta || '{}').camera;
    return typeof bound === 'string' ? bound.replace(/^assets\//, '').replace(/^\//, '') : '';
  } catch {
    return '';
  }
}

function camsForMotion(asset: AssetItem, cams: CamPick[]) {
  if (parseMotionCat(asset) !== 'dance') return cams;
  const bound = boundCameraPath(asset);
  if (bound) {
    return cams.filter((cam) => cam.kind !== 'vmd' || cameraPath(cam.name) === bound);
  }
  const dedicated = new Set<string>();
  for (const motion of useAssetsStore().motions) {
    const path = boundCameraPath(motion);
    if (path) dedicated.add(path);
  }
  return cams.filter((cam) => cam.kind !== 'vmd' || !dedicated.has(cameraPath(cam.name)));
}

function ratioOf(context: AuditContext) {
  return context.duration > 0 ? Math.min(1, context.outside / context.duration) : 0;
}

function addResult(
  verdicts: Record<string, Verdict>,
  samples: HeadAuditSample[],
  id: string,
  pass: boolean,
  ratio: number,
  firstOutside?: number,
  headOutside?: number,
  limbsOutside?: number,
) {
  const verdict = pass ? 'ok' : 'bad';
  verdicts[id] = verdict;
  samples.push({ combo_id: id, ratio: Number(ratio.toFixed(4)), verdict, firstOutside, headOutside, limbsOutside });
}

export async function auditMotionHead(
  asset: AssetItem,
  action: ActionPick,
  allCams: CamPick[],
  shouldCancel: () => boolean = () => false,
): Promise<MotionAuditResult> {
  const verdicts: Record<string, Verdict> = {};
  const samples: HeadAuditSample[] = [];
  const remove: string[] = [];
  let skipped = 0;
  const url = api.assetUrl(asset);
  const cams = camsForMotion(asset, allCams);
  const dance = parseMotionCat(asset) === 'dance';
  const excluded = allCams.filter((cam) => cam.kind === 'vmd' && !cams.includes(cam));
  for (const stand of STANDS) {
    if (shouldCancel()) return { ok: false, verdicts: {}, samples: [], remove: [], skipped };
    const standX = stage.stand.slotX(stand.id);
    const contexts: AuditContext[] = [];
    try {
      for (const cam of cams) {
        if (cam.kind === 'vmd') {
          const context = makeContext(cam, stand.id, standX);
          context.loaded = await context.rig.playVmd(
            `/assets/${encodeAssetPath(cameraPath(cam.name))}`,
            { once: true },
          );
          contexts.push(context);
        } else {
          for (const size of SIZES) {
            if (cam.kind === 'move' && !acceptsShot(size.id, cam.id)) continue;
            const context = makeContext(cam, stand.id, standX, size.id);
            if (cam.kind === 'move') context.rig.playFramedShot(size.id, cam.id);
            contexts.push(context);
          }
        }
      }
      const sampled = await stage.sampleMotionHead(url, standX, (points, dt, time, duration) => {
        if (shouldCancel()) throw new Error('auto-review-cancelled');
        const limbs = dance ? stage.framingLimbPoints() : [];
        for (const context of contexts) {
          if (!context.loaded) continue;
          context.duration = duration;
          context.rig.update(dt);
          context.camera.updateMatrixWorld(true);
          const checkLimbs = dance && (context.size === 'full' || context.size === 'long' || context.cam.kind === 'vmd');
          const clippedHead = outsideSafeFrame(context.camera, points, context.projected);
          const clippedLimbs = checkLimbs && outsideSafeFrame(context.camera, limbs, context.projected);
          if (clippedHead) context.headOutside = (context.headOutside ?? 0) + dt;
          if (clippedLimbs) context.limbsOutside = (context.limbsOutside ?? 0) + dt;
          if (clippedHead || clippedLimbs) {
            context.outside += dt;
            context.firstOutside ??= time;
          }
        }
      });
      if (!sampled) return { ok: false, verdicts: {}, samples: [], remove: [], skipped: skipped + 1 };
      for (const context of contexts) context.failed = ratioOf(context) > 1 / 8 + 1e-6;
      for (const cam of cams) {
        const owned = contexts.filter((c) => c.cam === cam);
        if (owned.some((c) => !c.loaded)) {
          skipped += 1;
          continue;
        }
        if (cam.kind === 'vmd') {
          const context = owned[0];
          for (const size of SIZES) {
            addResult(
              verdicts, samples,
              comboId({ size: size.id, cam, stand: stand.id, action }),
              !context.failed, ratioOf(context), context.firstOutside, context.headOutside, context.limbsOutside,
            );
          }
        } else {
          for (const size of SIZES) {
            const context = owned.find((c) => c.size === size.id);
            if (!context) continue;
            addResult(
              verdicts, samples,
              comboId({ size: size.id, cam, stand: stand.id, action }),
              !context.failed, ratioOf(context), context.firstOutside, context.headOutside, context.limbsOutside,
            );
          }
        }
      }
      for (const cam of excluded) {
        for (const size of SIZES) remove.push(comboId({ size: size.id, cam, stand: stand.id, action }));
      }
    } finally {
      for (const context of contexts) context.rig.stopVmd(false);
    }
  }
  return { ok: true, verdicts, samples, remove, skipped };
}
