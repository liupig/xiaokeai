/// <reference types="vite/client" />

interface PetDisplay {
  id: number;
  index: number;
  width: number;
  height: number;
  scaleFactor: number;
  primary: boolean;
  current: boolean;
  internal: boolean;
  label: string;
}

interface CompanionDesktop {
  isShell: true;
  pickFolder?: () => Promise<string>;
  getShellMode?: () => Promise<'stage' | 'pet'>;
  setShellMode?: (mode: 'stage' | 'pet') => Promise<'stage' | 'pet'>;
  setIgnoreMouse?: (ignore: boolean) => void;
  setPetHitRegion?: (region: {
    ax: number;
    ay: number;
    bx: number;
    by: number;
    r: number;
    rects: { x: number; y: number; w: number; h: number }[];
    pressed: boolean;
    focus: boolean;
  }) => void;
  dragBy?: (dx: number, dy: number) => void;
  resizeBy?: (dx: number, dy: number) => void;
  listDisplays?: () => Promise<PetDisplay[]>;
  setPetDisplay?: (id: number) => Promise<PetDisplay[]>;
  onDisplaysChanged?: (cb: () => void) => () => void;
  getPetSpot?: () => Promise<{ x: number; y: number } | null>;
  setPetSpot?: (spot: { x: number; y: number } | null) => void;
  minimize?: () => void;
  close?: () => void;
  reload?: () => Promise<boolean>;
  getTrayPrefs?: () => Promise<{ minimize: boolean; close: boolean }>;
  setTrayPrefs?: (prefs: { minimize?: boolean; close?: boolean }) => Promise<{ minimize: boolean; close: boolean }>;
  setTrayLocale?: (lang: string) => void;
}

interface Window {
  companionDesktop?: CompanionDesktop;
}
