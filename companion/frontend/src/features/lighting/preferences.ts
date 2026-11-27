export type LightingProfile = {
  direction: number;
  contrast: number;
  color: string;
  toon: boolean;
  outline: boolean;
};

export const lightingPresets = {
  default: { direction: 26, contrast: 0, color: '#ffffff', toon: false, outline: false },
  manga: { direction: -30, contrast: 38, color: '#cad3ff', toon: true, outline: true },
  soft: { direction: 15, contrast: -55, color: '#fff1df', toon: false, outline: false },
} satisfies Record<string, LightingProfile>;

export type LightingPreset = keyof typeof lightingPresets;
export type LightingSettings = {
  enabled: boolean;
  preset: LightingPreset;
  profile: LightingProfile;
};

const storageKey = 'shixu.character-lighting';
const previousManga = { direction: -42, contrast: 65, color: '#acbaff', toon: true, outline: true };

function numberInRange(value: unknown, min: number, max: number, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(min, Math.min(max, value))
    : fallback;
}

export function readLighting(): LightingSettings {
  const defaults = { enabled: false, preset: 'default', profile: { ...lightingPresets.default } } as const;
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    if (!saved) return defaults;
    const preset: LightingPreset = Object.prototype.hasOwnProperty.call(lightingPresets, saved.preset) ? saved.preset : 'default';
    const base = lightingPresets[preset];
    const profile = preset === 'manga' && saved.profile &&
      (Object.keys(previousManga) as (keyof LightingProfile)[]).every(
        (key) => saved.profile[key] === previousManga[key],
      )
      ? base
      : saved.profile ?? {};
    return {
      enabled: saved.enabled === true,
      preset,
      profile: {
        direction: numberInRange(profile.direction, -180, 180, base.direction),
        contrast: numberInRange(profile.contrast, -100, 100, base.contrast),
        color: typeof profile.color === 'string' && /^#[\da-f]{6}$/i.test(profile.color) ? profile.color : base.color,
        toon: typeof profile.toon === 'boolean' ? profile.toon : base.toon,
        outline: typeof profile.outline === 'boolean' ? profile.outline : base.outline,
      },
    };
  } catch {
    return defaults;
  }
}

export function saveLighting(settings: LightingSettings) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(settings));
  } catch { /* Live preview is still available when storage is unavailable. */ }
}
