import { shallowRef } from 'vue';
export const availableRelease = shallowRef<ReleaseInfo | null>(null);
export const UPDATE_URL = 'https://xiaoke.ai';
export const CURRENT_VERSION = String(import.meta.env.VITE_XIAOKEAI_VERSION || 'dev');

export interface ReleaseInfo { version: string; published_at?: string; notes?: { zh?: string; en?: string }; update_available?: boolean; baidu_password?: string; downloads?: { baidu?: string; huggingface?: string; google_drive?: string }; }

export const DEFAULT_DOWNLOADS = {
  baidu: 'https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai',
  huggingface: 'https://huggingface.co/datasets/liupigai/xiaokeai/tree/main',
  google_drive: 'https://drive.google.com/drive/folders/1mZcD4K90WgO2x2UxteAyMFsQlgTairPl?usp=drive_link',
};

const ignoredKey = 'xiaokeai.update.ignored';
export function ignored(version: string) { return localStorage.getItem(ignoredKey) === version; }
export function ignore(version: string) { localStorage.setItem(ignoredKey, version); }
export async function checkUpdate() {
  const q = CURRENT_VERSION === 'dev' ? '' : `?current_version=${encodeURIComponent(CURRENT_VERSION)}`;
  const r = await fetch(`/api/releases/latest${q}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(String(r.status));
  const info = await r.json() as ReleaseInfo;
  availableRelease.value = info.update_available ? info : null;
  if (info.update_available && !ignored(info.version)) window.dispatchEvent(new CustomEvent('xiaokeai:update', { detail: info }));
  return info;
}
