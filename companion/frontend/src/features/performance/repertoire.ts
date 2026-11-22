/**
 * 剧目库：线上表演只抽 cam_review 表里 verdict=ok 的四元组。
 * 未审 / 不可用 / 新资产一律不进 AI 调度，审查通过后下次 load 才生效。
 *
 * 一次表演是一整拍：景别 × 运镜 × 站位 × 动作，不再各抽各的。
 */
import { acceptsShot, isAdvancedShot } from '../../engine/shotRules';
import { shallowRef } from 'vue';
import { api } from '../../api/client';
import { stage } from '../../engine/stage';
import { live2dStage } from '../../engine/live2d';
import type { StandSlot } from '../../engine/stage';
import type { CamShotId } from '../../engine/types';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { isMotionRejected, playAssetMotion, stripCatPrefix } from '../assets/motionMeta';
import { INTENT_LABEL, MOVES, SIZES, STANDS } from '../review/camReview';
import { buildCamCards } from './camLexicon';
import { distanceOfShot, type Distance } from './grammar';
import {
  isIdleSafeIntents,
  idleMoveLabel,
  idleSizeScore,
  type IdleKind,
  type IdleMoveKind,
} from './idleLibrary';
import {
  INTENTS,
  buildMotionCards,
  type Intent,
  type MotionCard,
} from './lexicon';

const SIZE_SET = new Set(SIZES.map((s) => s.id));
const STAND_SET = new Set(STANDS.map((s) => s.id));
const MOVE_SET = new Set(MOVES.map((m) => m.id));

export interface ApprovedBeat {
  id: string;
  size: CamShotId;
  camKind: 'hold' | 'move' | 'vmd';
  camMove?: CamShotId;
  vmdName?: string;
  stand: StandSlot;
  actionKind: 'none' | 'builtin' | 'asset';
  builtin?: 'nod' | 'shake';
  assetName?: string;
  intents: Intent[];
  speakSafe: boolean;
  dance: boolean;
  showOnly: boolean;
  /** 闲时轻运镜（HUD 用，不进审查表） */
  idleMove?: IdleMoveKind;
}

export interface LiveNow {
  appliedApprovedCam?: boolean;
  beat: ApprovedBeat;
  cam: boolean;
  motion: boolean;
  at: number;
}

/** 舞台正在播的这一拍，给 HUD 用 */
export const liveNow = shallowRef<LiveNow | null>(null);
export const liveCamera = shallowRef<ApprovedBeat | null>(null);
export const liveRecent = shallowRef<ApprovedBeat[]>([]);

export interface BeatLabels {
  size: string;
  cam: string;
  stand: string;
  action: string;
  group: string;
}

export function describeBeat(beat: ApprovedBeat): BeatLabels {
  const assets = useAssetsStore();
  const size = SIZES.find((s) => s.id === beat.size)?.label ?? beat.size;
  const stand = STANDS.find((s) => s.id === beat.stand)?.label ?? beat.stand;
  let cam = '定镜';
  if (beat.idleMove) {
    cam = idleMoveLabel(beat.idleMove);
  } else if (beat.camKind === 'move' && beat.camMove) {
    cam = MOVES.find((m) => m.id === beat.camMove)?.label ?? beat.camMove;
  } else if (beat.camKind === 'vmd' && beat.vmdName) {
    const raw = assets.cameras.find((c) => c.name === beat.vmdName);
    cam = stripCatPrefix(raw?.label || '') || beat.vmdName;
  }
  let action = '无动作';
  let group = '';
  if (beat.actionKind === 'builtin' && beat.builtin) {
    action = beat.builtin === 'nod' ? '点头' : '摇头';
    group = action;
  } else if (beat.actionKind === 'asset' && beat.assetName) {
    const raw = assets.motions.find((m) => m.name === beat.assetName);
    action = stripCatPrefix(raw?.label || '') || beat.assetName;
    const tag = beat.intents[0];
    group = tag ? INTENT_LABEL[tag] : '';
  }
  return { size, cam, stand, action, group };
}

export interface PickNeed {
  intent?: Intent;
  assetName?: string;
  size?: CamShotId;
  stand?: StandSlot;
  camKey?: string;
  dancing?: boolean;
  speaking?: boolean;
  idle?: boolean;
  /** 跟句走：要成套动作，不要空镜/过小手势 */
  phrase?: boolean;
  /** 闲时成套拍：必须带动作，不要空镜 */
  needAction?: boolean;
  /** chat = 说话间隙；alone = goodbye 之后自己玩 */
  idleKind?: IdleKind;
  allowWalk?: boolean;
  preferSize?: CamShotId;
  preferStand?: StandSlot;
  /** 跳舞换镜：在同一支舞的过审景别里尽量换一条 */
  varyCam?: boolean;
  /** 只从这些景别里抽（塔罗锁 3/4 + 全身） */
  sizes?: CamShotId[];
}

function decodePart(raw: string) {
  try { return decodeURIComponent(raw); } catch { return raw; }
}

function parseBeatId(id: string): {
  size: CamShotId; cam: string; stand: StandSlot; action: string;
} | null {
  const parts = id.split('|').map(decodePart);
  if (parts.length !== 4) return null;
  const [size, cam, stand, action] = parts;
  if (!SIZE_SET.has(size as CamShotId)) return null;
  if (!STAND_SET.has(stand as StandSlot)) return null;
  return { size: size as CamShotId, cam, stand: stand as StandSlot, action };
}

function camOf(raw: string): Pick<ApprovedBeat, 'camKind' | 'camMove' | 'vmdName'> | null {
  if (raw === 'hold') return { camKind: 'hold' };
  if (raw.startsWith('move:')) {
    const id = raw.slice(5) as CamShotId;
    if (!MOVE_SET.has(id)) return null;
    return { camKind: 'move', camMove: id };
  }
  if (raw.startsWith('vmd:')) return { camKind: 'vmd', vmdName: raw.slice(4) };
  return null;
}

const RARE_CAMERA_CHANCE = 0.02;
const RARE_CAMERA_MIN_SHOTS = 20;
const RARE_CAMERA_COOLDOWN_MS = 60_000;

function isSideCamera(beat: ApprovedBeat) {
  return beat.camMove === 'yawL45' || beat.camMove === 'yawR45';
}

function pickCameraWeighted(scored: { b: ApprovedBeat; s: number }[], allowRare: boolean): ApprovedBeat | null {
  const rare = scored.filter(({ b }) => isAdvancedShot(b.camMove));
  const normal = scored.filter(({ b }) => !isAdvancedShot(b.camMove));
  if (!normal.length) return null;

  const front = normal.filter(({ b }) => !isSideCamera(b));
  const side = normal.filter(({ b }) => isSideCamera(b));
  let candidates: typeof scored;
  if (allowRare && rare.length && Math.random() < RARE_CAMERA_CHANCE) {
    candidates = rare;
  } else if (front.length && side.length) {
    candidates = Math.random() < 0.8 ? front : side;
  } else {
    candidates = normal;
  }
  // 先选角度组，再在组内选高分组合，避免某组资产多就抢走镜头份额。
  const cutoff = candidates[0].s - 8;
  const top = candidates.filter(({ s }) => s >= cutoff);
  return top[Math.floor(Math.random() * top.length)].b;
}

export class Repertoire {
  beats: ApprovedBeat[] = [];
  loaded = false;
  /** 角色卡上的闲时偏好，进池加权，不单独死循环 */
  idleFavorite = '';
  private recent: string[] = [];
  private playSeq = 0;
  private liveSeq = 0;
  private normalShotsSinceRare = 0;
  private lastRareCameraAt = 0;
  private cards: MotionCard[] = [];

  get size() { return this.beats.length; }

  async load() {
    const assets = useAssetsStore();
    this.cards = buildMotionCards(assets.motions.filter((m) => !isMotionRejected(m)));
    const cardBy = new Map(this.cards.map((c) => [c.name, c]));
    const camBy = new Map(buildCamCards(assets.cameras).map((c) => [c.name, c]));
    const remote = await api.getCamReview();
    const next: ApprovedBeat[] = [];
    for (const [id, verdict] of Object.entries(remote.verdicts || {})) {
      if (verdict !== 'ok') continue;
      const parsed = parseBeatId(id);
      if (!parsed) continue;
      const cam = camOf(parsed.cam);
      if (!cam || cam.camKind === 'vmd') continue;
      let actionKind: ApprovedBeat['actionKind'] = 'none';
      let builtin: 'nod' | 'shake' | undefined;
      let assetName: string | undefined;
      let intents: Intent[] = [];
      let speakSafe = true;
      let dance = false;
      if (parsed.action === 'none') {
        actionKind = 'none';
      } else if (parsed.action === 'builtin:nod' || parsed.action === 'builtin:shake') {
        actionKind = 'builtin';
        builtin = parsed.action === 'builtin:nod' ? 'nod' : 'shake';
        intents = [builtin];
      } else if (parsed.action.startsWith('asset:')) {
        assetName = parsed.action.slice(6);
        const card = cardBy.get(assetName);
        if (!card) continue;
        actionKind = 'asset';
        intents = card.tags;
        speakSafe = card.speakSafe;
        dance = card.stance === 'dance' || card.tags.includes('dance');
      } else {
        continue;
      }
      const showOnly = !!(cam.vmdName && camBy.get(cam.vmdName)?.showOnly);
      next.push({
        id,
        size: parsed.size,
        ...cam,
        stand: parsed.stand,
        actionKind,
        builtin,
        assetName,
        intents,
        speakSafe,
        dance,
        showOnly,
      });
    }
    this.beats = next;
    this.loaded = true;
  }

  hasIntent(intent: Intent) {
    return this.beats.some((b) => this.matchesIntent(b, intent));
  }

  allowsAsset(name: string) {
    return this.beats.some((b) => b.assetName === name);
  }

  allowsCam(name: string) {
    return this.beats.some((b) => b.vmdName === name || b.camMove === name);
  }

  allowsStand(slot: StandSlot) {
    return this.beats.some((b) => b.stand === slot);
  }

  pick(need: PickNeed): ApprovedBeat | null {
    if (!this.loaded || !this.beats.length) return null;
    const curStand = need.preferStand ?? stage.standSlot;
    const curSize = need.preferSize;
    let pool = this.beats.filter((b) => acceptsShot(b.size, b.camMove));

    if (need.assetName) pool = pool.filter((b) => b.assetName === need.assetName);
    if (need.sizes?.length) pool = pool.filter((b) => need.sizes!.includes(b.size));
    if (need.size) pool = pool.filter((b) => b.size === need.size);
    if (need.stand) pool = pool.filter((b) => b.stand === need.stand);
    if (need.camKey) {
      pool = pool.filter((b) => this.beatCamKey(b) === need.camKey);
    }
    if (need.intent) pool = pool.filter((b) => this.matchesIntent(b, need.intent!));
    if (need.dancing) pool = pool.filter((b) => b.dance);
    if (need.idle || need.idleKind) {
      const kind = need.idleKind ?? 'chat';
      pool = pool.filter((b) =>
        !b.showOnly && !b.dance
        && (b.actionKind === 'none' || isIdleSafeIntents(b.intents, kind)));
    }
    if (need.needAction) {
      pool = pool.filter((b) => b.actionKind !== 'none');
    }
    if (need.phrase) {
      pool = pool.filter((b) => !b.dance && !b.showOnly && b.actionKind !== 'none'
        && (b.speakSafe || need.intent === 'sit' || need.intent === 'walk' || need.intent === 'bow'));
    }
    if (need.speaking && !need.phrase) {
      pool = pool.filter((b) => !b.dance && !b.showOnly);
    }

    const stay = pool.filter((b) => b.stand === curStand);
    if (!need.allowWalk && stay.length) pool = stay;
    else if (!need.allowWalk && !stay.length && need.intent) {
      const walked = pool.filter((b) => b.stand !== curStand);
      if (walked.length) pool = walked;
    }

    if (!pool.length) return null;

    const scored = pool.map((b) => {
      let s = 0;
      if (b.stand === curStand) s += 36;
      if (curSize && b.size === curSize && !need.varyCam) s += 10;
      if (need.phrase && b.actionKind === 'asset') s += 28;
      if (need.phrase && b.actionKind === 'builtin') s += 8;
      if (need.phrase && need.intent && b.intents.includes(need.intent)) s += 22;
      if (need.phrase && (b.camKind === 'move' || b.camKind === 'vmd')) s += 10;
      if (need.idle || need.idleKind) {
        const kind = need.idleKind ?? 'chat';
        if (need.sizes?.length) s += need.sizes.includes(b.size) ? 20 : 0;
        else s += idleSizeScore(b.size, kind);
        if (b.actionKind === 'asset') s += 16;
        if (b.actionKind === 'builtin') s += 6;
        if (b.actionKind === 'none') s -= 14;
        if (this.idleFavorite && b.assetName === this.idleFavorite) s += 18;
        if (b.camKind === 'vmd' && !b.showOnly) s += 10;
        if (b.camKind === 'move') s += 8;
        if (kind === 'alone') {
          if (b.intents.includes('sit')) s += 14;
          if (b.intents.includes('look')) s += 10;
          if (b.intents.includes('stretch')) s += 8;
        }
      }
      if (need.dancing && b.dance) s += 30;
      if (need.varyCam) {
        if (curSize && b.size !== curSize) s += 22;
        if (this.beatCamKey(b) !== this.recentCam()) s += 14;
        if (curSize && b.size === curSize && this.beatCamKey(b) === this.recentCam()) s -= 28;
      }
      if (need.intent && b.intents.includes(need.intent)) s += 16;
      if (this.recent.includes(b.id)) s -= 28;
      if (this.recent.includes(this.beatCamKey(b))) s -= 10;
      if (b.assetName && this.recent.includes(b.assetName) && !need.assetName) s -= 18;
      return { b, s };
    });
    scored.sort((a, c) => c.s - a.s);
    return pickCameraWeighted(scored, this.canUseRareCamera());
  }

  drop(id: string) {
    this.beats = this.beats.filter((b) => b.id !== id);
    liveRecent.value = liveRecent.value.filter((b) => b.id !== id);
  }

  get playingAssetName() {
    const motion = stage.motion.reframePlayback;
    if (!motion?.url) return undefined;
    return useAssetsStore().motions.find(item => api.assetUrl(item) === motion.url)?.name;
  }

  async perform(beat: ApprovedBeat, parts: {
    cam?: boolean; stand?: boolean; motion?: boolean;
    once?: boolean; holdLast?: boolean; onMotionEnded?: () => void;
    idleMove?: IdleMoveKind;
    speechAligned?: boolean;
    sameMotionCamera?: boolean;
    onCameraApplied?: () => void;
  } = {}) {
    const doStand = parts.stand !== false;
    const motion = parts.motion !== false;
    const danceReservation = beat.dance && motion ? stage.danceReservation : undefined;
    const playing = motion ? undefined : this.playingAssetName;
    const cam = parts.cam !== false && !stage.reviewOwnsCamera
      && (!playing || (playing === beat.assetName && beat.stand === stage.standSlot));
    const seq = motion ? ++this.playSeq : this.playSeq;
    this.remember(beat);
    const liveSeq = ++this.liveSeq;
    const record = { beat, cam: false, motion, at: Date.now(), appliedApprovedCam: false };
    const publish = () => {
      liveNow.value = { ...record };
      if (!record.cam) return;
      liveCamera.value = record.beat;
      if (record.beat.size === beat.size && this.beatCamKey(record.beat) === this.beatCamKey(beat)) {
        liveRecent.value = [record.beat, ...liveRecent.value.filter(item => item.id !== beat.id)].slice(0, 6);
      } else {
        liveRecent.value = liveRecent.value.filter(item => item.id !== beat.id);
      }
    };
    const useCamera = () => {
      const accept = (move?: CamShotId, size = beat.size) => {
        record.cam = true;
        const matchesApproval = size === beat.size && move === beat.camMove && beat.camKind !== 'vmd';
        record.beat = { ...beat, size, camKind: move ? 'move' : 'hold', camMove: move, vmdName: undefined };
        record.appliedApprovedCam = matchesApproval;
        if (liveSeq === this.liveSeq) publish();
        else liveCamera.value = record.beat;
      };
      if (beat.camKind === 'vmd' && beat.vmdName && !stage.camSizeLock?.length && !stage.reviewOwnsCamera) {
        const asset = useAssetsStore().cameras.find(item => item.name === beat.vmdName);
        if (asset) {
          void stage.playCameraVmd(api.assetUrl(asset), { once: true }).then(played => {
            if (!played || liveSeq !== this.liveSeq) return;
            this.normalShotsSinceRare += 1;
            record.cam = true;
            record.appliedApprovedCam = true;
            publish();
          });
          return;
        }
      }
      const applied = this.playCam(beat, parts.idleMove, accept, parts.sameMotionCamera);
      if (applied) {
        accept(applied.move, applied.size);
        parts.onCameraApplied?.();
      }
    };
    publish();
    if (!beat.dance && !stage.danceLive) stage.silenceBgm();

    if (useCharacterStore().modelInfo?.format === 'live2d') {
      if (doStand) live2dStage.goToStand(beat.stand);
      if (cam) useCamera();
      if (!motion || beat.actionKind === 'none') return;
      if (cam && !parts.speechAligned) await this.wait(280, seq);
      if (seq !== this.playSeq) return;
      this.playLive2DMotion(beat, parts.onMotionEnded);
      return;
    }

    if (doStand && !stage.danceLive && stage.standSlot !== beat.stand) {
      stage.goToStand(beat.stand);
      await this.wait(1100, seq);
      if (seq !== this.playSeq) return;
    }
    if (cam) useCamera();
    if (!motion || beat.actionKind === 'none') return;
    if (cam && !parts.speechAligned) await this.wait(280, seq);
    if (seq !== this.playSeq || (danceReservation !== undefined && danceReservation !== stage.danceReservation)) return;
    this.playMotion(beat, parts.once, parts.onMotionEnded, parts.holdLast);
  }

  /** 闲时一整拍：过审轻动作 + 聊天距离景别 + 轻运镜 */
  async idleMoment() {
    const beat = this.pick({
      idle: true,
      needAction: true,
      allowWalk: false,
      varyCam: true,
      preferStand: stage.standSlot,
    }) ?? this.pick({
      idle: true,
      allowWalk: false,
      varyCam: true,
      preferStand: stage.standSlot,
    });
    if (!beat) return;
    await this.perform(beat, {
      stand: false,
      cam: true,
      motion: beat.actionKind !== 'none',
      once: true,
    });
  }

  pickIdleAssetUrl(): string | null {
    const beat = this.pick({
      idle: true,
      allowWalk: false,
      preferStand: stage.standSlot,
    });
    if (!beat?.assetName) return null;
    const raw = useAssetsStore().motions.find((m) => m.name === beat.assetName);
    if (!raw) return null;
    this.remember(beat);
    return api.assetUrl(raw);
  }

  distanceOf(beat: ApprovedBeat): Distance {
    return distanceOfShot(beat.size);
  }

  private matchesIntent(b: ApprovedBeat, intent: Intent) {
    if (b.intents.includes(intent)) return true;
    if (intent === 'nod' && b.builtin === 'nod') return true;
    if (intent === 'shake' && b.builtin === 'shake') return true;
    return false;
  }

  private beatCamKey(b: ApprovedBeat) {
    if (b.camKind === 'hold') return 'hold';
    if (b.camKind === 'move') return `move:${b.camMove}`;
    return `vmd:${b.vmdName}`;
  }

  private recentCam() {
    for (let i = this.recent.length - 1; i >= 0; i--) {
      const k = this.recent[i];
      if (k === 'hold' || k.startsWith('move:') || k.startsWith('vmd:')) return k;
    }
    return '';
  }

  private canUseRareCamera() {
    return this.normalShotsSinceRare >= RARE_CAMERA_MIN_SHOTS
      && Date.now() - this.lastRareCameraAt >= RARE_CAMERA_COOLDOWN_MS;
  }

  private playCam(beat: ApprovedBeat, idleMove?: IdleMoveKind, onChange?: (move?: CamShotId) => void, sameMotion = false) {
    if (stage.reviewOwnsCamera) return;
    const rare = isAdvancedShot(beat.camMove);
    const useRare = rare && this.canUseRareCamera() && acceptsShot(stage.clampCamSize(beat.size), beat.camMove);
    const actual = stage.playAutomaticFraming(beat.size, rare && !useRare ? undefined : beat.camMove, idleMove, onChange, false, sameMotion);
    if (!actual) return;
    if (isAdvancedShot(actual.move)) {
      this.normalShotsSinceRare = 0;
      this.lastRareCameraAt = Date.now();
    } else {
      this.normalShotsSinceRare += 1;
    }
    return actual;
  }

  private playLive2DMotion(beat: ApprovedBeat, onEnded?: () => void) {
    if (beat.actionKind === 'builtin' && beat.builtin) {
      stage.triggerAction(beat.builtin);
      onEnded?.();
      return;
    }
    const card = beat.assetName ? this.cards.find((c) => c.name === beat.assetName) : undefined;
    const intent = beat.intents[0] ?? card?.tags[0] ?? 'talk';
    if (!live2dStage.playAction(intent)) stage.triggerAction('nod');
    onEnded?.();
  }

  private playMotion(beat: ApprovedBeat, once?: boolean, onEnded?: () => void, holdLast?: boolean) {
    if (beat.actionKind === 'builtin' && beat.builtin) {
      if (!beat.dance && !stage.danceLive) stage.silenceBgm();
      stage.triggerAction(beat.builtin);
      onEnded?.();
      return;
    }
    if (beat.actionKind !== 'asset' || !beat.assetName) return;
    const raw = useAssetsStore().motions.find((m) => m.name === beat.assetName);
    if (!raw) return;
    const card = this.cards.find((c) => c.name === beat.assetName);
    void playAssetMotion(raw, {
      once: once ?? (holdLast ? true : (beat.dance ? true : !card?.loop)),
      holdLast,
      skipCamera: true,
      onEnded: holdLast ? undefined : onEnded,
    });
  }

  private remember(beat: ApprovedBeat) {
    this.recent.push(beat.id);
    if (beat.assetName) this.recent.push(beat.assetName);
    this.recent.push(this.beatCamKey(beat));
    if (this.recent.length > 24) this.recent.splice(0, this.recent.length - 24);
  }

  private wait(ms: number, seq: number) {
    return new Promise<void>((resolve) => {
      window.setTimeout(() => { if (seq === this.playSeq) resolve(); else resolve(); }, ms);
    });
  }
}

export const repertoire = new Repertoire();

