/**
 * 表演选角器：世界级用法的核心。
 * LLM 只给情绪 / 意图；本模块用语义目录从动作库、表情库配一整套表演，
 * 并在用户开口的瞬间先反应（不等回复）。
 */
import { api, type AssetItem } from '../../api/client';
import { stage } from '../../engine/stage';
import type { EmotionKey } from '../../engine/types';
import {
  type ExprKind,
  type Intent,
  type LineBeat,
  type LineCast,
  type TurnPlan,
  analyzeLine,
  exprKindsFor,
  inferEmotion,
  inferIntents,
  INTENTS,
  planTurn,
} from './catalog';
import {
  type MotionCard,
  buildMotionCards,
  cardsByTag,
  groupMorphs,
  idleCards,
} from './lexicon';
import { playAssetMotion } from '../assets/motionMeta';
import { applyEmotion, parseEmotionMap } from './emotionMap';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { shots } from './shotConductor';
import { repertoire } from './repertoire';
import {
  comboByDistance,
  distanceOfShot,
  exprKindsAllowed,
} from './grammar';

const EXPR_HOLD_MS = 9000;
const RECENT_CAP = 8;

function pickFresh<T>(pool: T[], recent: string[], key: (x: T) => string): T | null {
  if (!pool.length) return null;
  const fresh = pool.filter((x) => !recent.includes(key(x)));
  const src = fresh.length ? fresh : pool;
  return src[Math.floor(Math.random() * src.length)] ?? null;
}

export type SidecarKind = 'qa' | 'welcome' | 'delayed' | 'proactive' | 'goodbye';

export class PerformanceCaster {
  private cards: MotionCard[] = [];
  private morphByKind = new Map<ExprKind, string[]>();
  private idlePool: MotionCard[] = [];
  private recentMotions: string[] = [];
  private recentMorphs: string[] = [];
  private exprTimers = new Map<string, ReturnType<typeof setTimeout>>();

  private userText = '';
  private lastLine = '';
  private motionThisTurn = false;
  private danceThisTurn = false;
  private emotionSet = false;
  private lastSpeakMotionAt = 0;
  private lastLineAt = 0;
  private liveMorphs: string[] = [];
  private plan: TurnPlan | null = null;
  sidecarKind: SidecarKind = 'qa';
  private sidecarGesture = false;

  private ensureIndex() {
    const filled = this.cards.length > 0;
    const hasMorph = [...this.morphByKind.values()].some((a) => a.length);
    if (filled && hasMorph) return;
    this.indexFrom(useAssetsStore().motions, useCharacterStore().modelInfo?.morphNames ?? []);
  }

  indexFrom(motions: AssetItem[], morphNames: string[]) {
    this.cards = buildMotionCards(motions);
    this.morphByKind = groupMorphs(morphNames);
    this.idlePool = idleCards(this.cards, false);
    (window as unknown as { __lexicon?: MotionCard[] }).__lexicon = this.cards;
  }

  /** 一轮对话开始：立刻根据用户话反应，不等 LLM */
  beginTurn(userText: string) {
    this.ensureIndex();
    this.userText = userText;
    this.motionThisTurn = false;
    const wasDance = this.danceThisTurn;
    this.danceThisTurn = false;
    this.emotionSet = false;
    this.plan = null;
    this.sidecarKind = 'qa';
    this.sidecarGesture = false;
    shots.setIdleMode('chat');
    shots.endDance();
    if (wasDance) stage.stopMotion();
    shots.cover({
      beat: 'open',
      phase: 'qa',
      text: userText,
      mood: stage.director.moodKey,
      intensity: stage.director.moodIntensity,
      llmShot: stage.director.sceneCam ?? undefined,
      intents: stage.director.sceneIntent ? [stage.director.sceneIntent] : undefined,
      dancing: /跳.*舞|来一段|来一支|dance/i.test(userText),
    });
    this.reactToUser(userText);
  }

  /** 欢迎 / 续聊 / 告别：不重选角、不掐正在跳的舞 */
  beginSidecar(kind: Exclude<SidecarKind, 'qa'>) {
    this.ensureIndex();
    this.motionThisTurn = false;
    this.emotionSet = false;
    this.plan = null;
    this.sidecarKind = kind;
    this.sidecarGesture = false;
    if (kind === 'goodbye') shots.armAloneIdle();
    else shots.setIdleMode('chat');
    shots.cover({
      beat: 'open',
      phase: kind,
      mood: stage.director.moodKey,
      intensity: stage.director.moodIntensity,
      llmShot: stage.director.sceneCam ?? undefined,
      intents: stage.director.sceneIntent ? [stage.director.sceneIntent] : undefined,
      dancing: this.danceThisTurn,
    });
  }

  markEmotion() { this.emotionSet = true; }
  markMotion() { this.motionThisTurn = true; }
  markDance() {
    this.danceThisTurn = true;
    shots.onDanceEnded = () => { this.danceThisTurn = false; };
  }
  get holdingDance() { return this.danceThisTurn; }

  /** 审查：播指定动作资产，关掉自带镜头以免盖住正在审的运镜 */
  playAssetForReview(name: string): boolean {
    this.ensureIndex();
    const raw = useAssetsStore().motions.find((m) => m.name === name);
    if (!raw) return false;
    const card = this.cards.find((c) => c.name === name);
    void playAssetMotion(raw, { once: !card?.loop, skipCamera: true });
    return true;
  }

  /** 审查：不看景别门禁，直接播这类动作让人眼看合不合 */
  playForReview(intent: Intent): boolean {
    this.ensureIndex();
    this.danceThisTurn = false;
    shots.endDance();
    if (intent === 'nod') {
      stage.triggerAction('nod');
      return true;
    }
    if (intent === 'shake') {
      stage.triggerAction('shake');
      return true;
    }
    const pool = cardsByTag(this.cards, intent);
    const item = pickFresh(pool, this.recentMotions, (c) => c.name);
    if (!item) return false;
    this.rememberMotion(item.name);
    const raw = useAssetsStore().motions.find((m) => m.name === item.name);
    if (!raw) return false;
    void playAssetMotion(raw, { once: !item.loop });
    return true;
  }

  applyIntent(raw: string): boolean {
    let name = raw.trim().toLowerCase();
    if (name === 'wave') name = 'greet';
    if (!INTENTS.includes(name as Intent)) return false;
    const intent = name as Intent;
    if (this.sidecarKind === 'delayed' || this.sidecarKind === 'proactive') {
      if (!['nod', 'look', 'tease', 'talk', 'think', 'shy'].includes(intent)) return false;
    }
    const kinds = exprKindsFor(stage.director.moodKey, stage.director.moodIntensity, [intent]);
    this.applyExprKinds(kinds, stage.director.moodIntensity || 0.7);
    return this.playIntent(intent);
  }

  /** 边生成边更新整段计划，让第一句之后就按长叙述走 */
  preview(partial: string) {
    const mood = stage.director.moodKey || 'happy';
    const next = planTurn(partial, mood);
    this.plan = next;
    if (!this.emotionSet && next.baseKinds.length) {
      this.setEmotion(next.baseMood, next.baseIntensity);
      this.applyExprKinds(next.baseKinds, next.baseIntensity, 14000);
    }
  }

  /** LLM 流结束：按整段回复排主表演，小句只在节拍上加料 */
  finalize(assistantText: string) {
    const mood = stage.director.moodKey;
    this.plan = planTurn(assistantText, mood);
    if (!this.emotionSet) {
      this.setEmotion(this.plan.baseMood, this.plan.baseIntensity);
    }
    this.applyExprKinds(this.plan.baseKinds, this.plan.baseIntensity, 14000);
    const intents = inferIntents(this.userText, assistantText);
    shots.cover({
      beat: 'close',
      phase: this.sidecarKind,
      text: assistantText,
      mood: this.plan.baseMood,
      intensity: this.plan.baseIntensity,
      dancing: this.danceThisTurn,
      intents,
    });
  }

  /** 说话中按句补动作，跟着语义走 */
  onSpeakBeat() {
    if (this.danceThisTurn) return;
    if (Date.now() - this.lastSpeakMotionAt < 1600) return;
    const mood = stage.director.moodKey;
    this.performPhrase({
      kinds: exprKindsFor(mood, 0.55, ['talk']),
      motion: 'talk',
      intensity: 0.55,
      mood,
    });
  }

  /** 一句开播：表情 + 过审动作组一起跟上 */
  onSpeakSentence(text: string, allowMotion = true) {
    this.ensureIndex();
    if (this.danceThisTurn) return;
    const line = text.trim();
    if (!line) return;
    this.lastLine = line;
    this.lastLineAt = Date.now();

    const planBeat = this.matchBeat(line);
    if (this.plan?.narrative) {
      this.applyNarrativeBeat(planBeat, allowMotion);
      return;
    }

    const cast = planBeat ?? analyzeLine(line, stage.director.moodKey);
    this.performPhrase(cast, allowMotion);
  }

  /** 闲时微表情：轻微笑 / 眨眼 / 放松，不抢大动作 */
  onIdleBeat() {
    this.ensureIndex();
    const mood = stage.director.moodKey;
    const kinds = exprKindsFor(mood, 0.4, []);
    if (!kinds.length) kinds.push(mood === 'sad' ? 'sadEye' : 'relax');
    if (Math.random() < 0.35) kinds.push('wink');
    this.applyExprKinds(kinds.slice(0, 1), 0.4, 3200);
  }

  /** 待机：按当前心情从库里挑，避免连播同一个 */
  pickIdleUrl(): string | null {
    return repertoire.pickIdleAssetUrl();
  }

  private matchBeat(line: string): LineBeat | undefined {
    if (!this.plan) return undefined;
    const n = line.replace(/\s/g, '');
    return this.plan.beats.find((b) => {
      const t = b.text.replace(/\s/g, '');
      return t.includes(n) || n.includes(t) || t.slice(0, 10) === n.slice(0, 10);
    });
  }

  /** 讲长段时每句也有身体，反转句加重点 */
  private applyNarrativeBeat(beat: LineBeat | undefined, allowMotion: boolean) {
    const cast = beat ?? analyzeLine(this.lastLine, stage.director.moodKey);
    this.performPhrase({
      ...cast,
      motion: cast.motion || 'talk',
      intensity: beat?.special ? Math.max(cast.intensity, 0.8) : cast.intensity,
    }, allowMotion);
  }

  /** 一句：表情先到，再从过审表抽一套动作+景别+运镜 */
  private performPhrase(cast: LineCast, allowMotion = true) {
    if (this.danceThisTurn) return;
    if (cast.mood) this.setEmotion(cast.mood, cast.intensity);
    if (cast.kinds.length) this.shiftExpr(cast.kinds, cast.intensity);
    if (!allowMotion) return;
    if (stage.motion.active) return;
    if (Date.now() - this.lastSpeakMotionAt < 2200) return;

    const wanted = (cast.motion && repertoire.hasIntent(cast.motion))
      ? cast.motion
      : (['talk', 'look', 'nod'] as Intent[]).find((i) => repertoire.hasIntent(i));
    if (!wanted) return;

    const needWalk = wanted === 'walk' || wanted === 'sit' || wanted === 'dance';
    const beat = repertoire.pick({
      intent: wanted,
      phrase: true,
      allowWalk: needWalk,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    }) ?? repertoire.pick({
      intent: wanted,
      phrase: true,
      allowWalk: true,
      preferStand: stage.standSlot,
    }) ?? repertoire.pick({
      intent: wanted,
      allowWalk: needWalk,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) return;

    this.lastSpeakMotionAt = Date.now();
    this.motionThisTurn = true;
    this.sidecarGesture = true;
    if (beat.assetName) this.rememberMotion(beat.assetName);
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, {
      cam: true,
      motion: true,
      stand: needWalk || beat.intents.includes('walk') || beat.intents.includes('sit'),
    });
  }

  /** 换表情时只拿掉互斥的，主表情留下来，才像一个人把故事讲完 */
  private shiftExpr(kinds: ExprKind[], intensity: number) {
    this.applyExprKinds(kinds, intensity, 8000);
  }

  private trySpeakMotion(intent: Intent) {
    this.performPhrase({ kinds: exprKindsFor(stage.director.moodKey, 0.7, [intent]), motion: intent, intensity: 0.7 });
  }

  private reactToUser(user: string) {
    if (!user.trim()) return;
    if (/跳.*舞|来一段|来一支|dance/i.test(user)) return; // 跳舞留给 [dance:]
    const intents = inferIntents(user, '');
    const guessed = inferEmotion(user, '');
    if (guessed) this.setEmotion(guessed.key, Math.min(guessed.intensity, 0.65));
    const mood = stage.director.moodKey;
    const intensity = stage.director.moodIntensity || 0.55;
    this.applyExprKinds(exprKindsFor(mood, intensity, intents), intensity * 0.85);

    const immediate = intents.find((i) => ['greet', 'think', 'shy', 'heart', 'comfort'].includes(i));
    if (immediate && repertoire.hasIntent(immediate)) this.playIntent(immediate);
  }

  private setEmotion(key: EmotionKey, intensity: number) {
    const char = useCharacterStore().current;
    applyEmotion(key, parseEmotionMap(char?.emotion_map ?? '{}'), intensity);
    this.emotionSet = true;
  }

  private playIntent(intent: Intent): boolean {
    if (this.danceThisTurn) return false;
    const beat = repertoire.pick({
      intent,
      phrase: true,
      allowWalk: intent === 'walk' || intent === 'sit' || intent === 'dance',
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    }) ?? repertoire.pick({
      intent,
      phrase: true,
      allowWalk: true,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) return false;
    this.motionThisTurn = true;
    if (beat.assetName) this.rememberMotion(beat.assetName);
    shots.syncFromBeat(beat);
    void repertoire.perform(beat);
    return true;
  }

  private playSpeakMotion(intent: Intent): boolean {
    if (this.danceThisTurn) return false;
    const beat = repertoire.pick({
      intent,
      phrase: true,
      allowWalk: false,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) {
      if (intent === 'nod' && repertoire.beats.some((b) => b.builtin === 'nod')) {
        stage.triggerAction('nod');
        this.lastSpeakMotionAt = Date.now();
        return true;
      }
      if (intent === 'shake' && repertoire.beats.some((b) => b.builtin === 'shake')) {
        stage.triggerAction('shake');
        this.lastSpeakMotionAt = Date.now();
        return true;
      }
      return false;
    }
    if (beat.assetName) this.rememberMotion(beat.assetName);
    this.lastSpeakMotionAt = Date.now();
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, { stand: false });
    return true;
  }

  private applyExprKinds(kinds: ExprKind[], intensity: number, holdMs = EXPR_HOLD_MS) {
    const allowed = exprKindsAllowed(kinds, shots.current, stage.director.moodKey);
    const combo = comboByDistance(distanceOfShot(shots.current));
    const strength = Math.min(1, (combo.exprLead ? 0.55 : 0.4) + intensity * 0.55);
    let applied = 0;
    for (const kind of allowed) {
      if (applied >= 2) break;
      const pool = this.morphByKind.get(kind) ?? [];
      const name = pickFresh(pool, this.recentMorphs, (n) => n);
      if (!name) continue;
      this.flashMorph(name, strength, holdMs);
      this.liveMorphs.push(name);
      this.recentMorphs.push(name);
      if (this.recentMorphs.length > RECENT_CAP) this.recentMorphs.shift();
      applied += 1;
    }
  }

  private fadeLiveMorphs() {
    for (const name of this.liveMorphs) {
      clearTimeout(this.exprTimers.get(name));
      stage.setMorph(name, false);
      this.exprTimers.delete(name);
    }
    this.liveMorphs = [];
  }

  private flashMorph(name: string, strength: number, holdMs = EXPR_HOLD_MS) {
    stage.setMorph(name, strength);
    clearTimeout(this.exprTimers.get(name));
    this.exprTimers.set(name, setTimeout(() => {
      stage.setMorph(name, false);
      this.exprTimers.delete(name);
    }, holdMs));
  }

  private rememberMotion(name: string) {
    this.recentMotions.push(name);
    if (this.recentMotions.length > RECENT_CAP) this.recentMotions.shift();
  }
}

export const caster = new PerformanceCaster();
