import { api } from '../../api/client';

/** 酒馆台词。每人一条音色，排队说完这一句再放下一句，不跟聊天的那条嗓子抢。 */

let chain: Promise<void> = Promise.resolve();
let current: HTMLAudioElement | null = null;
let gen = 0;
let releaseCurrent: (() => void) | null = null;

const PITCH: Record<string, number> = { you: 1, qin: 1.32, bar: 0.78, her: 1.12, host: 0.9 };

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
  if (typeof speechSynthesis !== 'undefined') {
    try { speechSynthesis.cancel(); } catch { /* */ }
  }
  release?.();
}

function browserSay(text: string, who: string, mine: number) {
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
    utter.lang = 'zh-CN';
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

/** 说完这一句才兑现。被打断也会兑现，避免整桌后面的台词全堵住。 */
export function talk(text: string, who: string, voice: string, engine: string): Promise<void> {
  const line = (text || '').trim();
  if (!line) return Promise.resolve();
  const mine = gen;
  const job = chain.then(async () => {
    if (mine !== gen) return;
    if (engine === 'browser' || engine === 'off' || !voice) {
      await browserSay(line, who, mine);
      return;
    }
    try {
      const blob = await new Promise<Blob>((resolve, reject) => {
        const cap = window.setTimeout(() => reject(new Error('tts')), 8000);
        api.tts(line, voice, engine).then(
          (got) => { window.clearTimeout(cap); resolve(got); },
          (err) => { window.clearTimeout(cap); reject(err); },
        );
      });
      if (mine !== gen) return;
      const url = URL.createObjectURL(blob);
      const heard = await playClip(url, mine);
      if (mine !== gen || heard) return;
      await browserSay(line, who, mine);
    } catch {
      await browserSay(line, who, mine);
    }
  });
  chain = job.then(() => {}, () => {});
  return job.then(() => {});
}
