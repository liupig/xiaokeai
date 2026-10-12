/// <reference types="vite/client" />

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
  minimize?: () => void;
  close?: () => void;
}

interface Window {
  companionDesktop?: CompanionDesktop;
}
