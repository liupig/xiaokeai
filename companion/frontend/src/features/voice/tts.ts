import { api } from '../../api/client';
import { stage } from '../../engine/stage';
import { AecSpeaker } from './aecLoopback';
import { reportLoopback } from './aec';
import {
  DEFAULT_DUPLEX_REMAIN_SEC,
  normalizeDuplexCmd,
  normalizeSentenceType,
  resolveDuplex,
  type DuplexCmd,
  type PlayableUnit,
  type SentenceType,
} from './duplex';

export type { DuplexCmd, PlayableUnit, SentenceType };
export { DEFAULT_DUPLEX_REMAIN_SEC, normalizeDuplexCmd };

/**
 * ChannelPool + 播放器。
 * pushUnit 按 DuplexCmd 决定插队/排队/丢掉；真正拉 TTS 流只在决定要播之后。
 */
export type TtsEngine = 'cosy' | 'edge' | 'qwen' | 'browser' | 'off';

const STREAM_ENGINES = new Set<TtsEngine>(['cosy', 'edge', 'qwen']);
const VOICE_ENGINES = new Set<TtsEngine>(['cosy', 'edge', 'qwen']);

function isSidecarClip(clip: { duplexCmd?: DuplexCmd; kind?: string } | null): boolean {
  if (!clip) return false;
  if (clip.duplexCmd === 'skip_on_new') return true;
  const k = clip.kind || '';
  return k === 'delayed' || k === 'proactive' || k === 'goodbye' || k === 'welcome';
}

function estimateSpeechSec(text: string): number {
  const n = Array.from(text.replace(/\s/g, '')).length;
  return Math.max(0.6, n * 0.22);
}

const PERF_TAG = /\[(emo|act|dance|cam|expr|intent|stand):[^\[\]]{1,80}\]/g;

function stripCaption(text: string) {
  return (text || '')
    .replace(PERF_TAG, '')
    .replace(/[（(【][^）)】]{1,48}[）)】]/g, '')
    .replace(/[（(【][^）)】]{0,48}$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function speakForEngine(text: string) {
  const plain = stripCaption(text);
  return plain.replace(/[，、：:～~]+$/u, '。');
}

function normSpoken(text: string) {
  return (text || '').replace(/[\s，。！？、,.!?;；：:～~…"'“”]+/g, '');
}

/** 同时最多只让 1 段去占 GPU，插话才能立刻把锁让出来。 */
const MAX_PREFETCH = 1;

type PendingClip = {
  text: string;
  job: Promise<AudioBuffer | Response | null>;
  ac: AbortController;
  duplexCmd: DuplexCmd;
  sentenceType: SentenceType;
  inputGen: number;
  kind?: string;
};

export class SpeechPlayer {
  engine: TtsEngine = 'qwen';
  voice = '';
  qwenSize: '0.6b' | '1.7b' = '0.6b';
  qwenStyle = 'yujie';
  qwenInstruct = '';
  duplexCmd: DuplexCmd = 'interrupt_or_queue';
  duplexRemainSec = DEFAULT_DUPLEX_REMAIN_SEC;
  inputGen = 0;
  streamOpen = false;
  /** 看牌读牌：跨轮也排队，不丢掉上一张还没念完的句子。 */
  tarotHold = false;
  /** 每一句开播时回调（给选角器做句拍表演） */
  onSentence: ((text: string) => void) | null = null;
  onAllEnded: (() => void) | null = null;

  /** 正在合成或排队的语音，欢迎语 / 沉默续聊不要叠上去。 */
  isSpeaking(): boolean {
    return this.playing || this.pending.length > 0 || this.currentClip != null || this.waitQueue.length > 0;
  }

  /** 刚说完一小段：扬声器尾音还可能被 ASR 收进去。 */
  spokeRecently(ms = 900) {
    if (this.isSpeaking()) return true;
    return this.lastVoiceAt > 0 && Date.now() - this.lastVoiceAt < ms;
  }

  /** 整句落在她刚说的正文里，才当回声；三个字的日常话不要误杀。 */
  matchesSpoken(text: string): boolean {
    const a = normSpoken(text);
    if (a.length < 3) return false;
    const hay = normSpoken(this.spokenRecent + (this.currentClip?.text || ''));
    if (!hay) return false;
    if (hay.includes(a)) return true;
    const head = a.slice(0, Math.min(6, a.length));
    return head.length >= 4 && hay.includes(head);
  }

  unlock() {
    this.ensureCtx();
  }

  audioContext(): AudioContext | null {
    return this.ctx;
  }

  aecTap(): AudioNode | null {
    return this.analyser;
  }

  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private aecDest: MediaStreamAudioDestinationNode | null = null;
  private aecSpeaker = new AecSpeaker();
  private aecLive = false;
  private pending: PendingClip[] = [];
  /** 已分好句、还没发 TTS 请求。避免长故事一次性打满 GPU 锁。 */
  private waitQueue: PlayableUnit[] = [];
  private spokenRecent = '';
  private lastVoiceAt = 0;
  private playing = false;
  private currentSource: AudioBufferSourceNode | null = null;
  private pcmSources: AudioBufferSourceNode[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private mediaNode: MediaElementAudioSourceNode | null = null;
  private generation = 0;
  private playToken = 0;
  private currentClip: PendingClip | null = null;
  /** AudioContext 时间轴上，已排入的 PCM 播完时刻 */
  private pcmHorizon = 0;
  private clipStartTime = 0;
  /** 当前句还在收 TTS 流：字数估计才有意义；收完后只信声卡剩余 */
  private clipReceiving = false;
  /** 已排进声卡的最后一块何时结束；下一段接在这条时间轴上，避免句间空白 */
  private tailEnded: Promise<void> = Promise.resolve();
  private lastCutCheck = 0;
  /** 已排进声卡的句子时间轴：字幕跟正在出声的那一段，不跟正在拉流的下一句。 */
  private captionTimeline: { text: string; start: number; end: number }[] = [];

  remainingSec(): number {
    this.ensureCtx();
    const now = this.ctx!.currentTime;
    let audioLeft = 0;
    if (this.pcmHorizon > now) audioLeft = this.pcmHorizon - now;
    const audio = this.currentAudio;
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      audioLeft = Math.max(audioLeft, Math.max(0, audio.duration - audio.currentTime));
    }
    if (!this.clipReceiving) {
      if (audioLeft > 0) return audioLeft;
      if (!this.currentClip) return 0;
      const elapsed = this.clipStartTime > 0 ? Math.max(0, now - this.clipStartTime) : 0;
      return Math.max(0, estimateSpeechSec(this.currentClip.text) - elapsed);
    }
    let textLeft = 0;
    if (this.currentClip) {
      const elapsed = this.clipStartTime > 0 ? Math.max(0, now - this.clipStartTime) : 0;
      textLeft = Math.max(0, estimateSpeechSec(this.currentClip.text) - elapsed);
    }
    return Math.max(audioLeft, textLeft);
  }

  private noteCaption(text: string, start: number, end: number) {
    const plain = stripCaption(text);
    if (!plain || end <= start) return;
    const last = this.captionTimeline[this.captionTimeline.length - 1];
    if (last && last.text === plain && start <= last.end + 0.08) {
      last.end = Math.max(last.end, end);
      return;
    }
    this.captionTimeline.push({ text: plain, start, end });
  }

  private pruneCaption(now: number) {
    while (this.captionTimeline.length > 1 && this.captionTimeline[0].end <= now) {
      this.captionTimeline.shift();
    }
    if (this.captionTimeline.length === 1 && this.captionTimeline[0].end < now - 0.25) {
      this.captionTimeline.shift();
    }
  }

  /**
   * 字幕跟声卡时间轴上正在响的那一句，不是正在请求 TTS 的下一句。
   */
  liveCaption(): { text: string; progress: number } | null {
    const audio = this.currentAudio;
    if (audio && !audio.paused && Number.isFinite(audio.duration) && audio.duration > 0) {
      const text = stripCaption(this.currentClip?.text || '');
      if (text) {
        return { text, progress: Math.max(0, Math.min(1, audio.currentTime / audio.duration)) };
      }
    }
    this.ensureCtx();
    const now = this.ctx!.currentTime;
    this.pruneCaption(now);
    const hit = this.captionTimeline.find((c) => now >= c.start && now < c.end)
      ?? this.captionTimeline.find((c) => now >= c.start - 0.04 && now < c.end + 0.06);
    if (hit) {
      const dur = Math.max(0.08, hit.end - hit.start);
      return { text: hit.text, progress: Math.max(0, Math.min(1, (now - hit.start) / dur)) };
    }
    if (this.currentClip && this.clipStartTime <= 0) {
      const text = stripCaption(this.currentClip.text);
      if (text) return { text, progress: 0 };
    }
    return null;
  }

  private audible(): boolean {
    return this.clipStartTime > 0 || this.pcmHorizon > 0;
  }

  private currentType(): SentenceType | null {
    return this.currentClip?.sentenceType ?? null;
  }

  private resolveFor(unit: PlayableUnit, exceptPending?: PendingClip): ReturnType<typeof resolveDuplex> {
    const turn = unit.inputGen ?? this.inputGen;
    const sameTurn = this.isSameQa(turn, exceptPending);
    // 垫话「嗯…」可被同一轮正文打断；A1/A2/A3 仍只排队
    if (
      sameTurn
      && this.playing
      && this.audible()
      && this.currentClip?.kind === 'filler'
      && unit.kind !== 'filler'
    ) {
      return 'interrupt';
    }
    return resolveDuplex({
      cmd: sameTurn || this.tarotHold ? 'queue' : this.duplexCmd,
      remaining: this.remainingSec(),
      threshold: this.duplexRemainSec,
      currentAudible: this.playing && this.audible(),
      currentType: this.currentType(),
      userTurnMoved: turn !== this.inputGen,
      sameTurn,
    });
  }

  /** 正在播或已排队的这一轮 QA。正在判的那句自己不算「已入队」。 */
  private isSameQa(turn: number, except?: PendingClip): boolean {
    if (this.currentClip?.inputGen === turn) return true;
    if (this.pending.some((p) => p.inputGen === turn && p !== except)) return true;
    return this.waitQueue.some((u) => (u.inputGen ?? this.inputGen) === turn);
  }

  /** 丢掉还没开口的旧尾巴，当前这句继续播。 */
  discardQueued() {
    this.dropOtherTurns(-1);
  }

  /** 用户开口但还没出字：只掐续聊/欢迎，QA 正文先留着等分流。 */
  hushSidecar() {
    if (isSidecarClip(this.currentClip)) this.cutCurrent();
    const stay: PendingClip[] = [];
    for (const item of this.pending) {
      if (isSidecarClip(item)) item.ac.abort();
      else stay.push(item);
    }
    this.pending = stay;
    this.waitQueue = this.waitQueue.filter((u) => !isSidecarClip(u));
  }

  /** 用户开口：丢掉未播尾巴，并立刻停当前句，把本地 TTS GPU 让出来。 */
  onUserBargeIn() {
    this.waitQueue = [];
    this.discardQueued();
    this.cutCurrent();
  }

  /** 丢掉上一轮还没开口的 A2、A3，当前这句先留着，等 3 秒规则来判。 */
  private dropOtherTurns(keepTurn: number) {
    const stay: PendingClip[] = [];
    for (const item of this.pending) {
      if (item.inputGen === keepTurn) stay.push(item);
      else item.ac.abort();
    }
    this.pending = stay;
    this.waitQueue = this.waitQueue.filter((u) => (u.inputGen ?? this.inputGen) === keepTurn);
  }

  private dropFiller(turn: number) {
    const stay: PendingClip[] = [];
    for (const item of this.pending) {
      if (item.kind === 'filler' && item.inputGen === turn) item.ac.abort();
      else stay.push(item);
    }
    this.pending = stay;
  }

  private fadeBgmForSpeech(on: boolean) {
    if (!on) {
      stage.bgm.setDuck(1, 500);
      return;
    }
    // 跳舞时歌是主声，只略压；平时压低以免盖过台词。
    stage.bgm.setDuck(stage.danceLive ? 0.55 : 0.22, 280);
  }

  /** 当前句已经开口后，按队首的 DuplexCmd 再判一次。 */
  private maybeCutForPending() {
    const now = performance.now();
    if (now - this.lastCutCheck < 180) return;
    this.lastCutCheck = now;
    while (this.pending.length) {
      const head = this.pending[0];
      const action = this.resolveFor(head, head);
      if (action === 'skip') {
        const dropped = this.pending.shift()!;
        dropped.ac.abort();
        continue;
      }
      if (action === 'interrupt') this.cutCurrent();
      break;
    }
  }

  /** 只切掉正在播的这一句，队列里后面的句子还在。 */
  private cutCurrent() {
    this.playToken++;
    this.currentClip?.ac.abort();
    try { this.currentSource?.stop(); } catch { /* already stopped */ }
    this.currentSource = null;
    for (const src of this.pcmSources) {
      try { src.stop(); } catch { /* already stopped */ }
    }
    this.pcmSources = [];
    this.pcmHorizon = 0;
    this.clipStartTime = 0;
    this.clipReceiving = false;
    this.currentClip = null;
    this.captionTimeline = [];
    this.tailEnded = Promise.resolve();
    if (this.currentAudio) {
      this.currentAudio.pause();
    }
    speechSynthesis.cancel();
  }

  private makeClip(text: string, unit: PlayableUnit): PendingClip | null {
    const cleaned = stripCaption(text.trim());
    if (!cleaned || this.engine === 'off') return null;
    if (VOICE_ENGINES.has(this.engine) && !this.voice) return null;
    const gen = this.generation;
    const ac = new AbortController();
    this.ensureCtx();
    let job: Promise<AudioBuffer | Response | null>;
    if (this.engine === 'browser') {
      job = Promise.resolve(null);
    } else if (STREAM_ENGINES.has(this.engine)) {
      job = api.ttsResponse(
        speakForEngine(cleaned), this.voice, this.engine, ac.signal,
        this.qwenSize, this.qwenStyle, this.qwenInstruct,
      );
    } else {
      job = this.fetchBuffer(cleaned, ac.signal, gen);
    }
    return {
      text: cleaned, job, ac,
      duplexCmd: unit.duplexCmd,
      sentenceType: unit.sentenceType,
      inputGen: unit.inputGen ?? this.inputGen,
      kind: unit.kind,
    };
  }

  /** ChannelPool 入口。同轮 A1/A2/A3 只排队；新一轮 QA 才按剩余音频 3 秒决定切不切。 */
  pushUnit(unit: PlayableUnit) {
    const cleaned = (unit.text || '').trim();
    if (!cleaned) return;
    const turn = unit.inputGen ?? this.inputGen;
    const tagged: PlayableUnit = {
      ...unit,
      duplexCmd: normalizeDuplexCmd(unit.duplexCmd),
      sentenceType: normalizeSentenceType(unit.sentenceType),
      inputGen: turn,
    };
    const firstOfNewQa = !this.isSameQa(turn);
    if (firstOfNewQa && !this.tarotHold) this.dropOtherTurns(turn);
    if (tagged.kind !== 'filler') this.dropFiller(turn);
    const action = this.resolveFor(tagged);
    if (action === 'skip') return;
    // 上一轮还在说：垫话不要抢 3 秒判定，等正文到了再切
    const waitingOnPrev =
      this.playing && this.currentClip != null && this.currentClip.inputGen !== turn;
    if (tagged.kind === 'filler' && waitingOnPrev) return;
    if (action === 'interrupt') {
      this.cutCurrent();
      this.waitQueue.unshift(tagged);
    } else {
      this.waitQueue.push(tagged);
    }
    this.maybePrefetch();
    void this.pump();
  }

  /** 本地兜底 / 无 speech 事件时：按全局 body_cmd 进队。 */
  enqueue(text: string) {
    this.pushUnit({
      text,
      duplexCmd: this.duplexCmd,
      sentenceType: 'normal',
      inputGen: this.inputGen,
    });
  }

  /** 新一轮 QA：丢掉上一轮还没播的尾巴，但当前这句先不停，等新回复到了再按剩余时长判。 */
  beginNewQa() {
    this.inputGen++;
    this.streamOpen = true;
    this.spokenRecent = '';
    if (!this.tarotHold) this.dropOtherTurns(this.inputGen);
    // SkipOnNew（超时续聊）正在播：用户开口就立刻停，不等 3 秒
    if (isSidecarClip(this.currentClip)) {
      this.cutCurrent();
    }
  }

  /** @deprecated 换角色等硬停仍用 stop() */
  notifyUserStarted() {
    this.beginNewQa();
    this.stop();
  }

  stop() {
    this.generation++;
    this.playToken++;
    this.waitQueue = [];
    this.spokenRecent = '';
    for (const item of this.pending) item.ac.abort();
    this.pending.length = 0;
    this.currentClip?.ac.abort();
    this.currentClip = null;
    try { this.currentSource?.stop(); } catch { /* already stopped */ }
    this.currentSource = null;
    for (const src of this.pcmSources) {
      try { src.stop(); } catch { /* already stopped */ }
    }
    this.pcmSources = [];
    this.pcmHorizon = 0;
    this.clipStartTime = 0;
    this.clipReceiving = false;
    this.captionTimeline = [];
    this.tailEnded = Promise.resolve();
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.removeAttribute('src');
      this.currentAudio.load();
    }
    speechSynthesis.cancel();
    stage.lipsync.detachAnalyser();
    stage.lipsync.setTalking(false);
    this.playing = false;
    this.lastVoiceAt = Date.now();
    this.fadeBgmForSpeech(false);
  }

  private ensureCtx() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      this.aecDest = this.ctx.createMediaStreamDestination();
      this.analyser.connect(this.aecDest);
      void this.armAecSpeaker();
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
  }

  /** 环回成功后只从 WebRTC 远端出声，Chrome 才能拿 TTS 当 AEC 参考。 */
  private async armAecSpeaker() {
    if (!this.aecDest || this.aecLive) return;
    const ok = await this.aecSpeaker.start(this.aecDest.stream);
    if (!this.analyser || !this.ctx) {
      reportLoopback(false);
      return;
    }
    if (!ok) {
      try { this.analyser.connect(this.ctx.destination); } catch { /* */ }
      reportLoopback(false);
      return;
    }
    this.aecLive = true;
    reportLoopback(true);
  }

  private ensureMediaEl() {
    this.ensureCtx();
    if (!this.currentAudio) {
      this.currentAudio = new Audio();
      this.mediaNode = this.ctx!.createMediaElementSource(this.currentAudio);
      this.mediaNode.connect(this.analyser!);
    }
  }

  private async fetchBuffer(text: string, signal: AbortSignal, gen: number): Promise<AudioBuffer | null> {
    const blob = await api.tts(speakForEngine(text), this.voice, this.engine, signal);
    if (gen !== this.generation) return null;
    this.ensureCtx();
    return this.ctx!.decodeAudioData(await blob.arrayBuffer());
  }

  private maybePrefetch() {
    while (this.pending.length < MAX_PREFETCH && this.waitQueue.length) {
      const unit = this.waitQueue.shift()!;
      const clip = this.makeClip((unit.text || '').trim(), unit);
      if (clip) this.pending.push(clip);
    }
  }

  private rememberSpoken(text: string) {
    this.spokenRecent = (this.spokenRecent + (text || '')).slice(-120);
    this.lastVoiceAt = Date.now();
  }

  private async pump() {
    if (this.playing) return;
    this.playing = true;
    const gen = this.generation;
    while (gen === this.generation) {
      this.maybePrefetch();
      if (!this.pending.length) break;
      const item = this.pending.shift()!;
      this.maybePrefetch();
      const token = this.playToken;
      this.currentClip = item;
      this.rememberSpoken(item.text);
      this.clipStartTime = 0;
      this.pcmHorizon = this.pcmHorizon > (this.ctx?.currentTime ?? 0)
        ? this.pcmHorizon
        : 0;
      this.clipReceiving = true;
      this.fadeBgmForSpeech(true);
      this.onSentence?.(item.text);
      try {
        if (this.engine === 'browser') {
          await this.playBrowser(item.text, gen, token);
        } else if (STREAM_ENGINES.has(this.engine)) {
          const resp = await item.job;
          if (!(resp instanceof Response) || gen !== this.generation || token !== this.playToken) continue;
          const fmt = (resp.headers.get('X-Audio-Format') || '').toLowerCase();
          if (fmt.startsWith('pcm')) await this.playPcmStream(resp, gen, token);
          else await this.playMpegStream(resp, gen, token);
        } else {
          const buf = await item.job;
          if (!(buf instanceof AudioBuffer) || gen !== this.generation || token !== this.playToken) continue;
          await this.playBuffer(buf, gen, token);
        }
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') {
          if (gen !== this.generation) break;
          continue;
        }
        console.error('TTS 播放失败（不改用其它音色）', e);
      } finally {
        this.clipReceiving = false;
        if (this.currentClip === item) this.currentClip = null;
      }
    }
    if (gen === this.generation) {
      await this.tailEnded.catch(() => {});
      this.pcmSources = [];
      stage.lipsync.detachAnalyser();
      stage.lipsync.setTalking(false);
      this.fadeBgmForSpeech(false);
      this.onAllEnded?.();
    }
    this.playing = false;
    this.lastVoiceAt = Date.now();
    if (gen === this.generation && (this.pending.length || this.waitQueue.length)) void this.pump();
  }

  private playBuffer(buf: AudioBuffer, gen: number, token: number) {
    this.ensureCtx();
    stage.lipsync.attachAnalyser(this.analyser!);
    return new Promise<void>((resolve) => {
      const src = this.ctx!.createBufferSource();
      src.buffer = buf;
      src.connect(this.analyser!);
      src.onended = () => resolve();
      this.currentSource = src;
      const t = this.ctx!.currentTime;
      this.clipStartTime = t;
      this.pcmHorizon = t + buf.duration;
      this.clipReceiving = false;
      this.noteCaption(this.currentClip?.text || '', t, this.pcmHorizon);
      this.maybeCutForPending();
      if (gen !== this.generation || token !== this.playToken) {
        resolve();
        return;
      }
      src.start();
      if (gen !== this.generation || token !== this.playToken) {
        try { src.stop(); } catch { /* already stopped */ }
        resolve();
      }
    }).then(() => {
      this.currentSource = null;
    });
  }

  /** 边收 16-bit PCM 边排进 AudioContext。只等收流结束，播放接在 pcmHorizon 上，避免句间卡顿。 */
  private async playPcmStream(resp: Response, gen: number, token: number) {
    if (!resp.body) throw new Error('TTS 流为空');
    const sr = Number(resp.headers.get('X-Audio-Rate') || 24000);
    this.ensureCtx();
    this.clipReceiving = true;
    stage.lipsync.attachAnalyser(this.analyser!);
    const reader = resp.body.getReader();
    let leftover = new Uint8Array(0);
    const LOOKAHEAD = 0.05;
    const MIN_FIRST = Math.max(1, Math.floor(sr * 0.18));
    const MIN_REST = Math.max(1, Math.floor(sr * 0.12));
    const alive = () => gen === this.generation && token === this.playToken;
    let started = false;
    let nextTime = this.pcmHorizon > this.ctx!.currentTime ? this.pcmHorizon : 0;

    const playSamples = (samples: Int16Array) => {
      if (!samples.length || !alive()) return;
      const f32 = new Float32Array(samples.length);
      for (let i = 0; i < samples.length; i++) f32[i] = samples[i] / 32768;
      const buf = this.ctx!.createBuffer(1, f32.length, sr);
      buf.copyToChannel(f32, 0);
      const src = this.ctx!.createBufferSource();
      src.buffer = buf;
      src.connect(this.analyser!);
      const now = this.ctx!.currentTime;
      let t = nextTime > 0 ? nextTime : now + LOOKAHEAD;
      // 欠载时立刻接上，不要再垫 80ms，否则听起来像一个字一个字往外蹦
      if (t < now + 0.004) t = now + 0.004;
      nextTime = t + buf.duration;
      this.pcmHorizon = nextTime;
      const firstAudible = this.clipStartTime <= 0;
      if (firstAudible) this.clipStartTime = t;
      this.noteCaption(this.currentClip?.text || '', t, nextTime);
      this.tailEnded = new Promise((resolve) => {
        src.onended = () => {
          const i = this.pcmSources.indexOf(src);
          if (i >= 0) this.pcmSources.splice(i, 1);
          if (this.currentSource === src) this.currentSource = null;
          resolve();
        };
      });
      this.pcmSources.push(src);
      this.currentSource = src;
      src.start(t);
      this.maybeCutForPending();
    };

    let pending = new Int16Array(0);
    try {
      while (alive()) {
        const { done, value } = await reader.read();
        if (done) break;
        const merged = new Uint8Array(leftover.length + value.length);
        merged.set(leftover);
        merged.set(value, leftover.length);
        const even = merged.byteLength & ~1;
        leftover = merged.slice(even);
        if (even < 2) continue;
        const copy = merged.slice(0, even);
        const chunk = new Int16Array(copy.buffer, copy.byteOffset, copy.byteLength / 2);
        const acc = new Int16Array(pending.length + chunk.length);
        acc.set(pending);
        acc.set(chunk, pending.length);
        const min = started ? MIN_REST : MIN_FIRST;
        if (acc.length >= min) {
          playSamples(acc);
          started = true;
          pending = new Int16Array(0);
        } else {
          pending = acc;
        }
      }
      if (pending.length && alive()) playSamples(pending);
    } finally {
      this.clipReceiving = false;
      void reader.cancel().catch(() => {});
    }
    this.currentSource = null;
  }

  /** MP3 分片用 MediaSource 边收边播（edge-tts）。 */
  private playMpegStream(resp: Response, gen: number, token: number): Promise<void> {
    if (!resp.body) return Promise.reject(new Error('TTS 流为空'));
    const canMse = typeof MediaSource !== 'undefined'
      && MediaSource.isTypeSupported('audio/mpeg');
    if (!canMse) {
      return resp.arrayBuffer().then((buf) => {
        if (gen !== this.generation || token !== this.playToken) return;
        const blob = new Blob([buf], { type: 'audio/mpeg' });
        return this.playBlobUrl(blob, gen, token);
      });
    }
    this.ensureMediaEl();
    this.clipReceiving = true;
    stage.lipsync.attachAnalyser(this.analyser!);
    const audio = this.currentAudio!;
    const mse = new MediaSource();
    const url = URL.createObjectURL(mse);
    const state = { streamDone: false };
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (err?: unknown) => {
        if (settled) return;
        settled = true;
        URL.revokeObjectURL(url);
        if (err) reject(err);
        else resolve();
      };
      audio.onended = () => finish();
      audio.onerror = () => finish(new Error('MPEG 播放失败'));
      const poll = window.setInterval(() => {
        if (settled) {
          window.clearInterval(poll);
          return;
        }
        if (gen !== this.generation || token !== this.playToken) {
          finish();
          return;
        }
        this.maybeCutForPending();
        if (!state.streamDone) return;
        const d = audio.duration;
        if (audio.ended || (Number.isFinite(d) && d > 0 && audio.currentTime >= d - 0.08)) {
          finish();
        }
      }, 150);
      mse.addEventListener('sourceopen', () => {
        void this.feedMpeg(mse, resp, gen, token, audio, finish, state);
      }, { once: true });
      audio.src = url;
      if (gen !== this.generation || token !== this.playToken) {
        audio.pause();
        finish();
      }
    });
  }

  private async feedMpeg(
    mse: MediaSource,
    resp: Response,
    gen: number,
    token: number,
    audio: HTMLAudioElement,
    finish: (err?: unknown) => void,
    state: { streamDone: boolean },
  ) {
    let sb: SourceBuffer;
    try {
      sb = mse.addSourceBuffer('audio/mpeg');
    } catch (e) {
      finish(e);
      return;
    }
    sb.mode = 'sequence';
    const queue: Uint8Array[] = [];
    let streamDone = false;
    const reader = resp.body!.getReader();
    const appendNext = () => {
      if (sb.updating || !queue.length) {
        if (streamDone && !sb.updating && !queue.length && mse.readyState === 'open') {
          try { mse.endOfStream(); } catch { /* already ended */ }
        }
        return;
      }
      const chunk = queue.shift()!;
      try {
        const copy = new Uint8Array(chunk.byteLength);
        copy.set(chunk);
        sb.appendBuffer(copy);
      } catch (e) {
        finish(e);
      }
    };
    sb.addEventListener('updateend', appendNext);
    try {
      while (gen === this.generation && token === this.playToken) {
        const { done, value } = await reader.read();
        if (done) break;
        queue.push(value);
        appendNext();
        if (audio.paused) {
          void audio.play().catch(() => {});
          if (this.clipStartTime <= 0) {
            this.ensureCtx();
            this.clipStartTime = this.ctx!.currentTime;
            this.maybeCutForPending();
          }
        }
      }
      streamDone = true;
      state.streamDone = true;
      this.clipReceiving = false;
      appendNext();
      if (gen !== this.generation || token !== this.playToken) {
        audio.pause();
        finish();
      }
    } catch (e) {
      if ((e as { name?: string })?.name === 'AbortError') finish();
      else finish(e);
    } finally {
      void reader.cancel().catch(() => {});
    }
  }

  private playBlobUrl(blob: Blob, gen: number, token: number): Promise<void> {
    this.ensureMediaEl();
    stage.lipsync.attachAnalyser(this.analyser!);
    const audio = this.currentAudio!;
    const url = URL.createObjectURL(blob);
    return new Promise((resolve) => {
      audio.onended = audio.onerror = () => {
        URL.revokeObjectURL(url);
        resolve();
      };
      audio.src = url;
      void audio.play().then(() => {
        if (this.clipStartTime <= 0) this.clipStartTime = this.ctx?.currentTime ?? 0;
        this.clipReceiving = false;
        this.maybeCutForPending();
      }).catch(() => resolve());
      if (gen !== this.generation || token !== this.playToken) {
        audio.pause();
        URL.revokeObjectURL(url);
        resolve();
      }
    });
  }

  private playBrowser(text: string, gen: number, token: number) {
    return new Promise<void>((resolve) => {
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = 'zh-CN';
      utter.onstart = () => {
        if (gen !== this.generation || token !== this.playToken) {
          speechSynthesis.cancel();
          resolve();
          return;
        }
        this.ensureCtx();
        this.clipStartTime = this.ctx!.currentTime;
        this.clipReceiving = false;
        this.noteCaption(text, this.clipStartTime, this.clipStartTime + estimateSpeechSec(text));
        stage.lipsync.setTalking(true);
        this.maybeCutForPending();
      };
      utter.onend = utter.onerror = () => {
        stage.lipsync.setTalking(false);
        resolve();
      };
      speechSynthesis.speak(utter);
      if (gen !== this.generation || token !== this.playToken) {
        speechSynthesis.cancel();
        resolve();
      }
    });
  }
}

export const speechPlayer = new SpeechPlayer();
