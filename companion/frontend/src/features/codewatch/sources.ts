import type { CodewatchSource, CodewatchSourceId } from '../../api/client';

export const DESKS: {
  id: CodewatchSourceId;
  label: string;
  short: string;
}[] = [
  { id: 'cursor', label: 'Cursor', short: 'Cursor' },
  { id: 'codex', label: 'Codex', short: 'Codex' },
  { id: 'cc', label: 'Claude Code', short: 'CC' },
  { id: 'lingma', label: '通义灵码', short: '灵码' },
  { id: 'trae', label: 'Trae', short: 'Trae' },
  { id: 'comate', label: '文心快码', short: '快码' },
];

const PICK_KEY = 'xiaoke.codewatch.sources';

export function loadPicked(): CodewatchSourceId[] {
  try {
    const raw = localStorage.getItem(PICK_KEY);
    if (!raw) return ['cursor'];
    const ids = JSON.parse(raw) as string[];
    const ok = DESKS.map((d) => d.id).filter((id) => ids.includes(id));
    return ok.length ? ok : ['cursor'];
  } catch {
    return ['cursor'];
  }
}

export function savePicked(ids: CodewatchSourceId[]) {
  const ok = DESKS.map((d) => d.id).filter((id) => ids.includes(id));
  const picked = ok.length ? ok : ['cursor'];
  try {
    localStorage.setItem(PICK_KEY, JSON.stringify(picked));
  } catch { /* */ }
  return picked;
}

export function mergeSources(rows?: CodewatchSource[], picked?: CodewatchSourceId[]): CodewatchSource[] {
  const map = new Map((rows || []).map((r) => [r.id, r]));
  const on = new Set(picked || []);
  return DESKS.map((d) => {
    const hit = map.get(d.id);
    return {
      id: d.id,
      label: d.label,
      short: d.short,
      found: !!hit?.found,
      active: !!hit?.active,
      on: on.has(d.id) || !!hit?.on,
    };
  });
}
