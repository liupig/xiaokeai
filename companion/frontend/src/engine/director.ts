import * as THREE from 'three';
import type { Avatar, CamShotId, EmotionKey } from './types';
import type { ExpressionController } from './expression';
import type { Lipsync } from './lipsync';
import type { MotionPlayer } from './motion';

export type DirectorState = 'idle' | 'listening' | 'thinking' | 'speaking';

interface Deps {
  expr: ExpressionController;
  lipsync: Lipsync;
  motion: MotionPlayer;
}

/**
 * 表演导演：这是角色"活着"的核心。
 *
 * 感知：对话状态（待机/聆听/思考/说话）、TTS 语音能量、情绪标签。
 * 决策：
 *  - 连续情绪状态：情绪有强度、会随时间自然衰减回平静，不是硬开关；
 *  - 头部/视线：说话面向镜头、思考移开视线（还会换边）、聆听歪头；
 *  - 语音重音微表演：能量峰值处轻微点头 + 身体节奏前倾（像真人说话的强调）；
 *  - 空闲丰富化：待机久了从动作池随机播一个小动作（播一轮自动收）；
 *  - 微运镜：说话时视野极缓收紧，停下缓慢恢复（呼吸感）。
 * 执行层复用 Stage 现有设施，VMD/插件驱动骨骼时自动让位。
 */
export class PerformanceDirector {
  state: DirectorState = 'idle';
  /** 说话时的镜头收紧程度 0~1（Stage 主循环消费，用 fov 实现，可逆且不干扰用户轨道操作） */
  camPush = 0;

  private mood: { key: EmotionKey; intensity: number } = { key: 'neutral', intensity: 0 };
  private listeningFlag = false;
  private thinkingFlag = false;
  private thinkingTimeout = 0;

  // 头部姿态层（叠加在闲置动画之上）：x=pitch y=yaw z=roll
  private headCur = new THREE.Vector3();
  private headTarget = new THREE.Vector3();
  private lookAwaySide = 1;
  private lookAwayTimer = 0;

  // 语音能量重音检测
  private energyAvg = 0;
  private accentCooldown = 0;
  private nodImpulse = 0;

  // 空闲 / 说话节拍
  private idlePool: string[] = [];
  private idleTimer = 0;
  private idleNextAt = 6;
  private idleExprTimer = 0;
  private idleExprNextAt = 4;
  private idleCamTimer = 0;
  private idleCamNextAt = 8;
  private speakBeatTimer = 0;
  private speakBeatNextAt = 2.4;
  private prevState: DirectorState = 'idle';
  /** 跳舞时说话中也继续换镜 */
  camLive = false;
  /**
   * 闲时成套调度开着：动作+景别+运镜由 onIdleCam 一起切，
   * 不再等 VMD 播完才换，也不再单独抽一条循环待机。
   */
  idleLive = false;
  /** goodbye 之后自己玩：节拍更慢、动作更大 */
  idleAlone = false;
  /** 今晚这场戏的景别 / 意图，闲时镜头跟着走 */
  sceneCam: CamShotId | null = null;
  sceneIntent: string | null = null;

  constructor(private deps: Deps) {}

  get moodKey() { return this.mood.key; }
  get moodIntensity() { return this.mood.intensity; }

  setSceneFrame(cam: CamShotId | null, intent: string | null) {
    this.sceneCam = cam;
    this.sceneIntent = intent;
  }

  /** 空闲动作由选角器按心情从库里挑；未设置则回退 idlePool */
  idlePicker: (() => string | null) | null = null;
  /** 说话句拍 / 闲时微表情 / 闲时运镜：由选角器注入，导演只负责节奏 */
  onSpeakBeat: (() => void) | null = null;
  onIdleBeat: (() => void) | null = null;
  onIdleCam: (() => void) | null = null;
  /** 闲时补一条动作：走 Stage.playMotion，才会停掉上一支舞的配乐 */
  playIdleMotion: ((url: string) => void) | null = null;

  /** 设置情绪（0~1 强度），来源：LLM 标签 [emo:happy:0.8] 或 UI；之后自然衰减 */
  setMood(key: EmotionKey, intensity = 0.85) {
    if (key === 'neutral') {
      this.mood = { key: 'neutral', intensity: 0 };
      return;
    }
    this.mood = { key, intensity: THREE.MathUtils.clamp(intensity, 0, 1) };
  }

  /** 一轮对话开始（LLM 思考中） */
  notifyThinking() {
    this.thinkingFlag = true;
    this.thinkingTimeout = 2.4;
  }

  /** LLM 输出完毕（语音可能还在排队播放，说话状态由 lipsync 实时决定） */
  notifyTurnDone() {
    this.thinkingTimeout = Math.min(this.thinkingTimeout, 3);
  }

  /** 语音输入（麦克风）开关 */
  setListening(on: boolean) {
    this.listeningFlag = on;
  }

  /** 空闲随机小动作候选池（待机/互动类 VMD 的 URL） */
  setIdlePool(urls: string[]) {
    this.idlePool = urls;
  }

  /** 跳舞开跳后尽快进入换镜节奏 */
  nudgeCam(afterSec = 2.4) {
    this.idleCamTimer = 0;
    this.idleCamNextAt = afterSec;
  }

  /** 闲时第一拍：进场 / 说完 / 舞停 */
  nudgeIdle(afterSec = 0.9) {
    this.idleTimer = 0;
    this.idleNextAt = afterSec;
    this.idleCamTimer = 0;
    this.idleCamNextAt = afterSec;
  }

  reset() {
    this.state = 'idle';
    this.mood = { key: 'neutral', intensity: 0 };
    this.thinkingFlag = false;
    this.listeningFlag = false;
    this.headCur.set(0, 0, 0);
    this.headTarget.set(0, 0, 0);
    this.nodImpulse = 0;
    this.camPush = 0;
    this.idleTimer = 0;
    this.idleExprTimer = 0;
    this.idleCamTimer = 0;
    this.speakBeatTimer = 0;
    this.camLive = false;
    this.idleLive = false;
    this.idleAlone = false;
  }

  /** 每帧调用（Stage 主循环，位于 idle.update 之后、motion.update 之前的姿态叠加窗口） */
  update(av: Avatar, dt: number, motionActive: boolean) {
    const talking = this.deps.lipsync.talking;

    // ---- 状态推导 ----
    if (talking) this.thinkingFlag = false;
    if (this.thinkingFlag) {
      this.thinkingTimeout -= dt;
      if (this.thinkingTimeout <= 0) this.thinkingFlag = false;
    }
    // 开麦会话可以一直听；她正在出声时仍走 speaking，否则会整场卡在 listening 里不表演
    const next: DirectorState = talking ? 'speaking'
      : this.listeningFlag ? 'listening'
        : this.thinkingFlag ? 'thinking' : 'idle';
    if (this.prevState === 'speaking' && next === 'idle') {
      // 刚说完：很快给一个收势动作，不要干站
      this.nudgeIdle(1.6 + Math.random() * 1.2);
      this.idleExprTimer = 0;
      this.idleExprNextAt = 1.2;
    } else if (this.prevState === 'thinking' && next === 'idle') {
      this.nudgeIdle(1.4 + Math.random() * 1.0);
    }
    this.prevState = this.state;
    this.state = next;

    // ---- 情绪：说话中保持表达，其余时间向平静自然衰减（约 20s 半衰） ----
    if (this.state !== 'speaking' && this.mood.intensity > 0) {
      this.mood.intensity *= Math.exp(-dt / 20);
      if (this.mood.intensity < 0.03) this.mood = { key: 'neutral', intensity: 0 };
    }
    this.deps.expr.setEmotion(
      this.mood.intensity > 0.03 ? this.mood.key : 'neutral',
      0.9 * this.mood.intensity
    );

    // ---- 语音能量重音：峰值处点头冲量（说话的"强调感"） ----
    const mouth = this.deps.expr.mouthValue;
    this.energyAvg += (mouth - this.energyAvg) * Math.min(1, dt * 1.2);
    this.accentCooldown -= dt;
    if (this.state === 'speaking' && this.accentCooldown <= 0
        && mouth > 0.3 && mouth > this.energyAvg * 1.8) {
      this.nodImpulse = Math.min(0.09, 0.05 + mouth * 0.05);
      this.accentCooldown = 0.55 + Math.random() * 0.45;
    }
    this.nodImpulse *= Math.exp(-dt * 6);

    // ---- 头部姿态目标 ----
    this.lookAwayTimer -= dt;
    switch (this.state) {
      case 'speaking':
        if (this.lookAwayTimer <= 0) {
          if (Math.random() < 0.2) {
            // 说话中偶尔瞥一眼旁边，再看回镜头
            this.headTarget.set(-0.02, 0.14 * (Math.random() < 0.5 ? -1 : 1), 0.02);
            this.lookAwayTimer = 0.4 + Math.random() * 0.35;
          } else {
            this.headTarget.set(0.015, 0, 0);
            this.lookAwayTimer = 1.4 + Math.random() * 2.2;
          }
        }
        break;
      case 'listening':
        this.headTarget.set(0.02, 0.05, 0.1);
        break;
      case 'thinking':
        if (this.lookAwayTimer <= 0) {
          this.lookAwaySide = Math.random() < 0.5 ? -1 : 1;
          this.lookAwayTimer = 1.8 + Math.random() * 2.4;
        }
        this.headTarget.set(-0.04, 0.2 * this.lookAwaySide, 0.03 * this.lookAwaySide);
        break;
      default:
        if (this.lookAwayTimer <= 0) {
          // 闲时慢扫视，不要一直盯死镜头
          this.headTarget.set(
            (Math.random() - 0.5) * 0.05,
            (Math.random() - 0.5) * 0.2,
            (Math.random() - 0.5) * 0.05,
          );
          this.lookAwayTimer = 3.2 + Math.random() * 4.5;
        }
    }
    this.headCur.lerp(this.headTarget, 1 - Math.exp(-4.5 * dt));

    // ---- 应用姿态层（仅程序化闲置时；VMD / 动捕插件驱动时不抢骨骼） ----
    if (!motionActive) {
      const head = av.bone('head');
      if (head) {
        head.rotation.x += this.headCur.x + this.nodImpulse;
        head.rotation.y += this.headCur.y;
        head.rotation.z += this.headCur.z;
      }
      if (this.state === 'speaking') {
        const chest = av.bone('chest');
        if (chest) chest.rotation.x += mouth * 0.018 + this.nodImpulse * 0.3;
      }
    }

    // ---- 说话中：按句拍叠表情 / 补一个说话手势（舞蹈中不抢） ----
    if (this.state === 'speaking' && !this.deps.motion.active) {
      this.speakBeatTimer += dt;
      if (this.speakBeatTimer >= this.speakBeatNextAt) {
        this.speakBeatTimer = 0;
        this.speakBeatNextAt = 3.4 + Math.random() * 2.8;
        this.onSpeakBeat?.();
      }
    } else {
      this.speakBeatTimer = 0;
    }

    // ---- 闲时：微表情；成套拍（动作+景别+运镜）由 onIdleCam 一起走 ----
    if (this.state === 'idle' || this.state === 'listening') {
      this.idleExprTimer += dt;
      if (this.state === 'idle' && this.idleExprTimer >= this.idleExprNextAt) {
        this.idleExprTimer = 0;
        this.idleExprNextAt = 5 + Math.random() * 7;
        this.onIdleBeat?.();
      }
      // 旧路径：没有闲时导演时，才在「没 VMD」时空档抽一条动作
      if (!this.idleLive && this.state === 'idle' && !motionActive
          && (this.idlePicker || this.idlePool.length)) {
        this.idleTimer += dt;
        if (this.idleTimer >= this.idleNextAt) {
          this.idleTimer = 0;
          this.idleNextAt = 8 + Math.random() * 10;
          const url = this.idlePicker?.()
            ?? this.idlePool[Math.floor(Math.random() * this.idlePool.length)];
          if (url) {
            if (this.playIdleMotion) this.playIdleMotion(url);
            else void this.deps.motion.play(url, { once: true });
          }
        }
      }
    } else {
      this.idleTimer = 0;
      this.idleExprTimer = 0;
      if (!this.camLive) this.idleCamTimer = 0;
    }

    if (this.state === 'idle' || this.state === 'listening' || this.camLive) {
      this.idleCamTimer += dt;
      const gap = this.camLive
        ? 2.8 + Math.random() * 2.2
        : this.idleAlone
          ? 8 + Math.random() * 6
          : 6.4 + Math.random() * 4.6;
      if (this.idleCamTimer >= this.idleCamNextAt) {
        this.idleCamTimer = 0;
        this.idleCamNextAt = gap;
        this.onIdleCam?.();
      }
    }

    // ---- 微运镜：说话时视野极缓收紧（呼吸感），停下缓慢恢复 ----
    const pushTarget = this.state === 'speaking' ? 1 : this.state === 'thinking' ? 0.25 : 0;
    this.camPush += (pushTarget - this.camPush) * Math.min(1, dt * 0.35);
  }
}
