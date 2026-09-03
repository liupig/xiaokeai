/** 舞蹈配套 BGM：跟舞蹈 VMD 同开同停。说话时压低续播，说完还原。非舞蹈动作不播。 */
export class BgmPlayer {
  private el: HTMLAudioElement | null = null;
  private url = '';
  private vol = 0.5;
  /** 1 = 用户音量；说话时 < 1，歌还在，只是让路给 TTS。 */
  private duck = 1;

  get ducked() {
    return this.duck < 0.99;
  }

  private mixedVol() {
    return Math.max(0, Math.min(1, this.vol * this.duck));
  }

  setVolume(v: number) {
    this.vol = Math.max(0, Math.min(1, v));
    if (this.el) this.el.volume = this.mixedVol();
  }

  getVolume() {
    return this.vol;
  }

  /** 说话压低 / 说完还原。没有元素时也记住，下一首开播就带上。 */
  setDuck(factor: number, ms = 300) {
    this.duck = Math.max(0.12, Math.min(1, factor));
    this.fadeTo(this.mixedVol(), ms);
  }

  fadeTo(target: number, ms = 300) {
    const el = this.el;
    if (!el) return;
    const from = el.volume;
    const to = Math.max(0, Math.min(1, target));
    if (ms <= 0) {
      el.volume = to;
      return;
    }
    const t0 = performance.now();
    const step = () => {
      if (this.el !== el) return;
      const p = Math.min(1, (performance.now() - t0) / ms);
      el.volume = from + (to - from) * p;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  play(url: string, opts?: { loop?: boolean }) {
    const next = url.trim();
    if (!next) {
      this.stop();
      return;
    }
    if (this.el && this.url === next && !this.el.paused) {
      this.el.loop = opts?.loop === true;
      this.el.volume = this.mixedVol();
      return;
    }
    this.stop();
    this.url = next;
    const el = new Audio(next);
    el.loop = opts?.loop === true;
    el.volume = this.mixedVol();
    el.preload = 'auto';
    el.onended = () => {
      if (this.el !== el) return;
      this.onEnded?.();
    };
    void el.play().catch(() => {
      /* 浏览器未解锁音频时忽略，下一次用户点击会再播 */
    });
    this.el = el;
  }

  onEnded: (() => void) | null = null;

  stop() {
    if (this.el) {
      this.el.onended = null;
      this.el.pause();
      this.el.removeAttribute('src');
      this.el.load();
      this.el = null;
    }
    this.url = '';
  }
}
