import * as THREE from 'three';
import type { TarotCard } from '../../api/client';

const W = 512;
const H = 768;
const loader = new THREE.TextureLoader();
loader.setCrossOrigin('anonymous');

const texCache = new Map<string, THREE.Texture>();
let backTex: THREE.Texture | null = null;
let backPending: Promise<THREE.Texture> | null = null;

const SUIT_TONE: Record<string, [string, string]> = {
  wands: ['#3a1410', '#d4783a'],
  cups: ['#102030', '#7eb4c9'],
  swords: ['#161820', '#c5c8d4'],
  coins: ['#122016', '#8fbf7a'],
  '': ['#12101c', '#c9a227'],
};

function loadImage(url: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function paintFrame(ctx: CanvasRenderingContext2D) {
  const m = 18;
  ctx.strokeStyle = 'rgba(212, 176, 106, 0.92)';
  ctx.lineWidth = 5;
  roundRect(ctx, m, m, W - m * 2, H - m * 2, 22);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255, 228, 170, 0.35)';
  ctx.lineWidth = 1.2;
  roundRect(ctx, m + 8, m + 8, W - (m + 8) * 2, H - (m + 8) * 2, 16);
  ctx.stroke();
  ctx.fillStyle = 'rgba(212, 176, 106, 0.85)';
  for (const [x, y] of [[m, m], [W - m, m], [m, H - m], [W - m, H - m]] as const) {
    ctx.beginPath();
    ctx.arc(x, y, 3.2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function roundRect(
  ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function paintName(ctx: CanvasRenderingContext2D, card: TarotCard) {
  const plateH = 70;
  const y = H - 28 - plateH;
  ctx.fillStyle = 'rgba(8, 6, 14, 0.55)';
  roundRect(ctx, 36, y, W - 72, plateH, 10);
  ctx.fill();
  ctx.fillStyle = 'rgba(245, 228, 186, 0.96)';
  ctx.font = '600 36px "Songti SC", "Noto Serif SC", "Source Han Serif SC", SimSun, serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(card.name, W / 2, y + 28);
  ctx.font = '500 18px "Songti SC", "Noto Serif SC", SimSun, serif';
  ctx.fillStyle = 'rgba(212, 176, 106, 0.88)';
  const sub = card.reversed ? `${card.position} · 逆位` : `${card.position} · 正位`;
  ctx.fillText(sub, W / 2, y + 52);
}

function paintPlaceholder(ctx: CanvasRenderingContext2D, card: TarotCard) {
  const [bg, accent] = SUIT_TONE[card.suit] || SUIT_TONE[''];
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, bg);
  g.addColorStop(1, '#07060c');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.35;
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.ellipse(W / 2, H * 0.42, 118, 168, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.ellipse(W / 2, H * 0.42, 78, 110, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.fillStyle = accent;
  ctx.font = '500 28px "Songti SC", "Noto Serif SC", SimSun, serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(card.arcana === 'major' ? '大阿卡那' : '小阿卡那', W / 2, H * 0.42);
}

function canvasTexture(canvas: HTMLCanvasElement): THREE.Texture {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  tex.needsUpdate = true;
  return tex;
}

export async function loadBackTexture(url: string): Promise<THREE.Texture> {
  if (backTex) return backTex;
  if (backPending) return backPending;
  backPending = (async () => {
    const img = await loadImage(url);
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('no 2d');
    ctx.fillStyle = '#12101c';
    ctx.fillRect(0, 0, W, H);
    if (img) {
      ctx.drawImage(img, 0, 0, W, H);
    } else {
      const g = ctx.createRadialGradient(W / 2, H / 2, 20, W / 2, H / 2, 360);
      g.addColorStop(0, '#2a2440');
      g.addColorStop(1, '#0c0a14');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = 'rgba(212, 176, 106, 0.7)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, 92, 0, Math.PI * 2);
      ctx.stroke();
    }
    paintFrame(ctx);
    backTex = canvasTexture(canvas);
    return backTex;
  })();
  try {
    return await backPending;
  } finally {
    backPending = null;
  }
}

/** 装饰用真牌面：只有图，没有牌位名。和本局抽出的牌无关。 */
export async function loadArtTexture(url: string): Promise<THREE.Texture> {
  const key = `art|${url}`;
  const hit = texCache.get(key);
  if (hit) return hit;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('no 2d');
  ctx.fillStyle = '#0c0a12';
  ctx.fillRect(0, 0, W, H);
  const img = await loadImage(url);
  if (img) ctx.drawImage(img, 0, 0, W, H);
  else {
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#1a1428');
    g.addColorStop(1, '#07060c');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }
  paintFrame(ctx);
  const tex = canvasTexture(canvas);
  texCache.set(key, tex);
  return tex;
}

export async function composeFront(card: TarotCard): Promise<THREE.Texture> {
  const key = `${card.id}|${card.reversed ? 'r' : 'u'}|${card.has_art ? 'a' : 'p'}`;
  const hit = texCache.get(key);
  if (hit) return hit;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('no 2d');
  if (card.has_art && card.url) {
    const img = await loadImage(card.url);
    if (img) {
      ctx.fillStyle = '#0c0a12';
      ctx.fillRect(0, 0, W, H);
      ctx.drawImage(img, 0, 0, W, H);
    } else {
      paintPlaceholder(ctx, card);
    }
  } else {
    paintPlaceholder(ctx, card);
  }
  paintFrame(ctx);
  paintName(ctx, card);
  const tex = canvasTexture(canvas);
  texCache.set(key, tex);
  return tex;
}

export function disposeTarotTextures() {
  for (const t of texCache.values()) t.dispose();
  texCache.clear();
  backTex?.dispose();
  backTex = null;
  backPending = null;
}
