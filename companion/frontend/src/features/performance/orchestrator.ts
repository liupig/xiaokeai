/**
 * 表演编排器：消费对话事件流，驱动表情/动作/舞蹈/语音。
 * 文本增量按句切分送入 TTS 队列，标签事件映射到引擎控制。
 */
import type { ChatEvent } from '../../api/client';
import { isCamShot } from '../../engine/camera';
import { stage, type StandSlot } from '../../engine/stage';
import type { ActionKey, CamShotId, EmotionKey } from '../../engine/types';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { speechPlayer } from '../voice/tts';
import { normalizeDuplexCmd, normalizeSentenceType } from '../voice/duplex';
import { caster } from './caster';
import { parseMotionCat, stripCatPrefix } from '../assets/motionMeta';
import { applyEmotion, parseEmotionMap } from './emotionMap';
import { shots } from './shotConductor';
import { repertoire, type ApprovedBeat } from './repertoire';
import type { SidecarKind } from './caster';

const EMOTIONS: EmotionKey[] = ['neutral', 'happy', 'angry', 'sad', 'relaxed'];
const ACTIONS: ActionKey[] = ['wave', 'nod', 'shake'];
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
  仰拍: 'low45', 俯拍: 'high45',
  左侧: 'yawL45', 右侧: 'yawR45',
  左转: 'yawL90', 右转: 'yawR90',
  wave: 'half',
};
const HARD_END = /[。！？!?；;\n]/;
const SOFT_END = /[，、～~]/;
/** 首句不必等句号：攒够这些字就先送去合成，后面的仍按句切。 */
const FIRST_FLUSH_CHARS = 10;
const MAX_UNIT_CHARS = 15;

export class Orchestrator {
  private sentenceBuf = '';
  private turnText = '';
  private ttsStarted = false;
  private useBackendSpeech = false;
  delayedSec = 0;
  private continueMode = false;
  private sidecarKind: SidecarKind = 'qa';
  /** LLM 叠加表情的自动淡出计时器 */
  private exprTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private fillerTimer: ReturnType<typeof setTimeout> | null = null;
  private lastUserAsk = '';
  private lastDanceName = '';

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

  /** 每轮对话开始前调用：停语音，进入思考，并立刻按用户话选角 */
  beginTurn(userText = '') {
    this.sentenceBuf = '';
    this.turnText = '';
    this.ttsStarted = false;
    this.useBackendSpeech = true;
    this.delayedSec = 0;
    this.continueMode = false;
    this.sidecarKind = 'qa';
    this.clearFillerDelay();
    this.lastUserAsk = userText;
    speechPlayer.beginNewQa();
    speechPlayer.streamOpen = true;
    stage.director.notifyThinking();
    caster.beginTurn(userText);
  }

  /** 超时续聊 / 欢迎 / 告别：不开新一轮选角，正在跳的舞也不要被思考/句拍动作掐掉 */
  beginContinue(kind: Exclude<SidecarKind, 'qa'> = 'delayed') {
    this.sentenceBuf = '';
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

  handle(ev: ChatEvent) {
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
        });
        break;
      }
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
          applyEmotion(emo, parseEmotionMap(char?.emotion_map ?? '{}'), intensity);
          caster.markEmotion();
        }
        break;
      }
      case 'intent':
        caster.applyIntent(ev.value);
        break;
      case 'act': {
        if (this.continueMode && caster.holdingDance) break;
        const act = ev.value as ActionKey;
        if (ACTIONS.includes(act)) {
          const mapped = act === 'wave' ? 'greet' : act;
          caster.applyIntent(mapped);
          break;
        }
        this.playMotionByName(ev.value, { once: true });
        caster.markMotion();
        break;
      }
      case 'dance':
        if (this.continueMode) break;
        if (this.playDance(ev.value)) caster.markDance();
        break;
      case 'cam': {
        if (caster.holdingDance) break;
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
        // 模型自带形态键叠加（如 頬染め / ウィンク），8 秒后自动淡出
        const name = ev.value.trim();
        if (!name) break;
        stage.setMorph(name, true);
        clearTimeout(this.exprTimers.get(name));
        this.exprTimers.set(name, setTimeout(() => {
          stage.setMorph(name, false);
          this.exprTimers.delete(name);
        }, 8000));
        break;
      }
      case 'done':
        if (!this.useBackendSpeech) this.flushText();
        else this.sentenceBuf = '';
        speechPlayer.streamOpen = false;
        stage.director.notifyTurnDone();
        caster.finalize(ev.full_text || '');
        break;
      default:
        break;
    }
  }

  private feedText(delta: string) {
    if (this.useBackendSpeech) return;
    this.sentenceBuf += delta;
    this.drainBy(HARD_END);
    if (!this.ttsStarted && this.sentenceBuf.trim()) {
      const soft = this.sentenceBuf.search(SOFT_END);
      if (soft >= 3) {
        this.emitSentence(this.sentenceBuf.slice(0, soft + 1));
        this.sentenceBuf = this.sentenceBuf.slice(soft + 1);
      } else if (Array.from(this.sentenceBuf).length >= FIRST_FLUSH_CHARS) {
        const chars = Array.from(this.sentenceBuf);
        this.emitSentence(chars.slice(0, FIRST_FLUSH_CHARS).join(''));
        this.sentenceBuf = chars.slice(FIRST_FLUSH_CHARS).join('');
      }
    }
    this.drainBy(HARD_END);
    this.drainLong();
  }

  private drainLong() {
    const chars = Array.from(this.sentenceBuf);
    while (this.ttsStarted && chars.length >= MAX_UNIT_CHARS) {
      this.emitSentence(chars.splice(0, MAX_UNIT_CHARS).join(''));
    }
    this.sentenceBuf = chars.join('');
  }

  private drainBy(re: RegExp) {
    let idx: number;
    while ((idx = this.sentenceBuf.search(re)) !== -1) {
      this.emitSentence(this.sentenceBuf.slice(0, idx + 1));
      this.sentenceBuf = this.sentenceBuf.slice(idx + 1);
    }
  }

  private emitSentence(sentence: string) {
    const text = sentence.trim();
    if (!text) return;
    this.ttsStarted = true;
    const chars = Array.from(text);
    for (let i = 0; i < chars.length; i += MAX_UNIT_CHARS) {
      const piece = chars.slice(i, i + MAX_UNIT_CHARS).join('');
      this.turnText += piece;
      caster.preview(this.turnText);
      speechPlayer.enqueue(piece);
    }
  }

  private flushText() {
    if (this.sentenceBuf.trim()) this.emitSentence(this.sentenceBuf);
    this.sentenceBuf = '';
  }

  private playDance(nameOrLabel: string): boolean {
    const assets = useAssetsStore();
    const dances = assets.motions.filter((m) =>
      parseMotionCat(m) === 'dance' && repertoire.allowsAsset(m.name));
    if (!dances.length) return false;
    const norm = (s: string) => s.replace(/\.vmd$/i, '').trim().toLowerCase();
    const bare = (m: { label: string; name: string }) => stripCatPrefix(m.label).trim() || m.name;
    const t = norm(nameOrLabel);
    let motion =
      dances.find((m) => norm(m.name) === t) ??
      dances.find((m) => norm(bare(m)) === t) ??
      (t.length >= 4
        ? dances.find((m) => norm(m.name).includes(t) || norm(bare(m)).includes(t))
        : undefined);

    const ask = this.lastUserAsk;
    const wantAnother = /再来|再跳|换一|另一|继续|别的|不一样|一支别/.test(ask);
    const namedThis = !!(motion && (
      ask.includes(bare(motion)) || ask.toLowerCase().includes(norm(motion.name))
    ));
    const last = this.lastDanceName;
    if (motion && last && norm(motion.name) === norm(last) && dances.length > 1 && (wantAnother || !namedThis)) {
      const others = dances.filter((m) => norm(m.name) !== norm(last));
      if (others.length) motion = others[Math.floor(Math.random() * others.length)];
    }
    if (!motion) {
      const beat = repertoire.pick({ dancing: true, allowWalk: true, preferStand: stage.standSlot, varyCam: true });
      return this.launchDance(beat);
    }
    if (!repertoire.allowsAsset(motion.name)) {
      const beat = repertoire.pick({ dancing: true, allowWalk: true, preferStand: stage.standSlot, varyCam: true });
      return this.launchDance(beat);
    }
    const beat = repertoire.pick({
      dancing: true,
      assetName: motion.name,
      allowWalk: true,
      preferStand: stage.standSlot,
      varyCam: true,
    }) ?? repertoire.pick({ assetName: motion.name, allowWalk: true, varyCam: true });
    return this.launchDance(beat);
  }

  /** 对话开的舞：有配乐跟歌唱完，没配乐只跳一轮，然后停。 */
  private launchDance(beat: ApprovedBeat | null): boolean {
    if (!beat?.assetName) return false;
    this.lastDanceName = beat.assetName;
    shots.beginDance(beat.assetName);
    shots.syncFromBeat(beat);
    void repertoire.perform(beat, {
      once: true,
      onMotionEnded: () => shots.endDance(),
    });
    return true;
  }

  private playMotionByName(nameOrLabel: string, opts?: { fullCam?: boolean; once?: boolean }) {
    const assets = useAssetsStore();
    const target = nameOrLabel.trim().replace(/\.vmd$/i, '');
    const bare = (m: { label: string }) => stripCatPrefix(m.label).trim();
    const motion =
      assets.motions.find((m) => m.name === target || m.name === `${target}.vmd`) ??
      assets.motions.find((m) => bare(m) === target) ??
      assets.motions.find((m) => m.name.includes(target) || bare(m).includes(target));
    if (!motion || !repertoire.allowsAsset(motion.name)) return;
    if (parseMotionCat(motion) === 'dance') return;
    const beat = repertoire.pick({
      assetName: motion.name,
      allowWalk: true,
      preferStand: stage.standSlot,
      preferSize: shots.current ?? undefined,
    });
    if (!beat) return;
    shots.syncFromBeat(beat);
    void repertoire.perform(beat);
    void opts;
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
