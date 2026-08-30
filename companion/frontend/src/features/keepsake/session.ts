import { reactive } from 'vue';
import { api, type KeepsakeItem } from '../../api/client';

const CLIP_SEC_KEY = 'companion.clipSec';
export const CLIP_SEC_DEFAULT = 8;
export const CLIP_SEC_MIN = 1;
export const CLIP_SEC_MAX = 60;

export function clampClipSec(n: number) {
  const x = Math.round(Number(n));
  if (!Number.isFinite(x)) return CLIP_SEC_DEFAULT;
  return Math.min(CLIP_SEC_MAX, Math.max(CLIP_SEC_MIN, x));
}

function readClipSec() {
  try {
    const raw = localStorage.getItem(CLIP_SEC_KEY);
    if (raw == null || raw === '') return CLIP_SEC_DEFAULT;
    return clampClipSec(Number(raw));
  } catch {
    return CLIP_SEC_DEFAULT;
  }
}

export const keepsakeSession = reactive({
  items: [] as KeepsakeItem[],
  recording: false,
  saving: false,
  recSec: 0,
  clipSec: readClipSec(),
  /** 证物临时当背景时的地址；空表示没用证物盖住环境 */
  bgOverride: '',
  bgPrev: '',
});

export function isKeepsakeBgUrl(url: string) {
  return /\/api\/modules\/keepsakes\/file\//.test(url)
    || /^\/keepsakes\//.test(url);
}

export function noteSceneTookBg() {
  keepsakeSession.bgOverride = '';
}

export function setClipSec(n: number) {
  keepsakeSession.clipSec = clampClipSec(n);
  try {
    localStorage.setItem(CLIP_SEC_KEY, String(keepsakeSession.clipSec));
  } catch { /* 隐私模式 */ }
}

export async function refreshKeepsakes(characterId: number) {
  if (!characterId) {
    keepsakeSession.items = [];
    return;
  }
  try {
    keepsakeSession.items = await api.listKeepsakes(characterId);
  } catch {
    keepsakeSession.items = [];
  }
}
