import { Euler, Quaternion } from 'three';
import { OneEuroFilter } from './math';

export type FaceMorphWeights = Record<string, number>;

export interface FaceSolverResult {
  eyeRotation: Quaternion;
  morphWeights: FaceMorphWeights;
}

const FaceIndex = {
  LeftEyeUpper: 159, LeftEyeLower: 145, LeftEyeLeft: 33, LeftEyeRight: 133, LeftEyeIris: 468,
  RightEyeUpper: 386, RightEyeLower: 374, RightEyeLeft: 362, RightEyeRight: 263, RightEyeIris: 473,
  UpperLipTop: 13, LowerLipBottom: 14, MouthLeft: 61, MouthRight: 291,
} as const;

const MORPH_ALIASES: Record<string, string[]> = {
  まばたき: ['瞬き', 'blink'],
  ウィンク: ['ウィンク２'],
  ウィンク右: ['ウィンク右２', 'ウインク右'],
  あ: ['あ２', 'aa', 'A'],
  ワ: ['にっこり', 'にやり', 'happy'],
};

interface Landmark {
  x: number; y: number; z?: number;
}

export class FaceSolver {
  private morphNames: Record<string, string> = Object.fromEntries(
    Object.keys(MORPH_ALIASES).map((n) => [n, n]),
  );
  private leftOpen = new OneEuroFilter(2, 15, 1);
  private rightOpen = new OneEuroFilter(2, 15, 1);
  private mouthF = new OneEuroFilter(2, 15, 1);
  private smileF = new OneEuroFilter(2, 15, 1);
  private gazeXF = new OneEuroFilter(2, 10, 1);
  private gazeYF = new OneEuroFilter(2, 10, 1);
  private eyeEuler = new Euler();
  private eyeQuat = new Quaternion();

  configure(availableMorphs: string[]) {
    const avail = new Set(availableMorphs);
    for (const canonical of Object.keys(MORPH_ALIASES)) {
      this.morphNames[canonical] =
        [canonical, ...MORPH_ALIASES[canonical]].find((n) => avail.has(n)) ?? canonical;
    }
  }

  reset() {
    this.leftOpen.reset();
    this.rightOpen.reset();
    this.mouthF.reset();
    this.smileF.reset();
    this.gazeXF.reset();
    this.gazeYF.reset();
  }

  restWeights(): FaceMorphWeights {
    const n = this.morphNames;
    return { [n['まばたき']]: 0, [n['ウィンク']]: 0, [n['ウィンク右']]: 0, [n['あ']]: 0, [n['ワ']]: 0 };
  }

  solve(face: Landmark[], ts: number): FaceSolverResult {
    const names = this.morphNames;
    const empty: FaceSolverResult = {
      eyeRotation: this.eyeQuat.identity(),
      morphWeights: this.restWeights(),
    };
    if (!face || face.length < 474) return empty;

    const leftGaze = this.gaze(face[FaceIndex.LeftEyeLeft], face[FaceIndex.LeftEyeRight], face[FaceIndex.LeftEyeIris]);
    const rightGaze = this.gaze(face[FaceIndex.RightEyeLeft], face[FaceIndex.RightEyeRight], face[FaceIndex.RightEyeIris]);
    const gx = this.gazeXF.filter((leftGaze.x + rightGaze.x) / 2, ts);
    const gy = this.gazeYF.filter((leftGaze.y + rightGaze.y) / 2, ts);
    this.eyeEuler.set(gy * (Math.PI / 12), -gx * (Math.PI / 6), 0);
    this.eyeQuat.setFromEuler(this.eyeEuler);

    // 镜像：用户右眼驱动画面左侧模型眼
    const leftOpen = this.leftOpen.filter(
      this.eyeOpen(face[FaceIndex.RightEyeLeft], face[FaceIndex.RightEyeRight],
        face[FaceIndex.RightEyeUpper], face[FaceIndex.RightEyeLower]), ts);
    const rightOpen = this.rightOpen.filter(
      this.eyeOpen(face[FaceIndex.LeftEyeLeft], face[FaceIndex.LeftEyeRight],
        face[FaceIndex.LeftEyeUpper], face[FaceIndex.LeftEyeLower]), ts);
    const mouth = this.mouthF.filter(
      this.mouthOpen(face[FaceIndex.UpperLipTop], face[FaceIndex.LowerLipBottom],
        face[FaceIndex.MouthLeft], face[FaceIndex.MouthRight]), ts);
    const smile = this.smileF.filter(
      this.smile(face[FaceIndex.UpperLipTop], face[FaceIndex.LowerLipBottom],
        face[FaceIndex.MouthLeft], face[FaceIndex.MouthRight]), ts);

    const leftBlink = 1 - leftOpen;
    const rightBlink = 1 - rightOpen;
    return {
      eyeRotation: this.eyeQuat,
      morphWeights: {
        [names['まばたき']]: (leftBlink + rightBlink) / 2,
        [names['ウィンク']]: leftBlink > 0.5 && rightBlink < 0.3 ? leftBlink : 0,
        [names['ウィンク右']]: rightBlink > 0.5 && leftBlink < 0.3 ? rightBlink : 0,
        [names['あ']]: mouth,
        [names['ワ']]: smile,
      },
    };
  }

  private gaze(el: Landmark, er: Landmark, iris: Landmark) {
    const cx = (el.x + er.x) / 2;
    const cy = (el.y + er.y) / 2;
    const w = Math.abs(el.x - er.x) || 1e-6;
    return {
      x: Math.max(-1, Math.min(1, (iris.x - cx) / (w * 0.5))),
      y: Math.max(-0.5, Math.min(0.5, (iris.y - cy) / (w * 0.25))),
    };
  }

  private eyeOpen(el: Landmark, er: Landmark, up: Landmark, lo: Landmark) {
    const h = dist(up, lo);
    const w = dist(el, er) || 1e-6;
    const ratio = h / w;
    if (ratio <= 0.1) return 0;
    if (ratio >= 0.3) return 1;
    return (ratio - 0.1) / 0.2;
  }

  private mouthOpen(up: Landmark, lo: Landmark, ml: Landmark, mr: Landmark) {
    const h = dist(up, lo);
    const w = dist(ml, mr) || 1e-6;
    const ratio = h / w;
    if (ratio <= 0.18) return 0;
    return Math.max(0, Math.min(1, (ratio - 0.18) / 0.2));
  }

  private smile(up: Landmark, lo: Landmark, ml: Landmark, mr: Landmark) {
    const centerY = (up.y + lo.y) / 2;
    const cornerY = (ml.y + mr.y) / 2;
    const raw = centerY - cornerY;
    if (raw <= 0.008) return 0;
    return Math.max(0, Math.min(1, (raw - 0.008) * 120));
  }
}

function dist(a: Landmark, b: Landmark) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = (a.z ?? 0) - (b.z ?? 0);
  return Math.hypot(dx, dy, dz);
}
