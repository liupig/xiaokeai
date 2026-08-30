/** 后端 API 客户端封装 */

export interface AssetItem {
  id: number;
  kind: 'model' | 'motion' | 'camera';
  name: string;
  label: string;
  path: string;
  fmt: string;
  size: number;
  source: string;
  source_url: string;
  meta: string;
}

export interface CharacterItem {
  id: number;
  name: string;
  model_asset_id: number;
  persona: string;
  greeting: string;
  voice: string;
  emotion_map: string;
  idle_motion: string;
}

export interface DownloadTask {
  id: string;
  url: string;
  status: 'pending' | 'fetching' | 'downloading' | 'importing' | 'done' | 'error';
  message: string;
  downloaded: number;
  total: number;
  filename?: string;
  assets?: { id: number; kind: string; label: string }[];
}

export interface OnlineWork {
  work_uuid: string;
  work_name: string;
  introduction: string;
  cover: string;
  author: string;
  downloads: number;
  work_type: 'model' | 'motion';
  url: string;
}

export type ChatEvent =
  | { type: 'text'; delta: string }
  | { type: 'speech'; id: string; text: string; duplex_cmd: string; sentence_type: string; kind?: string }
  | { type: 'duplex'; delayed_sec: number }
  | { type: 'emo'; value: string }
  | { type: 'act'; value: string }
  | { type: 'dance'; value: string }
  | { type: 'cam'; value: string }
  | { type: 'expr'; value: string }
  | { type: 'intent'; value: string }
  | { type: 'stand'; value: string }
  | { type: 'error'; code: string; message: string }
  | { type: 'done'; full_text: string }
  | { type: 'meta'; user_id?: number | null; message_id?: number | null };

export interface ChatMessageRow {
  id?: number;
  role: string;
  content: string;
  kind?: string;
  created_at?: string;
}

export interface ChatExtra {
  scene_id?: string;
  scene_text?: string;
  scene_title?: string;
  scene_conflict?: string;
  scene_opening?: string;
  scene_cam?: string;
  scene_intent?: string;
  scene_background?: string;
  scene_avoid?: string;
  scene_salt?: string;
  variation?: string;
  reroll?: boolean;
}

export interface MemoryFact {
  id: string;
  character_id: number;
  kind: string;
  kind_cn: string;
  content: string;
  importance: number;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface SceneCard {
  id: string;
  title: string;
  setting: string;
  conflict: string;
  opening: string;
  cam: string;
  intent: string;
  background?: string;
}

export interface KeepsakeItem {
  id: number;
  character_id: number;
  kind: 'still' | 'clip' | string;
  url: string;
  mime: string;
  caption: string;
  quote: string;
  created_at: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const body = await resp.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* 保留状态码 */ }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  assetUrl(asset: AssetItem): string {
    return `/assets/${asset.path}`;
  },

  listAssets(kind?: string) {
    return request<AssetItem[]>(`/api/assets${kind ? `?kind=${kind}` : ''}`);
  },
  rescanAssets() {
    return request<{ created: number }>('/api/assets/rescan', { method: 'POST' });
  },
  importAsset(file: File) {
    const form = new FormData();
    form.append('file', file);
    return request<AssetItem[]>('/api/assets/import', { method: 'POST', body: form });
  },
  deleteAsset(id: number, removeFiles = false) {
    return request(`/api/assets/${id}?remove_files=${removeFiles}`, { method: 'DELETE' });
  },
  updateAsset(id: number, patch: { label?: string; category?: string }) {
    return request<AssetItem>(`/api/assets/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  },
  recategorizeMotions() {
    return request<{ updated: number }>('/api/assets/recategorize', { method: 'POST' });
  },

  listCharacters() {
    return request<CharacterItem[]>('/api/characters');
  },
  createCharacter(char: Partial<CharacterItem>) {
    return request<CharacterItem>('/api/characters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(char),
    });
  },
  updateCharacter(char: CharacterItem) {
    return request<CharacterItem>(`/api/characters/${char.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(char),
    });
  },
  deleteCharacter(id: number) {
    return request(`/api/characters/${id}`, { method: 'DELETE' });
  },

  getCamReview() {
    return request<{ version: number; updated_at: string; verdicts: Record<string, string>; path?: string }>(
      '/api/review/cam');
  },
  putCamReview(verdicts: Record<string, string>) {
    return request<{ version: number; updated_at: string; verdicts: Record<string, string>; path?: string }>(
      '/api/review/cam', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdicts }),
      });
  },

  getSettings() {
    return request<Record<string, any>>('/api/settings');
  },
  testLlm(conf: Record<string, any>) {
    return request<{ ok: boolean; message: string }>('/api/settings/test_llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(conf),
    });
  },
  updateSettings(patch: Record<string, any>) {
    return request<Record<string, any>>('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  },

  getVoices() {
    return request<{ id: string; label: string; engine: string }[]>('/api/speech/voices');
  },
  getSpeechStatus() {
    return request<{
      asr: { available: boolean; installed?: boolean; ready: boolean; downloading?: boolean;
             progress?: number; message: string };
      tts: { available: boolean; ready: boolean; loading?: boolean; downloading?: boolean;
             gpu?: boolean; device?: string; size?: string; message: string;
             sizes?: Record<string, { installed: boolean; label: string; gb: string }> };
    }>('/api/speech/status');
  },
  warmupSpeech(target: 'asr' | 'tts' | 'all' = 'all', qwenSize?: string) {
    return request<{ ok: boolean; message: string }>(
      '/api/speech/warmup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, qwen_size: qwenSize || '' }),
      });
  },

  searchOnline(keyword: string, kind: 'model' | 'motion', page = 1) {
    return request<{ total: number; items: OnlineWork[] }>(
      `/api/download/search?keyword=${encodeURIComponent(keyword)}&kind=${kind}&page=${page}`);
  },
  createDownload(url: string, category = '') {
    return request<{ task_id: string }>('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, category }),
    });
  },
  getDownloadTask(taskId: string) {
    return request<DownloadTask>(`/api/download/tasks/${taskId}`);
  },
  listDownloadTasks() {
    return request<DownloadTask[]>('/api/download/tasks');
  },

  getChatHistory(characterId: number) {
    return request<ChatMessageRow[]>(`/api/chat/history/${characterId}`);
  },
  classifyIngress(body: {
    text: string; busy: 'dance' | 'speech' | 'generate';
    last_user?: string; last_assistant?: string;
  }) {
    return request<{ act: 'drop' | 'hold' | 'cut' }>('/api/chat/ingress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
  clearChatHistory(characterId: number) {
    return request(`/api/chat/history/${characterId}`, { method: 'DELETE' });
  },

  listMemory(characterId: number) {
    return request<MemoryFact[]>(`/api/modules/memory/facts/${characterId}`);
  },
  saveMemory(body: Partial<MemoryFact> & { character_id: number; content: string }) {
    return request<MemoryFact>('/api/modules/memory/facts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
  deleteMemory(characterId: number, factId: string) {
    return request(`/api/modules/memory/facts/${characterId}/${encodeURIComponent(factId)}`, { method: 'DELETE' });
  },

  listScenes() {
    return request<SceneCard[]>('/api/modules/scenes/cards');
  },
  getCurrentScene(characterId: number, opts?: {
    lastUserAt?: number;
    seedId?: string;
    seedBackground?: string;
    seedDay?: string;
    fresh?: boolean;
  }) {
    const q = new URLSearchParams();
    if (opts?.lastUserAt) q.set('last_user_at', String(opts.lastUserAt));
    if (opts?.seedId) q.set('seed_id', opts.seedId);
    if (opts?.seedBackground) q.set('seed_background', opts.seedBackground);
    if (opts?.seedDay) q.set('seed_day', opts.seedDay);
    if (opts?.fresh) q.set('fresh', 'true');
    const qs = q.toString();
    return request<{
      card: SceneCard | null;
      rotated: boolean;
      assigned_day: string;
      next_rotate_at: number;
    }>(`/api/modules/scenes/current/${characterId}${qs ? `?${qs}` : ''}`);
  },
  putCurrentScene(characterId: number, card: SceneCard, assignedDay?: string) {
    return request<{ card: SceneCard; rotated: boolean; assigned_day: string }>(
      '/api/modules/scenes/current', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_id: characterId,
          id: card.id || '',
          title: card.title || '',
          setting: card.setting || '',
          conflict: card.conflict || '',
          opening: card.opening || '',
          cam: card.cam || 'half',
          intent: card.intent || 'look',
          background: card.background || '',
          assigned_day: assignedDay || '',
        }),
      });
  },
  generateTonight(characterId: number) {
    return request<SceneCard>('/api/modules/scenes/tonight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: characterId }),
    });
  },

  rewindChat(characterId: number, messageId: number, inclusive = false) {
    return request<{ ok: boolean; removed: number; messages: ChatMessageRow[] }>(
      '/api/modules/rewrite/rewind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: characterId, message_id: messageId, inclusive }),
      });
  },
  dropChatMessage(characterId: number, messageId: number) {
    return request('/api/modules/rewrite/drop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: characterId, message_id: messageId }),
    });
  },

  listKeepsakes(characterId: number) {
    return request<KeepsakeItem[]>(`/api/modules/keepsakes/${characterId}`);
  },
  async uploadKeepsake(characterId: number, file: Blob, opts: {
    kind: 'still' | 'clip'; filename: string; caption?: string; quote?: string;
  }) {
    const form = new FormData();
    form.append('character_id', String(characterId));
    form.append('kind', opts.kind);
    form.append('caption', opts.caption || '');
    form.append('quote', opts.quote || '');
    form.append('file', file, opts.filename);
    return request<KeepsakeItem>('/api/modules/keepsakes', { method: 'POST', body: form });
  },
  deleteKeepsake(id: number) {
    return request(`/api/modules/keepsakes/${id}`, { method: 'DELETE' });
  },

  /** 流式对话：SSE 事件逐个回调；morphs 为当前模型可用的表情形态键（供 LLM 使用） */
  async streamChat(characterId: number, text: string,
                   onEvent: (ev: ChatEvent) => void, signal?: AbortSignal,
                   morphs: string[] = [],
                   mode: 'user' | 'continue' | 'proactive' | 'goodbye' | 'welcome' = 'user',
                   extra: ChatExtra = {}) {
    const body = {
      character_id: characterId, text, morphs, mode,
      scene_id: extra.scene_id || '',
      scene_text: extra.scene_text || '',
      scene_title: extra.scene_title || '',
      scene_conflict: extra.scene_conflict || '',
      scene_opening: extra.scene_opening || '',
      scene_cam: extra.scene_cam || '',
      scene_intent: extra.scene_intent || '',
      scene_background: extra.scene_background || '',
      scene_avoid: extra.scene_avoid || '',
      scene_salt: extra.scene_salt || '',
      variation: extra.variation || '',
      reroll: !!extra.reroll,
    };
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
    if (!resp.ok || !resp.body) throw new Error(`chat ${resp.status}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = chunk.split('\n').find((l) => l.startsWith('data:'));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()) as ChatEvent);
        } catch { /* 忽略坏帧 */ }
      }
    }
  },

  /** TTS：开发时直连后端，避免 Vite 代理把 PCM 流攒满再给浏览器。 */
  async ttsResponse(
    text: string, voice?: string, engine?: string, signal?: AbortSignal,
    qwenSize?: string, qwenStyle?: string, instruct?: string,
  ): Promise<Response> {
    const url = import.meta.env.DEV ? 'http://127.0.0.1:8600/api/speech/tts' : '/api/speech/tts';
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text, voice: voice ?? '', engine: engine ?? '',
        qwen_size: qwenSize ?? '', qwen_style: qwenStyle ?? '', instruct: instruct ?? '',
      }),
      signal,
    });
    if (!resp.ok) {
      let detail = `tts ${resp.status}`;
      try {
        const body = await resp.json();
        detail = body.detail ?? detail;
      } catch { /* */ }
      throw new Error(detail);
    }
    return resp;
  },

  /** TTS：缓冲完整音频为 Blob。engine 覆盖后端已保存的设置 */
  async tts(text: string, voice?: string, engine?: string, signal?: AbortSignal): Promise<Blob> {
    const resp = await this.ttsResponse(text, voice, engine, signal);
    const buf = await resp.arrayBuffer();
    const type = resp.headers.get('Content-Type') || 'audio/wav';
    return new Blob([buf], { type });
  },

  async stt(wav: Blob): Promise<{ text: string }> {
    const form = new FormData();
    form.append('file', wav, 'speech.wav');
    return request<{ text: string }>('/api/speech/stt', { method: 'POST', body: form });
  },
};
