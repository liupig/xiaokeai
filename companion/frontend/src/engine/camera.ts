import * as THREE from 'three';
import { MMDAnimationHelper, MMDLoader } from 'three-stdlib';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { CamPreset, CamShotId } from './types';

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

const DEG45 = Math.PI / 4;
const DEG90 = Math.PI / 2;
/** MMD 单位 → 米（与 Stage.setupMMD 的 0.08 缩放一致） */
const MMD_SCALE = 0.08;
const BASE_FOV = 30;

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
  { id: 'low45', label: '仰拍45度', duration: 1.3 },
  { id: 'high45', label: '俯拍45度', duration: 1.3 },
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

/** 镜头预设、程序化运镜、镜头 VMD 播放 */
export class CameraRig {
  headY = 1.35;
  /** 角色站位 X：预设镜头与环绕都以该点为看点（跟拍走动） */
  focusX = 0;
  private lastFocusX = 0;
  /** 正在播镜头 VMD：主循环应跳过轨道控制器和 FOV 呼吸 */
  vmdPlaying = false;

  private anim: {
    from: ShotSpherical; to: ShotSpherical;
    t: number; dur: number;
  } | null = null;

  private loader = new MMDLoader();
  private vmdHelper: MMDAnimationHelper | null = null;
  private clipCache = new Map<string, THREE.AnimationClip>();
  private vmdSeq = 0;
  private vmdRemain = 0;

  constructor(
    private camera: THREE.PerspectiveCamera,
    private controls: OrbitControls,
  ) {}

  /** 角色卸载或换人时复位跟拍锚点 */
  resetFocus() {
    this.focusX = 0;
    this.lastFocusX = 0;
  }

  get driving() {
    return this.vmdPlaying || this.anim !== null;
  }

  /** 镜头始终围着角色转，人保持在画面里。theta=0 正面。 */
  private sph(id: CamShotId): ShotSpherical {
    const h = this.headY;
    const jitter = (Math.random() - 0.5) * 0.06;
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
    if (id === 'low45') {
      to = { ...from, height: Math.max(0.12, from.lookY - from.radius * Math.tan(DEG45)) };
    } else if (id === 'high45') {
      to = { ...from, height: from.lookY + from.radius * Math.tan(DEG45) };
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

  async playVmd(url: string, opts?: { once?: boolean; scale?: number }): Promise<boolean> {
    this.stopVmd(false);
    const seq = ++this.vmdSeq;
    const clip = await this.loadClip(url);
    if (!clip || seq !== this.vmdSeq) return false;
    const scaled = this.scaleClip(clip, opts?.scale ?? MMD_SCALE);
    this.controls.enabled = false;
    this.vmdHelper = new MMDAnimationHelper({ afterglow: 0, sync: false });
    this.vmdHelper.add(this.camera, { animation: scaled });
    this.vmdPlaying = true;
    this.vmdRemain = opts?.once === false ? 0 : Math.max(scaled.duration, 0.3);
    this.anim = null;
    return true;
  }

  stopVmd(restore = true) {
    this.vmdSeq += 1;
    if (this.vmdHelper) {
      try { this.vmdHelper.remove(this.camera); } catch { /* 已移除 */ }
      this.vmdHelper = null;
    }
    this.vmdPlaying = false;
    this.vmdRemain = 0;
    this.controls.enabled = true;
    if (restore) {
      this.camera.up.set(0, 1, 0);
      this.camera.fov = BASE_FOV;
      this.camera.updateProjectionMatrix();
      this.controls.target.set(this.focusX, this.headY * 0.7, 0);
    }
  }

  private loadClip(url: string): Promise<THREE.AnimationClip | null> {
    const cached = this.clipCache.get(url);
    if (cached) return Promise.resolve(cached);
    return new Promise((resolve) => {
      this.loader.loadAnimation(
        url,
        this.camera,
        (c) => {
          const clip = c as THREE.AnimationClip;
          this.clipCache.set(url, clip);
          resolve(clip);
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

  update(dt: number) {
    if (this.vmdPlaying && this.vmdHelper) {
      const dx = this.focusX - this.lastFocusX;
      if (Math.abs(dx) > 1e-5) {
        this.camera.position.x += dx;
        this.controls.target.x += dx;
        this.lastFocusX = this.focusX;
      }
      this.vmdHelper.update(dt);
      if (this.vmdRemain > 0) {
        this.vmdRemain -= dt;
        if (this.vmdRemain <= 0) this.stopVmd(false);
      }
      return;
    }

    if (this.anim) {
      this.anim.t += dt / this.anim.dur;
      const k = easeInOut(Math.min(this.anim.t, 1));
      this.applySph(this.lerpSph(this.anim.from, this.anim.to, k));
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
