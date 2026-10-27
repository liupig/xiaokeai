import { rememberCurrentCharacter } from '../../stores/character';

/** 桌面壳的两种窗口：舞台（整窗）和桌宠（透明小窗）。切换会重建窗口。 */

export type ShellMode = 'stage' | 'pet';

export const isPetShell = !!window.companionDesktop?.isShell
  && new URLSearchParams(location.search).get('shell') === 'pet';

if (isPetShell) document.documentElement.classList.add('is-pet');

export function setShellMode(mode: ShellMode) {
  rememberCurrentCharacter();
  return window.companionDesktop?.setShellMode?.(mode);
}
