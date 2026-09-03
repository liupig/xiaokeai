/**
 * 镜头导演：程序化景别/运镜 + 运镜库 VMD 一起抽。
 * 景别（comboDist）决定能做什么动作；运镜只负责从哪看、怎么连续看。
 */
import { api, type AssetItem } from '../../api/client';
import { stage } from '../../engine/stage';
import type { CamShotId, EmotionKey } from '../../engine/types';
import { useAssetsStore } from '../../stores/assets';
import { buildCamCards, type CamCard } from './camLexicon';
import { ANCHOR_SHOT, distanceOfShot, shotMoveSec, type Distance } from './grammar';
import {
  IDLE_CADENCE,
  idleIntentForMode,
  nextIdleMove,
  type IdleKind,
  type IdleMoveKind,
} from './idleLibrary';
import { INTENTS, type Intent } from './lexicon';
import { repertoire, type ApprovedBeat } from './repertoire';

const SIZE_SHOTS = new Set<CamShotId>(['close', 'bust', 'half', 'threeQ', 'full', 'long']);

export type CamPhase = 'qa' | 'welcome' | 'delayed' | 'proactive' | 'goodbye';
export type CamBeat = 'open' | 'line' | 'close' | 'dance';

export interface SceneCue {
  text?: string;
  mood?: EmotionKey;
  intensity?: number;
  phase?: CamPhase;
  dancing?: boolean;
  intents?: string[];
  llmShot?: CamShotId | null;
  beat?: CamBeat;
  forceWide?: boolean;
}

export class ShotConductor {
  /** 景别锚点：特写/1/4/1/2/3/4/全身/远景，动作用这个判断，不跟运镜走 */
  current: CamShotId | null = null;
  private comboDist: Distance = 'half';
  private lastAt = 0;
  private holdUntil = 0;
  private recent: string[] = [];
  private cards: CamCard[] = [];
  /** 审查面板打开时：禁止闲时自动运镜抢画面 */
  reviewLock = false;
  /** 正在跳的那支舞（资产名）。换镜只抽这支舞过审过的景别×运镜。 */
  private danceAsset: string | null = null;
  onDanceEnded: (() => void) | null = null;
  private lastIdleAsset: string | null = null;
  private lastIdleMove: IdleMoveKind | null = null;
  private idleCut = 0;
  /** 说话间隙 vs goodbye 之后自己玩 */
  idleKind: IdleKind = 'chat';
  private pendingAlone = false;
  private lastIdleSat = false;
  private poseHoldUntil = 0;

  get distance(): Distance {
    return this.comboDist;
  }

  private sizeLockNeed() {
    const sizes = stage.camSizeLock;
    return sizes?.length ? { sizes } : {};
  }

  indexFrom(cameras: AssetItem[]) {
    this.cards = buildCamCards(cameras);
  }

  private ensureIndex() {
    if (this.cards.length) return;
    this.indexFrom(useAssetsStore().cameras);
  }

  /** 读一场戏，只从过审四元组里抽镜头 */
  cover(cue: SceneCue) {
    if (this.reviewLock) return;
    if (stage.cameraDriving && Date.now() - this.lastAt < 900) return;
    if (!repertoire.loaded) return;
    const dancing = !!(cue.dancing || cue.beat === 'dance');
    if (dancing && this.danceAsset) {
      this.danceCut();
      return;
    }
    const rawHint = cue.llmShot && SIZE_SHOTS.has(cue.llmShot) ? cue.llmShot : undefined;
    const sizeHint = rawHint ? stage.clampCamSize(rawHint) : undefined;
    const prefer = dancing ? undefined : this.current ?? undefined;
    const intent = (cue.intents || []).find((i): i is Intent =>
      INTENTS.includes(i as Intent) && repertoire.hasIntent(i as Intent));
    const beat = repertoire.pick({
      dancing,
      phrase: cue.beat === 'line' && !dancing,
      idle: cue.beat === 'open' && cue.phase !== 'qa',
      intent: dancing ? undefined : intent,
      size: sizeHint,
      allowWalk: !dancing && (cue.beat === 'open' || cue.forceWide),
      preferStand: stage.standSlot,
      preferSize: prefer ? stage.clampCamSize(prefer) : undefined,
      ...this.sizeLockNeed(),
    });
    if (!beat) return;
    this.syncFromBeat(beat);
    void repertoire.perform(beat, {
      cam: true,
      stand: !dancing && (cue.beat === 'open' || !!cue.forceWide),
      // 跳舞等 playDance 开动作，这里只先把镜头落到这支舞能用的景别
      motion: !dancing && cue.beat === 'line',
    });
  }

  idleBreathe() {
    this.idleLive();
  }

  /**
   * 闲时活着：和跳舞同一套调度，降强度。
   * 每一拍 = 换景别 + 轻运镜 + 闲时动作库里抽一条（听你说话时只动镜头）。
   */
  idleLive() {
    if (this.reviewLock) return;
    if (this.danceAsset) {
      this.danceCut();
      return;
    }
    if (!repertoire.loaded) {
      stage.director.nudgeIdle(0.5);
      return;
    }
    const now = Date.now();
    const [minGap] = this.idleKind === 'alone' ? IDLE_CADENCE.aloneCuts : IDLE_CADENCE.betweenCuts;
    if (now - this.lastAt < minGap * 1000) return;
    if (stage.director.state === 'speaking') return;
    if (stage.director.state === 'thinking') return;

    const listening = stage.director.state === 'listening';
    if (this.pendingAlone && stage.director.state === 'idle') {
      this.setIdleMode('alone');
    }
    const kind = this.idleKind;
    const holdPose = kind === 'alone' && (stage.motion.holding || now < this.poseHoldUntil);
    const wantMotion = !listening && !holdPose;

    const beat = this.pickIdleBeat(wantMotion && !stage.motion.active, kind);
    const move = nextIdleMove(this.lastIdleMove);
    this.lastIdleMove = move;

    if (!beat) {
      const lock = stage.camSizeLock;
      let fallback: CamShotId;
      if (lock?.length) {
        const cur = this.current && lock.includes(this.current) ? this.current : lock[0];
        fallback = lock.find((s) => s !== cur) ?? cur;
      } else {
        fallback = kind === 'alone'
          ? (this.current && this.current !== 'close' ? this.current : 'full')
          : (this.current && this.current !== 'long' ? this.current : 'half');
      }
      stage.playIdleCut(fallback, move, kind === 'alone' ? 3.2 : 2.2 + Math.random() * 0.8);
      this.current = fallback;
      this.lastAt = now;
      this.idleCut += 1;
      return;
    }

    this.syncFromBeat(beat);
    this.lastAt = now;
    this.holdUntil = now + (kind === 'alone' ? 3600 : 2000);
    if (wantMotion && beat.assetName) this.lastIdleAsset = beat.assetName;
    if (wantMotion) {
      this.lastIdleSat = beat.intents.includes('sit');
      const [a, b] = IDLE_CADENCE.alonePoseHold;
      this.poseHoldUntil = kind === 'alone'
        ? now + (a + Math.random() * (b - a)) * 1000
        : 0;
    }
    this.idleCut += 1;
    const wander = kind === 'alone'
      && beat.stand !== stage.standSlot
      && (beat.intents.includes('walk') || Math.random() < 0.32);
    const holdLast = kind === 'alone' && !beat.intents.includes('walk') && beat.actionKind === 'asset';
    void repertoire.perform(beat, {
      cam: true,
      stand: wander,
      motion: wantMotion && !stage.motion.active && beat.actionKind !== 'none',
      holdLast,
      idleMove: move,
      onMotionEnded: holdLast ? undefined : () => {
        if (stage.director.idleLive && stage.director.state === 'idle') {
          stage.director.nudgeIdle(1.4 + Math.random() * 1.4);
        }
      },
    });
  }

  private pickIdleBeat(wantMotion: boolean, kind: IdleKind): ApprovedBeat | null {
    const preferStand = stage.standSlot;
    const sceneCam = stage.director.sceneCam;
    let preferSize = (sceneCam && SIZE_SHOTS.has(sceneCam) ? sceneCam : this.current) ?? undefined;
    if (preferSize) preferSize = stage.clampCamSize(preferSize);
    const mood = stage.director.moodKey;
    let intent = wantMotion ? idleIntentForMode(kind, mood) : undefined;
    const sceneIntent = stage.director.sceneIntent as Intent | null;
    if (wantMotion && kind === 'chat' && sceneIntent && repertoire.hasIntent(sceneIntent)
        && Math.random() < 0.7) {
      intent = sceneIntent;
    }
    const allowWalk = kind === 'alone';
    const idle = {
      idle: true as const, idleKind: kind, allowWalk, preferStand, preferSize, varyCam: true,
      ...this.sizeLockNeed(),
    };

    if (!wantMotion && stage.motion.active && this.lastIdleAsset) {
      return repertoire.pick({ ...idle, assetName: this.lastIdleAsset })
        ?? repertoire.pick(idle);
    }

    const withIntent = intent
      ? repertoire.pick({ ...idle, intent, needAction: true })
      : null;
    return withIntent
      ?? repertoire.pick({ ...idle, needAction: true })
      ?? repertoire.pick(idle);
  }

  /** 说话间隙 / 一个人玩 */
  setIdleMode(kind: IdleKind) {
    this.pendingAlone = false;
    const changed = this.idleKind !== kind;
    this.idleKind = kind;
    stage.director.idleAlone = kind === 'alone';
    if (!changed) return;
    this.lastIdleAsset = null;
    this.lastIdleSat = false;
    this.idleCut = 0;
    this.lastAt = 0;
    this.poseHoldUntil = 0;
    if (stage.director.idleLive) {
      stage.director.nudgeIdle(kind === 'alone' ? IDLE_CADENCE.aloneFirst : 0.8);
    }
  }

  /** goodbye 开口时记下，说完再切到一个人玩 */
  armAloneIdle() {
    this.pendingAlone = true;
  }

  /** 刚切过一刀：记下景别，闲时先别抢 */
  holdShot(id: CamShotId) {
    this.current = id;
    this.lastAt = Date.now();
    this.holdUntil = this.lastAt + 2800;
  }

  /** 进场 / 舞停：打开闲时导演，马上第一拍 */
  beginIdle() {
    if (this.danceAsset) return;
    this.lastIdleAsset = null;
    this.lastIdleSat = false;
    this.idleCut = 0;
    this.lastAt = 0;
    this.poseHoldUntil = 0;
    stage.director.idleLive = true;
    stage.director.idleAlone = this.idleKind === 'alone';
    stage.director.nudgeIdle(
      this.idleKind === 'alone' ? IDLE_CADENCE.aloneFirst : IDLE_CADENCE.firstCut,
    );
  }

  /** 开跳：之后换镜只抽这支舞过审过的组合，不重播动作 */
  beginDance(assetName: string) {
    this.danceAsset = assetName;
    this.lastIdleAsset = null;
    stage.director.idleLive = false;
    stage.director.camLive = true;
    stage.director.nudgeCam(2.6);
  }

  endDance() {
    const was = this.danceAsset;
    if (!was) {
      stage.director.camLive = false;
      return;
    }
    this.danceAsset = null;
    stage.director.camLive = false;
    this.onDanceEnded?.();
    this.beginIdle();
  }

  /** 同一支舞内部自由切景别/运镜，不跳出这支舞支持的格子 */
  danceCut() {
    if (this.reviewLock || !this.danceAsset) return;
    if (!stage.motion.active) {
      this.endDance();
      return;
    }
    const now = Date.now();
    if (now - this.lastAt < 2200) return;
    const name = this.danceAsset;
    const preferSize = this.current ? stage.clampCamSize(this.current) : undefined;
    const beat = repertoire.pick({
      assetName: name,
      dancing: true,
      allowWalk: false,
      preferStand: stage.standSlot,
      preferSize,
      varyCam: true,
      ...this.sizeLockNeed(),
    }) ?? repertoire.pick({
      assetName: name,
      allowWalk: false,
      preferStand: stage.standSlot,
      preferSize,
      varyCam: true,
      ...this.sizeLockNeed(),
    });
    if (!beat) return;
    this.syncFromBeat(beat);
    this.holdUntil = now + 2200 + Math.random() * 1800;
    void repertoire.perform(beat, { cam: true, stand: false, motion: false });
  }

  /** 审查：无视语法直接播一条程序化镜头；distHint 钉住所选景别，不跟运镜改距离 */
  forceShot(id: CamShotId, distHint?: Distance) {
    const dist = distHint ?? distanceOfShot(id);
    this.comboDist = dist;
    this.current = ANCHOR_SHOT[dist];
    this.lastAt = Date.now();
    this.holdUntil = this.lastAt + 5000;
    stage.playShot(id, false, shotMoveSec(id));
  }

  /** 审查：直接播一条运镜 VMD；distHint 钉住所选景别 */
  forceVmd(name: string, distHint?: Distance) {
    this.ensureIndex();
    const raw = useAssetsStore().cameras.find((c) => c.name === name);
    if (!raw) return;
    const card = this.cards.find((c) => c.name === name);
    const dist = distHint ?? card?.minDist ?? 'half';
    this.comboDist = dist;
    this.current = ANCHOR_SHOT[dist];
    this.lastAt = Date.now();
    this.holdUntil = this.lastAt + 8000;
    void stage.playCameraVmd(api.assetUrl(raw), { once: true });
  }

  /** LLM 点名一条程序镜头：必须落在过审组合上 */
  suggest(id: CamShotId, cue: SceneCue = {}) {
    if (this.reviewLock) return;
    const shot = SIZE_SHOTS.has(id) ? stage.clampCamSize(id) : id;
    const asSize = SIZE_SHOTS.has(shot);
    const beat = repertoire.pick({
      size: asSize ? shot : undefined,
      camKey: asSize ? undefined : `move:${shot}`,
      allowWalk: false,
      preferStand: stage.standSlot,
      preferSize: asSize ? shot : (this.current ? stage.clampCamSize(this.current) : undefined),
      ...this.sizeLockNeed(),
    });
    if (!beat) return;
    this.syncFromBeat(beat);
    void repertoire.perform(beat, { cam: true, stand: false, motion: false });
  }

  /** 走位 / 舞蹈等必须全身时，只切到表里过审的全身组合 */
  ensure(distance: Distance, cue: SceneCue = {}) {
    if (this.comboDist === distance && this.current) return;
    const size = stage.clampCamSize(ANCHOR_SHOT[distance]);
    const beat = repertoire.pick({
      size,
      allowWalk: !!cue.forceWide,
      preferStand: stage.standSlot,
      preferSize: size,
      ...this.sizeLockNeed(),
    });
    if (!beat) return;
    this.syncFromBeat(beat);
    void repertoire.perform(beat, { cam: true, stand: !!cue.forceWide, motion: false });
  }

  reset() {
    this.current = null;
    this.comboDist = 'half';
    this.lastAt = 0;
    this.holdUntil = 0;
    this.recent = [];
    this.idleKind = 'chat';
    this.pendingAlone = false;
    this.lastIdleSat = false;
    this.poseHoldUntil = 0;
    stage.director.idleAlone = false;
    this.endDance();
  }

  syncFromBeat(beat: ApprovedBeat) {
    this.comboDist = repertoire.distanceOf(beat);
    this.current = beat.size;
    this.lastAt = Date.now();
    this.holdUntil = this.lastAt + (beat.camKind === 'vmd' ? 7200 : 4200);
  }
}

export const shots = new ShotConductor();
