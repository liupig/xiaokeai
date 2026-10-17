import { ref } from 'vue';

/** 点过按钮或口头抽牌后才挂 Layer；默认不加载塔罗 UI / 3D。 */
export const tarotLayerOn = ref(false);
/** 牌还摊在场上（不含仅打开过 Layer）。 */
export const tarotLive = ref(false);

export function openTarotLayer() {
  tarotLayerOn.value = true;
}

export function closeTarotLayer() {
  tarotLayerOn.value = false;
  tarotLive.value = false;
}

export type TarotScreenRect = { x: number; y: number; w: number; h: number };

let hitRect: (() => TarotScreenRect | null) | null = null;
let hitOwns: ((x: number, y: number) => boolean) | null = null;

/** 牌在场上时，桌宠用这块屏幕区域接点击，并让牌上的点击不要变成拖人。 */
export function bindTarotHit(
  rect: () => TarotScreenRect | null,
  owns: (x: number, y: number) => boolean,
) {
  hitRect = rect;
  hitOwns = owns;
}

export function clearTarotHit() {
  hitRect = null;
  hitOwns = null;
}

export function tarotCardRect() {
  return hitRect?.() ?? null;
}

export function tarotPointerOwns(x: number, y: number) {
  return hitOwns?.(x, y) ?? false;
}
