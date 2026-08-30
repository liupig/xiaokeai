/** 舞蹈配套 BGM：跟舞蹈 VMD 同开同停。说话时按 Continuous 淡出，说完淡入续播。非舞蹈动作不播。 */
export class BgmPlayer {
  private el: HTMLAudioElement | null = null;
  private url = '';
  private vol = 0.5;

  setVolume(v: number) {
    this.vol = Math.max(0, Math.min(1, v));
    if (this.el) this.el.volume = this.vol;
  }

  getVolume() {
    return this.vol;
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
      this.el.volume = this.vol;
      return;
    }
    this.stop();
    this.url = next;
    const el = new Audio(next);
    el.loop = opts?.loop === true;
    el.volume = this.vol;
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
