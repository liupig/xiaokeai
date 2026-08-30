import { Quaternion } from 'three';
import { reactive } from 'vue';
import type { VRM } from '@pixiv/three-vrm';
import type { Avatar } from '../../engine/types';
import { type RestCapture } from './bones';
import { FaceSolver } from './face';
import type { PoseWorkerResponse } from './protocol';
import { Solver, type BoneState } from './solver';

const _q = new Quaternion();

export type MocapStatus = 'idle' | 'starting' | 'running' | 'error';
export type MocapSource = 'camera' | 'video';

export interface MocapTarget {
  root: import('three').Object3D;
  avatar: Avatar;
  vrm?: VRM | null;
  rest: RestCapture;
}

export const mocapState = reactive({
  status: 'idle' as MocapStatus,
  source: 'camera' as MocapSource,
  error: '',
  tracking: false,
  inferenceMs: 0,
  fps: 0,
  loop: true,
});

/**
 * 摄像头全身动捕：Worker 里跑 MediaPipe Holistic，主线程求解并写回 Three.js 骨骼。
 */
export class MocapSession {
  readonly video = document.createElement('video');
  stream: MediaStream | null = null;

  private worker: Worker | null = null;
  private solver = new Solver();
  private face = new FaceSolver();
  private target: MocapTarget | null = null;
  private latestBones: BoneState[] | null = null;
  private latestMorphs: Record<string, number> = {};
  private eyeRot: import('three').Quaternion | null = null;
  private busy = false;
  private raf = 0;
  private fpsT = 0;
  private fpsN = 0;
  private running = false;
  private ready = false;
  private waitReady: Promise<void> | null = null;
  private objectUrl: string | null = null;
  private lastVideoTime = -1;
  private pendingFrame = true;

  constructor() {
    this.video.playsInline = true;
    this.video.muted = true;
    this.video.autoplay = true;
    this.video.setAttribute('playsinline', '');
    this.video.addEventListener('seeked', () => this.onSeek());
  }

  get active() {
    return this.running;
  }

  attach(target: MocapTarget) {
    this.target = target;
    this.solver.calibrate(target.rest.worldPos);
    this.face.configure(target.avatar.morphNames());
    this.solver.reset();
    this.face.reset();
  }

  detach() {
    this.target = null;
    this.latestBones = null;
  }

  async start(kind: MocapSource = 'camera', file?: File) {
    if (kind === 'video' && !file) throw new Error('请选择视频文件');
    const switching = this.running;
    this.running = true;
    mocapState.status = 'starting';
    mocapState.error = '';
    mocapState.tracking = false;
    mocapState.source = kind;
    try {
      await this.ensureWorker();
      if (switching) {
        this.clearMedia();
        this.solver.reset();
        this.face.reset();
        this.worker?.postMessage({ type: 'reset' });
      }
      this.lastVideoTime = -1;
      this.pendingFrame = true;
      if (kind === 'camera') {
        this.stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        this.video.srcObject = this.stream;
        this.video.loop = false;
        this.video.controls = false;
      } else {
        this.objectUrl = URL.createObjectURL(file!);
        this.video.srcObject = null;
        this.video.src = this.objectUrl;
        this.video.loop = mocapState.loop;
        this.video.controls = true;
        await new Promise<void>((resolve, reject) => {
          const ok = () => { this.video.removeEventListener('error', bad); resolve(); };
          const bad = () => { this.video.removeEventListener('loadeddata', ok); reject(new Error('视频无法播放')); };
          this.video.addEventListener('loadeddata', ok, { once: true });
          this.video.addEventListener('error', bad, { once: true });
        });
      }
      await this.video.play();
      this.busy = false;
      if (!this.raf) this.loop();
      mocapState.status = 'running';
    } catch (e) {
      this.running = false;
      mocapState.status = 'error';
      mocapState.error = e instanceof Error ? e.message : String(e);
      if (/NotAllowedError|PermissionDenied/i.test(mocapState.error)) {
        mocapState.error = '摄像头权限被拒绝，请在浏览器设置中允许访问摄像头';
      } else if (/NotFoundError/i.test(mocapState.error)) {
        mocapState.error = '没有找到摄像头';
      } else if (/NotReadableError|Could not start video source/i.test(mocapState.error)) {
        mocapState.error = '无法打开摄像头（可能被其他程序占用）';
      }
      this.clearMedia();
    }
  }

  startCamera() {
    return this.start('camera');
  }

  startVideo(file: File) {
    return this.start('video', file);
  }

  setLoop(v: boolean) {
    mocapState.loop = v;
    this.video.loop = v;
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.busy = false;
    this.clearMedia();
    this.solver.reset();
    this.face.reset();
    this.latestBones = null;
    this.restoreRest();
    mocapState.status = 'idle';
    mocapState.tracking = false;
    mocapState.inferenceMs = 0;
    mocapState.fps = 0;
    mocapState.error = '';
  }

  /** 每帧由 Stage 调用：把最新求解结果写到骨骼和形态键。 */
  apply() {
    const t = this.target;
    if (!t || !this.latestBones) return;
    for (const st of this.latestBones) {
      if (st.name === 'センター') {
        const bone = t.rest.bones.get('センター') ?? t.rest.bones.get('下半身');
        const restP = t.rest.restPos.get('センター') ?? t.rest.restPos.get('下半身');
        if (bone && restP && st.translation) {
          bone.position.set(restP.x + st.translation.x, restP.y + st.translation.y, restP.z + st.translation.z);
        }
        continue;
      }
      const bone = t.rest.bones.get(st.name);
      if (!bone) continue;
      const q = this.composeLocal(t.rest, st, this.latestBones);
      const restQ = t.rest.restQuat.get(st.name);
      if (restQ) bone.quaternion.copy(restQ).multiply(q);
      else bone.quaternion.copy(q);
    }
    if (this.eyeRot) {
      for (const name of ['左目', '右目']) {
        const bone = t.rest.bones.get(name);
        const restQ = t.rest.restQuat.get(name);
        if (!bone) continue;
        if (restQ) bone.quaternion.copy(restQ).multiply(this.eyeRot);
        else bone.quaternion.copy(this.eyeRot);
      }
    }
    for (const [name, w] of Object.entries(this.latestMorphs)) {
      t.avatar.setMorph(name, w);
    }
  }

  /** PMX 若没有独立 手捩 骨，把扭转叠到手腕上，避免前臂拧转丢失。 */
  private composeLocal(
    rest: RestCapture,
    st: BoneState,
    bones: BoneState[],
  ): import('three').Quaternion {
    const parentTwist: Record<string, string> = { 左手首: '左手捩', 右手首: '右手捩' };
    const twistName = parentTwist[st.name];
    if (!twistName || rest.bones.has(twistName)) return st.rotation;
    const twist = bones.find((b) => b.name === twistName);
    if (!twist) return st.rotation;
    return _q.copy(twist.rotation).multiply(st.rotation);
  }

  private restoreRest() {
    const t = this.target;
    if (!t) return;
    for (const [name, bone] of t.rest.bones) {
      const q = t.rest.restQuat.get(name);
      const p = t.rest.restPos.get(name);
      if (q) bone.quaternion.copy(q);
      if (p) bone.position.copy(p);
    }
    for (const [name, w] of Object.entries(this.face.restWeights())) {
      t.avatar.setMorph(name, w);
    }
  }

  private onSeek = () => {
    if (!this.running || mocapState.source !== 'video') return;
    this.solver.reset();
    this.face.reset();
    this.worker?.postMessage({ type: 'reset' });
    this.lastVideoTime = -1;
    this.pendingFrame = true;
  };

  private clearMedia() {
    this.stream?.getTracks().forEach((tr) => tr.stop());
    this.stream = null;
    this.video.pause();
    this.video.removeAttribute('src');
    this.video.srcObject = null;
    this.video.load();
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
  }

  private stopTracks() {
    this.clearMedia();
  }

  private ensureWorker(): Promise<void> {
    if (this.ready && this.worker) return Promise.resolve();
    if (this.waitReady) return this.waitReady;
    this.waitReady = new Promise((resolve, reject) => {
      // 经典 Worker（非 module）：MediaPipe 靠 importScripts 加载 wasm 胶水
      const worker = new Worker(`${import.meta.env.BASE_URL}mocap/worker.js`);
      this.worker = worker;
      worker.onmessage = (e: MessageEvent<PoseWorkerResponse>) => {
        const msg = e.data;
        if (msg.type === 'ready') {
          this.ready = true;
          resolve();
        } else if (msg.type === 'result') {
          this.onResult(msg);
        } else if (msg.type === 'error') {
          mocapState.error = msg.message;
          if (!this.ready) {
            this.waitReady = null;
            this.worker = null;
            worker.terminate();
            reject(new Error(msg.message));
          }
        }
      };
      worker.onerror = (err) => {
        const message = err.message || '动捕 Worker 失败';
        mocapState.error = message;
        if (!this.ready) {
          this.waitReady = null;
          this.worker = null;
          worker.terminate();
          reject(new Error(message));
        }
      };
      worker.postMessage({ type: 'init' });
    });
    return this.waitReady;
  }

  private loop = () => {
    if (!this.running) return;
    this.raf = requestAnimationFrame(this.loop);
    if (this.busy || !this.ready || this.video.readyState < 2) return;
    if (mocapState.source === 'video') {
      const t = this.video.currentTime;
      if (t === this.lastVideoTime && !this.pendingFrame) return;
      this.lastVideoTime = t;
      this.pendingFrame = false;
    }
    this.busy = true;
    createImageBitmap(this.video).then((bitmap) => {
      if (!this.running || !this.worker) {
        bitmap.close();
        this.busy = false;
        return;
      }
      const ts = performance.now();
      const mediaTs = mocapState.source === 'video' ? this.video.currentTime * 1000 : ts;
      this.worker.postMessage({ type: 'video', bitmap, ts, mediaTs }, [bitmap]);
    }).catch(() => { this.busy = false; });
  };

  private onResult(msg: Extract<PoseWorkerResponse, { type: 'result' }>) {
    this.busy = false;
    if (!this.running) return;
    const r = msg.result;
    mocapState.inferenceMs = Math.round(r.inferenceMs);
    this.fpsN++;
    const now = performance.now();
    if (now - this.fpsT >= 1000) {
      mocapState.fps = this.fpsN;
      this.fpsN = 0;
      this.fpsT = now;
    }
    const pose = r.poseWorldLandmarks?.[0];
    mocapState.tracking = !!(pose && pose.length >= 33);
    if (!mocapState.tracking) return;
    this.latestBones = this.solver.solve({
      poseWorldLandmarks: r.poseWorldLandmarks,
      leftHandWorldLandmarks: r.leftHandWorldLandmarks,
      rightHandWorldLandmarks: r.rightHandWorldLandmarks,
    }, msg.mediaTs);
    const face = r.faceLandmarks?.[0];
    if (face && this.target) {
      const fr = this.face.solve(face, msg.mediaTs);
      this.latestMorphs = fr.morphWeights;
      this.eyeRot = fr.eyeRotation;
    }
  }
}

export const mocap = new MocapSession();
