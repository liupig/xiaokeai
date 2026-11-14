import * as THREE from 'three';
import { MMDAnimationHelper, MMDLoader } from 'three-stdlib';
import type { VRM } from '@pixiv/three-vrm';
import { createMixamoRig, loadMixamoClip, type MixamoRig } from './mixamo';
import { loadXkMotion } from './xkMotion';

type PoseMap = Map<THREE.Object3D, { pos: THREE.Vector3; quat: THREE.Quaternion }>;

/** 姿势过渡时长（秒）：动作切换 / 停止时从当前姿势平滑混合到目标姿势 */
const BLEND_DURATION = 0.35;
/** 已解析动作很占堆内存，只留最近几条；当前正在播的不踢 */
const CLIP_CACHE_MAX = 6;

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

/**
 * VMD / Mixamo FBX / xiaoke-motion 动作播放器：加载、切换和停止。
 * 新动作没覆盖到的骨骼先回初始姿势，避免上一个动作残留。
 */
export class MotionPlayer {
  active = false;
  suspended = false;
  currentUrl = '';
  onPhysicsReset: (() => void) | null = null;
  /** 动作被 stop / once 播完时回调（切到新动作 / 定格末帧 不会触发） */
  onStopped: (() => void) | null = null;
  /** 定格在动作末帧（goodbye 闲时：坐下就坐着，不弹回站姿） */
  holding = false;

  private root: THREE.Object3D | null = null;
  private mesh: THREE.SkinnedMesh | null = null;
  private mixamoRig: MixamoRig | null = null;
  private helper: MMDAnimationHelper | null = null;
  private mixer: THREE.AnimationMixer | null = null;
  private clipCache = new Map<string, THREE.AnimationClip>();
  private initPose: PoseMap = new Map();
  private loader = new MMDLoader();
  /** 过渡状态：期间暂停动画推进，只做骨骼插值 */
  private blend: {
    from: PoseMap; to: PoseMap; t: number; dur: number;
    onDone: (() => void) | null;
  } | null = null;
  private playSeq = 0;
  /** once 模式：播完一轮剩余时长，<=0 表示循环播放 */
  private onceRemain = 0;
  private holdLast = false;
  private holdPose: PoseMap | null = null;

  /** 绑定角色并记录初始姿势。必须在闲置动画放低手臂前调用，以保留重定向用的绑定姿势。 */
  attach(root: THREE.Object3D, format = 'pmx', vrm: VRM | null = null) {
    this.detach();
    this.root = root;
    this.mesh = (root as THREE.SkinnedMesh).isSkinnedMesh ? root as THREE.SkinnedMesh : null;
    this.mixamoRig = createMixamoRig(root, format, vrm);
    this.captureInitialPose();
  }

  /** PMX 会在 attach 后放低手臂；停止动作应回到自然姿势而不是 T-pose。 */
  captureInitialPose() {
    this.initPose.clear();
    if (!this.mixamoRig) return;
    for (const bone of this.mixamoRig.bones) {
      this.initPose.set(bone, { pos: bone.position.clone(), quat: bone.quaternion.clone() });
    }
  }

  detach() {
    ++this.playSeq;
    this.helper = null;
    this.mixer?.stopAllAction();
    this.mixer = null;
    this.active = false;
    this.holding = false;
    this.holdLast = false;
    this.holdPose = null;
    this.currentUrl = '';
    this.root = null;
    this.mesh = null;
    this.mixamoRig = null;
    const b = this.blend;
    this.blend = null;
    b?.onDone?.();
    this.clipCache.clear();
    this.initPose.clear();
  }

  /** 设置过渡；被打断的上一段过渡立即结束等待（其 onDone 均有 playSeq 守卫） */
  private setBlend(b: NonNullable<MotionPlayer['blend']>) {
    const prev = this.blend;
    this.blend = b;
    prev?.onDone?.();
  }

  private async loadClip(url: string): Promise<THREE.AnimationClip | null> {
    const cached = this.clipCache.get(url);
    if (cached) return cached;
    try {
      let clip: THREE.AnimationClip | null = null;
      if (/\.fbx(?:$|\?)/i.test(url)) {
        if (this.mixamoRig) clip = await loadMixamoClip(url, this.mixamoRig);
      } else if (/\.xkmotion(?:$|\?)/i.test(url)) {
        if (this.mixamoRig) clip = await loadXkMotion(url, this.mixamoRig);
      } else if (this.mesh) {
        clip = await new Promise<THREE.AnimationClip>((resolve, reject) => {
          this.loader.loadAnimation(
            url,
            this.mesh!,
            (c) => resolve(c as THREE.AnimationClip),
            undefined,
            reject,
          );
        });
      }
      if (clip) rememberClip(this.clipCache, url, clip, this.currentUrl);
      return clip;
    } catch (e) {
      console.warn('动作加载失败：', url, e);
      return null;
    }
  }

  private capturePose(): PoseMap {
    const m: PoseMap = new Map();
    if (!this.mixamoRig) return m;
    for (const bone of this.mixamoRig.bones) {
      m.set(bone, { pos: bone.position.clone(), quat: bone.quaternion.clone() });
    }
    return m;
  }

  private applyInitPose() {
    if (!this.root) return;
    for (const [bone, pose] of this.initPose) {
      bone.position.copy(pose.pos);
      bone.quaternion.copy(pose.quat);
    }
    this.root.updateMatrixWorld(true);
  }

  async play(url: string, opts?: { once?: boolean; holdLast?: boolean }): Promise<boolean> {
    const mixerMotion = /\.(?:fbx|xkmotion)(?:$|\?)/i.test(url);
    if (this.suspended || (mixerMotion ? !this.mixamoRig : !this.mesh)) return false;
    const seq = ++this.playSeq;
    this.onceRemain = 0;
    this.holding = false;
    this.holdLast = !!opts?.holdLast;
    this.holdPose = null;

    // MMDLoader 会以当前骨骼位置为基准叠加 VMD 位移；FBX 重定向也要先移除当前动作。
    if (!this.clipCache.has(url)) {
      this.helper = null;
      this.mixer?.stopAllAction();
      this.mixer = null;
      this.active = true;
      await this.blendTo(this.initPose, BLEND_DURATION);
      if (seq !== this.playSeq || !this.root) return false;
      this.applyInitPose();
    }
    const clip = await this.loadClip(url);
    if (!clip || seq !== this.playSeq || !this.root) return false;

    const from = this.capturePose();
    this.applyInitPose();
    this.helper = null;
    this.mixer = null;
    if (mixerMotion) {
      this.mixer = new THREE.AnimationMixer(this.root);
      this.mixer.clipAction(clip).play();
      this.mixer.update(0);
    } else {
      this.helper = new MMDAnimationHelper();
      // physics: false —— 物理由 Stage 主循环自己管理（修复高刷屏加速问题）
      this.helper.add(this.mesh!, { animation: clip, physics: false });
      this.helper.update(0.0001);
    }
    const to = this.capturePose();

    this.active = true;
    this.currentUrl = url;
    if (opts?.once || this.holdLast) this.onceRemain = Math.max(clip.duration, 0.5);
    this.setBlend({
      from, to, t: 0, dur: BLEND_DURATION,
      onDone: () => { if (seq === this.playSeq) this.onPhysicsReset?.(); },
    });
    return true;
  }

  /** 平滑过渡到目标姿势，过渡完成时 resolve（被新的 play/stop 打断也会结束等待） */
  private blendTo(to: PoseMap, dur: number): Promise<void> {
    return new Promise((resolve) => {
      if (!this.root) { resolve(); return; }
      this.setBlend({ from: this.capturePose(), to, t: 0, dur, onDone: resolve });
    });
  }

  stop() {
    if (!this.active && !this.helper && !this.mixer && !this.blend && !this.holding) return;
    const seq = ++this.playSeq;
    this.onceRemain = 0;
    this.holding = false;
    this.holdLast = false;
    this.holdPose = null;
    this.onStopped?.();
    const from = this.capturePose();
    this.helper = null;
    this.mixer?.stopAllAction();
    this.mixer = null;
    this.currentUrl = '';
    // 过渡期间保持 active，避免程序化闲置动画中途抢骨骼；过渡完再交还
    this.active = true;
    this.setBlend({
      from, to: this.initPose, t: 0, dur: BLEND_DURATION,
      onDone: () => {
        if (seq !== this.playSeq) return;
        this.active = false;
        this.onPhysicsReset?.();
      },
    });
  }

  /** 物理步进之后再钉一次末帧，避免刚体把定格姿势拉开 */
  pinHold() {
    if (this.holding) this.applyPose(this.holdPose);
  }

  private applyPose(pose: PoseMap | null) {
    if (!pose || !this.root) return;
    for (const [bone, target] of pose) {
      bone.position.copy(target.pos);
      bone.quaternion.copy(target.quat);
    }
  }

  private freezeLast() {
    this.holdPose = this.capturePose();
    this.helper = null;
    this.mixer?.stopAllAction();
    this.mixer = null;
    this.onceRemain = 0;
    this.holding = true;
    this.active = true;
    this.onPhysicsReset?.();
  }

  private advance(dt: number) {
    if (this.helper) this.helper.update(dt);
    this.mixer?.update(dt);
  }

  update(dt: number) {
    if (this.suspended) return;
    if (this.holding) {
      this.applyPose(this.holdPose);
      return;
    }
    if (this.blend) {
      const b = this.blend;
      b.t += dt;
      const k = Math.min(1, b.t / Math.max(b.dur, 1e-4));
      const e = k * k * (3 - 2 * k);
      for (const [bone, from] of b.from) {
        const to = b.to.get(bone);
        if (!to) continue;
        bone.position.lerpVectors(from.pos, to.pos, e);
        bone.quaternion.slerpQuaternions(from.quat, to.quat, e);
      }
      if (k >= 1) {
        this.blend = null;
        b.onDone?.();
      }
      return;
    }
    if ((this.helper || this.mixer) && this.onceRemain > 0) {
      // 循环回第一帧之前钉住当前姿势
      if (this.holdLast && this.onceRemain <= dt + 0.03) {
        this.freezeLast();
        return;
      }
      this.advance(dt);
      this.onceRemain -= dt;
      if (this.onceRemain <= 0) this.stop();
      return;
    }
    this.advance(dt);
  }

  private headPoints(head: THREE.Object3D): THREE.Vector3[] {
    const root = this.root!;
    root.updateMatrixWorld(true);
    const meshes: THREE.SkinnedMesh[] = [];
    if ((root as THREE.SkinnedMesh).isSkinnedMesh) meshes.push(root as THREE.SkinnedMesh);
    else root.traverse((obj) => {
      if ((obj as THREE.SkinnedMesh).isSkinnedMesh) meshes.push(obj as THREE.SkinnedMesh);
    });
    const selected: { mesh: THREE.SkinnedMesh; index: number }[] = [];
    for (const mesh of meshes) {
      const boneIndex = mesh.skeleton.bones.indexOf(head as THREE.Bone);
      if (boneIndex < 0) continue;
      const indices = mesh.geometry.getAttribute('skinIndex');
      const weights = mesh.geometry.getAttribute('skinWeight');
      if (!indices || !weights) continue;
      for (let i = 0; i < indices.count; i++) {
        const strongest = [0, 1, 2, 3].reduce((best, c) =>
          weights.getComponent(i, c) > weights.getComponent(i, best) ? c : best, 0);
        if (indices.getComponent(i, strongest) === boneIndex && weights.getComponent(i, strongest) >= 0.5) {
          selected.push({ mesh, index: i });
        }
      }
    }
    const points: THREE.Vector3[] = [];
    const stride = Math.max(1, Math.ceil(selected.length / 128));
    for (let i = 0; i < selected.length; i += stride) {
      const { mesh, index } = selected[i];
      const point = mesh.getVertexPosition(index, new THREE.Vector3());
      point.applyMatrix4(mesh.matrixWorld);
      points.push(head.worldToLocal(point));
    }
    if (points.length) return points;

    const center = head.getWorldPosition(new THREE.Vector3());
    for (const x of [-0.13, 0.13]) {
      for (const y of [-0.1, 0.2]) {
        for (const z of [-0.12, 0.12]) {
          points.push(head.worldToLocal(center.clone().add(new THREE.Vector3(x, y, z))));
        }
      }
    }
    return points;
  }

  async sampleHead(
    url: string,
    onSample: (points: THREE.Vector3[], dt: number, time: number, duration: number) => void,
  ): Promise<boolean> {
    const root = this.root;
    if (!root || !this.mixamoRig) return false;
    const clip = await this.loadClip(url);
    if (!clip) return false;
    const head = this.mixamoRig.pairs.find((p) => p.source === 'mixamorigHead')?.target;
    if (!head) return false;
    const localPoints = this.headPoints(head);
    const before = this.capturePose();
    let mixer: THREE.AnimationMixer | null = null;
    let helper: MMDAnimationHelper | null = null;
    try {
      this.applyInitPose();
      if (/\.(?:fbx|xkmotion)(?:$|\?)/i.test(url)) {
        mixer = new THREE.AnimationMixer(root);
        mixer.clipAction(clip).play();
      } else {
        if (!this.mesh) return false;
        helper = new MMDAnimationHelper();
        helper.add(this.mesh, { animation: clip, physics: false });
      }
      const frames = Math.max(1, Math.ceil(clip.duration * 30));
      let previous = 0;
      for (let frame = 0; frame <= frames; frame++) {
        const time = Math.min(clip.duration, frame / 30);
        const dt = Math.max(0, time - previous);
        if (helper) helper.update(dt);
        else mixer?.setTime(time);
        root.updateMatrixWorld(true);
        const points = localPoints.map((p) => head.localToWorld(p.clone()));
        onSample(points, frame === 0 ? 0 : dt, time, clip.duration);
        previous = time;
        if (frame > 0 && frame % 120 === 0) {
          await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        }
      }
      return true;
    } finally {
      if (helper && this.mesh) {
        try { helper.remove(this.mesh); } catch { /* 已移除 */ }
      }
      mixer?.stopAllAction();
      mixer?.uncacheRoot(root);
      for (const [bone, pose] of before) {
        bone.position.copy(pose.pos);
        bone.quaternion.copy(pose.quat);
      }
      root.updateMatrixWorld(true);
    }
  }
}
