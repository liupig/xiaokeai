import * as THREE from 'three';
import { MMDAnimationHelper, MMDLoader } from 'three-stdlib';

type PoseMap = Map<THREE.Bone, { pos: THREE.Vector3; quat: THREE.Quaternion }>;

/** 姿势过渡时长（秒）：动作切换 / 停止时从当前姿势平滑混合到目标姿势 */
const BLEND_DURATION = 0.35;

/**
 * VMD 动作播放器：运行时加载 / 切换 / 停止。
 * 切换与停止不再瞬间跳变，而是做一段姿势混合过渡；
 * 过渡目标以「初始姿势」为底再叠新动作第一帧，
 * 保证新动作没覆盖到的骨骼也回到初始姿势，杜绝上一个动作的姿势残留叠加。
 */
export class MotionPlayer {
  active = false;
  currentUrl = '';
  onPhysicsReset: (() => void) | null = null;
  /** 动作被 stop / once 播完时回调（切到新动作 / 定格末帧 不会触发） */
  onStopped: (() => void) | null = null;
  /** 定格在动作末帧（goodbye 闲时：坐下就坐着，不弹回站姿） */
  holding = false;

  private mesh: THREE.SkinnedMesh | null = null;
  private helper: MMDAnimationHelper | null = null;
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

  /** 绑定 PMX 模型并记录初始姿势 */
  attach(mesh: THREE.SkinnedMesh) {
    this.detach();
    this.mesh = mesh;
    for (const b of mesh.skeleton.bones) {
      this.initPose.set(b, { pos: b.position.clone(), quat: b.quaternion.clone() });
    }
  }

  detach() {
    ++this.playSeq; // 使进行中的 play 失效
    this.helper = null;
    this.active = false;
    this.holding = false;
    this.holdLast = false;
    this.holdPose = null;
    this.currentUrl = '';
    this.mesh = null;
    const b = this.blend;
    this.blend = null;
    b?.onDone?.(); // 放行等待过渡完成的 Promise（调用方以 playSeq 判定是否继续）
    this.clipCache.clear();
    this.initPose.clear();
  }

  /** 设置过渡；被打断的上一段过渡立即结束等待（其 onDone 均有 playSeq 守卫） */
  private setBlend(b: NonNullable<MotionPlayer['blend']>) {
    const prev = this.blend;
    this.blend = b;
    prev?.onDone?.();
  }

  private loadClip(url: string): Promise<THREE.AnimationClip | null> {
    const cached = this.clipCache.get(url);
    if (cached) return Promise.resolve(cached);
    return new Promise((resolve) => {
      this.loader.loadAnimation(
        url,
        this.mesh!,
        (c) => {
          this.clipCache.set(url, c as THREE.AnimationClip);
          resolve(c as THREE.AnimationClip);
        },
        undefined,
        (e) => {
          console.warn('VMD 动作加载失败：', url, e);
          resolve(null);
        }
      );
    });
  }

  private capturePose(): PoseMap {
    const m: PoseMap = new Map();
    if (!this.mesh) return m;
    for (const b of this.mesh.skeleton.bones) {
      m.set(b, { pos: b.position.clone(), quat: b.quaternion.clone() });
    }
    return m;
  }

  private applyInitPose() {
    if (!this.mesh) return;
    for (const [b, p] of this.initPose) {
      b.position.copy(p.pos);
      b.quaternion.copy(p.quat);
    }
    this.mesh.updateMatrixWorld(true);
  }

  async play(url: string, opts?: { once?: boolean; holdLast?: boolean }): Promise<boolean> {
    if (!this.mesh) return false;
    const seq = ++this.playSeq;
    this.onceRemain = 0;
    this.holding = false;
    this.holdLast = !!opts?.holdLast;
    this.holdPose = null;

    // 关键：MMDLoader 构建动画轨道时以「当前骨骼位置」为基准叠加 VMD 位移
    // （见 MMDLoader._buildSkeletalAnimation 里的 basePosition）。
    // 如果在坐姿等非初始姿势下构建，坐姿会被永久烙进新动作（走路仍弯腿）。
    // 所以：未缓存的动作必须先平滑归位到初始姿势，归位后再加载构建。
    if (!this.clipCache.has(url)) {
      this.helper = null;
      this.active = true; // 归位/加载期间不让程序化闲置动画抢骨骼
      await this.blendTo(this.initPose, BLEND_DURATION);
      if (seq !== this.playSeq || !this.mesh) return false;
      this.applyInitPose(); // 保底：确保构建时骨骼精确处于初始位置
    }
    const clip = await this.loadClip(url);
    if (!clip || seq !== this.playSeq || !this.mesh) return false;

    // 过渡起点 = 当前实际姿势（无论来自上一个 VMD、程序化动作还是待机）
    const from = this.capturePose();
    // 先整体回初始姿势再采样新动作第一帧：
    // 新 clip 没有关键帧的骨骼会落在初始姿势上，不会残留上一个动作
    this.applyInitPose();
    this.helper = new MMDAnimationHelper();
    // physics: false —— 物理由 Stage 主循环自己管理（修复高刷屏加速问题）
    this.helper.add(this.mesh, { animation: clip, physics: false });
    this.helper.update(0.0001);
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
      if (!this.mesh) { resolve(); return; }
      this.setBlend({ from: this.capturePose(), to, t: 0, dur, onDone: resolve });
    });
  }

  stop() {
    if (!this.active && !this.helper && !this.blend && !this.holding) return;
    const seq = ++this.playSeq;
    this.onceRemain = 0;
    this.holding = false;
    this.holdLast = false;
    this.holdPose = null;
    this.onStopped?.();
    const from = this.capturePose();
    this.helper = null;
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
    if (!pose || !this.mesh) return;
    for (const [b, p] of pose) {
      b.position.copy(p.pos);
      b.quaternion.copy(p.quat);
    }
  }

  private freezeLast() {
    this.holdPose = this.capturePose();
    this.helper = null;
    this.onceRemain = 0;
    this.holding = true;
    this.active = true;
    this.onPhysicsReset?.();
  }

  update(dt: number) {
    if (this.holding) {
      this.applyPose(this.holdPose);
      return;
    }
    if (this.blend) {
      const b = this.blend;
      b.t += dt;
      const k = Math.min(1, b.t / Math.max(b.dur, 1e-4));
      const e = k * k * (3 - 2 * k); // smoothstep 缓入缓出
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
    if (this.helper && this.onceRemain > 0) {
      // 循环回第一帧之前钉住当前姿势
      if (this.holdLast && this.onceRemain <= dt + 0.03) {
        this.freezeLast();
        return;
      }
      this.helper.update(dt);
      this.onceRemain -= dt;
      if (this.onceRemain <= 0) this.stop();
      return;
    }
    this.helper?.update(dt);
  }
}
