/**
 * 回声消除调度：浏览器 AEC（WebRTC 环回）优先，失效再切 AEC3 WASM。
 * 两套不同时开。
 */
import { openWasmAec, type WasmAecHandle } from './aecWasm';

export type AecMode = 'browser' | 'wasm';

const LOOPBACK_WAIT_MS = 2500;
const ECHO_LEAK_HITS = 3;

let loopbackOk: boolean | null = null;
let loopbackWaiters: Array<(ok: boolean) => void> = [];
let mode: AecMode | null = null;
let echoHits = 0;
let wasm: WasmAecHandle | null = null;
let wasmOpening: Promise<MediaStream> | null = null;

export function currentAecMode(): AecMode | null {
  return mode;
}

export function reportLoopback(ok: boolean) {
  if (loopbackOk !== null) return;
  loopbackOk = ok;
  const q = loopbackWaiters;
  loopbackWaiters = [];
  for (const w of q) w(ok);
  if (!ok) console.warn('浏览器 AEC 环回失败，改用 AEC3 WASM');
}

function whenLoopbackSettled(): Promise<boolean> {
  if (loopbackOk !== null) return Promise.resolve(loopbackOk);
  return new Promise((resolve) => {
    const t = window.setTimeout(() => {
      if (loopbackOk !== null) return;
      reportLoopback(false);
    }, LOOPBACK_WAIT_MS);
    loopbackWaiters.push((ok) => {
      window.clearTimeout(t);
      resolve(ok);
    });
  });
}

export async function resolveAecMode(): Promise<AecMode> {
  if (mode) return mode;
  const ok = await whenLoopbackSettled();
  mode = ok ? 'browser' : 'wasm';
  return mode;
}

export function browserMicConstraints(): MediaTrackConstraints {
  return {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: false,
  };
}

export function wasmMicConstraints(): MediaTrackConstraints {
  return {
    channelCount: 1,
    echoCancellation: false,
    noiseSuppression: true,
    autoGainControl: false,
  };
}

export function isWasmMicStream(stream: MediaStream) {
  return Boolean(wasm?.stream && wasm.stream === stream);
}

export async function getMicStream(opts: {
  ctx: AudioContext | null;
  tap: AudioNode | null;
}): Promise<MediaStream> {
  // 开麦不能等环回探测：第一次点麦克风会被卡 2.5s，再点一次又把麦掐掉。
  void resolveAecMode();
  if (mode === 'wasm') return ensureWasmStream(opts);
  return navigator.mediaDevices.getUserMedia({ audio: browserMicConstraints() });
}

async function ensureWasmStream(opts: {
  ctx: AudioContext | null;
  tap: AudioNode | null;
}): Promise<MediaStream> {
  if (wasm?.stream) return wasm.stream;
  if (!opts.ctx || !opts.tap) {
    return navigator.mediaDevices.getUserMedia({ audio: wasmMicConstraints() });
  }
  if (!wasmOpening) {
    wasmOpening = Promise.race([
      openWasmAec(opts.ctx, opts.tap),
      new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error('AEC3 超时')), 4000);
      }),
    ]).then((h) => {
      wasm = h;
      return h.stream;
    }).catch((e) => {
      console.warn('AEC3 WASM 启动失败，麦克风直出', e);
      return navigator.mediaDevices.getUserMedia({ audio: wasmMicConstraints() });
    }).finally(() => { wasmOpening = null; });
  }
  return wasmOpening;
}

/** 浏览器模式下连续听成回声 → 切 WASM。返回是否刚切换。 */
export function noteEchoLeak(): boolean {
  if (mode === 'wasm') return false;
  echoHits += 1;
  if (echoHits < ECHO_LEAK_HITS) return false;
  if (mode === 'browser') {
    console.warn('浏览器 AEC 仍漏回声，改用 AEC3 WASM');
  }
  mode = 'wasm';
  return true;
}
