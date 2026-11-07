import type { Application, Ticker } from 'pixi.js';
import type { Live2DModel } from 'untitled-pixi-live2d-engine/cubism';
import type { ModelInfo } from '../stage';
import { stage } from '../stage';
import type { CamShotId, EmotionKey, TouchZone } from '../types';
import type { StandSlot } from '../stand';
import { Live2DAvatar, type Live2DParameterMeta } from './avatar';
import { loadLive2DRuntime } from './runtime';
import {
  loadLive2DPreferences,
  saveLive2DPreferences,
  type Live2DPreferences,
} from './preferences';

const EMOTION_EXPRESSIONS: Record<Exclude<EmotionKey, 'neutral'>, string[]> = {
  happy: ['happy', 'smile', 'excited', 'blush', 'playful'],
  angry: ['angry', 'angry_face'],
  sad: ['sad', 'cry', 'gloomy'],
  relaxed: ['relaxed', 'calm', 'sleepy'],
};
const EMOTION_NAMES = new Set(Object.values(EMOTION_EXPRESSIONS).flat());

export class Live2DStage {
  avatar: Live2DAvatar | null = null;

  private host: HTMLElement | null = null;
  private app: Application | null = null;
  private appPromise: Promise<Application> | null = null;
  private model: Live2DModel | null = null;
  private modelUrl = '';
  private loadSeq = 0;
  private resizeObserver: ResizeObserver | null = null;
  private preferences: Live2DPreferences = loadLive2DPreferences('');
  private dragging: { x: number; y: number; offsetX: number; offsetY: number; moved: boolean } | null = null;
  private cameraTarget: { zoom: number; x: number; y: number } | null = null;
  private emotionExpression = '';
  private emotionSeq = 0;
  private resizeWidth = 0;
  private resizeHeight = 0;
  private readonly tick = (ticker: Ticker) => {
    this.model?.update(ticker.deltaMS);
    if (this.cameraTarget) {
      const target = this.cameraTarget;
      const blend = Math.min(1, ticker.deltaMS / 220);
      this.preferences.zoom += (target.zoom - this.preferences.zoom) * blend;
      this.preferences.offsetX += (target.x - this.preferences.offsetX) * blend;
      this.preferences.offsetY += (target.y - this.preferences.offsetY) * blend;
      if (Math.abs(target.zoom - this.preferences.zoom) < 0.005
        && Math.abs(target.x - this.preferences.offsetX) < 1
        && Math.abs(target.y - this.preferences.offsetY) < 1) {
        this.cameraTarget = null;
      }
      this.resize();
    }
  };

  init(host: HTMLElement) {
    this.host = host;
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(host);
    if (this.app) host.appendChild(this.app.canvas);
  }

  detach() {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.host = null;
  }

  private async ensureApp(): Promise<Application> {
    if (this.app) return this.app;
    if (this.appPromise) return this.appPromise;
    const host = this.host;
    if (!host) throw new Error('Live2D 舞台尚未初始化');
    this.appPromise = (async () => {
      const { Application } = await loadLive2DRuntime();
      const app = new Application();
      await app.init({
        width: Math.max(1, host.clientWidth),
        height: Math.max(1, host.clientHeight),
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        preference: 'webgl',
      });
      app.canvas.style.position = 'absolute';
      app.canvas.style.inset = '0';
      app.canvas.style.width = '100%';
      app.canvas.style.height = '100%';
      app.canvas.style.pointerEvents = 'none';
      app.canvas.dataset.renderer = 'live2d';
      app.ticker.add(this.tick);
      this.installInteraction(app.canvas);
      host.appendChild(app.canvas);
      this.app = app;
      return app;
    })().catch((err) => {
      this.appPromise = null;
      throw err;
    });
    return this.appPromise;
  }

  async loadModel(url: string): Promise<ModelInfo> {
    this.unloadModel();
    const seq = this.loadSeq;
    const app = await this.ensureApp();
    const { Live2DModel } = await loadLive2DRuntime();
    const model = await Live2DModel.from(url, {
      autoUpdate: false,
      autoHitTest: false,
      autoFocus: false,
    });
    if (seq !== this.loadSeq) {
      model.destroy();
      throw new Error('已被更新的加载取代');
    }
    this.model = model;
    this.modelUrl = url;
    stage.setExternalController(this);
    app.stage.addChild(model);
    this.avatar = new Live2DAvatar(model);
    model.internalModel.on('beforeModelUpdate', this.applyParameters);
    app.canvas.style.pointerEvents = 'auto';
    this.preferences = loadLive2DPreferences(url);
    this.preferences.expressions = this.preferences.expressions.filter((name) =>
      !EMOTION_NAMES.has(name.toLowerCase()));
    this.avatar.setGazeEnabled(this.preferences.gaze);
    for (const [id, value] of Object.entries(this.preferences.parameters)) {
      this.avatar.setParameter(id, Number(value));
    }
    for (const name of this.preferences.expressions) {
      try {
        await this.avatar.setExpressionEnabled(name, true);
      } catch (err) {
        console.warn('[live2d] 跳过无法恢复的装扮', name, err);
      }
    }
    for (const id of this.preferences.suppressedParameters) {
      this.avatar.setParameterSuppressed(id, true);
    }
    const displayInfo = (model.internalModel.settings.json as { DisplayInfo?: string }).DisplayInfo;
    if (displayInfo) {
      try {
        const response = await fetch(model.internalModel.settings.resolveURL(displayInfo));
        if (response.ok) {
          const data = await response.json() as { Parameters?: { Id: string; Name?: string }[] };
          this.avatar.setDisplayInfo(data.Parameters ?? []);
        }
      } catch { /* 没有显示名时使用参数 ID */ }
    }
    const idle = this.avatar.motionGroups.find((item) => /^(idling|idle)$/i.test(item.group));
    if (idle) void model.motion(idle.group, 0, 1).catch(() => {});
    this.resize();
    return {
      url,
      format: 'live2d',
      morphNames: this.avatar.morphNames(),
      supportsVmd: false,
    };
  }

  private readonly applyParameters = () => {
    this.avatar?.applyParameters();
  };

  private resize() {
    if (!this.host || !this.app) return;
    const width = Math.max(1, this.host.clientWidth);
    const height = Math.max(1, this.host.clientHeight);
    if (width !== this.resizeWidth || height !== this.resizeHeight) {
      this.app.renderer.resize(width, height);
      this.resizeWidth = width;
      this.resizeHeight = height;
    }
    if (!this.model) return;
    const internal = this.model.internalModel;
    const scale = Math.min(
      width / Math.max(1, internal.width) * 0.82,
      height / Math.max(1, internal.height) * 0.9,
    );
    this.model.scale.set(scale * this.preferences.zoom);
    this.model.anchor.set(0.5, 1);
    this.model.position.set(
      width / 2 + this.preferences.offsetX,
      height * 0.97 + this.preferences.offsetY,
    );
  }

  private installInteraction(canvas: HTMLCanvasElement) {
    canvas.addEventListener('pointermove', (event) => {
      if (!this.model || !this.avatar) return;
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      if (this.dragging) {
        const dx = event.clientX - this.dragging.x;
        const dy = event.clientY - this.dragging.y;
        if (Math.hypot(dx, dy) > 4) this.dragging.moved = true;
        this.preferences.offsetX = this.dragging.offsetX + dx;
        this.preferences.offsetY = this.dragging.offsetY + dy;
        this.resize();
        return;
      }
      this.avatar.setGaze(
        (x / Math.max(1, rect.width) - 0.5) * 2,
        (0.5 - y / Math.max(1, rect.height)) * 2,
      );
    });
    canvas.addEventListener('pointerleave', () => {
      this.avatar?.setGaze(0, 0);
      this.dragging = null;
    });
    canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || !this.model) return;
      this.dragging = {
        x: event.clientX,
        y: event.clientY,
        offsetX: this.preferences.offsetX,
        offsetY: this.preferences.offsetY,
        moved: false,
      };
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    canvas.addEventListener('pointerup', (event) => {
      const drag = this.dragging;
      this.dragging = null;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      this.saveView();
      if (drag && !drag.moved) this.playTouchAt(event.clientX, event.clientY);
    });
    canvas.addEventListener('pointercancel', () => {
      this.dragging = null;
      this.saveView();
    });
    canvas.addEventListener('wheel', (event) => {
      if (!this.model) return;
      event.preventDefault();
      this.preferences.zoom = Math.min(3, Math.max(0.1,
        this.preferences.zoom * Math.exp(-event.deltaY * 0.001)));
      this.resize();
      this.saveView();
    }, { passive: false });
  }

  private saveView() {
    if (!this.modelUrl) return;
    this.preferences = saveLive2DPreferences(this.modelUrl, {
      zoom: this.preferences.zoom,
      offsetX: this.preferences.offsetX,
      offsetY: this.preferences.offsetY,
    });
  }

  get view() {
    return {
      zoom: this.preferences.zoom,
      offsetX: this.preferences.offsetX,
      offsetY: this.preferences.offsetY,
      gaze: this.preferences.gaze,
    };
  }

  resetView() {
    this.cameraTarget = null;
    this.preferences.zoom = 0.3;
    this.preferences.offsetX = 0;
    this.preferences.offsetY = 0;
    this.resize();
    this.saveView();
  }

  setZoom(zoom: number) {
    this.cameraTarget = null;
    this.preferences.zoom = Math.min(3, Math.max(0.1, zoom));
    this.resize();
    this.saveView();
  }

  playShot(_id: CamShotId) {
    this.cameraTarget = null;
  }

  goToStand(slot: StandSlot) {
    if (!this.host) return;
    const x = slot === 'left' ? -this.host.clientWidth * 0.2
      : slot === 'right' ? this.host.clientWidth * 0.2 : 0;
    this.cameraTarget = { zoom: this.preferences.zoom, x, y: this.preferences.offsetY };
    this.preferences = saveLive2DPreferences(this.modelUrl, {
      zoom: this.preferences.zoom, offsetX: x, offsetY: this.preferences.offsetY,
    });
  }

  setGazeEnabled(enabled: boolean) {
    this.avatar?.setGazeEnabled(enabled);
    this.preferences.gaze = enabled;
    if (this.modelUrl) this.preferences = saveLive2DPreferences(this.modelUrl, { gaze: enabled });
  }

  probeTouch(clientX: number, clientY: number): TouchZone | null {
    if (!this.model || !this.avatar || !this.app) return null;
    const rect = this.app.canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const hits = this.model.hitTest(x, y);
    for (const hit of hits) {
      const name = hit.toLowerCase();
      if (name.includes('head') || name.includes('face')) return 'head';
      if (name.includes('body') || name.includes('chest')) return 'chest';
      if (name.includes('hand') || name.includes('arm')) return 'hand';
      if (name.includes('waist') || name.includes('leg')) return 'waist';
    }
    const bounds = this.model.getBounds();
    if (bounds.width <= 0 || bounds.height <= 0) return null;
    return this.avatar.probeTouch(x - bounds.x, y - bounds.y, bounds.width, bounds.height);
  }

  playTouchAt(clientX: number, clientY: number): boolean {
    return this.probeTouch(clientX, clientY) ? this.avatar?.playTouch() ?? false : false;
  }

  playMotion(group: string, index: number): boolean {
    return this.avatar?.playNativeMotion(group, index) ?? false;
  }

  playAction(name: string): boolean {
    return this.avatar?.playAction(name) ?? false;
  }

  stopMotion() {
    this.avatar?.stopNativeMotion();
    this.model?.stopMotions();
    if (this.avatar) this.avatar.actionActive = false;
  }

  get motionGroups() {
    return this.avatar?.motionGroups ?? [];
  }

  parameterMeta(): Live2DParameterMeta[] {
    return this.avatar?.parameterMeta() ?? [];
  }

  setParameter(id: string, value: number) {
    this.avatar?.setParameter(id, value);
    if (!this.modelUrl) return;
    const parameters = { ...this.preferences.parameters, [id]: value };
    this.preferences = saveLive2DPreferences(this.modelUrl, { parameters });
  }

  resetParameter(id: string) {
    this.avatar?.resetParameter(id);
    if (!this.modelUrl) return;
    const parameters = { ...this.preferences.parameters };
    delete parameters[id];
    this.preferences = saveLive2DPreferences(this.modelUrl, { parameters });
  }

  resetParameters() {
    for (const id of this.avatar?.suppressedParameters ?? []) this.avatar?.setParameterSuppressed(id, false);
    for (const parameter of this.parameterMeta()) this.avatar?.resetParameter(parameter.id);
    if (this.modelUrl) {
      this.preferences = saveLive2DPreferences(this.modelUrl, { parameters: {}, suppressedParameters: [] });
    }
  }

  get presets() {
    return Object.keys(this.preferences.presets);
  }

  savePreset(name: string): boolean {
    const key = name.trim().slice(0, 32);
    if (!key || !this.modelUrl) return false;
    const parameters = Object.fromEntries(this.parameterMeta().map((item) => [item.id, item.value]));
    const presets = {
      ...this.preferences.presets,
      [key]: {
        parameters,
        expressions: this.activeExpressions.filter((item) => item !== this.emotionExpression),
      },
    };
    this.preferences = saveLive2DPreferences(this.modelUrl, { presets });
    return true;
  }

  deletePreset(name: string) {
    const presets = { ...this.preferences.presets };
    delete presets[name];
    if (this.modelUrl) this.preferences = saveLive2DPreferences(this.modelUrl, { presets });
  }

  async applyPreset(name: string): Promise<boolean> {
    const preset = this.preferences.presets[name];
    if (!preset || !this.avatar) return false;
    for (const expression of this.activeExpressions) {
      await this.avatar.setExpressionEnabled(expression, false);
    }
    this.resetParameters();
    for (const [id, value] of Object.entries(preset.parameters)) {
      this.setParameter(id, value);
    }
    for (const expression of preset.expressions) {
      await this.setExpressionEnabled(expression, true);
    }
    return true;
  }

  get capabilities() {
    return {
      motions: this.motionGroups.flatMap((item) =>
        Array.from({ length: item.count }, (_, index) => ({ group: item.group, index }))),
      expressions: this.expressionNames,
      activeExpressions: this.activeExpressions,
      parameters: this.parameterMeta().map((item) => ({
        id: item.id, min: item.min, max: item.max,
      })),
      presets: this.presets,
    };
  }

  setEmotion(emotion: EmotionKey, intensity: number) {
    const aliases = emotion === 'neutral' ? [] : EMOTION_EXPRESSIONS[emotion];
    const names = this.expressionNames;
    const next = intensity > 0.03
      ? aliases.map((alias) => names.find((name) => name.toLowerCase() === alias)).find(Boolean) ?? ''
      : '';
    if (next === this.emotionExpression) return;
    const previous = this.emotionExpression;
    const seq = ++this.emotionSeq;
    this.emotionExpression = next;
    void (async () => {
      if (previous) await this.setExpressionEnabled(previous, false, false);
      if (seq === this.emotionSeq && next) await this.setExpressionEnabled(next, true, false);
    })().catch(() => {});
  }

  async setExpressionEnabled(name: string, enabled: boolean, persist = true): Promise<void> {
    if (!this.avatar) return;
    if (name.toLowerCase() === 'glasses') {
      if (!enabled) {
        await this.avatar.clearExpressionCategory(/glasses|sunglasses/i);
      } else {
        const glasses = this.expressionNames.filter((item) => /glasses|sunglasses/i.test(item));
        const selected = glasses.find((item) => this.avatar?.activeExpressions.includes(item))
          ?? glasses.find((item) => !/sunglasses/i.test(item)) ?? glasses[0];
        if (!selected) return;
        name = selected;
        await this.avatar.setExpressionEnabled(name, true);
      }
    } else {
      await this.avatar.setExpressionEnabled(name, enabled);
    }
    if (!enabled) this.avatar.clearNativeExpressions();
    const exclusive = /glasses|sunglasses/i.test(name);
    if (enabled && exclusive) {
      for (const active of this.avatar.activeExpressions) {
        if (active !== name && /glasses|sunglasses/i.test(active)) {
          await this.avatar.setExpressionEnabled(active, false);
        }
      }
    }
    if (persist && this.modelUrl) {
      this.preferences = saveLive2DPreferences(this.modelUrl, {
        expressions: this.avatar.activeExpressions.filter((item) => item !== this.emotionExpression),
        suppressedParameters: this.avatar.suppressedParameters,
      });
    }
  }

  get activeExpressions(): string[] {
    return this.avatar?.activeExpressions ?? [];
  }

  get expressionNames(): string[] {
    const settings = this.model?.internalModel.settings.json as {
      FileReferences?: { Expressions?: { Name?: string }[] };
    } | undefined;
    return (settings?.FileReferences?.Expressions ?? [])
      .map((item) => item.Name || '')
      .filter(Boolean);
  }

  unloadModel() {
    ++this.loadSeq;
    ++this.emotionSeq;
    this.emotionExpression = '';
    if (this.model) {
      this.model.internalModel.off('beforeModelUpdate', this.applyParameters);
      this.model.removeFromParent();
      this.model.destroy();
      this.model = null;
    }
    if (this.app) this.app.canvas.style.pointerEvents = 'none';
    this.avatar?.reset();
    this.avatar = null;
    stage.setExternalController(null);
    this.modelUrl = '';
    this.dragging = null;
    this.app?.render();
  }

  dispose() {
    this.unloadModel();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.app) {
      this.app.ticker.remove(this.tick);
      this.app.destroy(true);
      this.app = null;
    }
    this.appPromise = null;
    this.host = null;
  }
}

export const live2dStage = new Live2DStage();
