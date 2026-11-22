/**
 * 表演编排器：消费对话事件流，驱动表情/动作/舞蹈/语音。
 * 文本增量按句切分送入 TTS 队列，标签事件映射到引擎控制。
 */
import type { AssetItem, ChatEvent } from '../../api/client';
import { isCamShot } from '../../engine/camera';
import { stage, type StandSlot } from '../../engine/stage';
import { live2dStage } from '../../engine/live2d';
import type { ActionKey, CamShotId, EmotionKey } from '../../engine/types';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { speechPlayer } from '../voice/tts';
import { SpeechSplitter } from '../voice/speechSplit';
import { normalizeDuplexCmd, normalizeSentenceType, type PlayableUnit } from '../voice/duplex';
import { caster } from './caster';
import { isMotionRejected, parseMotionCat, playAssetMotion, stripCatPrefix } from '../assets/motionMeta';
import { parseExpressionCue } from './expressionCue';
import { applyEmotion, parseEmotionMap } from './emotionMap';
import { shots } from './shotConductor';
import { INTENTS, type Intent } from './lexicon';
import { asksForDance, danceIntent, discussionOnlyDance, explicitDanceTitle, isDanceYes, noteDancePlayed, sampleDance, stopsCurrentDance } from './dancePick';
import { repertoire, type ApprovedBeat } from './repertoire';
import type { SidecarKind } from './caster';

const EMOTIONS: EmotionKey[] = ['neutral', 'happy', 'angry', 'sad', 'relaxed'];
const ACTIONS: ActionKey[] = ['nod', 'shake'];
const STAND_ALIASES: Record<string, StandSlot> = {
  left: 'left', l: 'left', '左': 'left', '左边': 'left', '¼': 'left', '1/4': 'left',
  center: 'center', mid: 'center', middle: 'center',
  '中': 'center', '中间': 'center', '½': 'center', '1/2': 'center',
  right: 'right', r: 'right', '右': 'right', '右边': 'right', '¾': 'right', '3/4': 'right',
};
const CAM_ALIASES: Record<string, CamShotId> = {
  close: 'close', 特写: 'close',
  bust: 'bust', '1/4': 'bust', '¼': 'bust',
  half: 'half', '1/2': 'half', '½': 'half', 半身: 'half',
  threeq: 'threeQ', '3/4': 'threeQ', '¾': 'threeQ',
  full: 'full', 全身: 'full',
  long: 'long', 远景: 'long',
  俯拍: 'high45',
  左侧: 'yawL45', 右侧: 'yawR45',
  左转: 'yawL90', 右转: 'yawR90',
  wave: 'half',
};
export function userAskedDance(text: string) {
  return asksForDance(text);
}

export class Orchestrator {
  private splitter = new SpeechSplitter();
  private turnText = '';
  private ttsStarted = false;
  private useBackendSpeech = false;
  delayedSec = 0;
  private continueMode = false;
  private sidecarKind: SidecarKind = 'qa';
  private presentationTurn = 0;
  private queuedMood: (() => void) | undefined;
  private queuedGesture: (() => boolean) | undefined;
  private queuedExpressions = new Map<string, () => void>();

  private resetFaceCues() {
    this.presentationTurn += 1;
    this.queuedMood = undefined;
    this.queuedGesture = undefined;
    this.queuedExpressions.clear();
    stage.releasePerformanceExpressions();
  }

  private takeFaceCues() {
    if (!this.queuedMood && !this.queuedGesture && !this.queuedExpressions.size) return undefined;
    const turn = this.presentationTurn;
    const character = useCharacterStore().currentId;
    const mood = this.queuedMood;
    const gesture = this.queuedGesture;
    const cues = [...this.queuedExpressions.values()];
    this.queuedMood = undefined;
    this.queuedGesture = undefined;
    this.queuedExpressions.clear();
    return () => {
      if (turn !== this.presentationTurn || character !== useCharacterStore().currentId) return;
      mood?.();
      const played = gesture?.() ?? false;
      for (const cue of cues) cue();
      return played;
    };
  }
  private fillerTimer: ReturnType<typeof setTimeout> | null = null;
  private lastUserAsk = '';
  private lastDanceName = '';
  /** 这一轮已经按用户的话开过舞。模型再点熟舞不再覆盖；点到没跳过的可以换成嘴上那支 */
  private danceThisTurn = '';
  /** 用户用「好的」答应的那支 */
  private acceptedName = '';

  private clearFillerDelay() {
    if (this.fillerTimer != null) {
      clearTimeout(this.fillerTimer);
      this.fillerTimer = null;
    }
  }

  /** 用户插话：取消还没开口的垫话 */
  cancelPendingFiller() {
    this.clearFillerDelay();
  }

  /** 每轮对话开始前调用：停语音并布置舞台，选舞交给 LLM 标签。 */
  beginTurn(userText = '', prevAssistant = '') {
    this.resetFaceCues();
    this.splitter.reset();
    this.turnText = '';
    this.ttsStarted = false;
    this.useBackendSpeech = true;
    this.delayedSec = 0;
    this.continueMode = false;
    this.sidecarKind = 'qa';
    this.clearFillerDelay();
    this.lastUserAsk = userText;
    this.danceThisTurn = '';
    this.acceptedName = '';
    const offered = isDanceYes(userText) ? this.offeredDance(prevAssistant) : undefined;
    if (offered) this.acceptedName = offered.name;
    const stopDance = stage.danceLive && stopsCurrentDance(userText);
    if (stopDance) {
      stage.stopMotion();
      shots.endDance();
    }
    const danceNow = !stopDance && (stage.danceLive || asksForDance(userText) || !!offered);
    speechPlayer.beginNewQa();
    speechPlayer.streamOpen = true;
    stage.director.notifyThinking();
    caster.beginTurn(userText, { keepDance: danceNow });
  }

  /** 超时续聊 / 欢迎 / 告别：不开新一轮选角，正在跳的舞也不要被思考/句拍动作掐掉 */
  beginContinue(kind: Exclude<SidecarKind, 'qa'> = 'delayed') {
    this.resetFaceCues();
    this.splitter.reset();
    this.turnText = '';
    this.ttsStarted = false;
    this.useBackendSpeech = true;
    this.delayedSec = 0;
    this.continueMode = true;
    this.sidecarKind = kind;
    this.clearFillerDelay();
    speechPlayer.beginNewQa();
    speechPlayer.streamOpen = true;
    caster.beginSidecar(kind);
  }

  /** 无 API Key 的本地兜底：改走前端分句 TTS */
  allowLocalSpeech() {
    this.useBackendSpeech = false;
    this.ttsStarted = false;
  }

  handle(ev: ChatEvent, noteTiming?: PlayableUnit['noteTiming']) {
    switch (ev.type) {
      case 'speech': {
        this.useBackendSpeech = true;
        if (ev.kind === 'filler') break;
        this.clearFillerDelay();
        this.ttsStarted = true;
        if (ev.kind !== 'filler') {
          this.turnText += ev.text;
          caster.preview(this.turnText);
        }
        speechPlayer.pushUnit({
          text: ev.text,
          duplexCmd: normalizeDuplexCmd(ev.duplex_cmd),
          sentenceType: normalizeSentenceType(ev.sentence_type),
          kind: ev.kind,
          id: ev.id,
          onAudible: this.takeFaceCues(),
          noteTiming,
        });
        break;
      }
      case 'duplex_decision':
        speechPlayer.applyTurnDuplex(ev.duplex_cmd);
        break;
      case 'duplex':
        this.delayedSec = Number(ev.delayed_sec) || 0;
        break;
      case 'text':
        this.feedText(ev.delta);
        break;
      case 'emo': {
        // 支持强度：[emo:happy:0.8]，缺省 0.85
        const [name, numStr] = ev.value.split(':');
        const emo = name.trim() as EmotionKey;
        if (EMOTIONS.includes(emo)) {
          const n = parseFloat(numStr);
          const intensity = Number.isFinite(n) ? Math.min(Math.max(n, 0), 1) : 0.85;
          const char = useCharacterStore().current;
          const map = parseEmotionMap(char?.emotion_map ?? '{}');
          this.queuedMood = () => applyEmotion(emo, map, intensity);
          caster.markEmotion();
        }
        break;
      }
      case 'intent': {
        const raw = ev.value.trim().toLowerCase();
        const intent = raw === 'wave' ? 'greet' : raw;
        if (intent !== 'dance' && INTENTS.includes(intent as Intent)) {
          this.queuedGesture = () => !stage.danceLive && caster.applyIntent(intent);
        }
        break;
      }
      case 'motion': {
        if (useCharacterStore().modelInfo?.format !== 'live2d') break;
        const cut = ev.value.lastIndexOf(':');
        const group = ev.value.slice(0, cut).trim();
        const index = Number(ev.value.slice(cut + 1));
        if (group && Number.isInteger(index) && index >= 0) live2dStage.playMotion(group, index);
        break;
      }
      case 'outfit': {
        if (useCharacterStore().modelInfo?.format !== 'live2d') break;
        const cut = ev.value.lastIndexOf(':');
        const name = ev.value.slice(0, cut).trim();
        const state = ev.value.slice(cut + 1).trim().toLowerCase();
        if (name && (state === 'on' || state === 'off')) {
          void live2dStage.setExpressionEnabled(name, state === 'on').catch(() => {});
        }
        break;
      }
      case 'param': {
        if (useCharacterStore().modelInfo?.format !== 'live2d') break;
        const cut = ev.value.indexOf('=');
        const id = ev.value.slice(0, cut).trim();
        const value = Number(ev.value.slice(cut + 1));
        const meta = live2dStage.parameterMeta().find((item) => item.id === id);
        if (meta && Number.isFinite(value) && value >= meta.min && value <= meta.max) {
          live2dStage.setParameter(id, value);
        }
        break;
      }
      case 'preset':
        if (useCharacterStore().modelInfo?.format === 'live2d') {
          void live2dStage.applyPreset(ev.value.trim()).catch(() => {});
        }
        break;
      case 'act': {
        if (stage.danceLive) break;
        const act = ev.value.trim();
        if (!act || act === 'dance') break;
        this.queuedGesture = () => {
          if (stage.danceLive) return false;
          if (act === 'wave') return caster.applyIntent('greet');
          if (ACTIONS.includes(act as ActionKey)) return caster.applyIntent(act);
          const played = this.playMotionByName(act);
          if (played) caster.markMotion();
          return played;
        };
        break;
      }
      case 'dance':
        if (this.continueMode) break;
        if (this.playDance(ev.value)) caster.markDance();
        break;
      case 'cam': {
        if (stage.danceLive || caster.holdingDance) break;
        const raw = ev.value.trim().toLowerCase();
        const alias = CAM_ALIASES[raw] ?? (isCamShot(raw) ? raw : null);
        if (alias) {
          shots.suggest(alias, {
            beat: 'line',
            phase: this.sidecarKind,
            mood: stage.director.moodKey,
            intensity: stage.director.moodIntensity,
            dancing: caster.holdingDance,
          });
        } else {
          this.playCameraByName(ev.value);
        }
        break;
      }
      case 'stand': {
        if (stage.danceLive) break;
        const key = ev.value.trim().toLowerCase();
        const slot = STAND_ALIASES[key] ?? STAND_ALIASES[ev.value.trim()];
        if (!slot || !repertoire.allowsStand(slot)) break;
        const beat = repertoire.pick({
          stand: slot,
          allowWalk: true,
          preferSize: shots.current ?? undefined,
        });
        if (!beat) break;
        shots.syncFromBeat(beat);
        void repertoire.perform(beat, { motion: false });
        break;
      }
      case 'expr': {
        const model = useCharacterStore().modelInfo;
        const names = model?.format === 'live2d' ? live2dStage.capabilities.expressions : (model?.morphNames ?? []);
        const cue = parseExpressionCue(ev.value, names);
        if (!cue) break;
        if (this.queuedExpressions.size >= 2 && !this.queuedExpressions.has(cue.name)) break;
        this.queuedExpressions.set(cue.name, () => {
          if (model === useCharacterStore().modelInfo) stage.setPerformanceExpression(cue.name, cue.weight, cue.seconds);
        });
        break;
      }
      case 'done':
        if (!this.useBackendSpeech) this.flushText();
        else this.splitter.reset();
        if (!this.ttsStarted) this.takeFaceCues()?.();
        else {
          this.queuedMood = undefined;
          this.queuedGesture = undefined;
          this.queuedExpressions.clear();
        }
        speechPlayer.streamOpen = false;
        stage.director.notifyTurnDone();
        caster.finalize(ev.full_text || '');
        break;
      case 'picture':
        if (useCharacterStore().modelInfo?.format === 'live2d') live2dStage.playAction('heart');
        if (!ev.url) {
          void import('../draw/card').then((m) => m.showDrawnCard('', ''));
          break;
        }
        void import('../tarot/session').then((m) => m.showDrawnPicture(ev.url, ev.name || ''));
        break;
      case 'drawing':
        if (useCharacterStore().modelInfo?.format === 'live2d') live2dStage.playAction('cute');
        void import('../draw/card').then((m) => m.showDrawing(ev.name || ''));
        break;
      case 'tarot':
      case 'meta':
      case 'error':
        break;
      default:
        break;
    }
  }

  private feedText(delta: string) {
    if (this.useBackendSpeech) return;
    for (const sent of this.splitter.feed(delta)) this.emitSentence(sent);
  }

  private emitSentence(sentence: string) {
    const text = sentence.trim();
    if (!text) return;
    this.ttsStarted = true;
    this.turnText += text;
    caster.preview(this.turnText);
    speechPlayer.enqueue(text, this.takeFaceCues());
  }

  private flushText() {
    for (const sent of this.splitter.flush()) this.emitSentence(sent);
  }

  private playDance(nameOrLabel: string): boolean {
    const assets = useAssetsStore();
    const format = useCharacterStore().modelInfo?.format;
    if (format === 'live2d') return false;
    const supported = (m: AssetItem) => !format || format === 'pmx' || !/\.vmd$/i.test(m.name);
    const inventory = assets.motions.filter(m => parseMotionCat(m) === 'dance');
    const dances = inventory.filter(m => supported(m) && !isMotionRejected(m) && repertoire.allowsAsset(m.name));
    if (!dances.length || stopsCurrentDance(this.lastUserAsk) || discussionOnlyDance(this.lastUserAsk)) return false;
    const norm = (s: string) => s.replace(/\.(?:vmd|fbx|xkmotion)$/i, '').trim().toLowerCase();
    const bare = (m: AssetItem) => stripCatPrefix(m.label).trim() || m.name;
    const ask = this.lastUserAsk;
    const fullName = this.acceptedName
      ? inventory.find(m => norm(m.name) === norm(this.acceptedName))
      : this.danceNamedIn(ask, inventory, bare, norm);
    const intent = danceIntent(ask);
    const title = intent === 'open' ? explicitDanceTitle(ask) : '';
    const tagged = nameOrLabel.trim() ? dances.find(m => norm(m.name) === norm(nameOrLabel) || norm(bare(m)) === norm(nameOrLabel)) : undefined;
    const matches = title ? dances.filter(m => norm(bare(m)).includes(norm(title)) || norm(m.name).includes(norm(title))) : [];
    const named = fullName ?? (matches.length === 1 ? matches[0] : undefined);
    if (!named && !asksForDance(ask)) return false;
    if (named && !dances.includes(named)) return false;
    if (this.danceThisTurn) return true;
    let motion: AssetItem | null | undefined;
    if (named) motion = named;
    else if (intent === 'repeat') motion = dances.find(m => norm(m.name) === norm(this.lastDanceName));
    else if (intent === 'switch') motion = sampleDance(dances.filter(m => norm(m.name) !== norm(this.lastDanceName)), m => m.name, 'switch');
    else if (title) motion = tagged && matches.includes(tagged) ? tagged : undefined;
    else motion = sampleDance(dances, m => m.name, 'open');
    if (!motion) return false;
    const beat = repertoire.allowsAsset(motion.name)
      ? repertoire.pick({
          dancing: true,
          assetName: motion.name,
          allowWalk: true,
          preferStand: stage.standSlot,
          varyCam: true,
        }) ?? repertoire.pick({ assetName: motion.name, allowWalk: true, varyCam: true })
      : null;
    if (this.launchDance(beat)) return true;
    return this.launchDanceAsset(motion);
  }

  /** 对话开的舞：有配乐跟歌唱完，没配乐只跳一轮，然后停。 */
  private launchDance(beat: ApprovedBeat | null): boolean {
    if (!beat?.assetName) return false;
    this.lastDanceName = beat.assetName;
    this.danceThisTurn = beat.assetName;
    noteDancePlayed(beat.assetName);
    stage.holdDance();
    shots.beginDance(beat.assetName);
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, {
      once: true,
      stand: false,
      onMotionEnded: () => shots.endDance(),
    });
    return true;
  }

  private launchDanceAsset(motion: AssetItem): boolean {
    if (!motion?.name) return false;
    this.lastDanceName = motion.name;
    this.danceThisTurn = motion.name;
    noteDancePlayed(motion.name);
    stage.holdDance();
    shots.beginDance(motion.name);
    void playAssetMotion(motion, {
      once: true,
      onEnded: () => shots.endDance(),
    });
    return true;
  }

  /** 上一句嘴里点到的舞。用户说好的，就跳这支。 */
  private offeredDance(text: string) {
    const assets = useAssetsStore();
    const dances = assets.motions.filter((m) => parseMotionCat(m) === 'dance');
    if (!dances.length || !text.trim()) return undefined;
    const norm = (s: string) => s.replace(/\.(?:vmd|fbx|xkmotion)$/i, '').trim().toLowerCase();
    const bare = (m: { label: string; name: string }) => stripCatPrefix(m.label).trim() || m.name;
    return this.danceNamedIn(text, dances, bare, norm, true);
  }

  /** 用户话里点到的舞名。最长的名字优先，避免短词误撞。 */
  private danceNamedIn<T extends { label: string; name: string }>(
    ask: string,
    dances: T[],
    bare: (m: T) => string,
    norm: (s: string) => string,
    requireUnique = false,
  ) {
    const text = ask || '';
    const low = text.toLowerCase();
    const hits = dances.filter((m) => {
      const label = bare(m);
      const file = norm(m.name);
      return (label.length >= 2 && text.includes(label))
        || (file.length >= 2 && low.includes(file));
    });
    hits.sort((a, b) => bare(b).length - bare(a).length);
    if (requireUnique && hits.length > 1 && hits.slice(1).some(m => bare(m) === bare(hits[0]) || !bare(hits[0]).includes(bare(m)))) return undefined;
    return hits[0];
  }

  private playMotionByName(nameOrLabel: string) {
    const assets = useAssetsStore();
    const target = nameOrLabel.trim().replace(/\.(?:vmd|fbx|xkmotion)$/i, '');
    if (!target) return false;
    const bare = (m: { label: string }) => stripCatPrefix(m.label).trim();
    const motion =
      assets.motions.find((m) => m.name === target || m.name === `${target}.vmd` || m.name === `${target}.fbx` || m.name === `${target}.xkmotion`) ??
      assets.motions.find((m) => bare(m) === target) ??
      assets.motions.find((m) => m.name.includes(target) || bare(m).includes(target));
    if (!motion || isMotionRejected(motion) || !repertoire.allowsAsset(motion.name)) return false;
    if (parseMotionCat(motion) === 'dance') return false;
    const beat = repertoire.pick({
      assetName: motion.name,
      allowWalk: true,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) return false;
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, { speechAligned: true });
    return true;
  }

  private playCameraByName(nameOrLabel: string) {
    const assets = useAssetsStore();
    const target = nameOrLabel.trim().replace(/\.vmd$/i, '');
    const bare = (c: { label: string }) => stripCatPrefix(c.label).trim();
    const cam =
      assets.cameras.find((c) => c.name === target || c.name === `${target}.vmd`) ??
      assets.cameras.find((c) => bare(c) === target) ??
      assets.cameras.find((c) => c.name.includes(target) || bare(c).includes(target));
    if (!cam || !repertoire.allowsCam(cam.name)) return;
    const beat = repertoire.pick({
      camKey: `vmd:${cam.name}`,
      allowWalk: false,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) return;
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, { motion: false, stand: false });
  }

  /** 同一句台词换情绪/意图再演，不调 LLM。 */
  recast(text: string, emo: EmotionKey = 'relaxed', intent = 'talk') {
    const plain = text.trim();
    if (!plain) return;
    this.beginTurn('');
    this.allowLocalSpeech();
    this.handle({ type: 'emo', value: emo });
    this.handle({ type: 'intent', value: intent });
    this.handle({ type: 'cam', value: 'half' });
    this.handle({ type: 'text', delta: plain });
    this.handle({ type: 'done', full_text: plain });
  }
}

export const orchestrator = new Orchestrator();
