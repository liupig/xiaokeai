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

  const imported = await import('@ennuicastr/webrtcaec3.js') as {
    default?: () => Promise<{ AEC3: new (rate: number, r: number, c: number) => Aec3Instance }>;
    WebRtcAec3?: () => Promise<{ AEC3: new (rate: number, r: number, c: number) => Aec3Instance }>;
  };
  const WebRtcAec3 = imported.default ?? imported.WebRtcAec3;
  if (!WebRtcAec3) throw new Error('webrtcaec3 模块无效');
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
