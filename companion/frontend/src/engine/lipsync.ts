/** 口型驱动：正弦波模拟（无音频时）或音频振幅分析（TTS 播放时） */
export class Lipsync {
  private mode: 'off' | 'sine' | 'analyser' = 'off';
  private analyser: AnalyserNode | null = null;
  private data: Uint8Array | null = null;
  private smooth = 0;

  /** 开/关正弦波说话模式（无真实音频时的模拟口型） */
  setTalking(on: boolean) {
    if (this.mode === 'analyser' && on) return; // 音频驱动优先
    this.mode = on ? 'sine' : 'off';
  }

  /** 绑定 WebAudio 分析节点，用真实音频振幅驱动口型 */
  attachAnalyser(analyser: AnalyserNode) {
    this.analyser = analyser;
    this.data = new Uint8Array(analyser.fftSize);
    this.mode = 'analyser';
  }

  detachAnalyser() {
    this.analyser = null;
    this.data = null;
    if (this.mode === 'analyser') this.mode = 'off';
  }

  get talking() {
    return this.mode !== 'off';
  }

  /** 每帧计算口型开合值 0~1 */
  value(t: number, dt: number): number {
    let target = 0;
    if (this.mode === 'sine') {
      target = Math.max(0, 0.32 + 0.28 * Math.sin(t * 11) + 0.2 * Math.sin(t * 23 + 1.3));
    } else if (this.mode === 'analyser' && this.analyser && this.data) {
      this.analyser.getByteTimeDomainData(this.data);
      let sum = 0;
      for (let i = 0; i < this.data.length; i++) {
        const v = (this.data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / this.data.length);
      target = Math.min(1, rms * 7); // 放大到可见开合幅度
    }
    // 平滑，避免口型抖动
    this.smooth += (target - this.smooth) * Math.min(1, dt * 18);
    return this.smooth;
  }
}
