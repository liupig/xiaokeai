/** AEC3 WASM：用正在播的 TTS 当参考，从麦克风里减掉喇叭漏音。 */

type Aec3Instance = {
  analyze: (data: Float32Array[], opts?: { sampleRateIn?: number }) => void;
  processSize: (data: Float32Array[], opts?: { sampleRateIn?: number; sampleRateOut?: number }) => number;
  process: (out: Float32Array[], data: Float32Array[], opts?: { sampleRateIn?: number; sampleRateOut?: number }) => void;
  setAudioBufferDelay: (delay: number) => void;
};

export type WasmAecHandle = {
  stream: MediaStream;
  keep: object[];
};

class SampleQueue {
  private chunks: Float32Array[] = [];
  private len = 0;

  push(samples: Float32Array) {
    if (!samples.length) return;
    this.chunks.push(samples);
    this.len += samples.length;
  }

  pull(dest: Float32Array) {
    let o = 0;
    while (o < dest.length && this.len) {
      const cur = this.chunks[0]!;
      const n = Math.min(cur.length, dest.length - o);
      dest.set(cur.subarray(0, n), o);
      o += n;
      this.len -= n;
      if (n >= cur.length) this.chunks.shift();
      else this.chunks[0] = cur.subarray(n);
    }
    if (o < dest.length) dest.fill(0, o);
  }
}

type Aec3Factory = {
  AEC3: new (rate: number, r: number, c: number) => Aec3Instance;
};

type WebRtcAec3Fn = () => Promise<Aec3Factory>;

function publicUrl(rel: string): string {
  const base = import.meta.env.BASE_URL.endsWith('/')
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL}/`;
  return `${base}${rel}`;
}

let aec3Loader: Promise<WebRtcAec3Fn> | null = null;

/** 用经典 script 加载：库顶层写了 WebRtcAec3Wasm=…，ES 模块严格模式会直接抛 ReferenceError。 */
function loadWebRtcAec3(): Promise<WebRtcAec3Fn> {
  if (aec3Loader) return aec3Loader;
  aec3Loader = new Promise<WebRtcAec3Fn>((resolve, reject) => {
    const w = window as Window & { WebRtcAec3?: WebRtcAec3Fn };
    if (typeof w.WebRtcAec3 === 'function') {
      resolve(w.WebRtcAec3);
      return;
    }
    const s = document.createElement('script');
    s.src = publicUrl('aec3/webrtcaec3-0.3.0.js');
    s.async = true;
    s.onload = () => {
      if (typeof w.WebRtcAec3 === 'function') resolve(w.WebRtcAec3);
      else reject(new Error('webrtcaec3 模块无效'));
    };
    s.onerror = () => reject(new Error('webrtcaec3 脚本加载失败'));
    document.head.appendChild(s);
  }).catch((e) => {
    aec3Loader = null;
    throw e;
  });
  return aec3Loader;
}

export async function openWasmAec(ctx: AudioContext, tap: AudioNode): Promise<WasmAecHandle> {
  const raw = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: true,
      autoGainControl: false,
    },
  });
  if (ctx.state === 'suspended') await ctx.resume();

  const WebRtcAec3 = await loadWebRtcAec3();
  const factory = await WebRtcAec3();
  const aec: Aec3Instance = new factory.AEC3(48000, 1, 1);
  aec.setAudioBufferDelay(80);

  const opts = { sampleRateIn: ctx.sampleRate, sampleRateOut: ctx.sampleRate };
  const capSrc = ctx.createMediaStreamSource(raw);
  const dest = ctx.createMediaStreamDestination();
  const silent = ctx.createGain();
  silent.gain.value = 0;

  const rendProc = ctx.createScriptProcessor(1024, 1, 1);
  rendProc.onaudioprocess = (ev) => {
    const ch = ev.inputBuffer.getChannelData(0);
    aec.analyze([new Float32Array(ch)], { sampleRateIn: ctx.sampleRate });
    ev.outputBuffer.getChannelData(0).fill(0);
  };

  const outQ = new SampleQueue();
  const capProc = ctx.createScriptProcessor(1024, 1, 1);
  capProc.onaudioprocess = (ev) => {
    const ch = new Float32Array(ev.inputBuffer.getChannelData(0));
    const data = [ch];
    const n = aec.processSize(data, opts);
    const buf = [new Float32Array(Math.max(n, 0))];
    if (n > 0) aec.process(buf, data, opts);
    outQ.push(buf[0]);
    outQ.pull(ev.outputBuffer.getChannelData(0));
  };

  tap.connect(rendProc);
  rendProc.connect(silent);
  silent.connect(ctx.destination);
  capSrc.connect(capProc);
  capProc.connect(dest);

  return {
    stream: dest.stream,
    keep: [raw, capSrc, dest, silent, rendProc, capProc, aec, tap],
  };
}
