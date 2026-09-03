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
