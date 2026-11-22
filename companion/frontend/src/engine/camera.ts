import * as THREE from 'three';
import { MMDAnimationHelper, MMDLoader } from 'three-stdlib';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { CamPreset, CamShotId } from './types';
import { outsideSafeFrame } from './framing';
import { isSideProfile } from './shotRules';

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

const DEG25 = Math.PI * 25 / 180;
const DEG45 = Math.PI / 4;
const DEG90 = Math.PI / 2;
/** MMD 单位 → 米（与 Stage.setupMMD 的 0.08 缩放一致） */
const MMD_SCALE = 0.08;
const BASE_FOV = 30;
const CLIP_CACHE_MAX = 4;

function rememberClip(
  map: Map<string, THREE.AnimationClip>,
  key: string,
  clip: THREE.AnimationClip,
  keep?: string,
) {
  if (map.has(key)) map.delete(key);
  map.set(key, clip);
  while (map.size > CLIP_CACHE_MAX) {
    let drop: string | undefined;
    for (const k of map.keys()) {
      if (k !== keep && k !== key) { drop = k; break; }
    }
    if (drop === undefined) break;
    map.delete(drop);
  }
}

interface ShotSpherical {
  theta: number;
  radius: number;
  height: number;
  lookY: number;
}

export const CAM_SHOTS: { id: CamShotId; label: string; duration: number }[] = [
  { id: 'close', label: '特写', duration: 0.9 },
  { id: 'bust', label: '1/4', duration: 0.9 },
  { id: 'half', label: '1/2', duration: 0.9 },
  { id: 'threeQ', label: '3/4', duration: 1.0 },
  { id: 'full', label: '全身', duration: 0.9 },
  { id: 'long', label: '远景', duration: 1.1 },
  { id: 'tilt12', label: '轻俯12度', duration: 1.3 },
  { id: 'high45', label: '俯拍25度', duration: 1.3 },
  { id: 'yawL45', label: '左侧45度旋转', duration: 1.4 },
  { id: 'yawR45', label: '右侧45度旋转', duration: 1.4 },
  { id: 'yawL90', label: '左转90度', duration: 1.8 },
  { id: 'yawR90', label: '右转90度', duration: 1.8 },
];

const SHOT_IDS = new Set(CAM_SHOTS.map((s) => s.id));

export function isCamShot(name: string): name is CamShotId {
  return SHOT_IDS.has(name as CamShotId);
}

/** 闲时轻运镜：换景别的同时带一点推/移/仰，不拉到特写或远景 */
export type IdleMoveKind = 'driftL' | 'driftR' | 'push' | 'pull' | 'rise' | 'settle';
export const REVIEW_FOV = 32;

/** 镜头预设、程序化运镜、镜头 VMD 播放 */
export class CameraRig {
  headY = 1.35;
  /** 角色站位 X：预设镜头与环绕都以该点为看点（跟拍走动） */
  focusX = 0;
  private lastFocusX = 0;
  private sideProfile = false;
  /** 正在播镜头 VMD：主循环应跳过轨道控制器和 FOV 呼吸 */
  vmdPlaying = false;

  private anim: {
    from: ShotSpherical; to: ShotSpherical;
    t: number; dur: number;
    fov?: { from: number; to: number };
  } | null = null;

  private loader = new MMDLoader();
  private vmdHelper: MMDAnimationHelper | null = null;
  private clipCache = new Map<string, THREE.AnimationClip>();
  private vmdSeq = 0;
  private vmdRemain = 0;
  private vmdDuration = 0;
  private vmdAdapt = false;
  private vmdOffsetX = 0;
  vmdFrozen = false;
  private vmdCacheKey = '';

  constructor(
    private camera: THREE.PerspectiveCamera,
    private controls: OrbitControls,
  ) {}

  /** 角色卸载或换人时复位跟拍锚点 */
  resetFocus() {
    this.focusX = 0;
    this.lastFocusX = 0;
    this.sideProfile = false;
  }

  get driving() {
    return this.vmdPlaying || this.anim !== null;
  }

  /** 镜头始终围着角色转，人保持在画面里。theta=0 正面。 */
  private sph(id: CamShotId, varyAngle = true): ShotSpherical {
    const h = this.headY;
    const jitter = varyAngle ? (Math.random() - 0.5) * 0.06 : 0;
    switch (id) {
      case 'close':
        return { theta: jitter * 0.5, radius: 0.78, height: h + 0.02, lookY: h - 0.04 };
      case 'bust':
        return { theta: jitter * 0.7, radius: h * 0.92, height: h + 0.01, lookY: h - 0.1 };
      case 'threeQ':
        return { theta: jitter * 0.35, radius: h * 1.62, height: h * 0.7, lookY: h * 0.58 };
      case 'long':
        return { theta: jitter * 0.25, radius: h * 3.35, height: h * 0.78, lookY: h * 0.48 };
      case 'full':
        return { theta: jitter * 0.3, radius: h * 2.35, height: h * 0.62, lookY: h * 0.55 };
      case 'half':
      default:
        return { theta: jitter, radius: h * 1.08, height: h - 0.02, lookY: h - 0.12 };
    }
  }

  /** 先确定景别，再应用机位角度，目标构图与上一个镜头无关。 */
  playFramedShot(size: CamShotId, move?: CamShotId, instant = false, fovTarget = REVIEW_FOV, fit?: { points: THREE.Vector3[]; fallback: boolean }, idleMove?: IdleMoveKind) {
    this.stopVmd(false);
    const from = this.readSph();
    const to = this.sph(size, false);
    let actualMove = move;
    switch (move) {
      case 'tilt12': to.height = to.lookY + to.radius * Math.tan(Math.PI / 15); break;
      case 'high45': to.height = to.lookY + to.radius * Math.tan(DEG25); break;
      case 'yawL45': to.theta = -DEG45; break;
      case 'yawR45': to.theta = DEG45; break;
      case 'yawL90': to.theta = -DEG90; break;
      case 'yawR90': to.theta = DEG90; break;
    }
    if (idleMove && !move) {
      if (idleMove === 'push') to.radius *= 0.95;
      if (idleMove === 'pull') to.radius *= 1.06;
    }
    if (fit?.points.length && !this.fitsShot(to, fovTarget, fit.points)) {
      if (fit.fallback) {
        Object.assign(to, this.sph(size, false));
        actualMove = undefined;
      }
      const rise = (to.height - to.lookY) / to.radius;
      const limit = this.headY * 4.2;
      while (to.radius < limit && !this.fitsShot(to, fovTarget, fit.points)) {
        to.radius = Math.min(limit, to.radius * 1.1);
        to.height = to.lookY + to.radius * rise;
      }
    }
    const profile = isSideProfile(actualMove);
    instant ||= this.sideProfile || profile;
    this.sideProfile = profile;
    if (instant) {
      this.anim = null;
      this.applySph(to);
      this.camera.fov = fovTarget;
      this.camera.updateProjectionMatrix();
      return actualMove;
    }
    const delta = to.theta - from.theta;
    to.theta = from.theta + Math.atan2(Math.sin(delta), Math.cos(delta));
    const duration = idleMove && !actualMove ? 2.4 : CAM_SHOTS.find((shot) => shot.id === (actualMove ?? size))?.duration ?? 0.9;
    this.anim = { from, to, t: 0, dur: duration, fov: { from: this.camera.fov, to: fovTarget } };
    return actualMove;
  }

  private fitsShot(shot: ShotSpherical, fov: number, points: THREE.Vector3[]) {
    const camera = new THREE.PerspectiveCamera(fov, this.camera.aspect, this.camera.near, this.camera.far);
    camera.position.set(this.focusX + Math.sin(shot.theta) * shot.radius, shot.height, Math.cos(shot.theta) * shot.radius);
    camera.lookAt(this.focusX, shot.lookY, 0);
    camera.updateMatrixWorld(true);
    return !outsideSafeFrame(camera, points);
  }

  private readSph(): ShotSpherical {
    const fx = this.focusX;
    const dx = this.camera.position.x - fx;
    const dz = this.camera.position.z;
    const radius = Math.max(0.55, Math.hypot(dx, dz));
    return {
      theta: Math.atan2(dx, dz),
      radius,
      height: this.camera.position.y,
      lookY: this.controls.target.y,
    };
  }

  private applySph(s: ShotSpherical) {
    const fx = this.focusX;
    const theta = s.theta;
    const radius = THREE.MathUtils.clamp(s.radius, 0.58, this.headY * 4.2);
    const height = Math.max(0.12, s.height);
    this.camera.position.set(
      fx + Math.sin(theta) * radius,
      height,
      Math.cos(theta) * radius,
    );
    this.controls.target.set(fx, s.lookY, 0);
    this.camera.up.set(0, 1, 0);
    this.camera.lookAt(this.controls.target);
    this.lastFocusX = fx;
  }

  private lerpSph(a: ShotSpherical, b: ShotSpherical, k: number): ShotSpherical {
    return {
      theta: a.theta + (b.theta - a.theta) * k,
      radius: a.radius + (b.radius - a.radius) * k,
      height: a.height + (b.height - a.height) * k,
      lookY: a.lookY + (b.lookY - a.lookY) * k,
    };
  }

  set(preset: CamPreset, instant = false) {
    this.playShot(preset, instant);
  }

  playShot(id: CamShotId, instant = false, duration?: number) {
    this.stopVmd(false);
    const base = CAM_SHOTS.find((s) => s.id === id)?.duration ?? 0.9;
    const dur = duration && duration > 0.3 ? duration : base;
    const from = this.readSph();
    let to: ShotSpherical;
    if (id === 'tilt12') {
      to = { ...from, height: from.lookY + from.radius * Math.tan(Math.PI / 15) };
    } else if (id === 'high45') {
      to = { ...from, height: from.lookY + from.radius * Math.tan(DEG25) };
    } else if (id === 'yawL45') {
      to = { ...from, theta: -DEG45 };
    } else if (id === 'yawR45') {
      to = { ...from, theta: DEG45 };
    } else if (id === 'yawL90') {
      to = { ...from, theta: -DEG90 };
    } else if (id === 'yawR90') {
      to = { ...from, theta: DEG90 };
    } else {
      to = this.sph(id);
    }
    if (instant) {
      this.anim = null;
      this.applySph(to);
      return;
    }
    this.anim = { from, to, t: 0, dur };
  }

  /**
   * 闲时一整镜：落到目标景别，并叠一层轻运镜。
   * 只在当前景别上微推/微移，不改成特写或远景。
   */
  playIdleCut(size: CamShotId, move: IdleMoveKind, duration = 2.4) {
    this.stopVmd(false);
    const dur = Math.max(1.4, duration);
    const from = this.readSph();
    const base = this.sph(size);
    const to: ShotSpherical = { ...base };
    switch (move) {
      case 'driftL':
        to.theta = THREE.MathUtils.clamp(base.theta - 0.18, -0.4, 0.4);
        break;
      case 'driftR':
        to.theta = THREE.MathUtils.clamp(base.theta + 0.18, -0.4, 0.4);
        break;
      case 'push':
        to.radius = base.radius * 0.88;
        break;
      case 'pull':
        to.radius = base.radius * 1.13;
        break;
      case 'rise':
        to.height = base.height + this.headY * 0.055;
        to.lookY = base.lookY - this.headY * 0.02;
        break;
      default:
        break;
    }
    this.anim = { from, to, t: 0, dur };
  }

  async playVmd(url: string, opts?: { once?: boolean; scale?: number; adapt?: boolean }): Promise<boolean> {
    this.stopVmd(false);
    const seq = ++this.vmdSeq;
    const scale = opts?.scale ?? this.vmdScale(opts?.adapt);
    const clip = await this.loadClip(url, scale);
    if (!clip || seq !== this.vmdSeq) return false;
    this.controls.enabled = false;
    this.vmdHelper = new MMDAnimationHelper({ afterglow: 0, sync: false });
    this.vmdHelper.add(this.camera, { animation: clip });
    this.vmdPlaying = true;
    this.vmdCacheKey = `${url}#${scale}`;
    this.vmdDuration = clip.duration;
    this.vmdRemain = opts?.once === false ? 0 : clip.duration;
    this.vmdAdapt = !!opts?.adapt;
    this.sideProfile = false;
    this.anim = null;
    return true;
  }

  stopVmd(restore = true) {
    this.vmdSeq += 1;
    if (this.vmdHelper) {
      if (!restore) this.controls.target.copy(this.vmdHelper.cameraTarget.position);
      try { this.vmdHelper.remove(this.camera); } catch { /* 已移除 */ }
      this.vmdHelper = null;
    }
    this.vmdPlaying = false;
    this.vmdRemain = 0;
    this.vmdOffsetX = 0;
    this.vmdFrozen = false;
    this.controls.enabled = true;
    if (restore) {
      this.camera.up.set(0, 1, 0);
      this.camera.fov = BASE_FOV;
      this.camera.updateProjectionMatrix();
      this.controls.target.set(this.focusX, this.headY * 0.7, 0);
    }
  }

  private vmdScale(adapt?: boolean) {
    return MMD_SCALE * (adapt ? THREE.MathUtils.clamp(this.headY / 1.35, 0.65, 1.6) : 1);
  }

  preloadVmd(url: string, adapt?: boolean) {
    return this.loadClip(url, this.vmdScale(adapt));
  }

  private loadClip(url: string, scale: number): Promise<THREE.AnimationClip | null> {
    const key = `${url}#${scale}`;
    const cached = this.clipCache.get(key);
    if (cached) return Promise.resolve(cached);
    return new Promise((resolve) => {
      this.loader.loadAnimation(
        url,
        this.camera,
        (c) => {
          const scaled = this.scaleClip(c as THREE.AnimationClip, scale);
          rememberClip(this.clipCache, key, scaled, this.vmdCacheKey);
          resolve(scaled);
        },
        undefined,
        (e) => {
          console.warn('镜头 VMD 加载失败：', url, e);
          resolve(null);
        },
      );
    });
  }

  private scaleClip(clip: THREE.AnimationClip, scale: number): THREE.AnimationClip {
    const c = clip.clone();
    for (const track of c.tracks) {
      if (track.name === '.position' || track.name === 'target.position') {
        const vals = track.values;
        for (let i = 0; i < vals.length; i++) vals[i] *= scale;
      }
    }
    return c;
  }

  seekVmd(seconds: number) {
    const mixer = this.vmdHelper?.objects.get(this.camera)?.mixer;
    if (!mixer || this.vmdDuration <= 0) return;
    const target = THREE.MathUtils.clamp(seconds, 0, Math.max(0, this.vmdDuration - 0.0001));
    this.vmdRemain = 0;
    this.vmdFrozen = false;
    this.update(target - mixer.time);
    this.vmdRemain = this.vmdDuration - target;
    this.vmdFrozen = true;
  }

  update(dt: number) {
    if (this.vmdPlaying && this.vmdHelper) {
      if (this.vmdFrozen) return;
      const last = this.vmdRemain > 0 && dt >= this.vmdRemain;
      this.camera.position.x -= this.vmdOffsetX;
      this.vmdHelper.cameraTarget.position.x -= this.vmdOffsetX;
      this.vmdHelper.update(last ? Math.max(0, this.vmdRemain - Math.min(0.0001, this.vmdDuration / 2)) : dt);
      if (this.vmdAdapt) {
        this.vmdOffsetX = this.focusX;
        this.camera.position.x += this.vmdOffsetX;
        this.vmdHelper.cameraTarget.position.x += this.vmdOffsetX;
      }
      this.lastFocusX = this.focusX;
      if (last) this.stopVmd(false);
      else if (this.vmdRemain > 0) this.vmdRemain -= dt;
      return;
    }

    if (this.anim) {
      this.anim.t += dt / this.anim.dur;
      const k = easeInOut(Math.min(this.anim.t, 1));
      this.applySph(this.lerpSph(this.anim.from, this.anim.to, k));
      const fov = this.anim.fov;
      const nextFov = fov ? THREE.MathUtils.lerp(fov.from, fov.to, k) : this.camera.fov;
      if (this.camera.fov !== nextFov) {
        this.camera.fov = nextFov;
        this.camera.updateProjectionMatrix();
      }
      if (this.anim.t >= 1) this.anim = null;
      return;
    }

    const dx = this.focusX - this.lastFocusX;
    if (Math.abs(dx) > 1e-5) {
      this.camera.position.x += dx;
      this.controls.target.x += dx;
      this.lastFocusX = this.focusX;
    }
  }
}
