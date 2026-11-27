import { recordingToWav } from './wav';
const box = document.createElement('section');
box.id = 'chat-box';
box.innerHTML = `<strong>小可爱 · 在线体验</strong><div id="messages" aria-live="polite">你好，和我聊聊天吧。</div><form id="chat-form"><input id="chat-input" maxlength="2000" placeholder="输入消息…" required><button>发送</button><button type="button" id="record">🎙️</button></form><small id="status"></small>`;
document.body.append(box);
const messages = document.querySelector<HTMLDivElement>('#messages')!;
const input = document.querySelector<HTMLInputElement>('#chat-input')!;
const status = document.querySelector<HTMLElement>('#status')!;
const history: {role: string; content: string}[] = [];
function show(text: string) { const p = document.createElement('p'); p.textContent = text; messages.append(p); messages.scrollTop = messages.scrollHeight; }
declare global { interface Window { XIAOKE_API_ORIGINS?: string[] } }
const origins = window.XIAOKE_API_ORIGINS ?? [];
let selected: string | undefined;
async function chooseBackend(): Promise<string> {
  if (selected !== undefined) return selected;
  if (!origins.length) return selected = '';
  const probes = origins.map(async origin => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(origin + '/api/health', {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error('unavailable');
      return origin;
    } finally { clearTimeout(timer); }
  });
  try { return selected = await Promise.any(probes); }
  catch { throw new Error('没有可用的服务节点'); }
}
async function post(path: string, body: BodyInit, json = false) {
  const origin = await chooseBackend();
  let response: Response;
  try { response = await fetch(origin + '/api/' + path, { method: 'POST', headers: json ? {'Content-Type':'application/json'} : {}, body }); }
  catch (error) { selected = undefined; throw error; }
  if (!response.ok) throw new Error('服务暂时不可用，请稍后再试');
  return response;
}
document.querySelector<HTMLFormElement>('#chat-form')!.onsubmit = async e => {
  e.preventDefault(); const text = input.value.trim(); if (!text) return;
  input.value = ''; show('你：' + text); history.push({role:'user', content:text});
  status.textContent = '正在回复…';
  try {
    const response = await post('chat', JSON.stringify({messages: history.slice(-12)}), true);
    const result = await response.json(); show('小可爱：' + result.text); history.push({role:'assistant', content:result.text});
    status.textContent = '正在合成语音…';
    const speech = await post('tts', JSON.stringify({text: result.text.slice(0,1000)}), true);
    const url = URL.createObjectURL(await speech.blob()); const audio = new Audio(url);
    const talk = document.querySelector<HTMLButtonElement>('#btn-talk')!;
    audio.onplay = () => { if (!talk.classList.contains('active')) talk.click(); };
    audio.onended = audio.onerror = () => { if (talk.classList.contains('active')) talk.click(); URL.revokeObjectURL(url); };
    await audio.play(); status.textContent = '';
  } catch { status.textContent = '服务暂时不可用，请稍后再试。'; }
};
let recorder: MediaRecorder | undefined; let chunks: Blob[] = [];
document.querySelector<HTMLButtonElement>('#record')!.onclick = async () => {
  if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    recorder = new MediaRecorder(stream); chunks = [];
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop()); status.textContent = '正在识别…';
      try { const form = new FormData(); form.append('file', await recordingToWav(new Blob(chunks, {type:recorder!.mimeType})), 'recording.wav');
        const result = await (await post('asr', form)).json(); input.value = result.text; status.textContent = '识别完成，请确认后发送。';
      } catch { status.textContent = '语音识别失败。'; }
    };
    recorder.start(); status.textContent = '录音中，再按一次结束。';
    setTimeout(() => { if (recorder?.state === 'recording') recorder.stop(); }, 30000);
  } catch { status.textContent = '无法使用麦克风，请检查权限和 HTTPS。'; }
};

export {};
