// Convert the browser recording to PCM WAV accepted by MiMo ASR.
export async function recordingToWav(blob: Blob): Promise<Blob> {
  const context = new AudioContext();
  try {
    const audio = await context.decodeAudioData(await blob.arrayBuffer());
    const frames = audio.length, channels = audio.numberOfChannels;
    const buffer = new ArrayBuffer(44 + frames * 2), view = new DataView(buffer);
    const text = (offset: number, value: string) => { for (let i=0; i<value.length; i++) view.setUint8(offset+i, value.charCodeAt(i)); };
    text(0,'RIFF'); view.setUint32(4,36+frames*2,true); text(8,'WAVE'); text(12,'fmt ');
    view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
    view.setUint32(24,audio.sampleRate,true); view.setUint32(28,audio.sampleRate*2,true);
    view.setUint16(32,2,true); view.setUint16(34,16,true); text(36,'data'); view.setUint32(40,frames*2,true);
    const samples = Array.from({length:channels},(_,i)=>audio.getChannelData(i));
    for (let i=0;i<frames;i++) { let v=0; for (const channel of samples) v+=channel[i]/channels; v=Math.max(-1,Math.min(1,v)); view.setInt16(44+i*2,v<0?v*32768:v*32767,true); }
    return new Blob([buffer],{type:'audio/wav'});
  } finally { await context.close(); }
}
