import { api, type CodewatchSourceId, type CodewatchStatus } from '../../api/client';
import { applyCodewatch, resetCodewatchShow } from './perform';
import { codewatchLive } from './live';
import { loadPicked, mergeSources, savePicked } from './sources';

export { codewatchLive };

const OPEN_KEY = 'xiaoke.codewatch.open';
let es: EventSource | null = null;
let pollTimer = 0;
let lastSeq = -1;

function applySnap(snap: CodewatchStatus) {
  const prev = lastSeq;
  codewatchLive.watching = !!snap.watching;
  codewatchLive.phase = snap.phase || 'idle';
  codewatchLive.source = snap.source || 'cursor';
  if (snap.enabled?.length) codewatchLive.picked = snap.enabled;
  codewatchLive.sources = mergeSources(snap.sources, codewatchLive.picked);
  codewatchLive.title = snap.title || '';
  codewatchLive.project = snap.project || '';
  codewatchLive.tool = snap.tool || '';
  codewatchLive.hint = snap.hint || '';
  codewatchLive.seq = snap.seq || 0;
  codewatchLive.cursorFound = !!snap.cursor_found;
  codewatchLive.cursorHome = snap.cursor_home !== false;
  if (snap.hooks) codewatchLive.hooksInstalled = !!snap.hooks.installed;
  if (snap.seq !== prev) {
    lastSeq = snap.seq;
    if (codewatchLive.open && snap.watching) applyCodewatch(snap);
  }
}

function stopStream() {
  if (es) {
    es.close();
    es = null;
  }
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = 0;
  }
}

function eventsUrl() {
  if (import.meta.env.DEV) return 'http://127.0.0.1:8600/api/modules/codewatch/events';
  const { protocol, hostname, port } = window.location;
  if (port === '5211') return `${protocol}//${hostname}:5201/api/modules/codewatch/events`;
  return '/api/modules/codewatch/events';
}

function startStream() {
  stopStream();
  pollTimer = window.setInterval(() => { void refresh(); }, 2000);
  try {
    es = new EventSource(eventsUrl());
    es.onmessage = (ev) => {
      try {
        applySnap(JSON.parse(ev.data) as CodewatchStatus);
      } catch { /* 坏帧 */ }
    };
    es.onerror = () => {
      es?.close();
      es = null;
    };
  } catch { /* 只靠轮询 */ }
}

export async function refresh() {
  try {
    applySnap(await api.codewatchStatus());
  } catch { /* 模块关着或后端未起 */ }
}

export async function openCodewatch() {
  if (codewatchLive.busy) return;
  codewatchLive.busy = true;
  codewatchLive.open = true;
  try {
    localStorage.setItem(OPEN_KEY, '1');
  } catch { /* */ }
  try {
    applySnap(await api.codewatchStart(codewatchLive.picked.length ? codewatchLive.picked : loadPicked()));
    startStream();
  } finally {
    codewatchLive.busy = false;
  }
}

export async function closeCodewatch() {
  if (codewatchLive.busy) return;
  codewatchLive.busy = true;
  stopStream();
  try {
    applySnap(await api.codewatchStop());
  } catch { /* */ }
  resetCodewatchShow();
  codewatchLive.open = false;
  codewatchLive.watching = false;
  codewatchLive.phase = 'idle';
  codewatchLive.hudPhase = 'idle';
  try {
    localStorage.removeItem(OPEN_KEY);
  } catch { /* */ }
  codewatchLive.busy = false;
}

export async function setPicked(id: CodewatchSourceId) {
  const cur = codewatchLive.picked.includes(id)
    ? codewatchLive.picked.filter((x) => x !== id)
    : [...codewatchLive.picked, id];
  codewatchLive.picked = savePicked(cur);
  codewatchLive.sources = mergeSources(codewatchLive.sources, codewatchLive.picked);
  if (!codewatchLive.open) return;
  try {
    applySnap(await api.codewatchSources(codewatchLive.picked));
  } catch { /* */ }
}

export async function toggleCodewatch() {
  if (codewatchLive.open) await closeCodewatch();
  else await openCodewatch();
}

export async function installHooks() {
  const st = await api.codewatchInstallHooks();
  codewatchLive.hooksInstalled = !!st.installed;
  return st;
}

export async function uninstallHooks() {
  const st = await api.codewatchUninstallHooks();
  codewatchLive.hooksInstalled = !!st.installed;
  return st;
}

export async function restoreCodewatch() {
  let want = false;
  try {
    want = localStorage.getItem(OPEN_KEY) === '1';
  } catch { /* */ }
  if (!want) return;
  await openCodewatch();
}

export function onModuleOff() {
  stopStream();
  resetCodewatchShow();
  codewatchLive.open = false;
  codewatchLive.watching = false;
  codewatchLive.phase = 'idle';
  codewatchLive.hudPhase = 'idle';
  try {
    localStorage.removeItem(OPEN_KEY);
  } catch { /* */ }
}
