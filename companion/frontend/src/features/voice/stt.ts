/** 语音识别：在线浏览器 Web Speech，或离线 SenseVoice（浏览器端 Silero VAD 切段后送后端）。 */

import { api } from '../../api/client';
import { speechPlayer } from './tts';
import { peekIngressCut } from './ingress';
import { getMicStream, noteEchoLeak, isWasmMicStream } from './aec';
import { isTarotVoiceCommand } from '../tarot/intent';
import { tarotUi } from '../tarot/session';

type MicVAD = import('@ricky0123/vad-web').MicVAD;

async function loadMicVAD(): Promise<typeof import('@ricky0123/vad-web').MicVAD> {
  const vadWeb = await import('@ricky0123/vad-web') as {
    MicVAD?: typeof import('@ricky0123/vad-web').MicVAD;
    default?: { MicVAD: typeof import('@ricky0123/vad-web').MicVAD };
  };
  const Ctor = vadWeb.MicVAD ?? vadWeb.default?.MicVAD;
  if (!Ctor) throw new Error('Silero VAD 模块无效');
  return Ctor;
}

export type SttEngine = 'browser' | 'sensevoice';

type SpeechRecognitionCtor = new () => any;

export type SttMeta = { phase?: 'recognizing'; asrFail?: boolean; echo?: boolean };
type ResultCb = (text: string, isFinal: boolean, meta?: SttMeta) => void;
type EndCb = () => void;

function vadAssetBase(): string {
  const base = import.meta.env.BASE_URL.endsWith('/')
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL}/`;
  return new URL('vad/', window.location.origin + base).href;
}

export function browserSttSupported(): boolean {
  const w = window as any;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function micAvailable(engine: SttEngine): boolean {
  if (engine === 'sensevoice') {
    return Boolean(navigator.mediaDevices?.getUserMedia);
  }
  return browserSttSupported();
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buf);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

function rmsOf(samples: Float32Array) {
  if (!samples.length) return 0;
  let s = 0;
  for (let i = 0; i < samples.length; i++) s += samples[i] * samples[i];
  return Math.sqrt(s / samples.length);
}

const JUNK_RE = /^([.。,，!！?？…~～、]+|(yeah|yes|yep|yup|ok(ay)?)+|(the|a|oh+|ah+|um+|hmm+|uh+|huh|mhm)[.。!！]*)+$/i;
const FILLER_RE = /^(嗯+|啊+|哦+|噢+|额+|唔+|哈+|嘿+|哇+|呵+)$/;
const GARBAGE_LINE_RE =
  /^(字幕(组|志愿者|by.*)?|中文字幕|谢谢(观看|收看|大家)|感谢观看|请(订阅|点赞|收看)|下[一期集]再见|作[词曲]|编曲|哔哩哔哩|bilibili|thankyouforwatching|thanksforwatching|pleasesubscribe|明镜与点点|欢迎收看|本期节目|打开腾讯|小爱同学|我是小爱|music|歌词|asmr)$/i;

function compactVoice(text: string) {
  return (text || '').replace(/\s+/g, '').trim();
}

function cjkCount(text: string) {
  return (text.match(/[\u4e00-\u9fff]/g) || []).length;
}

function meaningfulLen(text: string) {
  return Array.from(text.replace(/[^\u4e00-\u9fffA-Za-z0-9]/g, '')).length;
}

/** 句号、The.、Yeah.、字幕、嗯嗯 这类杂音，不当作用户话。 */
export function looksLikeAsrJunk(text: string) {
  const t = compactVoice(text);
  if (!t) return true;
  if (meaningfulLen(t) <= 1) return true;
  if (FILLER_RE.test(t)) return true;
  if (GARBAGE_LINE_RE.test(t.replace(/[。！？、,.!?;；…~～]/g, ''))) return true;
  return JUNK_RE.test(t);
}

/**
 * 像回声就不发送。
 * 她在说话：真回声 + 单字/杂音拦；三个汉字以上放行（整句落在她刚说的正文里除外）。
 * 她没说话：只拦单字和杂音，方便收音。
 * 跳舞夸奖不在这里拦，交给 ingress 走「附和」。
 */
export function shouldDropAsEcho(text: string) {
  const raw = (text || '').trim();
  const t = compactVoice(raw);
  if (!t) return true;

  const phase = tarotUi.phase || '';
  if (phase === 'intent' || isTarotVoiceCommand(raw, phase)) return false;

  if (looksLikeAsrJunk(t)) return true;

  const cjk = cjkCount(t);
  const live = speechPlayer.isSpeaking() || speechPlayer.spokeRecently(900);

  if (!live) {
    if (cjk >= 2) return false;
    return JUNK_RE.test(t) || meaningfulLen(t) < 3;
  }

  if (speechPlayer.matchesSpoken(raw)) return true;
  if (cjk >= 3) return false;
  if (peekIngressCut(raw)) return false;
  return true;
}

export class SpeechInput {
  engine: SttEngine = 'browser';
  listening = false;
  opening = false;

  private recognition: any = null;
  private vad: MicVAD | null = null;
  private vadLoading: Promise<MicVAD> | null = null;
  private gen = 0;
  private localBusy = false;
  private onResult: ResultCb | null = null;
  private onEnd: EndCb | null = null;
  private onSpeechStart: (() => void) | undefined;
  private gotUtterance = false;
  private closing = false;
  private queued: Float32Array | null = null;
  private utteranceTimer: ReturnType<typeof setTimeout> | null = null;
  private sliceTimer: ReturnType<typeof setInterval> | null = null;
  private ring: Float32Array[] = [];
  private ringSamples = 0;
  private echoFloor = 0.008;
  private lastFrameRms = 0;
  private needMicBounce = false;

  private echoGate() {
    return Math.max(0.022, this.echoFloor * 2.4);
  }

  private noteEchoRms(rms: number) {
    if (!Number.isFinite(rms) || rms <= 0) return;
    this.lastFrameRms = rms;
    if (speechPlayer.isSpeaking()) {
      this.echoFloor = this.echoFloor * 0.9 + rms * 0.1;
    } else {
      this.echoFloor = this.echoFloor * 0.97 + 0.008 * 0.03;
    }
  }

  /** 她正在念、音量又没明显高出喇叭底噪 → 当回声，不送 ASR。 */
  private isPlaybackEcho(audio: Float32Array) {
    if (!speechPlayer.isSpeaking() || !audio.length) return false;
    const rms = rmsOf(audio);
    this.noteEchoRms(rms);
    return rms < this.echoGate();
  }

  /** 预加载 Silero VAD 模型，不打开麦克风 */
  warmupVad() {
    return this.ensureVad();
  }

  start(onResult: ResultCb, onEnd: EndCb, onSpeechStart?: () => void, onError?: (err: unknown) => void): boolean {
    if (this.engine === 'sensevoice') {
      void this.startLocal(onResult, onEnd, onSpeechStart).catch((e) => {
        onError?.(e);
      });
      return true;
    }
    return this.startBrowser(onResult, onEnd, onSpeechStart);
  }

  private clearUtteranceTimer() {
    if (this.utteranceTimer != null) {
      clearTimeout(this.utteranceTimer);
      this.utteranceTimer = null;
    }
  }

  /** 回声把 VAD 卡在 speaking 时，到期强制交这段，否则永远等不到句尾。 */
  private armUtteranceTimer() {
    this.clearUtteranceTimer();
    const gen = this.gen;
    this.utteranceTimer = window.setTimeout(() => {
      this.utteranceTimer = null;
      if (this.gen !== gen || this.closing || !this.listening || this.localBusy) return;
      void this.forceSubmitVad();
    }, 2200);
  }

  private async forceSubmitVad() {
    if (!this.vad || this.localBusy || this.closing || !this.listening) return;
    try {
      if (this.vad.listening) await this.vad.pause();
    } catch { /* */ }
    if (this.closing || !this.listening) return;
    if (!this.localBusy) await this.resumeVad();
  }

  private clearSliceTimer() {
    if (this.sliceTimer != null) {
      clearInterval(this.sliceTimer);
      this.sliceTimer = null;
    }
  }

  private armSliceTimer() {
    this.clearSliceTimer();
    this.sliceTimer = window.setInterval(() => { void this.maybeSliceRecognize(); }, 1800);
  }

  private pushRing(frame: Float32Array) {
    if (!frame?.length || !this.listening) return;
    this.ring.push(frame);
    this.ringSamples += frame.length;
    const max = 16000 * 1.35;
    while (this.ringSamples > max && this.ring.length > 1) {
      const drop = this.ring.shift()!;
      this.ringSamples -= drop.length;
    }
  }

  private takeRing(): Float32Array {
    const out = new Float32Array(this.ringSamples);
    let o = 0;
    for (const f of this.ring) {
      out.set(f, o);
      o += f.length;
    }
    return out;
  }

  /** 她正在说时 VAD 等不到句尾：按音量切 1 秒送 ASR，才能插话。 */
  private async maybeSliceRecognize() {
    if (!this.listening || this.closing || this.localBusy || !this.onResult) return;
    if (!speechPlayer.isSpeaking()) return;
    const audio = this.takeRing();
    if (audio.length < 16000 * 0.5) return;
    if (this.isPlaybackEcho(audio)) return;
    void this.recognize(audio);
  }

  stop() {
    this.clearUtteranceTimer();
    this.clearSliceTimer();
    this.ring = [];
    this.ringSamples = 0;
    this.closing = true;
    this.listening = false;
    this.gen++;
    this.queued = null;
    this.recognition?.stop();
    this.recognition = null;
    const end = this.onEnd;
    this.onResult = null;
    this.onEnd = null;
    this.onSpeechStart = undefined;
    void this.pauseVad();
    end?.();
  }

  /** 用户再次点击麦克风：提交当前这段（如果有）并收麦 */
  async stopAndRecognize() {
    if (this.engine !== 'sensevoice' || !this.listening) {
      this.stop();
      return;
    }
    this.clearUtteranceTimer();
    this.clearSliceTimer();
    this.closing = true;
    this.listening = false;
    await this.pauseVad();
    if (!this.gotUtterance && !this.localBusy) {
      this.finishSession();
    }
  }

  private finishSession() {
    this.clearUtteranceTimer();
    this.clearSliceTimer();
    this.ring = [];
    this.ringSamples = 0;
    this.listening = false;
    this.closing = true;
    this.queued = null;
    const end = this.onEnd;
    this.onResult = null;
    this.onEnd = null;
    this.onSpeechStart = undefined;
    void this.pauseVad();
    end?.();
  }

  private async ensureVad(): Promise<MicVAD> {
    if (this.vad) return this.vad;
    if (!this.vadLoading) {
      const base = vadAssetBase();
      const getStream = () => {
        speechPlayer.unlock();
        return getMicStream({
          ctx: speechPlayer.audioContext(),
          tap: speechPlayer.aecTap(),
        });
      };
      this.vadLoading = loadMicVAD().then((MicVAD) => MicVAD.new({
        startOnLoad: false,
        model: 'v5',
        baseAssetPath: base,
        onnxWASMBasePath: base,
        submitUserSpeechOnPause: true,
        getStream,
        resumeStream: getStream,
        pauseStream: async (stream) => {
          if (isWasmMicStream(stream)) return;
          stream.getTracks().forEach((t) => t.stop());
        },
        // 扬声器回声时尽快结束一段，好让 ASR 跑起来
        positiveSpeechThreshold: 0.4,
        negativeSpeechThreshold: 0.28,
        minSpeechMs: 250,
        redemptionMs: 480,
        processorType: 'auto',
        ortConfig: (ort) => {
          ort.env.logLevel = 'error';
          (ort.env.wasm as { numThreads?: number }).numThreads = 1;
        },
        onSpeechStart: () => {
          if (speechPlayer.isSpeaking() && this.lastFrameRms < this.echoGate()) return;
          this.onSpeechStart?.();
        },
        onSpeechRealStart: () => {
          if (speechPlayer.isSpeaking() && this.lastFrameRms < this.echoGate()) return;
          this.onSpeechStart?.();
          this.armUtteranceTimer();
        },
        onFrameProcessed: (_probs, frame) => {
          if (!frame) return;
          this.pushRing(frame);
          this.noteEchoRms(rmsOf(frame));
        },
        onSpeechEnd: (audio) => {
          this.clearUtteranceTimer();
          if (this.isPlaybackEcho(audio)) return;
          this.gotUtterance = true;
          if (this.localBusy) {
            this.queued = audio;
            return;
          }
          void this.recognize(audio);
        },
        onVADMisfire: () => {
          this.clearUtteranceTimer();
          if (this.localBusy || this.listening) return;
          if (this.closing) this.finishSession();
        },
      }).then((vad) => {
        this.vad = vad;
        return vad;
      }).catch((e) => {
        this.vadLoading = null;
        throw e;
      }));
    }
    return this.vadLoading;
  }

  private async pauseVad() {
    try {
      if (this.vad?.listening) await this.vad.pause();
    } catch { /* */ }
  }

  private async resumeVad() {
    if (this.closing || !this.listening || !this.vad) return;
    try {
      if (!this.vad.listening) await this.vad.start();
    } catch (e) {
      console.warn('恢复麦克风失败', e);
    }
  }

  private startBrowser(onResult: ResultCb, onEnd: EndCb, onSpeechStart?: () => void): boolean {
    const w = window as any;
    const Ctor: SpeechRecognitionCtor | undefined =
      w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return false;
    const rec = new Ctor();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (event: any) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      if (final || interim) onSpeechStart?.();
      if (final) {
        if (shouldDropAsEcho(final)) onResult(final, true, { echo: true });
        else onResult(final, true);
      }
      else if (interim) onResult(interim, false);
    };
    rec.onend = () => {
      if (this.listening && this.recognition === rec) {
        try {
          rec.start();
          return;
        } catch { /* 浏览器不允许立刻重启时才真正收麦 */ }
      }
      if (this.recognition !== rec) return;
      this.recognition = null;
      this.listening = false;
      const end = this.onEnd;
      this.onEnd = null;
      end?.();
    };
    rec.onerror = (event: any) => {
      if (event?.error === 'no-speech' && this.listening && this.recognition === rec) {
        try {
          rec.start();
          return;
        } catch { /* */ }
      }
      if (this.recognition !== rec) return;
      this.listening = false;
      const end = this.onEnd;
      this.onEnd = null;
      end?.();
    };
    rec.start();
    this.recognition = rec;
    this.onResult = onResult;
    this.onEnd = onEnd;
    this.onSpeechStart = onSpeechStart;
    this.listening = true;
    this.closing = false;
    return true;
  }

  private async startLocal(onResult: ResultCb, onEnd: EndCb, onSpeechStart?: () => void) {
    const gen = ++this.gen;
    this.opening = true;
    this.onResult = onResult;
    this.onEnd = onEnd;
    this.onSpeechStart = onSpeechStart;
    this.gotUtterance = false;
    this.closing = false;
    this.queued = null;
    this.listening = true;
    let vad: MicVAD;
    try {
      vad = await this.ensureVad();
      if (this.gen !== gen) return;
      await vad.start();
      if (this.gen !== gen) {
        await this.pauseVad();
        return;
      }
      this.armSliceTimer();
    } catch (e) {
      console.warn('打开麦克风失败', e);
      if (this.gen !== gen) return;
      this.finishSession();
      throw e;
    } finally {
      if (this.gen === gen) this.opening = false;
    }
  }

  private async recognize(audio: Float32Array) {
    if (this.localBusy || !this.onResult) return;
    this.localBusy = true;
    const gen = this.gen;
    if (!audio.length) {
      this.localBusy = false;
      if (this.closing) this.finishSession();
      else await this.resumeVad();
      return;
    }
    const blob = encodeWav(audio, 16000);
    try {
      this.onResult?.('…', false, { phase: 'recognizing' });
      const r = await api.stt(blob);
      if (this.gen !== gen) return;
      const text = (r.text || '').trim();
      if (!text) this.onResult?.('', true, { asrFail: true });
      else if (shouldDropAsEcho(text)) {
        this.onResult?.(text, true, { echo: true });
        if (noteEchoLeak()) this.needMicBounce = true;
      } else {
        this.onResult?.(text, true);
      }
    } catch (e) {
      console.warn('本地 ASR 失败', e);
      if (this.gen !== gen) return;
      this.onResult?.('', true, { asrFail: true });
    } finally {
      if (this.gen !== gen) return;
      this.localBusy = false;
      const next = this.queued;
      this.queued = null;
      if (next?.length && this.onResult) {
        void this.recognize(next);
        return;
      }
      if (this.closing || !this.listening) {
        this.finishSession();
        return;
      }
      if (this.needMicBounce) {
        this.needMicBounce = false;
        await this.pauseVad();
      }
      await this.resumeVad();
    }
  }
}

export const speechInput = new SpeechInput();

/** @deprecated 用 micAvailable / browserSttSupported */
export function sttSupported(): boolean {
  return browserSttSupported();
}
