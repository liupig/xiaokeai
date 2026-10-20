// Wish ritual drawn beside the character.
//
// The pool opens on a random screen side. Three painted props fly in from
// the opposite side. Each prop has its own delay, arc, tumble, and scale,
// then rests in the water. Textures are generated 3D objects with a
// transparent background (assets/wish/items), not emoji badges. Planes face
// the camera, skip the depth test, and draw in front of the body.
//
// After a pause the payoff is a coin shower on the other side of the pool.
// Coins are parented to the camera-facing group, not to the pool, so they
// fall from the top of the frame to the bottom and never land in the water.
// The shower is atmosphere: every wish uses the full set of meshes, not one
// mesh per coin. The spoken amount comes from the server. A short
// synthesized metal tick plays while the shower is up. There is no audio file.
import * as THREE from 'three';
import type { Stage } from '../../engine/stage';
import { t } from '../../i18n';

const RISE = 1.0;
const TOSS = 3.4;
const HOLD = 1.4;
const FALL = 1.8;
const LEAVE = 0.9;
const COIN_N = 5;
const RAIN_MAX = 52;
const POOL_R = 0.16;
const GOLD = 0xd4b06a;
const ITEM_IDS = ['work', 'phone', 'computer', 'bracelet', 'key', 'letter', 'worry', 'magnet', 'card', 'alarm', 'sock', 'meeting'];

type Phase = 'off' | 'rise' | 'well' | 'toss' | 'hold' | 'reveal' | 'leave';

type Flight = {
  delay: number;
  dur: number;
  fromX: number;
  fromY: number;
  fromZ: number;
  toX: number;
  toY: number;
  toZ: number;
  arc: number;
  bend: number;
  scale0: number;
  scale1: number;
  spinX: number;
  spinY: number;
  spinZ: number;
  tilt: number;
  landed: boolean;
};

function clamp01(t: number) {
  return Math.max(0, Math.min(1, t));
}
function easeInOut(t: number) {
  const u = clamp01(t);
  return u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;
}
function easeOut(t: number) {
  const u = clamp01(t);
  return 1 - (1 - u) ** 3;
}

function loadTex(url: string) {
  return new Promise<THREE.Texture | null>((resolve) => {
    const timer = window.setTimeout(() => resolve(null), 4000);
    new THREE.TextureLoader().load(url, (tex) => {
      window.clearTimeout(timer);
      try { tex.colorSpace = THREE.SRGBColorSpace; } catch { /* 旧版 three */ }
      resolve(tex);
    }, undefined, () => {
      window.clearTimeout(timer);
      resolve(null);
    });
  });
}

function paper(map: THREE.Texture | null, color: number) {
  return new THREE.MeshBasicMaterial({
    map,
    color,
    transparent: true,
    opacity: 1,
    side: THREE.FrontSide,
    toneMapped: false,
  });
}

function goldMat(color = GOLD) {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 1,
    toneMapped: false,
  });
}

function crop(map: THREE.Texture, zoom: number) {
  const tex = map.clone();
  tex.colorSpace = map.colorSpace;
  tex.center.set(0.5, 0.5);
  tex.repeat.set(zoom, zoom);
  tex.offset.set(0, 0);
  tex.needsUpdate = true;
  return tex;
}

function faceFont(px: number, weight = 600) {
  return `${weight} ${px}px "PingFang SC", "Microsoft YaHei", "Yu Gothic", "Hiragino Sans", "Malgun Gothic", "Segoe UI", sans-serif`;
}

function planFlight(i: number, side: number): Flight {
  const from = -side;
  const preset = [
    { delay: 0, dur: 1.55, arc: 0.12, bend: 0.1, scale0: 1.8, scale1: 1.05, tilt: 0.6 },
    { delay: 0.38, dur: 1.3, arc: 0.26, bend: -0.14, scale0: 1.25, scale1: 0.9, tilt: -0.45 },
    { delay: 0.7, dur: 1.6, arc: 0.08, bend: 0.18, scale0: 2.1, scale1: 1.15, tilt: 0.25 },
  ][i] ?? { delay: 0.2 * i, dur: 1.4, arc: 0.4, bend: 0.1, scale0: 1.5, scale1: 0.68, tilt: 0.3 };
  return {
    delay: preset.delay,
    dur: preset.dur,
    fromX: from * (0.78 + i * 0.1),
    fromY: -0.02 + (i === 1 ? 0.08 : 0),
    fromZ: 0.58 + i * 0.06,
    toX: (i - 1) * 0.075,
    toY: -0.015 + (i % 2) * 0.012,
    toZ: 0.04 + i * 0.012,
    arc: preset.arc,
    bend: from * preset.bend,
    scale0: preset.scale0,
    scale1: preset.scale1,
    spinX: 2.2 + i * 1.4,
    spinY: (i % 2 === 0 ? 1 : -1) * (3.4 + i * 0.7),
    spinZ: 0.7 + i * 0.85,
    tilt: preset.tilt,
    landed: false,
  };
}

function makeProp(map: THREE.Texture | null) {
  const root = new THREE.Group();
  const spin = new THREE.Group();
  const image = map?.image as { width?: number; height?: number } | undefined;
  const aspect = image?.width && image?.height ? image.width / image.height : 1;
  const height = 0.34;
  const geo = new THREE.PlaneGeometry(height * aspect, height);
  const front = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    map,
    color: map ? 0xffffff : 0xe7c98a,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
  }));
  const back = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    map,
    color: 0x5c4630,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
  }));
  back.position.z = -0.02;
  front.material.depthTest = false;
  back.material.depthTest = false;
  front.renderOrder = 12;
  back.renderOrder = 11;
  spin.add(front, back);
  root.add(spin);
  root.userData.spin = spin;
  root.frustumCulled = false;
  root.traverse((obj) => { obj.frustumCulled = false; });
  return root;
}

function makeCoin(map: THREE.Texture | null, radius: number) {
  const root = new THREE.Group();
  const spin = new THREE.Group();
  const depth = 0.016;
  const faceGeo = new THREE.CircleGeometry(radius, 64);
  const front = new THREE.Mesh(faceGeo, paper(map, 0xffffff));
  front.position.z = depth / 2;
  const back = new THREE.Mesh(faceGeo.clone(), paper(map, 0xffffff));
  back.rotation.y = Math.PI;
  back.position.z = -depth / 2;
  const edge = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, depth, 40, 1, true),
    goldMat(0xe7c98a),
  );
  edge.rotation.x = Math.PI / 2;
  (edge.material as THREE.MeshBasicMaterial).side = THREE.DoubleSide;
  spin.add(front, back, edge);
  root.add(spin);
  root.userData.spin = spin;
  root.renderOrder = 8;
  root.frustumCulled = false;
  root.traverse((obj) => {
    obj.frustumCulled = false;
    obj.renderOrder = 8;
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) {
      if (!mat) continue;
      mat.depthTest = false;
      mat.depthWrite = false;
    }
  });
  return root;
}

class WishPlugin {
  readonly id = 'wish';
  private stage: Stage;
  private rig = new THREE.Group();
  private face = new THREE.Group();
  private well = new THREE.Group();
  private pool = new THREE.Group();
  private poolDisc: THREE.Mesh;
  private sheen: THREE.Mesh;
  private coins: THREE.Group[] = [];
  private rain: THREE.Group[] = [];
  private rainCount = 0;
  private rainHit: boolean[] = [];
  private things: THREE.Group[] = [];
  private side = 1;
  private chimeAt = 0;
  private chimeCtx: AudioContext | null = null;
  private itemMaps = new Map<string, THREE.Texture | null>();
  private splashes: THREE.Mesh[] = [];
  private dust: THREE.Points;
  private dustPos: Float32Array;
  private lamp = new THREE.PointLight(0xffe2a8, 0, 2.2, 2);
  private phase: Phase = 'off';
  private t = 0;
  private spin = 0;
  private fade = 0;
  private splash = 0;
  private chestY = 1.16;
  private raf = 0;
  private lastTick = 0;
  private booted = false;
  private camQ = new THREE.Quaternion();
  private parentQ = new THREE.Quaternion();
  private tmp = new THREE.Vector3();
  private tmp2 = new THREE.Vector3();
  private readyWait: Array<() => void> = [];
  private holdWait: Array<() => void> = [];
  private leaveWait: Array<() => void> = [];
  private coinImage: (CanvasImageSource & { width?: number; height?: number }) | null = null;
  private coinCanvas: HTMLCanvasElement | null = null;
  private coinMap: THREE.CanvasTexture | null = null;

  constructor(stage: Stage) {
    this.stage = stage;
    this.rig.name = 'wish-rig';
    this.poolDisc = new THREE.Mesh(new THREE.CircleGeometry(POOL_R, 72), paper(null, 0x1a2744));
    const rim = new THREE.Mesh(
      new THREE.TorusGeometry(POOL_R, 0.0026, 8, 72),
      goldMat(0xe7c98a),
    );
    this.sheen = new THREE.Mesh(
      new THREE.CircleGeometry(POOL_R * 0.55, 48),
      new THREE.MeshBasicMaterial({
        color: 0xffe2a8,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        toneMapped: false,
      }),
    );
    this.sheen.position.z = 0.004;
    this.sheen.userData.wishOwn = true;
    this.pool.add(this.poolDisc, rim, this.sheen);
    this.pool.rotation.x = -0.42;
    for (let i = 0; i < 3; i += 1) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.07, 0.086, 64),
        goldMat(0xf3e2bc),
      );
      ring.userData.wishOwn = true;
      ring.visible = false;
      this.splashes.push(ring);
      this.pool.add(ring);
    }
    this.dustPos = new Float32Array(48 * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.dustPos, 3));
    this.dust = new THREE.Points(geo, new THREE.PointsMaterial({
      color: GOLD,
      size: 0.016,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    }));
    this.dust.frustumCulled = false;
    this.well.name = 'wish-well';
    this.well.add(this.pool, this.dust, this.lamp);
    this.face.add(this.well);
    this.rig.add(this.face);
    this.rig.visible = false;
  }

  onFrame = () => { /* 自己的循环在跑 */ };

  async start() {
    await this.boot();
    this.phase = 'rise';
    this.t = 0;
    this.spin = 0;
    this.fade = 0;
    this.splash = 0;
    this.rainCount = 0;
    this.rainHit = [];
    this.side = Math.random() < 0.5 ? -1 : 1;
    this.clearThings();
    for (const coin of this.rain) coin.visible = false;
    this.stampCoin(t('wish.face'));
    this.rig.visible = true;
    this.follow();
    this.layout(0);
    this.startLoop();
  }

  whenReady() {
    return new Promise<void>((resolve) => {
      if (this.phase === 'well' || this.phase === 'reveal' || this.phase === 'leave') {
        resolve();
        return;
      }
      this.readyWait.push(resolve);
    });
  }

  toss(items: { id: string }[]) {
    this.clearThings();
    (items || []).slice(0, 3).forEach((item, i) => {
      const mesh = makeProp(this.itemMaps.get(item.id) ?? null);
      mesh.userData.flight = planFlight(i, this.side);
      this.things.push(mesh);
      this.well.add(mesh);
    });
    this.phase = 'toss';
    this.t = 0;
    return new Promise<void>((resolve) => this.holdWait.push(resolve));
  }

  reveal(_label: string) {
    const n = RAIN_MAX;
    this.rainCount = n;
    this.rainHit = Array.from({ length: n }, () => false);
    this.phase = 'reveal';
    this.t = 0;
    this.chimeAt = 0;
    this.splash = 0;
    for (let i = 0; i < this.rain.length; i += 1) {
      if (this.rain[i].parent !== this.face) this.face.add(this.rain[i]);
      this.rain[i].visible = false;
    }
    this.playChime();
  }

  finish() {
    if (this.phase === 'off') return Promise.resolve();
    this.phase = 'leave';
    this.t = 0;
    return new Promise<void>((resolve) => this.leaveWait.push(resolve));
  }

  private async boot() {
    const scene = this.stage.threeScene;
    if (scene && this.rig.parent !== scene) scene.add(this.rig);
    if (this.booted) return;
    this.booted = true;
    const [poolMap, coinMap, ...itemMaps] = await Promise.all([
      loadTex('/assets/wish/pool.png'),
      loadTex('/assets/wish/coin.png'),
      ...ITEM_IDS.map((id) => loadTex(`/assets/wish/items/${id}.png`)),
    ]);
    ITEM_IDS.forEach((id, i) => {
      const map = itemMaps[i];
      if (map) map.anisotropy = 8;
      this.itemMaps.set(id, map);
    });
    if (poolMap) {
      const mat = this.poolDisc.material as THREE.MeshBasicMaterial;
      mat.map = crop(poolMap, 0.9);
      mat.color.setHex(0xffffff);
      mat.needsUpdate = true;
    }
    this.coinImage = (coinMap?.image as (CanvasImageSource & { width?: number; height?: number }) | undefined) ?? null;
    this.coinMap = this.makeCoinTexture();
    for (let i = 0; i < COIN_N; i += 1) {
      const card = makeCoin(this.coinMap, 0.04);
      card.visible = false;
      this.coins.push(card);
      this.face.add(card);
    }
    for (let i = 0; i < RAIN_MAX; i += 1) {
      const drop = makeCoin(this.coinMap, 0.05);
      drop.visible = false;
      drop.userData.bulk = 0.55 + ((i * 7) % 9) * 0.08;
      this.rain.push(drop);
      this.face.add(drop);
    }
  }

  private startLoop() {
    if (this.raf) return;
    this.lastTick = performance.now();
    const loop = (now: number) => {
      this.raf = requestAnimationFrame(loop);
      const dt = Math.min(0.05, (now - this.lastTick) / 1000);
      this.lastTick = now;
      this.step(dt);
    };
    this.raf = requestAnimationFrame(loop);
  }

  private stopLoop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private step(dt: number) {
    if (this.phase === 'off') return;
    this.t += dt;
    this.spin += dt * (this.phase === 'toss' ? 0.7 : 0.42);
    this.follow();
    if (this.phase === 'reveal' && this.t < 3.4) this.tickChime();
    if (this.phase === 'rise') {
      this.fade = easeOut(this.t / RISE);
      if (this.t >= RISE) {
        this.go('well');
        const wait = this.readyWait.splice(0);
        for (const fn of wait) fn();
      }
    } else if (this.phase === 'toss') {
      this.fade = 1;
      if (this.t >= TOSS) {
        this.go('hold');
        this.splash = 0.001;
      }
    } else if (this.phase === 'hold') {
      this.fade = 1;
      if (this.splash > 0) this.splash += dt;
      if (this.t >= HOLD && this.holdWait.length) {
        const wait = this.holdWait.splice(0);
        for (const fn of wait) fn();
      }
    } else if (this.phase === 'well' || this.phase === 'reveal') {
      this.fade = 1;
      if (this.splash > 0) this.splash += dt;
    } else if (this.phase === 'leave') {
      this.fade = 1 - easeInOut(this.t / LEAVE);
      if (this.splash > 0) this.splash += dt;
      if (this.t >= LEAVE) {
        this.phase = 'off';
        this.rig.visible = false;
        this.lamp.intensity = 0;
        this.stopLoop();
        const wait = this.leaveWait.splice(0);
        for (const fn of wait) fn();
        return;
      }
    }
    this.layout(dt);
  }

  private go(phase: Phase) {
    this.phase = phase;
    this.t = 0;
  }

  private follow() {
    const root = this.stage.avatarRoot;
    if (root) {
      root.getWorldPosition(this.tmp);
      this.rig.position.set(this.tmp.x, 0, this.tmp.z);
    }
    const avatar = this.stage.currentAvatar;
    const bone = avatar?.bone('chest') || avatar?.bone('spine');
    if (bone) {
      bone.getWorldPosition(this.tmp);
      this.chestY = this.tmp.y;
    }
    this.face.position.set(0, this.chestY - 0.08, 0.5);
    const cam = this.stage.threeCamera;
    if (!cam) return;
    cam.getWorldQuaternion(this.camQ);
    this.rig.getWorldQuaternion(this.parentQ).invert();
    this.face.quaternion.copy(this.camQ).premultiply(this.parentQ);
  }

  private layout(dt: number) {
    const rise = this.phase === 'rise' ? easeOut(this.t / RISE) : 1;
    const leave = this.phase === 'leave' ? easeInOut(this.t / LEAVE) : 0;
    const breathe = this.phase === 'well' || this.phase === 'hold' || this.phase === 'toss'
      ? Math.sin(this.t * 2.2) * 0.018
      : 0;
    const punch = this.phase === 'well'
      ? Math.sin(clamp01(this.t / 0.35) * Math.PI) * 0.05
      : 0;
    const slide = (1 - rise) * -this.side * 0.22;
    this.well.position.set(this.side * 0.46 + slide, 0.34, 0.12);
    this.pool.position.set(0, -0.08 + (1 - rise) * -0.22 - leave * 0.16, 0);
    this.pool.scale.setScalar((0.22 + 0.78 * rise) * (1 - leave * 0.35) * (1 + breathe + punch));
    this.poolDisc.rotation.z = this.spin * 0.08;
    this.fadeGroup(this.pool, this.fade);
    const sheenMat = this.sheen.material as THREE.MeshBasicMaterial;
    sheenMat.opacity = this.fade * (0.08 + Math.sin(this.t * 3) * 0.04 + (this.phase === 'reveal' ? 0.08 : 0));
    this.poseSplashes();

    for (const card of this.coins) card.visible = false;
    this.poseThings(leave);
    this.poseRain(leave);
    this.lamp.position.set(0, 0.36, 0.55);
    const glow = this.phase === 'reveal' ? 0.9 : (this.phase === 'toss' || this.phase === 'hold' ? 0.42 : 0.16);
    this.lamp.intensity = this.fade * glow;
    this.poseDust(dt);
  }

  private poseThings(leave: number) {
    const live = this.phase === 'toss' || this.phase === 'hold' || this.phase === 'reveal' || this.phase === 'leave';
    for (const thing of this.things) {
      const flight = thing.userData.flight as Flight | undefined;
      const spin = thing.userData.spin as THREE.Group | undefined;
      if (!flight || !live || !spin) {
        thing.visible = false;
        continue;
      }
      const clock = this.phase === 'toss' ? this.t : flight.delay + flight.dur + 1;
      if (clock < flight.delay) {
        thing.visible = false;
        continue;
      }
      thing.visible = true;
      const p = clamp01((clock - flight.delay) / flight.dur);
      const eased = easeOut(p);
      const hump = Math.sin(p * Math.PI);
      const sink = this.phase === 'leave' ? leave : 0;
      thing.position.set(
        flight.fromX + (flight.toX - flight.fromX) * eased + hump * flight.bend,
        flight.fromY + (flight.toY - flight.fromY) * eased + hump * flight.arc - sink * 0.18,
        flight.fromZ + (flight.toZ - flight.fromZ) * eased,
      );
      const scale = flight.scale0 + (flight.scale1 - flight.scale0) * eased;
      const squash = p > 0.84 ? 1 - Math.sin(((p - 0.84) / 0.16) * Math.PI) * 0.18 : 1;
      thing.scale.set(scale * (1 - sink * 0.35), scale * squash * (1 - sink * 0.35), 1);
      const fly = 1 - eased;
      spin.rotation.set(
        flight.spinX * fly + -0.55 * eased,
        flight.spinY * fly + flight.tilt * eased,
        flight.spinZ * fly * 0.35,
      );
      this.fadeGroup(thing, this.fade * (1 - sink));
      if (p > 0.92 && !flight.landed) {
        flight.landed = true;
        this.splash = 0.001;
      }
    }
  }

  private clearThings() {
    for (const thing of this.things) {
      thing.removeFromParent();
      thing.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.geometry?.dispose();
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const mat of mats) mat?.dispose();
      });
    }
    this.things = [];
  }

  private poseRain(leave: number) {
    const n = this.rainCount;
    const live = this.phase === 'reveal' || this.phase === 'leave';
    if (!live || n <= 0) {
      for (const coin of this.rain) coin.visible = false;
      return;
    }
    const stagger = 0.016;
    const clock = this.phase === 'leave' ? (n - 1) * stagger + FALL : this.t;
    const opposite = -this.side;
    for (let i = 0; i < this.rain.length; i += 1) {
      const coin = this.rain[i];
      if (i >= n) {
        coin.visible = false;
        continue;
      }
      const u = clamp01((clock - i * stagger) / FALL);
      if (u <= 0) {
        coin.visible = false;
        continue;
      }
      coin.visible = true;
      const drop = u * u;
      const column = ((i * 5) % 9) / 8;
      const x = opposite * (0.2 + column * 0.5);
      const sway = Math.sin(i * 1.7 + this.t * 2.2) * 0.04;
      const startY = 1.05 + (i % 6) * 0.04;
      const endY = -1.42 - (i % 4) * 0.05;
      coin.position.set(
        x + sway,
        startY + (endY - startY) * drop - leave * 0.15,
        0.22 + (i % 3) * 0.06,
      );
      const spin = coin.userData.spin as THREE.Group;
      spin.rotation.set(
        this.t * (6 + (i % 5)),
        this.t * (2.2 + (i % 3) * 0.5),
        Math.sin(i) * 0.4,
      );
      const bulk = Number(coin.userData.bulk) || 0.8;
      const fadeOut = drop > 0.9 ? 1 - (drop - 0.9) / 0.1 : 1;
      coin.scale.setScalar(bulk * (1 - leave * 0.4));
      this.fadeGroup(coin, this.fade * fadeOut);
    }
  }

  private tickChime() {
    if (this.t < this.chimeAt) return;
    this.chimeAt = this.t + 0.038 + Math.random() * 0.028;
    this.playChime();
    if (Math.random() < 0.55) this.playChime();
  }

  private playChime() {
    const Ctx = window.AudioContext;
    if (!Ctx) return;
    if (!this.chimeCtx) this.chimeCtx = new Ctx();
    const ctx = this.chimeCtx;
    void ctx.resume();
    const now = ctx.currentTime;
    const pitch = 0.82 + Math.random() * 0.46;
    const base = 1760 * pitch;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.07, now + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);
    gain.connect(ctx.destination);
    for (const partial of [1, 2.01, 3.42]) {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(base * partial, now);
      osc.frequency.exponentialRampToValueAtTime(Math.max(80, base * partial * 0.7), now + 0.11);
      osc.connect(gain);
      osc.start(now);
      osc.stop(now + 0.16);
    }
    const samples = Math.floor(ctx.sampleRate * 0.02);
    const buffer = ctx.createBuffer(1, samples, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < samples; i += 1) data[i] = (Math.random() * 2 - 1) * (1 - i / samples);
    const noise = ctx.createBufferSource();
    noise.buffer = buffer;
    const noiseGain = ctx.createGain();
    noiseGain.gain.setValueAtTime(0.045, now);
    noiseGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.02);
    noise.connect(noiseGain);
    noiseGain.connect(ctx.destination);
    noise.start(now);
  }

  private poseSplashes() {
    for (let i = 0; i < this.splashes.length; i += 1) {
      const ring = this.splashes[i];
      const mat = ring.material as THREE.MeshBasicMaterial;
      if (this.splash <= 0) {
        ring.visible = false;
        mat.opacity = 0;
        continue;
      }
      const u = clamp01((this.splash - i * 0.14) / 0.7);
      ring.visible = u > 0 && u < 1;
      ring.scale.setScalar(0.35 + u * 2.4);
      mat.opacity = (1 - u) * 0.7 * this.fade;
      mat.depthWrite = false;
    }
  }

  private poseDust(dt: number) {
    const mat = this.dust.material as THREE.PointsMaterial;
    const live = this.phase === 'rise' || this.phase === 'toss' || this.phase === 'hold' || this.phase === 'reveal';
    const target = (live ? 0.72 : 0.2) * this.fade;
    mat.opacity += (target - mat.opacity) * (1 - Math.exp(-dt * 4));
    for (let i = 0; i < 48; i += 1) {
      const seed = (i + 1) * 0.37;
      const a = this.spin * 1.5 + seed * Math.PI * 2;
      const rad = 0.22 + (i % 7) * 0.045;
      this.dustPos[i * 3] = Math.sin(a) * rad;
      this.dustPos[i * 3 + 1] = Math.cos(a * 2) * 0.16 + Math.sin(this.t * 2 + seed) * 0.03;
      this.dustPos[i * 3 + 2] = 0.08 + Math.cos(a) * 0.06;
    }
    (this.dust.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
  }

  private fadeGroup(root: THREE.Object3D, opacity: number) {
    root.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh || mesh.userData.wishOwn) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mat of mats) {
        if (!mat) continue;
        mat.transparent = true;
        mat.opacity = opacity;
        mat.depthWrite = opacity > 0.9;
      }
    });
  }

  private makeCoinTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 1024;
    this.coinCanvas = canvas;
    this.drawCoin(canvas, t('wish.face'));
    const tex = new THREE.CanvasTexture(canvas);
    try { tex.colorSpace = THREE.SRGBColorSpace; } catch { /* 旧版 three */ }
    tex.anisotropy = 8;
    tex.needsUpdate = true;
    return tex;
  }

  private stampCoin(legend: string) {
    if (!this.coinCanvas || !this.coinMap) return;
    this.drawCoin(this.coinCanvas, legend);
    this.coinMap.needsUpdate = true;
  }

  private drawCoin(canvas: HTMLCanvasElement, legend: string) {
    const g = canvas.getContext('2d');
    if (!g) return;
    const size = canvas.width;
    g.clearRect(0, 0, size, size);
    g.fillStyle = '#c6a15a';
    g.beginPath();
    g.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
    g.fill();
    const img = this.coinImage;
    if (img && img.width && img.height) {
      const sx = img.width * (517 / 2048);
      const sy = img.height * (510 / 2048);
      const side = img.width * (1020 / 2048);
      g.save();
      g.beginPath();
      g.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
      g.clip();
      g.drawImage(img, sx, sy, side, side, 0, 0, size, size);
      g.restore();
    }
    if (legend) {
      const y = size * 0.73;
      g.font = faceFont(legend.length > 5 ? 46 : 58);
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillStyle = 'rgba(255, 236, 200, 0.45)';
      g.fillText(legend, size / 2, y + 2);
      g.fillStyle = 'rgba(74, 46, 16, 0.92)';
      g.fillText(legend, size / 2, y);
    }
    g.strokeStyle = 'rgba(255, 236, 196, 0.7)';
    g.lineWidth = 7;
    g.beginPath();
    g.arc(size / 2, size / 2, size / 2 - 16, 0, Math.PI * 2);
    g.stroke();
  }
}

let plugin: WishPlugin | null = null;

export function installWish(stage: Stage) {
  if (!plugin) {
    plugin = new WishPlugin(stage);
    stage.use(plugin);
  }
  return plugin;
}
