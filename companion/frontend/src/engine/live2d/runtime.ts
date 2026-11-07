import type { Application } from 'pixi.js';
import type { Live2DModel } from 'untitled-pixi-live2d-engine/cubism';

export type Live2DRuntime = {
  Application: typeof Application;
  Live2DModel: typeof Live2DModel;
};

declare global {
  interface Window {
    Live2DCubismCore?: unknown;
  }
}

let corePromise: Promise<void> | null = null;
let runtimePromise: Promise<Live2DRuntime> | null = null;

function loadCore(): Promise<void> {
  if (window.Live2DCubismCore) return Promise.resolve();
  if (corePromise) return corePromise;
  corePromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `${import.meta.env.BASE_URL}live2dcubismcore.min.js`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Live2D Cubism Core 加载失败'));
    document.head.appendChild(script);
  }).catch((err) => {
    corePromise = null;
    throw err;
  });
  return corePromise;
}

export function loadLive2DRuntime(): Promise<Live2DRuntime> {
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    await loadCore();
    const [pixi, live2d] = await Promise.all([
      import('pixi.js'),
      import('untitled-pixi-live2d-engine/cubism'),
    ]);
    pixi.extensions.add(live2d.Live2DPlugin);
    return {
      Application: pixi.Application,
      Live2DModel: live2d.Live2DModel,
    };
  })().catch((err) => {
    runtimePromise = null;
    throw err;
  });
  return runtimePromise;
}
