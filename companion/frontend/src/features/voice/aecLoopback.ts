/**
 * Chrome 的 AEC 只认 WebRTC 远端轨道当参考信号。
 * TTS 若直接接到 AudioContext.destination，喇叭漏音消不掉。
 * 这里把 Web Audio 绕进一对本地 PeerConnection，再从 <audio> 播出。
 * @see https://dev.to/focused_dot_io/echo-cancellation-with-web-audio-api-and-chromium-1f8m
 */

export class AecSpeaker {
  private send: RTCPeerConnection | null = null;
  private recv: RTCPeerConnection | null = null;
  private el: HTMLAudioElement | null = null;
  private ready: Promise<boolean> | null = null;

  /** 成功后应把 Analyser 从 ctx.destination 断开，避免播两遍。 */
  start(stream: MediaStream): Promise<boolean> {
    if (!this.ready) this.ready = this.open(stream);
    return this.ready;
  }

  private async open(stream: MediaStream): Promise<boolean> {
    try {
      const send = new RTCPeerConnection({ iceServers: [] });
      const recv = new RTCPeerConnection({ iceServers: [] });
      this.send = send;
      this.recv = recv;
      send.onicecandidate = (e) => { if (e.candidate) void recv.addIceCandidate(e.candidate); };
      recv.onicecandidate = (e) => { if (e.candidate) void send.addIceCandidate(e.candidate); };

      const remote = new MediaStream();
      const gotTrack = new Promise<void>((resolve) => {
        recv.ontrack = (ev) => {
          remote.addTrack(ev.track);
          resolve();
        };
      });
      for (const track of stream.getAudioTracks()) send.addTrack(track, stream);

      const offer = await send.createOffer();
      await send.setLocalDescription(offer);
      await recv.setRemoteDescription(offer);
      const answer = await recv.createAnswer();
      await recv.setLocalDescription(answer);
      await send.setRemoteDescription(answer);
      await Promise.race([
        gotTrack,
        new Promise<void>((_, reject) => {
          window.setTimeout(() => reject(new Error('loopback timeout')), 2000);
        }),
      ]);

      const el = new Audio();
      el.autoplay = true;
      el.srcObject = remote;
      this.el = el;
      await el.play();
      return true;
    } catch (e) {
      console.warn('AEC 环回未就绪，TTS 仍走扬声器直出', e);
      this.close();
      return false;
    }
  }

  private close() {
    try { this.el?.pause(); } catch { /* */ }
    this.el = null;
    try { this.send?.close(); } catch { /* */ }
    try { this.recv?.close(); } catch { /* */ }
    this.send = null;
    this.recv = null;
    this.ready = null;
  }
}
