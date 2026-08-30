/**
 * MediaPipe 3D 关键点 → MMD 骨骼父空间四元数。
 * 算法思路参考 Reze MiPo（https://github.com/AmyangXYZ/reze-mipo）：
 * 静止时 parent→child 世界方向即父空间参考方向；每帧将活体节段旋到父空间后 shortest-arc。
 */
import { Quaternion, Vector3 } from 'three';
import {
  OneEuroFilter, QuaternionOneEuroFilter, Vec3OneEuroFilter,
  basisFromYAndX, nlerp, quatFromBasis, rotateVec, rotateVecInv,
} from './math';
import { HandLM, PoseLM } from './landmarks';

export interface XYZ { x: number; y: number; z: number }

export interface BoneState {
  name: string;
  rotation: Quaternion;
  translation?: Vector3;
}

export interface SolverInput {
  poseWorldLandmarks?: { x: number; y: number; z: number; visibility?: number }[][];
  leftHandWorldLandmarks?: { x: number; y: number; z: number }[][];
  rightHandWorldLandmarks?: { x: number; y: number; z: number }[][];
}

type Source = 'pose' | 'leftHand' | 'rightHand';
type Point = string | [string, string];

interface DirDef {
  kind: 'dir';
  name: string;
  parent: string | null;
  source: Source;
  from: Point;
  to: Point;
  witness?: string;
  rollFallback?: string;
}
interface BasisDef { kind: 'basis'; name: '上半身' | '上半身2' | '下半身' | '頭'; parent: string | null }
interface TwistDef {
  kind: 'twist'; name: string; parent: string; source: 'leftHand' | 'rightHand';
  from: string; to: string; axisRef: string;
}
interface RatioDef { kind: 'ratio'; name: string; base: string; axis: Vector3; ratio: number }
type BoneDef = DirDef | BasisDef | TwistDef | RatioDef;

const DEG = Math.PI / 180;
const L: Source = 'leftHand';
const R: Source = 'rightHand';

const BONE_DEFS: BoneDef[] = [
  { kind: 'basis', name: '下半身', parent: null },
  { kind: 'basis', name: '上半身', parent: null },
  { kind: 'basis', name: '上半身2', parent: '上半身' },
  { kind: 'dir', name: '首', parent: '上半身2', source: 'pose', from: ['left_shoulder', 'right_shoulder'], to: ['left_ear', 'right_ear'] },
  { kind: 'basis', name: '頭', parent: '首' },

  { kind: 'dir', name: '左足', parent: '下半身', source: 'pose', from: 'left_hip', to: 'left_knee', witness: '左ひざ', rollFallback: '左足首' },
  { kind: 'dir', name: '右足', parent: '下半身', source: 'pose', from: 'right_hip', to: 'right_knee', witness: '右ひざ', rollFallback: '右足首' },
  { kind: 'dir', name: '左ひざ', parent: '左足', source: 'pose', from: 'left_knee', to: 'left_ankle' },
  { kind: 'dir', name: '右ひざ', parent: '右足', source: 'pose', from: 'right_knee', to: 'right_ankle' },
  { kind: 'dir', name: '左足首', parent: '左ひざ', source: 'pose', from: 'left_ankle', to: 'left_foot_index' },
  { kind: 'dir', name: '右足首', parent: '右ひざ', source: 'pose', from: 'right_ankle', to: 'right_foot_index' },

  { kind: 'dir', name: '左腕', parent: '上半身2', source: 'pose', from: 'left_shoulder', to: 'left_elbow', witness: '左ひじ' },
  { kind: 'dir', name: '右腕', parent: '上半身2', source: 'pose', from: 'right_shoulder', to: 'right_elbow', witness: '右ひじ' },
  { kind: 'dir', name: '左ひじ', parent: '左腕', source: 'pose', from: 'left_elbow', to: 'left_wrist' },
  { kind: 'dir', name: '右ひじ', parent: '右腕', source: 'pose', from: 'right_elbow', to: 'right_wrist' },

  { kind: 'twist', name: '左手捩', parent: '左ひじ', source: L, from: 'ring_mcp', to: 'index_mcp', axisRef: '左ひじ' },
  { kind: 'twist', name: '右手捩', parent: '右ひじ', source: R, from: 'ring_mcp', to: 'index_mcp', axisRef: '右ひじ' },
  { kind: 'dir', name: '左手首', parent: '左手捩', source: L, from: 'wrist', to: 'middle_mcp' },
  { kind: 'dir', name: '右手首', parent: '右手捩', source: R, from: 'wrist', to: 'middle_mcp' },

  { kind: 'dir', name: '左親指１', parent: '左手首', source: L, from: 'thumb_mcp', to: 'thumb_ip' },
  { kind: 'dir', name: '左人指１', parent: '左手首', source: L, from: 'index_mcp', to: 'index_pip' },
  { kind: 'dir', name: '左中指１', parent: '左手首', source: L, from: 'middle_mcp', to: 'middle_pip' },
  { kind: 'dir', name: '左薬指１', parent: '左手首', source: L, from: 'ring_mcp', to: 'ring_pip' },
  { kind: 'dir', name: '左小指１', parent: '左手首', source: L, from: 'pinky_mcp', to: 'pinky_pip' },
  { kind: 'dir', name: '右親指１', parent: '右手首', source: R, from: 'thumb_mcp', to: 'thumb_ip' },
  { kind: 'dir', name: '右人指１', parent: '右手首', source: R, from: 'index_mcp', to: 'index_pip' },
  { kind: 'dir', name: '右中指１', parent: '右手首', source: R, from: 'middle_mcp', to: 'middle_pip' },
  { kind: 'dir', name: '右薬指１', parent: '右手首', source: R, from: 'ring_mcp', to: 'ring_pip' },
  { kind: 'dir', name: '右小指１', parent: '右手首', source: R, from: 'pinky_mcp', to: 'pinky_pip' },

  { kind: 'ratio', name: '左親指２', base: '左親指１', axis: new Vector3(-1, -1, 0).normalize(), ratio: 0.85 },
  { kind: 'ratio', name: '左人指２', base: '左人指１', axis: new Vector3(0, 0, -1), ratio: 0.9 },
  { kind: 'ratio', name: '左人指３', base: '左人指１', axis: new Vector3(0, 0, -1), ratio: 0.65 },
  { kind: 'ratio', name: '左中指２', base: '左中指１', axis: new Vector3(0, 0, -1), ratio: 0.9 },
  { kind: 'ratio', name: '左中指３', base: '左中指１', axis: new Vector3(0, 0, -1), ratio: 0.65 },
  { kind: 'ratio', name: '左薬指２', base: '左薬指１', axis: new Vector3(0, 0, 1), ratio: 0.88 },
  { kind: 'ratio', name: '左薬指３', base: '左薬指１', axis: new Vector3(0, 0, 1), ratio: 0.6 },
  { kind: 'ratio', name: '左小指２', base: '左小指１', axis: new Vector3(0, 0, -1), ratio: 0.85 },
  { kind: 'ratio', name: '左小指３', base: '左小指１', axis: new Vector3(0, 0, -1), ratio: 0.55 },
  { kind: 'ratio', name: '右親指２', base: '右親指１', axis: new Vector3(-1, 1, 0).normalize(), ratio: 0.85 },
  { kind: 'ratio', name: '右人指２', base: '右人指１', axis: new Vector3(0, 0, 1), ratio: 0.9 },
  { kind: 'ratio', name: '右人指３', base: '右人指１', axis: new Vector3(0, 0, 1), ratio: 0.65 },
  { kind: 'ratio', name: '右中指２', base: '右中指１', axis: new Vector3(0, 0, 1), ratio: 0.9 },
  { kind: 'ratio', name: '右中指３', base: '右中指１', axis: new Vector3(0, 0, 1), ratio: 0.65 },
  { kind: 'ratio', name: '右薬指２', base: '右薬指１', axis: new Vector3(0, 0, -1), ratio: 0.88 },
  { kind: 'ratio', name: '右薬指３', base: '右薬指１', axis: new Vector3(0, 0, -1), ratio: 0.6 },
  { kind: 'ratio', name: '右小指２', base: '右小指１', axis: new Vector3(0, 0, 1), ratio: 0.85 },
  { kind: 'ratio', name: '右小指３', base: '右小指１', axis: new Vector3(0, 0, 1), ratio: 0.55 },
];

const DEF_BY = Object.fromEntries(BONE_DEFS.map((d) => [d.name, d]));
const SHOULDER_BONES = ['左肩', '右肩'] as const;
const ARM_TWIST = ['左腕捩', '右腕捩'] as const;
const LEG_OF: Record<string, '左' | '右'> = {
  左足: '左', 左ひざ: '左', 左足首: '左', 右足: '右', 右ひざ: '右', 右足首: '右',
};
const LEG_LMS: Record<'左' | '右', string[]> = {
  左: ['left_knee', 'left_ankle'], 右: ['right_knee', 'right_ankle'],
};
const BASIS_LMS: Record<string, string[]> = {
  上半身: ['left_shoulder', 'right_shoulder'],
  上半身2: ['left_shoulder', 'right_shoulder'],
  下半身: ['left_hip', 'right_hip', 'left_shoulder', 'right_shoulder'],
  頭: ['left_ear', 'right_ear', 'left_eye', 'right_eye'],
};

const MIN_VIS = 0.35;
const VIS_EXIT = 0.25;
const FADE_IN = 250;
const FADE_OUT = 500;
const LOST_GRACE = 250;
const HAND_WARM = 1000;
const HAND_GRACE = 400;
const LEG_WARM = 500;
const LEG_GRACE = 500;
const HEAD_MAX = 100 * DEG;
const PELVIS_SHARE = 0.25;
const CLAVICLE_SHARE = 0.33;
const WITNESS_LO = 0.12;
const WITNESS_HI = 0.45;

type LM = { x: number; y: number; z: number; visibility?: number };

const sFrom = new Vector3();
const sTo = new Vector3();
const sDir = new Vector3();
const sWit = new Vector3();
const sA = new Vector3();
const sB = new Vector3();
const sC = new Vector3();
const sQ = new Quaternion();
const sQ2 = new Quaternion();
const sQ3 = new Quaternion();
const sMeas = new Quaternion();
const sRest = new Vector3();

function lmBuf(n: number): LM[] {
  return Array.from({ length: n }, () => ({ x: 0, y: 0, z: 0, visibility: 0 }));
}

export class Solver {
  private pose: LM[] | null = null;
  private leftHand: LM[] | null = null;
  private rightHand: LM[] | null = null;
  private poseBuf = lmBuf(33);
  private leftBuf = lmBuf(21);
  private rightBuf = lmBuf(21);
  private zFilters: Record<Source, OneEuroFilter[]> = {
    pose: Array.from({ length: 33 }, () => new OneEuroFilter(1, 1, 2)),
    leftHand: Array.from({ length: 21 }, () => new OneEuroFilter(1, 1, 2)),
    rightHand: Array.from({ length: 21 }, () => new OneEuroFilter(1, 1, 2)),
  };
  private zActive: Record<Source, boolean> = { pose: false, leftHand: false, rightHand: false };
  private signalFilters: Record<string, Vec3OneEuroFilter> = {};
  private locals: Record<string, Quaternion> = {};
  private held: Record<string, Quaternion> = {};
  private fades: Record<string, number> = {};
  private lostMs: Record<string, number> = {};
  private worlds: Record<string, Quaternion> = {};
  private filteredWorlds: Record<string, Quaternion> = {};
  private filters: Record<string, QuaternionOneEuroFilter> = {};
  private refs: Record<string, Vector3> = {};
  private restPos: Record<string, XYZ> = {};
  private outputs: BoneState[] = [];
  private byName: Record<string, BoneState> = {};
  private fadePrevTs: number | null = null;
  private frameTs = 0;
  private hasUpper2 = true;
  private chestHalf = new Quaternion();
  private chestHalfSeen = false;
  private chestMeasured = false;
  private pelvisBasis = new Quaternion();
  private pelvisMeasured = false;
  private headPrev = new Quaternion();
  private headSeen = false;
  private heldDy = 0;
  private visOn: Record<string, boolean> = {};
  private handEng = {
    leftHand: { seen: 0, gone: 0, on: false },
    rightHand: { seen: 0, gone: 0, on: false },
  };
  private legEng = {
    左: { seen: 0, gone: 0, on: true },
    右: { seen: 0, gone: 0, on: true },
  };
  private smoothing = { minCutoff: 1.5, beta: 1.5, dCutoff: 4 };

  constructor() {
    const add = (name: string, withT = false) => {
      const st: BoneState = { name, rotation: new Quaternion() };
      if (withT) st.translation = new Vector3();
      this.byName[name] = st;
      this.outputs.push(st);
      this.locals[name] = new Quaternion();
      this.held[name] = new Quaternion();
      this.fades[name] = 0;
      this.lostMs[name] = 0;
      this.worlds[name] = new Quaternion();
      this.filteredWorlds[name] = new Quaternion();
    };
    for (const d of BONE_DEFS) add(d.name);
    for (const n of [...SHOULDER_BONES, ...ARM_TWIST]) add(n);
    add('センター', true);
  }

  reset() {
    this.heldDy = 0;
    this.fadePrevTs = null;
    this.chestHalfSeen = false;
    this.pelvisMeasured = false;
    this.headSeen = false;
    for (const k of Object.keys(this.fades)) {
      this.fades[k] = 0;
      this.lostMs[k] = 0;
      this.held[k].identity();
      this.filters[k]?.reset();
    }
    for (const s of ['leftHand', 'rightHand'] as const) {
      this.handEng[s] = { seen: 0, gone: 0, on: false };
    }
    this.legEng.左 = { seen: 0, gone: 0, on: true };
    this.legEng.右 = { seen: 0, gone: 0, on: true };
    for (const f of Object.values(this.signalFilters)) f.reset();
    for (const bank of Object.values(this.zFilters)) for (const f of bank) f.reset();
    const c = this.byName['センター']?.translation;
    if (c) c.set(0, 0, 0);
  }

  calibrate(rest: Record<string, XYZ>) {
    this.restPos = rest;
    this.hasUpper2 = !!rest['上半身2'];
    const dir = (a: string, b: string) => {
      const p = rest[a], c = rest[b];
      if (!p || !c) return null;
      const v = new Vector3(c.x - p.x, c.y - p.y, c.z - p.z);
      return v.length() < 1e-6 ? null : v.normalize();
    };
    const set = (k: string, v: Vector3 | null) => { if (v) this.refs[k] = v; };
    set('左腕', dir('左腕', '左ひじ'));
    set('右腕', dir('右腕', '右ひじ'));
    set('左ひじ', dir('左ひじ', '左手首'));
    set('右ひじ', dir('右ひじ', '右手首'));
    set('左足', dir('左足', '左ひざ'));
    set('右足', dir('右足', '右ひざ'));
    set('左ひざ', dir('左ひざ', '左足首'));
    set('右ひざ', dir('右ひざ', '右足首'));
    set('左足首', dir('左足首', '左つま先'));
    set('右足首', dir('右足首', '右つま先'));
    set('首', dir('首', '頭'));
    const ls = rest['左肩'], rs = rest['右肩'], le = rest['左目'], re = rest['右目'];
    if (ls && rs && le && re) {
      const v = new Vector3(
        (le.x + re.x - ls.x - rs.x) / 2,
        (le.y + re.y - ls.y - rs.y) / 2,
        (le.z + re.z - ls.z - rs.z) / 2,
      );
      if (v.length() > 1e-6) this.refs['首'] = v.normalize();
    }
    set('左手首', dir('左手首', '左中指１'));
    set('右手首', dir('右手首', '右中指１'));
    set('左手捩', dir('左薬指１', '左人指１'));
    set('右手捩', dir('右薬指１', '右人指１'));
    for (const [a, b] of [
      ['左親指１', '左親指２'], ['右親指１', '右親指２'],
      ['左人指１', '左人指２'], ['右人指１', '右人指２'],
      ['左中指１', '左中指２'], ['右中指１', '右中指２'],
      ['左薬指１', '左薬指２'], ['右薬指１', '右薬指２'],
      ['左小指１', '左小指２'], ['右小指１', '右小指２'],
    ] as const) set(a, dir(a, b));
  }

  solve(input: SolverInput, ts: number = performance.now()): BoneState[] {
    this.frameTs = ts;
    this.pose = this.intake(input.poseWorldLandmarks?.[0]?.length === 33 ? input.poseWorldLandmarks[0] : null, 'pose', this.poseBuf, ts);
    this.leftHand = this.intake(input.leftHandWorldLandmarks?.[0]?.length === 21 ? input.leftHandWorldLandmarks[0] : null, 'leftHand', this.leftBuf, ts);
    this.rightHand = this.intake(input.rightHandWorldLandmarks?.[0]?.length === 21 ? input.rightHandWorldLandmarks[0] : null, 'rightHand', this.rightBuf, ts);

    let fadeDt = 33.3;
    if (this.fadePrevTs !== null) {
      const d = ts - this.fadePrevTs;
      if (d > 0) fadeDt = Math.min(d, 100);
    }
    this.fadePrevTs = ts;

    for (const side of ['左', '右'] as const) {
      const g = this.legEng[side];
      if (this.vis('pose', LEG_LMS[side]) >= MIN_VIS) {
        g.seen += fadeDt; g.gone = 0;
        if (g.seen >= LEG_WARM) g.on = true;
      } else {
        g.gone += fadeDt; g.seen = 0;
        if (g.gone >= LEG_GRACE) g.on = false;
      }
    }
    for (const side of ['leftHand', 'rightHand'] as const) {
      const h = this.handEng[side];
      if (this.handConf(side) >= MIN_VIS) {
        h.seen += fadeDt; h.gone = 0;
        if (h.seen >= HAND_WARM) h.on = true;
      } else {
        h.gone += fadeDt;
        if (h.gone >= HAND_GRACE) { h.on = false; h.seen = 0; }
      }
    }

    this.chestMeasured = false;
    this.pelvisMeasured = false;
    for (const def of BONE_DEFS) {
      const local = this.locals[def.name];
      if (def.kind === 'ratio') {
        this.solveRatio(def, local);
        continue;
      }
      let ok = false;
      if (def.kind === 'basis') ok = this.solveBasis(def, sMeas);
      else if (def.kind === 'dir') ok = this.solveDir(def, sMeas);
      else ok = this.solveTwist(def, sMeas);

      if (ok && def.kind !== 'basis' && !this.handOn(def.source)) ok = false;
      const leg = LEG_OF[def.name];
      if (ok && leg && !this.legEng[leg].on) ok = false;

      if (ok) {
        if (sMeas.w < 0) sMeas.set(-sMeas.x, -sMeas.y, -sMeas.z, -sMeas.w);
        this.held[def.name].copy(sMeas);
      }
      let fade = this.fades[def.name];
      let lost = this.lostMs[def.name];
      lost = ok ? 0 : lost + fadeDt;
      this.lostMs[def.name] = lost;
      const src = def.kind === 'basis' ? 'pose' : def.source;
      const grace = lost < LOST_GRACE || (src !== 'pose' && this.handEng[src].on);
      if (ok) fade = Math.min(1, fade + fadeDt / FADE_IN);
      else if (!grace) fade = Math.max(0, fade - fadeDt / FADE_OUT);
      this.fades[def.name] = fade;
      const w = 0.5 - 0.5 * Math.cos(Math.PI * fade);
      const held = this.held[def.name];
      if (w >= 1) local.copy(held);
      else if (w <= 0) local.identity();
      else local.set(held.x * w, held.y * w, held.z * w, held.w * w + (1 - w)).normalize();

      const parent = def.parent ? this.worlds[def.parent] : null;
      if (parent) this.worlds[def.name].multiplyQuaternions(parent, local);
      else this.worlds[def.name].copy(local);
    }

    this.applyClavicle();
    for (const def of BONE_DEFS) {
      if (def.kind === 'ratio') continue;
      const parent = def.parent ? this.worlds[def.parent] : null;
      if (parent) this.worlds[def.name].multiplyQuaternions(parent, this.locals[def.name]);
      else this.worlds[def.name].copy(this.locals[def.name]);
    }

    const sm = this.smoothing;
    const filter = (name: string, src: Quaternion) => {
      let f = this.filters[name];
      if (!f) {
        f = new QuaternionOneEuroFilter(sm.minCutoff, sm.beta, sm.dCutoff);
        this.filters[name] = f;
      }
      f.filterInto(src, ts, this.byName[name].rotation);
    };
    for (const def of BONE_DEFS) filter(def.name, this.locals[def.name]);
    for (const n of SHOULDER_BONES) filter(n, this.locals[n] ?? this.byName[n].rotation);

    for (const def of BONE_DEFS) {
      if (def.kind === 'ratio') continue;
      const parent = def.parent ? this.filteredWorlds[def.parent] : null;
      const local = this.byName[def.name].rotation;
      if (parent) this.filteredWorlds[def.name].multiplyQuaternions(parent, local);
      else this.filteredWorlds[def.name].copy(local);
    }
    this.solveGrounding();
    return this.outputs;
  }

  private intake(src: LM[] | null, source: Source, buf: LM[], ts: number): LM[] | null {
    const bank = this.zFilters[source];
    const on = src !== null;
    if (!on && this.zActive[source]) for (const f of bank) f.reset();
    this.zActive[source] = on;
    if (!src) return null;
    for (let i = 0; i < buf.length; i++) {
      const s = src[i], d = buf[i];
      d.x = s.x; d.y = s.y; d.visibility = s.visibility;
      d.z = bank[i].filter(s.z, ts);
    }
    return buf;
  }

  private handOn(src: Source): boolean {
    return src === 'pose' ? true : this.handEng[src].on;
  }

  private lms(src: Source): LM[] | null {
    return src === 'pose' ? this.pose : src === 'leftHand' ? this.leftHand : this.rightHand;
  }
  private idx(src: Source, name: string) {
    return src === 'pose' ? PoseLM[name] : HandLM[name];
  }

  /** MediaPipe → MMD：Y 轴取反。 */
  private point(src: Source, p: Point, out: Vector3): Vector3 | null {
    const arr = this.lms(src);
    if (!arr) return null;
    if (typeof p === 'string') {
      const lm = arr[this.idx(src, p)];
      if (!lm) return null;
      return out.set(lm.x, -lm.y, lm.z);
    }
    const a = arr[this.idx(src, p[0])], b = arr[this.idx(src, p[1])];
    if (!a || !b) return null;
    return out.set((a.x + b.x) / 2, -(a.y + b.y) / 2, (a.z + b.z) / 2);
  }

  private handConf(src: Source): number {
    const hand = src === 'leftHand' ? this.leftHand : this.rightHand;
    if (!hand || hand.length < 21) return 0;
    const w = hand[HandLM.wrist], m = hand[HandLM.middle_mcp];
    if (!w || !m) return 0;
    if (Math.hypot(m.x - w.x, m.y - w.y, m.z - w.z) < 0.01) return 0;
    const wrist = src === 'leftHand' ? 'left_wrist' : 'right_wrist';
    return this.pose?.[PoseLM[wrist]]?.visibility ?? 1;
  }

  private vis(src: Source, points: Point[]): number {
    if (src !== 'pose') return this.handConf(src);
    if (!this.pose) return 1;
    let worst = 1;
    for (const p of points) {
      for (const n of typeof p === 'string' ? [p] : p) {
        worst = Math.min(worst, this.pose[PoseLM[n]]?.visibility ?? 1);
      }
    }
    return worst;
  }

  private visGate(name: string, src: Source, pts: Point[]): boolean {
    const v = this.vis(src, pts);
    const on = this.visOn[name];
    if (on) {
      if (v < VIS_EXIT) { this.visOn[name] = false; return false; }
      return true;
    }
    if (v >= MIN_VIS) { this.visOn[name] = true; return true; }
    return false;
  }

  private getRef(name: string): Vector3 {
    return this.refs[name] ?? (this.refs[name] = new Vector3(0, name.includes('足') || name.includes('ひざ') ? -1 : 0.8, name.includes('腕') || name.includes('指') || name.includes('手首') ? 0 : -0.2).normalize());
  }

  private filterDir(key: string, v: Vector3) {
    let f = this.signalFilters[key];
    if (!f) {
      f = new Vec3OneEuroFilter(this.smoothing.minCutoff, this.smoothing.beta, this.smoothing.dCutoff);
      this.signalFilters[key] = f;
    }
    f.filterInto(v, this.frameTs, v);
    if (v.lengthSq() > 1e-12) v.normalize();
  }

  private solveDir(def: DirDef, out: Quaternion): boolean {
    if (!this.point(def.source, def.from, sFrom) || !this.point(def.source, def.to, sTo)) return false;
    if (!this.visGate(def.name, def.source, [def.from, def.to])) return false;
    sDir.subVectors(sTo, sFrom);
    if (sDir.lengthSq() < 1e-12) return false;
    sDir.normalize();
    this.filterDir(def.name, sDir);
    if (def.parent) rotateVecInv(this.worlds[def.parent], sDir, sDir);
    if (sDir.lengthSq() < 1e-12) return false;
    sDir.normalize();
    out.setFromUnitVectors(this.getRef(def.name), sDir);
    if (def.witness) this.applyWitness(def, out);
    return true;
  }

  private applyWitness(def: DirDef, out: Quaternion) {
    const wname = def.witness!;
    const wdef = DEF_BY[wname] as DirDef | undefined;
    if (!wdef || wdef.kind !== 'dir') return;
    const restWit = this.getRef(wname);
    if (!this.point(wdef.source, wdef.from, sA) || !this.point(wdef.source, wdef.to, sB)) return;
    sWit.subVectors(sB, sA);
    if (def.parent) rotateVecInv(this.worlds[def.parent], sWit, sWit);
    if (sWit.lengthSq() < 1e-12) return;
    sWit.normalize();
    const dLive = sWit.dot(sDir);
    sA.copy(sWit).addScaledVector(sDir, -dLive);
    const perp = sA.length();
    if (perp < WITNESS_LO) return;
    sA.normalize();
    sRest.copy(restWit).addScaledVector(this.getRef(def.name), -restWit.dot(this.getRef(def.name)));
    if (sRest.lengthSq() < 1e-12) return;
    sRest.normalize();
    sC.crossVectors(this.getRef(def.name), sRest).normalize();
    sB.crossVectors(sDir, sA).normalize();
    quatFromBasis(sRest, sC, this.getRef(def.name), sQ); // rest basis — wait, columns should be restX, restY, restZ
    // rest: X = restWit⊥, Y = bone × restWit⊥, Z = bone?  We want rest→live: liveBasis * inv(restBasis)
    // Use: rest = (boneRef, rest⊥, boneRef × rest⊥) is not unique. Simpler:
    // shortest-arc from restWit⊥ to live⊥, composed onto out, faded.
    sQ.setFromUnitVectors(sRest, sA);
    sQ2.copy(sQ).multiply(out);
    const t = perp <= WITNESS_LO ? 0 : perp >= WITNESS_HI ? 1 : (() => {
      const u = (perp - WITNESS_LO) / (WITNESS_HI - WITNESS_LO);
      return u * u * (3 - 2 * u);
    })();
    if (t <= 0) return;
    nlerp(out, sQ2, t, out);
  }

  private solveTwist(def: TwistDef, out: Quaternion): boolean {
    if (!this.handEng[def.source].on) return false;
    if (!this.point(def.source, def.from, sFrom) || !this.point(def.source, def.to, sTo)) return false;
    sDir.subVectors(sTo, sFrom);
    rotateVecInv(this.worlds[def.parent], sDir, sDir);
    if (sDir.lengthSq() < 1e-12) return false;
    sDir.normalize();
    const axis = this.getRef(def.axisRef);
    const rest = this.getRef(def.name);
    sA.copy(rest).addScaledVector(axis, -rest.dot(axis));
    sB.copy(sDir).addScaledVector(axis, -sDir.dot(axis));
    if (sA.lengthSq() < 1e-8 || sB.lengthSq() < 1e-8) { out.identity(); return true; }
    sA.normalize(); sB.normalize();
    out.setFromUnitVectors(sA, sB);
    // 只保留绕前臂轴的扭转
    const tw = out.x * axis.x + out.y * axis.y + out.z * axis.z;
    const ang = 2 * Math.atan2(tw, out.w);
    out.setFromAxisAngle(axis, ang);
    return true;
  }

  private solveRatio(def: RatioDef, out: Quaternion) {
    const base = this.locals[def.base];
    if (!base) { out.identity(); return; }
    const k = base.x * def.axis.x + base.y * def.axis.y + base.z * def.axis.z;
    const ang = 2 * Math.atan2(k, base.w) * def.ratio;
    out.setFromAxisAngle(def.axis, ang);
  }

  private solveBasis(def: BasisDef, out: Quaternion): boolean {
    if (!this.pose) return false;
    if (!this.visGate(def.name, 'pose', BASIS_LMS[def.name])) return false;
    switch (def.name) {
      case '上半身': {
        if (!this.point('pose', 'left_shoulder', sA) || !this.point('pose', 'right_shoulder', sB)) return false;
        sDir.set((sA.x + sB.x) / 2, (sA.y + sB.y) / 2, (sA.z + sB.z) / 2).normalize();
        this.filterDir('spine', sDir);
        sC.subVectors(sA, sB).normalize();
        this.filterDir('shoulderLine', sC);
        basisFromYAndX(sDir, sC, out);
        if (out.w < 0) out.set(-out.x, -out.y, -out.z, -out.w);
        this.chestMeasured = true;
        if (this.hasUpper2) {
          if (this.pelvisMeasured) {
            sQ.copy(this.pelvisBasis).conjugate();
            sQ2.copy(sQ).multiply(out);
            out.copy(sQ2);
            if (out.w < 0) out.set(-out.x, -out.y, -out.z, -out.w);
          }
          const nPlus = Math.hypot(out.x, out.y, out.z, out.w + 1);
          sQ.set(out.x / nPlus, out.y / nPlus, out.z / nPlus, (out.w + 1) / nPlus);
          this.chestHalf.copy(sQ);
          this.chestHalfSeen = true;
          if (this.pelvisMeasured) out.copy(this.pelvisBasis).multiply(this.chestHalf);
          else out.copy(this.chestHalf);
        }
        return true;
      }
      case '上半身2': {
        if (!this.hasUpper2 || !this.chestMeasured) return false;
        out.copy(this.chestHalf);
        return true;
      }
      case '下半身': {
        if (!this.point('pose', 'left_shoulder', sA) || !this.point('pose', 'right_shoulder', sB)) return false;
        sFrom.set((sA.x + sB.x) / 2, (sA.y + sB.y) / 2, (sA.z + sB.z) / 2);
        if (!this.point('pose', 'left_hip', sA) || !this.point('pose', 'right_hip', sB)) return false;
        sTo.set((sA.x + sB.x) / 2, (sA.y + sB.y) / 2, (sA.z + sB.z) / 2);
        sDir.subVectors(sFrom, sTo).normalize();
        this.filterDir('pelvisUp', sDir);
        sC.subVectors(sA, sB).normalize();
        this.filterDir('hipLine', sC);
        basisFromYAndX(sDir, sC, out);
        this.pelvisBasis.copy(out);
        this.pelvisMeasured = true;
        this.applyPelvisTuck(out);
        return true;
      }
      case '頭': {
        if (!this.point('pose', 'left_ear', sA) || !this.point('pose', 'right_ear', sB)) return false;
        if (!this.point('pose', 'left_eye', sFrom) || !this.point('pose', 'right_eye', sTo)) return false;
        const parent = this.worlds[def.parent!];
        sC.subVectors(sA, sB).normalize();
        this.filterDir('earAxis', sC);
        rotateVecInv(parent, sC, sC).normalize();
        sDir.set(
          (sA.x + sB.x - sFrom.x - sTo.x) / 2,
          (sA.y + sB.y - sFrom.y - sTo.y) / 2,
          (sA.z + sB.z - sFrom.z - sTo.z) / 2,
        ).normalize();
        this.filterDir('headBack', sDir);
        rotateVecInv(parent, sDir, sDir).normalize();
        const d = sC.dot(sDir);
        sC.addScaledVector(sDir, -d).normalize();
        sA.crossVectors(sDir, sC).normalize();
        quatFromBasis(sC, sA, sDir, out);
        if (this.headSeen && out.angleTo(this.headPrev) > HEAD_MAX) return false;
        this.headPrev.copy(out);
        this.headSeen = true;
        return true;
      }
    }
    return false;
  }

  private applyPelvisTuck(out: Quaternion) {
    let sum = 0, n = 0;
    for (const side of ['left', 'right'] as const) {
      if (this.vis('pose', [`${side}_hip`, `${side}_knee`]) < MIN_VIS) continue;
      if (!this.point('pose', `${side}_hip`, sFrom) || !this.point('pose', `${side}_knee`, sTo)) continue;
      sWit.subVectors(sTo, sFrom);
      rotateVecInv(out, sWit, sWit);
      if (sWit.lengthSq() < 1e-12) continue;
      sWit.normalize();
      sum += Math.atan2(-sWit.z, -sWit.y);
      n++;
    }
    if (!n) return;
    sQ.setFromAxisAngle(sA.set(1, 0, 0), (sum / n) * PELVIS_SHARE);
    out.multiply(sQ);
  }

  /** 锁骨承担部分上臂抬升，合成仍指向关键点。 */
  private applyClavicle() {
    for (const [shoulder, arm] of [['左肩', '左腕'], ['右肩', '右腕']] as const) {
      const armQ = this.locals[arm];
      if (!armQ || !this.byName[shoulder]) continue;
      sQ.identity().slerp(armQ, CLAVICLE_SHARE);
      this.locals[shoulder] = this.locals[shoulder] ?? new Quaternion();
      this.locals[shoulder].copy(sQ);
      sQ2.copy(sQ).conjugate();
      armQ.premultiply(sQ2);
    }
  }

  private solveGrounding() {
    const center = this.byName['センター'];
    if (!center?.translation) return;
    const rest = this.restPos;
    if (!this.pose || !rest['左足'] || !rest['右足']) return;
    const ankleY: number[] = [];
    const lowerRest = rest['下半身'];
    const lowerWorld = this.filteredWorlds['下半身'];
    for (const side of ['左', '右'] as const) {
      const hipRest = rest[side + '足'];
      const knee = rest[side + 'ひざ'];
      const ankle = rest[side + '足首'];
      const thighW = this.filteredWorlds[side + '足'];
      const shinW = this.filteredWorlds[side + 'ひざ'];
      if (!hipRest || !knee || !ankle || !thighW || !shinW) continue;
      let hipY = hipRest.y;
      if (lowerRest && lowerWorld) {
        sA.set(hipRest.x - lowerRest.x, hipRest.y - lowerRest.y, hipRest.z - lowerRest.z);
        rotateVec(lowerWorld, sA, sA);
        hipY = lowerRest.y + sA.y;
      }
      sA.set(knee.x - hipRest.x, knee.y - hipRest.y, knee.z - hipRest.z);
      rotateVec(thighW, sA, sA);
      sB.set(ankle.x - knee.x, ankle.y - knee.y, ankle.z - knee.z);
      rotateVec(shinW, sB, sB);
      ankleY.push(hipY + sA.y + sB.y);
    }
    if (!ankleY.length) return;
    const restAnkleY = Math.min(rest['左足首']?.y ?? 0, rest['右足首']?.y ?? 0);
    let rawDy = -Infinity;
    for (const y of ankleY) rawDy = Math.max(rawDy, restAnkleY - y);
    const legRootY = ((rest['左足']?.y ?? 0) + (rest['右足']?.y ?? 0)) / 2;
    const legSpan = Math.max(1e-3, legRootY - restAnkleY);
    rawDy = Math.min(rawDy, legSpan * 0.15);
    const spine = this.filteredWorlds['上半身'];
    if (spine) {
      sA.set(0, 1, 0);
      rotateVec(spine, sA, sA);
      const upright = Math.min(1, Math.max(0, (sA.y - 0.35) / 0.3));
      rawDy = this.heldDy + (rawDy - this.heldDy) * upright;
    }
    if (!Number.isFinite(rawDy)) return;
    this.heldDy = rawDy;
    center.translation.set(0, rawDy, 0);
    center.rotation.identity();
  }
}
