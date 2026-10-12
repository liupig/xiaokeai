import { stage } from '../../engine/stage';
import { speechPlayer } from '../voice/tts';

/**
 * 桌宠点击：主进程按身体胶囊和对话条决定穿透。
 * 人身上的点击留给她，其余落到桌面。按住拖动时窗口一直接着鼠标。
 */
export function installPetPointer() {
  const desktop = window.companionDesktop;
  if (!desktop?.setPetHitRegion) return () => {};

  let dragging = false;
  let pressed = false;
  let downX = 0;
  let downY = 0;
  let stopped = false;
  let raf = 0;
  let lastKey = '';

  const paintCursor = (grab: boolean) => {
    document.body.style.cursor = dragging ? 'grabbing' : grab ? 'grab' : '';
  };

  const chromeRects = () => {
    const rects: { x: number; y: number; w: number; h: number }[] = [];
    document.querySelectorAll<HTMLElement>('[data-pet-hit]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      rects.push({
        x: Math.round(r.left),
        y: Math.round(r.top),
        w: Math.round(r.width),
        h: Math.round(r.height),
      });
    });
    return rects;
  };

  const publish = () => {
    const body = stage.petHitBody();
    const rects = chromeRects();
    const dock = document.querySelector<HTMLElement>('.pet-dock');
    const focus = !!dock && dock.getClientRects().length > 0;
    const region = {
      ax: body ? Math.round(body.ax) : 0,
      ay: body ? Math.round(body.ay) : 0,
      bx: body ? Math.round(body.bx) : 0,
      by: body ? Math.round(body.by) : 0,
      r: body ? Math.round(body.r) : 0,
      rects,
      pressed: pressed || dragging,
      focus,
    };
    const key = JSON.stringify(region);
    if (key === lastKey) return;
    lastKey = key;
    desktop.setPetHitRegion?.(region);
  };

  const endPress = () => {
    if (pressed && !dragging) {
      window.dispatchEvent(new CustomEvent('xiaoke-pet-ui'));
      stage.petReveal();
    }
    if (dragging) stage.petRelease();
    pressed = false;
    dragging = false;
    publish();
  };

  const overChrome = (x: number, y: number) => {
    const el = document.elementFromPoint(x, y);
    return !!el?.closest('[data-pet-hit]');
  };

  const onMove = (e: MouseEvent) => {
    if (pressed && (e.buttons & 1) === 0) endPress();
    if (pressed && !dragging) {
      const dist = Math.hypot(e.clientX - downX, e.clientY - downY);
      if (dist > 8) {
        dragging = true;
        stage.petGrab(downX, downY);
        publish();
      }
    }
    if (dragging) {
      stage.petSlide(e.clientX, e.clientY);
      paintCursor(true);
      return;
    }
    paintCursor(!overChrome(e.clientX, e.clientY) && stage.hitsAvatar(e.clientX, e.clientY));
  };

  const onDown = (e: MouseEvent) => {
    if (e.button !== 0 || pressed) return;
    if (overChrome(e.clientX, e.clientY)) return;
    if (!stage.hitsAvatar(e.clientX, e.clientY)) return;
    e.preventDefault();
    speechPlayer.unlock();
    pressed = true;
    downX = e.clientX;
    downY = e.clientY;
    paintCursor(true);
    publish();
  };

  const onUp = () => {
    if (!pressed && !dragging) return;
    endPress();
    paintCursor(false);
  };

  const loop = () => {
    if (stopped) return;
    publish();
    raf = requestAnimationFrame(loop);
  };

  window.addEventListener('mousemove', onMove);
  window.addEventListener('mousedown', onDown);
  window.addEventListener('mouseup', onUp);
  window.addEventListener('blur', onUp);
  loop();

  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mousedown', onDown);
    window.removeEventListener('mouseup', onUp);
    window.removeEventListener('blur', onUp);
    document.body.style.cursor = '';
  };
}
