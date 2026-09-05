import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { MMDLoader, MMDPhysics } from 'three-stdlib';
import type { VRM } from '@pixiv/three-vrm';

import { makeMeshAvatar } from './avatar/mesh';
import { BgmPlayer } from './bgm';
import { CameraRig, type IdleMoveKind } from './camera';
import { PerformanceDirector } from './director';
import { ExpressionController } from './expression';
import { IdleAnimator } from './idle';
import { Lipsync } from './lipsync';
import { GLB_BONES, GLB_MORPHS, MMD_BONES, MMD_MORPHS } from './mappings';
import { MotionPlayer } from './motion';
import { StandController, type StandSlot } from './stand';
import type { ActionKey, Avatar, CamPreset, CamShotId, EmotionKey, QualityOptions } from './types';

export type { StandSlot };

const PHY_STEP = 1 / 65; // MMDPhysics 内部最小步长
/** 1080p @ 2x；更高分辨率不再叠 DPR，避免 4K 开 2x 吃掉上百 MB 显存 */
const PIXEL_BUDGET = 1920 * 1080 * 4;

function fitPixelRatio(cap: number, w: number, h: number) {
  const want = Math.min(window.devicePixelRatio || 1, Math.max(1, cap || 1));
  const area = Math.max(1, w * h);
  return Math.max(1, Math.min(want, Math.sqrt(PIXEL_BUDGET / area)));
}

function disposeGpu(root: THREE.Object3D) {
  const seen = new Set<THREE.Texture>();
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry?.dispose();
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) {
      if (!mat) continue;
      for (const v of Object.values(mat)) {
        const tex = v as THREE.Texture | undefined;
        if (tex && tex.isTexture && !seen.has(tex)) {
          seen.add(tex);
          tex.dispose();
        }
      }
      mat.dispose();
    }
  });
}

export interface ModelInfo {
  url: string;
  format: string;
  morphNames: string[];
  supportsVmd: boolean;
}

/** 舞台插件：动捕 / 塔罗等通过 use() 接入，舞台本身不依赖具体实现。 */
export interface StagePlugin {
  id?: string;
  /** PMX：摆臂 / 物理之前的 T-pose。 */
  onTPose?(root: THREE.Object3D, vrm: VRM | null): void;
  onAvatarReady?(root: THREE.Object3D, avatar: Avatar, vrm: VRM | null): void;
  onAvatarUnload?(): void;
  onMotionWillPlay?(): void;
  /** 每帧：只动插件自己的物体，不要驱动骨骼。 */
  onFrame?(dt: number): void;
  /** 返回 true 表示本帧骨骼已由插件驱动，跳过闲置 / VMD。 */
  applyPose?(): boolean;
}

/**
 * 3D 舞台门面：渲染循环、模型加载、物理、各控制器的统一入口。
 * UI 层只与本类交互，不直接触碰 three.js 对象。
 */
export class Stage {
  readonly expr = new ExpressionController();
  readonly idle = new IdleAnimator();
  readonly lipsync = new Lipsync();
  readonly motion = new MotionPlayer();
  readonly bgm = new BgmPlayer();
  readonly stand = new StandController();
  private bgmGen = 0;
  /** 舞+歌正在播：说话 / 走路 / 闲时动作不许把歌掐掉 */
  private _danceLive = false;

  get danceLive() {
    return this._danceLive;
  }
  /** 当前站位走动是否由本层发起的走路 VMD（到位后只停这一条） */
  private walkLocUrl = '';
  private walkLocActive = false;
  /** 表演导演：状态机 + 情绪衰减 + 视线 + 语音微表演 + 空闲丰富化 */
  readonly director = new PerformanceDirector({
    expr: this.expr, lipsync: this.lipsync, motion: this.motion,
  });

  constructor() {
    this.director.playIdleMotion = (url) => {
      if (this._danceLive) return;
      void this.playMotion(url, { once: true });
    };
  }

  onModelReady: ((info: ModelInfo) => void) | null = null;

  private renderer!: THREE.WebGLRenderer;
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private camRig!: CameraRig;
  private keyLight!: THREE.DirectionalLight;
  private rimLight!: THREE.DirectionalLight;
  private ambient!: THREE.AmbientLight;
  private ground!: THREE.Mesh<THREE.CircleGeometry, THREE.MeshStandardMaterial>;
  private platform: THREE.Group | null = null;
  private platformSpin: { obj: THREE.Object3D; speed: number }[] = [];
  private platformOpts = {
    show: true, color: '#232342', glow: '#5b5bd6', style: 'classic',
    texture: '', opacity: 1,
  };
  /** 台面贴图缓存（跨重建复用，卸载时不随 platform 一起 dispose） */
  private platformTexCache = new Map<string, THREE.Texture>();
  private clock = new THREE.Clock();

  private avatar: Avatar | null = null;
  private modelRoot: THREE.Object3D | null = null;
  private vrm: VRM | null = null;
  private physics: MMDPhysics | null = null;
  private physicsHeld: MMDPhysics | null = null;
  private physicsGen = 0;
  private modelKind = '';
  private phyAcc = 0;
  private disposed = false;
  private loadSeq = 0;
  private bgSeq = 0;
  private bgUrl = '';
  private bgTex: THREE.Texture | null = null;
  private plugins: StagePlugin[] = [];
  private ammoReady: Promise<unknown> | null = null;
  private pageVisible = true;
  private host: HTMLElement | null = null;
  private onResize: (() => void) | null = null;
  private onVis: (() => void) | null = null;

  private quality: QualityOptions = { physics: false, pixelRatioCap: 2, lightLevel: 1 };
  // 当前模型类型的灯光基准值，乘以 lightLevel 得到实际强度
  private lightBase = { key: 1.8, rim: 1.0, amb: 0.9 };
  /** 景别白名单：塔罗等玩法期间只许这些身位，空则不限制 */
  camSizeLock: CamShotId[] | null = null;

  use(plugin: StagePlugin) {
    if (plugin.id) this.plugins = this.plugins.filter((p) => p.id !== plugin.id);
    this.plugins.push(plugin);
  }

  unuse(id: string) {
    const gone = this.plugins.filter((p) => p.id === id);
    this.plugins = this.plugins.filter((p) => p.id !== id);
    for (const p of gone) p.onAvatarUnload?.();
  }

  private emit<K extends Exclude<keyof StagePlugin, 'id'>>(
    name: K,
    ...args: StagePlugin[K] extends ((...a: infer A) => unknown) | undefined ? A : never
  ) {
    for (const p of this.plugins) {
      const fn = p[name] as ((...a: typeof args) => unknown) | undefined;
      if (fn) fn(...args);
    }
  }

  private applyPluginPose(): boolean {
    for (const p of this.plugins) {
      if (p.applyPose?.()) return true;
    }
    return false;
  }

  init(container: HTMLElement) {
    this.host = container;
    const dpr = fitPixelRatio(
      this.quality.pixelRatioCap, container.clientWidth, container.clientHeight);
    this.renderer = new THREE.WebGLRenderer({
      antialias: true, preserveDrawingBuffer: false, stencil: false,
    });
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x141420);
    this.scene.fog = new THREE.Fog(0x141420, 6, 14);

    this.camera = new THREE.PerspectiveCamera(
      30, container.clientWidth / container.clientHeight, 0.1, 50);
    this.camera.position.set(0, 1.3, 3.6);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0.95, 0);
    this.controls.minDistance = 0.35;
    this.controls.maxDistance = 8;

    this.camRig = new CameraRig(this.camera, this.controls);

    // 灯光：主光 + 环境光 + 蓝色轮廓光
    // 环境光用中性白，避免给贴图罩上色偏；氛围感交给轮廓光
    this.keyLight = new THREE.DirectionalLight(0xffffff, 1.8);
    this.keyLight.position.set(1.2, 2.2, 2.5);
    this.scene.add(this.keyLight);
    this.ambient = new THREE.AmbientLight(0xffffff, 0.9);
    this.scene.add(this.ambient);
    this.rimLight = new THREE.DirectionalLight(0x7788ff, 1.0);
    this.rimLight.position.set(-2, 1.6, -2.5);
    this.scene.add(this.rimLight);

    // 远景地面（纯色背景模式下与背景色融合），下沉到舞台底座下沿
    this.ground = new THREE.Mesh(
      new THREE.CircleGeometry(4.5, 64),
      new THREE.MeshStandardMaterial({ color: 0x232342, roughness: 0.95 })
    );
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.position.y = -0.08;
    this.scene.add(this.ground);

    this.buildPlatform();

    this.onResize = () => {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.applyPixelRatio();
      this.renderer.setSize(w, h);
    };
    window.addEventListener('resize', this.onResize);
    this.onVis = () => {
      const vis = document.visibilityState !== 'hidden';
      if (vis && !this.pageVisible) {
        this.pageVisible = true;
        this.clock.getDelta();
        this.animate();
      } else {
        this.pageVisible = vis;
      }
    };
    document.addEventListener('visibilitychange', this.onVis);

    this.animate();
  }

  setQuality(opts: Partial<QualityOptions>) {
    const wantPhysics = opts.physics;
    Object.assign(this.quality, opts);
    this.applyPixelRatio();
    this.applyLights();
    if (wantPhysics === false) {
      this.detachPhysics();
    } else if (wantPhysics === true) {
      void this.attachPhysics();
    }
  }

  private applyPixelRatio() {
    if (!this.renderer || !this.host) return;
    const w = this.host.clientWidth || window.innerWidth;
    const h = this.host.clientHeight || window.innerHeight;
    this.renderer.setPixelRatio(fitPixelRatio(this.quality.pixelRatioCap, w, h));
  }

  private applyLights() {
    if (!this.keyLight) return;
    const k = this.quality.lightLevel || 1;
    this.keyLight.intensity = this.lightBase.key * k;
    this.rimLight.intensity = this.lightBase.rim * k;
    this.ambient.intensity = this.lightBase.amb * k;
  }

  /** 配置舞台底座：显隐、台面颜色、发光环颜色、风格、台面贴图、不透明度。改任何一项都整体重建（几何量很小） */
  setStagePlatform(opts: {
    show?: boolean; color?: string; glow?: string; style?: string;
    texture?: string; opacity?: number;
  }) {
    Object.assign(this.platformOpts, opts);
    if (this.scene) this.buildPlatform();
  }

  /** 取台面贴图（带缓存；three 会在图片加载完成后自动刷新材质） */
  private getPlatformTexture(url: string): THREE.Texture {
    let tex = this.platformTexCache.get(url);
    if (!tex) {
      tex = new THREE.TextureLoader().load(url);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      this.platformTexCache.set(url, tex);
    }
    return tex;
  }

  private disposePlatform() {
    if (!this.platform) return;
    const cached = new Set(this.platformTexCache.values());
    this.platform.traverse((o: any) => {
      o.geometry?.dispose?.();
      const m = o.material;
      const kill = (x: any) => {
        if (x.map && !cached.has(x.map)) x.map.dispose?.();
        x.dispose?.();
      };
      if (Array.isArray(m)) m.forEach(kill);
      else if (m) kill(m);
    });
    this.scene.remove(this.platform);
    this.platform = null;
    this.platformSpin = [];
  }

  /**
   * 圆形舞台底座：10 种风格。台面上沿统一在 y=0（角色脚底），
   * 部分风格带缓慢旋转的装饰元素（见 platformSpin）。
   */
  private buildPlatform() {
    this.disposePlatform();
    const g = new THREE.Group();
    this.platform = g;
    g.visible = this.platformOpts.show;

    const base = new THREE.Color(this.platformOpts.color);
    const glow = new THREE.Color(this.platformOpts.glow);
    // 整体不透明度：<1 时所有主体/发光材质都按比例变透明，让底座融进背景
    const OP = Math.min(1, Math.max(0.1, this.platformOpts.opacity ?? 1));
    const fade = (m: THREE.Material, k = 1) => {
      if (OP < 1) { m.transparent = true; m.opacity = OP * k; }
      return m;
    };
    const baseMat = (rough = 0.55, metal = 0.25, color: THREE.Color = base) =>
      fade(new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal })) as THREE.MeshStandardMaterial;
    const glowMat = () => fade(new THREE.MeshBasicMaterial({ color: glow })) as THREE.MeshBasicMaterial;
    const haloMat = (opacity = 0.22) => new THREE.MeshBasicMaterial({
      color: glow, transparent: true, opacity: opacity * OP,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    });
    // 台面贴图材质（未设置贴图时为 null）
    const topTex = this.platformOpts.texture ? this.getPlatformTexture(this.platformOpts.texture) : null;
    const topMat = (rough = 0.5, metal = 0.15) => topTex
      ? fade(new THREE.MeshStandardMaterial({ map: topTex, roughness: rough, metalness: metal })) as THREE.MeshStandardMaterial
      : null;
    // 台面圆盘：上沿在 y=0。textured=true 且设置了贴图时，顶面贴图、侧/底保持主体材质
    const disc = (rTop: number, rBottom: number, h: number, mat: THREE.Material,
                  segments = 96, topY = 0, textured = false) => {
      const top = textured ? topMat() : null;
      const material = top ? [mat, top, mat] : mat;
      const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBottom, h, segments), material as any);
      m.position.y = topY - h / 2;
      g.add(m);
      return m;
    };
    // 平放的发光圆环（大半径 r、管径 tube）
    const rim = (r: number, tube = 0.014, y = -0.004, radialSegments = 128) => {
      const m = new THREE.Mesh(new THREE.TorusGeometry(r, tube, 12, radialSegments), glowMat());
      m.rotation.x = -Math.PI / 2;
      m.position.y = y;
      g.add(m);
      return m;
    };
    // 地面光晕环
    const halo = (r0: number, r1: number, opacity = 0.22) => {
      const m = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 96), haloMat(opacity));
      m.rotation.x = -Math.PI / 2;
      m.position.y = -0.075;
      g.add(m);
      return m;
    };
    const spin = (obj: THREE.Object3D, speed: number) => this.platformSpin.push({ obj, speed });

    switch (this.platformOpts.style) {
      case 'double': { // 双层舞台：大小两层圆台
        disc(1.25, 1.3, 0.07, baseMat(), 96, 0, true);
        disc(1.85, 1.9, 0.05, baseMat(0.7, 0.15), 96, -0.07);
        rim(1.3);
        rim(1.9, 0.012, -0.073);
        halo(1.95, 2.4);
        this.stand.setRadius(1.25);
        break;
      }
      case 'magic': { // 魔法阵：薄盘 + 旋转的符文刻度与三角环
        disc(1.6, 1.6, 0.02, baseMat(0.8, 0.05), 96, 0, true);
        rim(1.55, 0.012, -0.002);
        const inner = rim(1.05, 0.01, -0.002);
        spin(inner, 0.3);
        const runes = new THREE.Group();
        for (let i = 0; i < 16; i++) {
          const tick = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.006, 0.035), glowMat());
          const a = (i / 16) * Math.PI * 2;
          tick.position.set(Math.cos(a) * 1.3, 0.004, Math.sin(a) * 1.3);
          tick.rotation.y = -a;
          runes.add(tick);
        }
        g.add(runes);
        spin(runes, -0.2);
        const tri = new THREE.Mesh(new THREE.RingGeometry(1.22, 1.26, 3), haloMat(0.5));
        tri.rotation.x = -Math.PI / 2;
        tri.position.y = 0.002;
        g.add(tri);
        spin(tri, 0.15);
        halo(1.62, 2.1);
        this.stand.setRadius(1.6);
        break;
      }
      case 'crystal': { // 水晶棱台：六棱柱 + 六边形发光棱线
        const m = disc(1.45, 1.65, 0.14, new THREE.MeshStandardMaterial({
          color: base, roughness: 0.15, metalness: 0.1, transparent: true, opacity: 0.92 * OP,
        }), 6, 0, true);
        m.rotation.y = Math.PI / 6;
        const hex = rim(1.58, 0.015, -0.004, 6);
        hex.rotation.z = Math.PI / 6;
        halo(1.7, 2.15);
        this.stand.setRadius(1.45);
        break;
      }
      case 'tech': { // 科幻光环:金属盘 + 同心环与旋转刻度
        disc(1.6, 1.65, 0.06, baseMat(0.3, 0.6), 96, 0, true);
        rim(1.6, 0.012, -0.002);
        for (const [r0, r1] of [[1.15, 1.19], [0.35, 0.38]] as const) {
          const ring = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 96), glowMat());
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = 0.002;
          g.add(ring);
        }
        const ticks = new THREE.Group();
        for (let i = 0; i < 24; i++) {
          const tick = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.004, 0.1), glowMat());
          const a = (i / 24) * Math.PI * 2;
          tick.position.set(Math.cos(a) * 1.4, 0.003, Math.sin(a) * 1.4);
          tick.rotation.y = -a;
          ticks.add(tick);
        }
        g.add(ticks);
        spin(ticks, 0.25);
        halo(1.68, 2.1);
        this.stand.setRadius(1.6);
        break;
      }
      case 'lotus': { // 莲花宝座：中心台 + 两圈花瓣
        disc(1.15, 1.25, 0.09, baseMat(0.5, 0.15), 96, 0, true);
        const petalMat = baseMat(0.45, 0.1, base.clone().lerp(new THREE.Color(0xffffff), 0.28));
        const addPetals = (count: number, r: number, y: number, tilt: number, scale: number) => {
          for (let i = 0; i < count; i++) {
            const petal = new THREE.Mesh(new THREE.SphereGeometry(0.5, 20, 14), petalMat);
            petal.scale.set(scale, 0.12, 0.5 * scale);
            const a = (i / count) * Math.PI * 2;
            petal.position.set(Math.cos(a) * r, y, Math.sin(a) * r);
            petal.rotation.y = -a + Math.PI / 2;
            petal.rotation.x = tilt;
            g.add(petal);
          }
        };
        addPetals(12, 1.32, -0.05, 0.28, 0.52);
        addPetals(8, 1.05, -0.02, 0.5, 0.45);
        rim(1.2, 0.012);
        halo(1.55, 2.0);
        this.stand.setRadius(1.15);
        break;
      }
      case 'orbit': { // 星环轨道：中心盘 + 两条倾斜旋转的光环
        disc(1.35, 1.4, 0.07, baseMat(), 96, 0, true);
        rim(1.35);
        for (const [tiltZ, speed] of [[0.18, 0.45], [-0.14, -0.3]] as const) {
          const wrap = new THREE.Group();
          const ring = new THREE.Mesh(new THREE.TorusGeometry(1.85, 0.012, 10, 128), glowMat());
          ring.rotation.x = -Math.PI / 2;
          wrap.add(ring);
          wrap.rotation.z = tiltZ;
          wrap.position.y = 0.15;
          g.add(wrap);
          spin(wrap, speed);
        }
        halo(1.45, 1.9);
        this.stand.setRadius(1.35);
        break;
      }
      case 'minimal': { // 极简光环：超薄暗盘 + 一圈细光环
        disc(1.5, 1.5, 0.015, baseMat(0.85, 0.05), 96, 0, true);
        rim(1.5, 0.01, -0.003);
        halo(1.55, 2.05, 0.15);
        this.stand.setRadius(1.5);
        break;
      }
      case 'vinyl': { // 黑胶唱片：缓慢旋转的盘面 + 音纹 + 中心标签
        const record = new THREE.Group();
        const bodyTop = topMat(0.35, 0.2);
        const body = new THREE.Mesh(
          new THREE.CylinderGeometry(1.6, 1.6, 0.05, 96),
          bodyTop ? [baseMat(0.35, 0.2), bodyTop, baseMat(0.35, 0.2)] : baseMat(0.35, 0.2));
        body.position.y = -0.025;
        record.add(body);
        const grooveMat = new THREE.MeshBasicMaterial({
          color: 0x000000, transparent: true, opacity: 0.45, depthWrite: false,
        });
        for (const r of [0.75, 0.95, 1.15, 1.3, 1.45]) {
          const groove = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.015, 96), grooveMat);
          groove.rotation.x = -Math.PI / 2;
          groove.position.y = 0.002;
          record.add(groove);
        }
        const label = new THREE.Mesh(
          new THREE.CylinderGeometry(0.5, 0.5, 0.054, 48), baseMat(0.6, 0, glow));
        label.position.y = -0.024;
        record.add(label);
        g.add(record);
        spin(record, 0.6);
        rim(1.62, 0.012, -0.002);
        halo(1.68, 2.1);
        this.stand.setRadius(1.6);
        break;
      }
      case 'disco': { // 迪斯科舞池：棋盘格台面（台面色 × 发光色）；设置了贴图时优先用贴图
        let top = topMat(0.4, 0.1);
        if (!top) {
          const canvas = document.createElement('canvas');
          canvas.width = canvas.height = 256;
          const ctx = canvas.getContext('2d')!;
          const c1 = '#' + base.getHexString();
          const c2 = '#' + glow.getHexString();
          for (let i = 0; i < 8; i++) {
            for (let j = 0; j < 8; j++) {
              ctx.fillStyle = (i + j) % 2 ? c1 : c2;
              ctx.fillRect(i * 32, j * 32, 32, 32);
            }
          }
          const tex = new THREE.CanvasTexture(canvas);
          tex.colorSpace = THREE.SRGBColorSpace;
          top = fade(new THREE.MeshStandardMaterial({
            map: tex, roughness: 0.4, metalness: 0.1,
          })) as THREE.MeshStandardMaterial;
        }
        const floor = new THREE.Mesh(
          new THREE.CylinderGeometry(1.6, 1.65, 0.06, 48), [baseMat(), top, baseMat()]);
        floor.position.y = -0.03;
        g.add(floor);
        rim(1.62, 0.012, -0.002);
        halo(1.68, 2.15);
        this.stand.setRadius(1.6);
        break;
      }
      default: { // classic 经典圆盘
        disc(1.6, 1.66, 0.08, baseMat(), 96, 0, true);
        rim(1.6);
        halo(1.63, 2.4);
        this.stand.setRadius(1.6);
        break;
      }
    }

    this.scene.add(g);
  }

  /**
   * 更换背景：纯色 或 图片（预设场景/自定义 dataURL）。
   * 图片模式关闭景深雾、隐藏远景地面，只保留圆形舞台底座悬浮在场景前。
   */
  setBackground(color: string, imageUrl?: string | null) {
    if (!this.scene) return;
    const url = imageUrl || '';
    if (url) {
      if (url === this.bgUrl) return;
      this.bgUrl = url;
      const seq = ++this.bgSeq;
      new THREE.TextureLoader().load(url, (tex) => {
        if (seq !== this.bgSeq) {
          tex.dispose();
          return;
        }
        tex.colorSpace = THREE.SRGBColorSpace;
        this.dropBackgroundTex();
        this.bgTex = tex;
        this.scene.background = tex;
        this.scene.fog = null;
        this.ground.visible = false;
      });
      return;
    }
    this.bgUrl = '';
    ++this.bgSeq;
    this.dropBackgroundTex();
    const c = new THREE.Color(color || '#141420');
    this.scene.background = c;
    this.scene.fog = new THREE.Fog(c, 6, 14);
    // 地面颜色跟随背景：稍微提亮一点做出台面层次
    this.ground.visible = true;
    this.ground.material.color.copy(c).lerp(new THREE.Color(0xffffff), 0.08);
  }

  private dropBackgroundTex() {
    if (!this.bgTex) return;
    if (this.scene?.background === this.bgTex) this.scene.background = null;
    this.bgTex.dispose();
    this.bgTex = null;
  }

  /** 加载模型（.pmx / .vrm / .glb），自动卸载旧模型 */
  async loadModel(url: string): Promise<ModelInfo> {
    const seq = ++this.loadSeq;
    const ext = url.toLowerCase().split('?')[0].split('.').pop() ?? '';
    this.unloadModel();

    if (ext === 'pmx') {
      const manager = new THREE.LoadingManager();
      manager.setURLModifier((u) => {
        if (!u || u.startsWith('data:')) return u;
        const hash = u.indexOf('#');
        const query = u.indexOf('?');
        let cut = u.length;
        if (hash >= 0) cut = Math.min(cut, hash);
        if (query >= 0) cut = Math.min(cut, query);
        const path = u.slice(0, cut).replace(/\\/g, '/');
        const tail = u.slice(cut);
        const encoded = path.split('/').map((seg) => {
          if (!seg) return seg;
          try {
            return encodeURIComponent(decodeURIComponent(seg));
          } catch {
            return encodeURIComponent(seg);
          }
        }).join('/');
        return encoded + tail;
      });
      manager.onError = (u) => {
        console.warn('MMD 贴图/附件加载失败，继续显示模型：', u);
      };
      const mmd = await new Promise<THREE.SkinnedMesh>((resolve, reject) => {
        let settled = false;
        const loader = new MMDLoader(manager);
        loader.setResourcePath(url.slice(0, url.lastIndexOf('/') + 1));
        loader.load(
          url,
          (m) => {
            settled = true;
            resolve(m as THREE.SkinnedMesh);
          },
          undefined,
          (err) => {
            if (settled) return;
            reject(err);
          },
        );
      });
      if (seq !== this.loadSeq) {
        disposeGpu(mmd);
        return Promise.reject(new Error('已被更新的加载取代'));
      }
      return this.setupMMD(mmd, url);
    }

    const loaderMod = await import('three/examples/jsm/loaders/GLTFLoader.js');
    const loader = new loaderMod.GLTFLoader();
    let root: THREE.Object3D;
    if (ext === 'vrm') {
      const [{ VRMLoaderPlugin, VRMUtils }, { makeVRMAvatar }] = await Promise.all([
        import('@pixiv/three-vrm'),
        import('./avatar/vrm'),
      ]);
      loader.register((parser) => new VRMLoaderPlugin(parser));
      const gltf = await loader.loadAsync(url);
      if (seq !== this.loadSeq) {
        disposeGpu(gltf.scene);
        return Promise.reject(new Error('已被更新的加载取代'));
      }
      const vrm = gltf.userData.vrm as VRM;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      if (typeof (VRMUtils as any).combineSkeletons === 'function') {
        (VRMUtils as any).combineSkeletons(gltf.scene);
      }
      VRMUtils.rotateVRM0(vrm); // VRM 0.x 模型转为面向镜头
      this.avatar = makeVRMAvatar(vrm);
      this.vrm = vrm;
      root = vrm.scene;
      if (vrm.lookAt) vrm.lookAt.target = this.camera;
    } else {
      const gltf = await loader.loadAsync(url);
      if (seq !== this.loadSeq) {
        disposeGpu(gltf.scene);
        return Promise.reject(new Error('已被更新的加载取代'));
      }
      this.avatar = makeMeshAvatar(gltf.scene, GLB_BONES, GLB_MORPHS);
      root = gltf.scene;
    }
    // 非 MMD 模型的灯光基准
    this.lightBase = { key: 1.8, rim: 1.0, amb: 0.9 };
    this.applyLights();
    return this.finishSetup(root, url, ext, false);
  }

  private async setupMMD(mmd: THREE.SkinnedMesh, url: string): Promise<ModelInfo> {
    // MMD 单位约 8cm，缩放到米制
    mmd.scale.setScalar(0.08);
    mmd.updateMatrixWorld(true);
    // three-stdlib 的 MMDLoader 没给颜色贴图标记 sRGB，
    // 新版 three 会把它们当线性数据导致颜色发灰，这里补上
    const mats = Array.isArray(mmd.material) ? mmd.material : [mmd.material];
    for (const m of mats as THREE.MeshToonMaterial[]) {
      if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
      const envMap = (m as any).envMap as THREE.Texture | null;
      if (envMap) envMap.colorSpace = THREE.SRGBColorSpace;
      m.needsUpdate = true;
    }
    // MMD 卡通材质自带环境色贡献，灯光基准略低于 PBR 模型
    // （此前压得更低是为掩盖贴图色彩空间 bug 的过曝假象，bug 已修复）
    this.lightBase = { key: 1.5, rim: 0.5, amb: 0.75 };
    this.applyLights();

    const av = makeMeshAvatar(mmd, MMD_BONES, MMD_MORPHS);
    this.avatar = av;
    // 动捕校准必须用 T-pose 世界坐标；摆臂之后再采集会把下垂写进参考方向
    this.emit('onTPose', mmd, null);

    // 手臂预先放到自然姿势，避免布料从 T-pose 大幅甩动
    for (const [key, rig] of [['leftUpperArm', av.armL], ['rightUpperArm', av.armR]] as const) {
      const b = av.bone(key);
      if (b) b.rotation[rig.axis] = av.base(b)[rig.axis] + rig.down;
    }
    mmd.updateMatrixWorld(true);

    // 必须在手臂摆好之后 attach：停止动作时恢复的是这里记录的姿势，
    // 若记录的是 T-pose，恢复后闲置动画会瞬间拉回自然位、把挂饰链抽飞
    this.motion.attach(mmd);
    this.motion.onPhysicsReset = () => this.physics?.reset();
    const info = this.finishSetup(mmd, url, 'pmx', true);
    await this.attachPhysics();
    return info;
  }

  private detachPhysics() {
    this.physicsGen += 1;
    try { this.physics?.reset(); } catch { /* */ }
    this.physics = null;
    this.phyAcc = 0;
  }

  private async attachPhysics() {
    const gen = ++this.physicsGen;
    if (!this.quality.physics || this.physics) return;
    if (this.physicsHeld) {
      if (gen !== this.physicsGen || !this.quality.physics) return;
      this.physics = this.physicsHeld;
      try { this.physics.reset(); } catch { /* */ }
      return;
    }
    const mmd = this.modelRoot as THREE.SkinnedMesh | null;
    if (this.modelKind !== 'pmx' || !mmd?.isSkinnedMesh) return;
    try {
      await this.ensureAmmo();
      if (gen !== this.physicsGen || !this.quality.physics) return;
      const ud = (mmd.geometry as THREE.BufferGeometry).userData.MMD;
      if (!ud?.rigidBodies?.length) return;
      this.physics = new MMDPhysics(mmd, ud.rigidBodies, ud.constraints);
      this.physics.warmup(60);
      this.physicsHeld = this.physics;
    } catch (e) {
      console.warn('MMD 物理初始化失败，继续以无物理模式运行：', e);
      if (gen === this.physicsGen) this.physics = null;
    }
  }

  private ensureAmmo(): Promise<unknown> {
    if (this.ammoReady) return this.ammoReady;
    this.ammoReady = (async () => {
      const w = window as any;
      if (typeof w.Ammo !== 'function' && typeof w.Ammo !== 'object') {
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement('script');
          const base = import.meta.env.BASE_URL.endsWith('/')
            ? import.meta.env.BASE_URL
            : `${import.meta.env.BASE_URL}/`;
          s.src = `${base}libs/ammo.wasm.js`;
          s.async = true;
          s.onload = () => resolve();
          s.onerror = () => reject(new Error('ammo.wasm.js 加载失败'));
          document.head.appendChild(s);
        });
      }
      if (typeof w.Ammo === 'function') {
        w.Ammo = await w.Ammo();
      }
      return w.Ammo;
    })().catch((e) => {
      this.ammoReady = null;
      throw e;
    });
    return this.ammoReady;
  }

  private finishSetup(root: THREE.Object3D, url: string, format: string,
                      supportsVmd: boolean): ModelInfo {
    this.scene.add(root);
    this.modelRoot = root;
    this.modelKind = format;
    // 保持当前站位（换模型不强制回中心）
    root.position.x = this.stand.x;
    this.camRig.focusX = this.stand.x;
    if (this.avatar) this.emit('onAvatarReady', root, this.avatar, this.vrm);

    // 根据模型头部实际高度设置镜头
    const head = this.avatar!.bone('head');
    if (head) {
      this.camRig.headY = head.getWorldPosition(new THREE.Vector3()).y + 0.06;
    }
    this.camRig.set('full', true);

    const info: ModelInfo = {
      url, format,
      morphNames: this.avatar!.morphNames(),
      supportsVmd,
    };
    this.onModelReady?.(info);
    return info;
  }

  private unloadModel() {
    this.bgmGen += 1;
    this._danceLive = false;
    this.bgm.stop();
    this.emit('onAvatarUnload');
    this.motion?.detach();
    this.camRig.stopVmd();
    this.stand.reset();
    this.camRig.resetFocus();
    this.walkLocActive = false;
    this.walkLocUrl = '';
    this.physicsGen += 1;
    this.physics = null;
    this.physicsHeld = null;
    this.modelKind = '';
    this.phyAcc = 0;
    this.expr.reset();
    this.director.reset();
    this.lipsync.setTalking(false);
    if (this.modelRoot) {
      this.scene.remove(this.modelRoot);
      disposeGpu(this.modelRoot);
      this.modelRoot = null;
    }
    this.vrm = null;
    this.avatar = null;
  }

  // ---------- 对外控制 ----------
  playMotion(url: string, opts?: {
    once?: boolean;
    holdLast?: boolean;
    bgm?: string;
    camera?: string;
    onEnded?: () => void;
    /** 只有舞蹈才出配乐；其它动作即使传了 bgm 也不播。 */
    dance?: boolean;
  }) {
    // 用户主动播别的动作时，取消「到位停走路」的所有权
    if (url !== this.walkLocUrl) this.walkLocActive = false;
    this.emit('onMotionWillPlay');
    const isDance = !!opts?.dance;
    if (!isDance && this._danceLive) {
      return Promise.resolve(false);
    }
    const gen = ++this.bgmGen;
    this.bgm.onEnded = null;
    const finish = () => {
      if (gen !== this.bgmGen) return;
      this.bgm.onEnded = null;
      this.bgm.stop();
      this._danceLive = false;
      if (opts?.camera) this.camRig.stopVmd();
      opts?.onEnded?.();
    };
    this.motion.onStopped = finish;
    if (opts?.camera) void this.camRig.playVmd(opts.camera);
    if (isDance && opts.bgm) {
      this._danceLive = true;
      this.bgm.play(opts.bgm, { loop: false });
      if (this.bgm.ducked) this.bgm.setDuck(0.55, 180);
      this.bgm.onEnded = () => {
        if (gen === this.bgmGen) this.motion.stop();
      };
      return this.motion.play(url, { once: false }).then((ok) => {
        if (!ok) finish();
        return ok;
      });
    }
    this._danceLive = isDance;
    this.bgm.stop();
    return this.motion.play(url, { once: opts?.once, holdLast: opts?.holdLast }).then((ok) => {
      if (!ok) finish();
      return ok;
    });
  }

  stopMotion() {
    this.bgmGen += 1;
    this._danceLive = false;
    this.walkLocActive = false;
    this.bgm.stop();
    this.motion.stop();
    this.camRig.stopVmd();
  }

  /** 非舞蹈拍一上场就停歌，不要等动作真正开播（中间可能空 1 秒多）。 */
  silenceBgm() {
    if (this._danceLive) return;
    this.bgmGen += 1;
    this.bgm.onEnded = null;
    this.bgm.stop();
  }

  setBgmVolume(v: number) {
    this.bgm.setVolume(v);
  }

  /** 舞已经定了、歌可能还在加载：先占住，别让走路/说话动作把即将开的歌掐掉。 */
  holdDance() {
    this._danceLive = true;
  }

  setEmotion(e: EmotionKey, intensity = 0.85) {
    this.director.setMood(e, intensity);
  }

  triggerAction(a: ActionKey) {
    this.idle.trigger(a);
  }

  setMorph(name: string, on: boolean | number) {
    this.expr.setMorphTarget(name, on);
  }

  resetMorphs() {
    this.expr.resetMorphs();
  }

  setCamera(preset: CamPreset, instant = false) {
    this.camRig.set(preset, instant);
  }

  /** 走到站台直径 1/4（左）/ 1/2（中）/ 3/4（右），并用走路动作走过去 */
  goToStand(slot: StandSlot) {
    if (!this.stand.goTo(slot)) return;
    void this.startWalkLocomotion();
  }

  /** 向左或向右挪一档 */
  stepStand(dir: 'left' | 'right') {
    if (!this.stand.step(dir === 'left' ? -1 : 1)) return;
    void this.startWalkLocomotion();
  }

  get standSlot(): StandSlot {
    return this.stand.slot;
  }

  /** 从动作库挑走路循环，到位后停掉 */
  private async startWalkLocomotion() {
    if (this._danceLive) return;
    this.stand.onArrive = () => this.finishWalkLocomotion();
    try {
      const { useAssetsStore } = await import('../stores/assets');
      const { api } = await import('../api/client');
      const assets = useAssetsStore();
      const walk =
        assets.motions.find((m) => /^walk\.vmd$/i.test(m.name)) ??
        assets.motions.find((m) =>
          /走路|walk/i.test(`${m.label}${m.name}`) && !/挥手|wave|cute/i.test(`${m.label}${m.name}`));
      if (!walk || !this.modelRoot) return;
      const url = api.assetUrl(walk);
      // 已经在走同款步态：只续上到位回调，不重播打断
      if (this.walkLocActive && this.motion.currentUrl === url) {
        this.walkLocUrl = url;
        return;
      }
      this.walkLocUrl = url;
      this.walkLocActive = true;
      await this.playMotion(url);
      if (!this.walkLocActive) return;
      if (!this.stand.isMoving && this.motion.currentUrl === url) {
        this.finishWalkLocomotion();
      }
    } catch (e) {
      console.warn('站位走路动作启动失败：', e);
    }
  }

  private finishWalkLocomotion() {
    if (!this.walkLocActive) return;
    this.walkLocActive = false;
    if (this.motion.currentUrl === this.walkLocUrl && !this._danceLive) {
      this.bgmGen += 1;
      this.bgm.stop();
      this.motion.stop();
    }
    this.walkLocUrl = '';
  }

  playShot(id: CamShotId, instant = false, duration?: number) {
    this.camRig.playShot(this.clampCamSize(id), instant, duration);
  }

  playIdleCut(size: CamShotId, move: IdleMoveKind, duration?: number) {
    this.camRig.playIdleCut(this.clampCamSize(size), move, duration);
  }

  playCameraVmd(url: string, opts?: { once?: boolean }) {
    if (this.camSizeLock?.length) return Promise.resolve();
    return this.camRig.playVmd(url, opts);
  }

  /** 景别锁：特写/半身近的落到 3/4，远景落到全身；运镜（偏转/俯仰）原样放行 */
  clampCamSize(id: CamShotId): CamShotId {
    const lock = this.camSizeLock;
    if (!lock?.length) return id;
    if (lock.includes(id)) return id;
    const sizes: CamShotId[] = ['close', 'bust', 'half', 'threeQ', 'full', 'long'];
    if (!sizes.includes(id)) return id;
    if (id === 'long') return lock.includes('full') ? 'full' : lock[lock.length - 1];
    return lock.includes('threeQ') ? 'threeQ' : lock[0];
  }

  stopCamera() {
    this.camRig.stopVmd();
    this.camRig.playShot('full');
  }

  get cameraDriving() {
    return this.camRig.driving;
  }

  get threeCamera() {
    return this.camera;
  }

  get threeScene() {
    return this.scene;
  }

  get canvas() {
    return this.renderer?.domElement ?? null;
  }

  get avatarRoot() {
    return this.modelRoot;
  }

  get currentAvatar() {
    return this.avatar;
  }

  get motionActive() {
    return this.motion.active;
  }

  get currentMotionUrl() {
    return this.motion.currentUrl;
  }

  dispose() {
    this.disposed = true;
    if (this.onResize) window.removeEventListener('resize', this.onResize);
    if (this.onVis) document.removeEventListener('visibilitychange', this.onVis);
    this.unloadModel();
    this.dropBackgroundTex();
    this.disposePlatform();
    for (const tex of this.platformTexCache.values()) tex.dispose();
    this.platformTexCache.clear();
    this.renderer?.dispose();
    this.renderer?.domElement.remove();
  }

  // ---------- 主循环 ----------
  private animate = () => {
    if (this.disposed || !this.pageVisible) return;
    requestAnimationFrame(this.animate);
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.elapsedTime;

    this.stand.update(dt, this.modelRoot);
    this.camRig.focusX = this.stand.x;
    this.camRig.update(dt);
    if (!this.camRig.driving) {
      const fov = 32 - this.director.camPush * 0.6;
      if (Math.abs(this.camera.fov - fov) > 0.002) {
        this.camera.fov = fov;
        this.camera.updateProjectionMatrix();
      }
      this.controls.update();
    }
    for (const s of this.platformSpin) s.obj.rotation.y += s.speed * dt;

    if (this.avatar) {
      const av = this.avatar;
      av.beginFrame();

      this.expr.mouthValue = this.lipsync.value(t, dt);

      if (!this.applyPluginPose()) {
        this.expr.update(av, dt);
        if (!this.motion.active) this.idle.update(av, dt, t);
        this.motion.update(dt);
        // 表演导演：在闲置姿态之上叠加视线/微表演层（VMD 播放时自动让位）
        this.director.update(av, dt, this.motion.active);
      }

      // 物理：累积真实时间，攒够一个物理步长才推进一次（高刷屏防加速）
      if (this.physics) {
        this.phyAcc += dt;
        if (this.phyAcc >= PHY_STEP) {
          this.physics.update(Math.min(this.phyAcc, 1 / 30));
          this.phyAcc = 0;
        }
      }

      av.update(dt); // VRM 内部更新（表情/弹簧骨），MMD 为空操作
      this.motion.pinHold();
    }

    this.emit('onFrame', dt);

    this.renderer.render(this.scene, this.camera);
  };

  /** 当场再渲一帧后导出 JPEG，不改主循环的 preserveDrawingBuffer。 */
  async captureStill(maxW = 1280): Promise<Blob> {
    if (!this.renderer) throw new Error('舞台未初始化');
    this.renderer.render(this.scene, this.camera);
    const src = this.renderer.domElement;
    const scale = Math.min(1, maxW / Math.max(src.width, 1));
    const w = Math.max(1, Math.round(src.width * scale));
    const h = Math.max(1, Math.round(src.height * scale));
    const out = document.createElement('canvas');
    out.width = w;
    out.height = h;
    const ctx = out.getContext('2d');
    if (!ctx) throw new Error('无法截图');
    ctx.drawImage(src, 0, 0, w, h);
    return new Promise((resolve, reject) => {
      out.toBlob((b) => (b ? resolve(b) : reject(new Error('截图失败'))), 'image/jpeg', 0.92);
    });
  }

  /** 录舞台短片。时长按墙上时钟，优先 Mediabunny + WebCodecs 出 mp4，否则 MediaRecorder。 */
  async captureClip(seconds = 8, onTick?: (sec: number) => void): Promise<Blob> {
    if (!this.renderer) throw new Error('舞台未初始化');
    const sec = Math.min(60, Math.max(1, Math.round(Number(seconds)) || 8));
    const canvas = this.renderer.domElement;
    try {
      return await encodeClipWebCodecs(canvas, sec, onTick);
    } catch {
      return recordClipMedia(canvas, sec, onTick);
    }
  }
}

async function encodeClipWebCodecs(
  canvas: HTMLCanvasElement,
  seconds: number,
  onTick?: (sec: number) => void,
): Promise<Blob> {
  if (typeof VideoEncoder === 'undefined') throw new Error('no VideoEncoder');
  const {
    BufferTarget, CanvasSource, Mp4OutputFormat, Output, QUALITY_HIGH,
  } = await import('mediabunny');
  const target = new BufferTarget();
  const output = new Output({ format: new Mp4OutputFormat(), target });
  const source = new CanvasSource(canvas, { codec: 'avc', bitrate: QUALITY_HIGH });
  output.addVideoTrack(source, { frameRate: 30 });
  await output.start();
  const fps = 30;
  const n = Math.round(seconds * fps);
  const frameMs = 1000 / fps;
  const t0 = performance.now();
  for (let i = 0; i < n; i++) {
    const due = t0 + i * frameMs;
    while (performance.now() < due) {
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
    }
    await source.add(i / fps, 1 / fps);
    onTick?.(Math.min(seconds, (performance.now() - t0) / 1000));
  }
  await output.finalize();
  const buf = target.buffer;
  if (!buf) throw new Error('empty mp4');
  return new Blob([buf], { type: 'video/mp4' });
}

function recordClipMedia(
  canvas: HTMLCanvasElement,
  seconds: number,
  onTick?: (sec: number) => void,
): Promise<Blob> {
  const stream = canvas.captureStream(30);
  const mime = [
    'video/webm;codecs=av01',
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm',
  ].find((t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t))
    || 'video/webm';
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 5_000_000 });
  const chunks: BlobPart[] = [];
  rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  rec.start(200);
  const t0 = performance.now();
  return new Promise((resolve, reject) => {
    const timer = window.setInterval(() => {
      onTick?.((performance.now() - t0) / 1000);
    }, 200);
    rec.onerror = () => {
      clearInterval(timer);
      reject(new Error('录制失败'));
    };
    rec.onstop = () => {
      clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      resolve(new Blob(chunks, { type: rec.mimeType || mime }));
    };
    window.setTimeout(() => rec.stop(), Math.max(500, seconds * 1000));
  });
}

/** 全局单例：UI 各处共享同一个舞台 */
export const stage = new Stage();
// 调试入口（控制台可用）
(window as any).__stage = stage;
