export interface Live2DPreset {
  parameters: Record<string, number>;
  expressions: string[];
}

export interface Live2DPreferences {
  gaze: boolean;
  parameters: Record<string, number>;
  expressions: string[];
  suppressedParameters: string[];
  zoom: number;
  offsetX: number;
  offsetY: number;
  presets: Record<string, Live2DPreset>;
}

const DEFAULTS: Live2DPreferences = {
  gaze: true,
  parameters: {},
  expressions: [],
  suppressedParameters: [],
  zoom: 0.3,
  offsetX: 0,
  offsetY: 0,
  presets: {},
};

function key(url: string) {
  return `companion.live2d.${encodeURIComponent(url)}`;
}

export function loadLive2DPreferences(url: string): Live2DPreferences {
  try {
    const raw = JSON.parse(localStorage.getItem(key(url)) || '{}');
    return {
      gaze: raw.gaze !== false,
      parameters: raw.parameters && typeof raw.parameters === 'object' ? raw.parameters : {},
      expressions: Array.isArray(raw.expressions) ? raw.expressions.filter((x: unknown) => typeof x === 'string') : [],
      suppressedParameters: Array.isArray(raw.suppressedParameters) ? raw.suppressedParameters.filter((x: unknown) => typeof x === 'string') : [],
      zoom: Math.min(3, Math.max(0.1, Number(raw.zoom) || 0.3)),
      offsetX: Number(raw.offsetX) || 0,
      offsetY: Number(raw.offsetY) || 0,
      presets: raw.presets && typeof raw.presets === 'object' ? raw.presets : {},
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveLive2DPreferences(url: string, patch: Partial<Live2DPreferences>) {
  const next = { ...loadLive2DPreferences(url), ...patch };
  try {
    localStorage.setItem(key(url), JSON.stringify(next));
  } catch { /* 隐私模式下仅保留本次会话 */ }
  return next;
}
