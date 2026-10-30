import { api } from '../../api/client';

/** 酒馆台词。每人一条音色，排队说完这一句再放下一句，不跟聊天的那条嗓子抢。 */

let chain: Promise<void> = Promise.resolve();
let current: HTMLAudioElement | null = null;
let gen = 0;
let releaseCurrent: (() => void) | null = null;
let pcmCtx: AudioContext | null = null;
let pcmSrc: AudioBufferSourceNode | null = null;

const PITCH: Record<string, number> = { you: 1, qin: 1.32, bar: 0.78, her: 1.12, host: 0.9 };

const BROWSER_LANG: Record<string, string> = {
  'zh-CN': 'zh-CN',
  en: 'en-US',
  ja: 'ja-JP',
  ko: 'ko-KR',
};

export function stopTalk() {
  gen += 1;
  const release = releaseCurrent;
  releaseCurrent = null;
  if (current) {
    const el = current;
    current = null;
    el.onended = null;
    el.onerror = null;
    try { el.pause(); } catch { /* 停掉就行，别让这一句把后面的队列卡死。 */ }
  }
  if (pcmSrc) {
    const src = pcmSrc;
    pcmSrc = null;
    src.onended = null;
    try { src.stop(); } catch { /* */ }
  }
  if (typeof speechSynthesis !== 'undefined') {
    try { speechSynthesis.cancel(); } catch { /* */ }
  }
  release?.();
}

function browserSay(text: string, who: string, lang: string, mine: number) {
  return new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      if (releaseCurrent === finish) releaseCurrent = null;
      resolve();
    };
    if (mine !== gen || typeof speechSynthesis === 'undefined') {
      finish();
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = BROWSER_LANG[lang] || 'zh-CN';
    utter.pitch = PITCH[who] || 1;
    utter.rate = 1.02;
    utter.onend = finish;
    utter.onerror = finish;
    releaseCurrent = finish;
    speechSynthesis.speak(utter);
  });
}

function playClip(url: string, mine: number) {
  return new Promise<boolean>((resolve) => {
    const el = new Audio(url);
    current = el;
    let settled = false;
    const finish = (heard: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(cap);
      URL.revokeObjectURL(url);
      if (current === el) current = null;
      if (releaseCurrent === finish) releaseCurrent = null;
      resolve(heard);
    };
    const cap = window.setTimeout(() => finish(false), 12000);
    if (mine !== gen) {
      finish(false);
      return;
    }
    releaseCurrent = () => finish(false);
    el.onended = () => finish(true);
    el.onerror = () => finish(false);
    void el.play().catch(() => finish(false));
  });
}

/** 本地 Qwen 回来的是裸 PCM，浏览器的 Audio 标签播不了。 */
function playPcm(raw: ArrayBuffer, rate: number, mine: number) {
  return new Promise<boolean>((resolve) => {
    const bytes = raw.byteLength % 2 ? raw.slice(0, raw.byteLength - 1) : raw;
    const samples = new Int16Array(bytes);
    if (mine !== gen || !samples.length) {
      resolve(false);
      return;
    }
    const Ctx = window.AudioContext;
    if (!Ctx) {
      resolve(false);
      return;
    }
    if (!pcmCtx || pcmCtx.state === 'closed') pcmCtx = new Ctx();
    const ctx = pcmCtx;
    const floats = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i += 1) floats[i] = samples[i] / 32768;
    const buf = ctx.createBuffer(1, floats.length, rate || 24000);
    buf.copyToChannel(floats, 0);
    const src = ctx.createBufferSource();
    pcmSrc = src;
    src.buffer = buf;
    src.connect(ctx.destination);
    let settled = false;
    const finish = (heard: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(cap);
      if (pcmSrc === src) pcmSrc = null;
      src.onended = null;
      try { src.stop(); } catch { /* 已经播完。 */ }
      if (releaseCurrent === finish) releaseCurrent = null;
      resolve(heard);
    };
    const cap = window.setTimeout(() => finish(false), 14000);
    if (mine !== gen) {
      finish(false);
      return;
    }
    releaseCurrent = () => finish(false);
    src.onended = () => finish(true);
    void ctx.resume().then(() => {
      if (mine !== gen) {
        finish(false);
        return;
      }
      src.start();
    }).catch(() => finish(false));
  });
}

type ReadyClip = { fmt: string; rate: number; raw: ArrayBuffer };

const ready = new Map<string, Promise<ReadyClip | null>>();

function clipKey(engine: string, voice: string, text: string) {
  return `${engine}|${voice}|${text}`;
}

/** 下一句先合成好。这一句还在说的时候，模型空出来就把下一段做好。 */
export function prefetchTalk(
  text: string,
  voice: string,
  engine: string,
  qwenStyle = '',
) {
  const line = (text || '').trim();
  if (!line || engine === 'browser' || engine === 'off' || !voice) return;
  const key = clipKey(engine, voice, line);
  if (ready.has(key)) return;
    ready.set(key, api.ttsResponse(line, voice, engine, undefined, '', qwenStyle).then(
    async (resp) => {
      const fmt = (resp.headers.get('X-Audio-Format') || resp.headers.get('Content-Type') || '').toLowerCase();
      const rate = Number(resp.headers.get('X-Audio-Rate') || 24000);
      return { fmt, rate, raw: await resp.arrayBuffer() };
    },
    () => null,
  ));
}

/** 说完这一句才兑现。被打断也会兑现，避免整桌后面的台词全堵住。 */
export function talk(
  text: string,
  who: string,
  voice: string,
  engine: string,
  lang = 'zh-CN',
  qwenStyle = '',
): Promise<void> {
  const line = (text || '').trim();
  if (!line) return Promise.resolve();
  const mine = gen;
  const job = chain.then(async () => {
    if (mine !== gen) return;
    if (engine === 'browser' || engine === 'off' || !voice) {
      await browserSay(line, who, lang, mine);
      return;
    }
    const key = clipKey(engine, voice, line);
    const cached = ready.get(key);
    if (cached) ready.delete(key);
    try {
      const clip = cached ? await cached : null;
      if (mine !== gen) return;
      if (clip) {
        if (clip.fmt.startsWith('pcm') || clip.fmt.includes('octet-stream')) await playPcm(clip.raw, clip.rate, mine);
        else {
          const url = URL.createObjectURL(new Blob([clip.raw], { type: 'audio/mpeg' }));
          await playClip(url, mine);
        }
        return;
      }
      const resp = await new Promise<Response>((resolve, reject) => {
        const cap = window.setTimeout(() => reject(new Error('tts')), 45000);
        api.ttsResponse(line, voice, engine, undefined, '', qwenStyle).then(
          (got) => { window.clearTimeout(cap); resolve(got); },
          (err) => { window.clearTimeout(cap); reject(err); },
        );
      });
      if (mine !== gen) return;
      const fmt = (resp.headers.get('X-Audio-Format') || resp.headers.get('Content-Type') || '').toLowerCase();
      let heard = false;
      if (fmt.startsWith('pcm') || fmt.includes('octet-stream')) {
        const rate = Number(resp.headers.get('X-Audio-Rate') || 24000);
        heard = await playPcm(await resp.arrayBuffer(), rate, mine);
      } else {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        heard = await playClip(url, mine);
      }
      if (mine !== gen || heard) return;
    } catch {
      /* 在线音色失败就别改用系统朗读，那是机械声。这一句跳过，牌照打。 */
    }
  });
  chain = job.then(() => {}, () => {});
  return job.then(() => {});
}
