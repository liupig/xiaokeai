import { reactive } from 'vue';

export const tavernUi = reactive({ on: false });

export function openTavern() {
  tavernUi.on = true;
}

export function closeTavern() {
  tavernUi.on = false;
}
