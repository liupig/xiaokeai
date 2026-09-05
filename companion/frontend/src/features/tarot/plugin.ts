import * as THREE from 'three';
import type { VRM } from '@pixiv/three-vrm';
import type { Stage } from '../../engine/stage';
import type { Avatar } from '../../engine/types';
import type { TarotCard } from '../../api/client';
import { composeFront, disposeTarotTextures, loadArtTexture, loadBackTexture } from './textures';
import { api } from '../../api/client';
import { cardScale, clarifierOffset, slotOf, type TarotLayout } from './layout';

const RING_N = 26;
const CARD_W = 0.172;
const CARD_H = 0.258;
const RING_R = 0.96;
const RISE = 1.35;
const SHUFFLE = 1.65;
const DEAL_ONE = 0.85;
const DEAL_STAGGER = 0.78;
const FLIP_ONE = 0.72;
const SCATTER = 0.9;
const LEAVE = 1.05;
const GOLD = 0xd4b06a;
const INSPECT_SCALE = 1.12;
const INSPECT_DIST = 1.12;
const HOVER_LIFT = 0.014;
const HOVER_GROW = 0.036;
const HOVER_EASE = 14;
const HOVER_MISS = 6;

type Phase = 'off' | 'rise' | 'shuffle' | 'cut' | 'fan' | 'deal' | 'table' | 'leave';

export interface DrawnView {
  index: number;
  name: string;
  position: string;
  reversed: boolean;
  faceUp?: boolean;
}

export type FocusWhy = 'hover' | 'inspect';

export type RitualHandler = {
  onShuffleReady?: () => void;
  onCut?: (entropy: string) => void;
  onPick?: (fanIndex: number) => void;
  onReveal?: (index: number) => void;
  onAsk?: (index: number) => void;
  onFocus?: (view: DrawnView | null, why: FocusWhy) => void;
};

function easeInOut(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}
function easeOut(t: number) {
  return 1 - (1 - t) ** 3;
}
function clamp01(t: number) {
  return Math.max(0, Math.min(1, t));
}

function goldMat() {
  return new THREE.MeshBasicMaterial({
    color: 0x8a7040,
    toneMapped: false,
  });
}

function paperMat(map: THREE.Texture) {
  return new THREE.MeshBasicMaterial({
    map,
    color: 0xa69f93,
    toneMapped: false,
    side: THREE.FrontSide,
  });
}

function setPaperLook(mesh: THREE.Mesh, k: number) {
  const mat = mesh.material as THREE.MeshBasicMaterial;
  if (!mat.isMeshBasicMaterial) return;
  const overlay = k >= 0.35;
  mat.color.setHex(k >= 0.22 ? 0x8c867b : 0xa69f93);
  mat.depthTest = !overlay;
  mat.depthWrite = true;
}

function dressRim(mat: THREE.Material, k: number) {
  const m = mat as THREE.MeshBasicMaterial;
  if (!m.isMeshBasicMaterial) return;
  m.color.setHex(k >= 0.22 ? 0x6e5830 : 0x8a7040);
}

function makeRim(w: number, h: number, t: number) {
  const g = new THREE.Group();
  const mat = goldMat();
  const e = 0.0036;
  const top = new THREE.Mesh(new THREE.BoxGeometry(w + e * 2, e, t + 0.001), mat);
  top.position.y = h / 2 + e / 2;
  const bot = top.clone();
  bot.position.y = -h / 2 - e / 2;
  const left = new THREE.Mesh(new THREE.BoxGeometry(e, h + e * 2, t + 0.001), mat);
  left.position.x = -w / 2 - e / 2;
  const right = left.clone();
  right.position.x = w / 2 + e / 2;
  g.add(top, bot, left, right);
  return g;
}

function makeCard(front: THREE.Texture, back: THREE.Texture) {
  const g = new THREE.Group();
  const flip = new THREE.Group();
  flip.name = 'tarot-flip';
  const t = 0.0022;
  const geo = new THREE.PlaneGeometry(CARD_W, CARD_H);
  const fm = new THREE.Mesh(geo, paperMat(front));
  fm.position.z = t / 2;
  fm.userData.tarotFace = 'front';
  const bm = new THREE.Mesh(geo.clone(), paperMat(back));
  bm.rotation.y = Math.PI;
  bm.position.z = -t / 2;
  bm.userData.tarotFace = 'back';
  flip.add(fm, bm, makeRim(CARD_W, CARD_H, t));
  const hit = new THREE.Mesh(
    new THREE.PlaneGeometry(CARD_W * 1.16, CARD_H * 1.16),
    new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0, depthTest: false, depthWrite: false,
      colorWrite: false, side: THREE.DoubleSide,
    }),
  );
  hit.name = 'tarot-hit';
  hit.position.z = 0.012;
  g.add(flip, hit);
  g.userData.flip = flip;
  g.castShadow = false;
  g.frustumCulled = false;
  g.traverse((obj) => { obj.frustumCulled = false; });
  return g;
}

function makeDust() {
  const n = 48;
  const pos = new Float32Array(n * 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({
    color: GOLD, size: 0.018, transparent: true, opacity: 0,
    depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true,
  });
  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  return { pts, n, pos, seeds: Array.from({ length: n }, () => Math.random()) };
}

class TarotPlugin {
  readonly id = 'tarot';
  private stage: Stage;
  private root: THREE.Object3D | null = null;
  private avatar: Avatar | null = null;
  private rig = new THREE.Group();
  private ring: THREE.Group[] = [];
  private drawn: { mesh: THREE.Group; card: TarotCard; slot: THREE.Vector3 }[] = [];
  private dust = makeDust();
  private lamp = new THREE.PointLight(0xffe2a8, 0, 2.4, 2);
  private phase: Phase = 'off';
  private t = 0;
  private spin = 0;
  private chestY = 1.12;
  private dealIndex = 0;
  private lastTick = 0;
  private raf = 0;
  private hiddenRing = new Set<number>();
  private scatterFrom: THREE.Vector3[] = [];
  private scatterDir: THREE.Vector3[] = [];
  private backTex: THREE.Texture | null = null;
  private handler: RitualHandler = {};
  private hover: DrawnView | null = null;
  private hoverBlend: number[] = [];
  private hoverMiss = 0;
  private inspectIndex: number | null = null;
  private inspectBlend: number[] = [];
  private press: { x: number; y: number; index: number; kind: 'ring' | 'drawn' } | null = null;
  private offWait: Array<() => void> = [];
  private dealWait: Array<() => void> = [];
  private fronts: THREE.Texture[] = [];
  private pointer = new THREE.Vector2();
  private ray = new THREE.Raycaster();
  private bound = false;
  private tmp = new THREE.Vector3();
  private tmp2 = new THREE.Vector3();
  private tmp3 = new THREE.Vector3();
  private camQ = new THREE.Quaternion();
  private parentQ = new THREE.Quaternion();
  private ndc = new THREE.Vector3();
  private dockPos = new THREE.Vector3();
  private leaveFrom: THREE.Vector3[] = [];
  private leaveScale: number[] = [];
  private fanN = 0;
  private pickedFan = new Set<number>();
  private layout: TarotLayout = 'row';
  private revealed = new Set<number>();
  private flipT: number[] = [];
  private readySent = false;
  private ringMeta: { rad: number; yOff: number; wobble: number; lean: number; twist: number }[] = [];
  private fanHover = -1;
  private dressing = false;

  constructor(stage: Stage) {
    this.stage = stage;
    this.rig.name = 'tarot-rig';
    this.rig.visible = false;
    this.lamp.position.set(0, 1.2, 0.2);
    this.rig.add(this.lamp, this.dust.pts);
  }

  setRitualHandler(fn: RitualHandler | null) {
    this.handler = fn || {};
  }

  setFocusHandler(fn: RitualHandler['onFocus'] | null) {
    this.handler.onFocus = fn || undefined;
  }

  inspect(index: number | null) {
    if (this.phase !== 'table') return;
    if (index !== null && !this.revealed.has(index)) return;
    let next = index;
    if (next === this.inspectIndex) next = null;
    if (next !== null && (next < 0 || next >= this.drawn.length)) return;
    this.inspectIndex = next;
    this.handler.onFocus?.(next === null ? null : this.viewOf(next), 'inspect');
    if (next === null && this.hover) this.handler.onFocus?.(this.hover, 'hover');
  }

  get inspected() {
    return this.inspectIndex;
  }

  private viewOf(i: number): DrawnView {
    const c = this.drawn[i].card;
    return {
      index: i,
      name: this.revealed.has(i) ? c.name : '牌背',
      position: c.position,
      reversed: !!c.reversed,
      faceUp: this.revealed.has(i),
    };
  }

  onAvatarReady(root: THREE.Object3D, avatar: Avatar, _vrm: VRM | null) {
    this.attach(root, avatar);
  }

  onAvatarUnload() {
    this.detach();
  }

  onFrame(_dt: number) { /* rAF */ }

  async beginRing() {
    await this.boot();
    this.dropDrawnMeshes();
    this.fronts = [];
    this.phase = 'rise';
    this.t = 0;
    this.spin = 0;
    this.dealIndex = 0;
    this.hiddenRing.clear();
    this.pickedFan.clear();
    this.revealed.clear();
    this.flipT = [];
    this.readySent = false;
    this.fanN = 0;
    this.inspectIndex = null;
    this.press = null;
    this.fanHover = -1;
    this.hover = null;
    this.hoverBlend = [];
    this.hoverMiss = 0;
    await this.dressRing();
    this.rig.visible = true;
    this.rig.scale.setScalar(1);
    this.bindPointer();
    this.startLoop();
    for (const g of this.ring) {
      g.visible = true;
      g.scale.setScalar(1);
    }
  }

  presentFan(count: number, picked: number[] = []) {
    this.fanN = Math.max(1, Math.min(RING_N, count));
    this.pickedFan = new Set(picked);
    this.fanHover = -1;
    this.hoverBlend = [];
    this.hoverMiss = 0;
    this.hiddenRing.clear();
    for (let i = this.fanN; i < RING_N; i++) this.hiddenRing.add(i);
    for (const i of this.pickedFan) this.hiddenRing.add(i);
    this.phase = 'fan';
    this.t = 0;
  }

  markPicked(fanIndex: number) {
    this.pickedFan.add(fanIndex);
    this.hiddenRing.add(fanIndex);
  }

  async dealTable(cards: TarotCard[], layout: TarotLayout, revealed: number[] = []) {
    await this.boot();
    this.layout = layout || 'row';
    this.dropDrawnMeshes();
    this.fronts = await Promise.all(cards.map((c) => composeFront(c)));
    this.revealed = new Set(revealed);
    this.flipT = cards.map((_, i) => (this.revealed.has(i) ? 1 : 0));
    this.inspectBlend = cards.map(() => 0);
    this.hoverBlend = cards.map(() => 0);
    this.hover = null;
    this.hoverMiss = 0;
    this.inspectIndex = null;
    this.skinDrawn(cards);
    this.scatterFrom = this.ring.map((g) => g.position.clone());
    this.scatterDir = this.ring.map((g, i) => {
      const dir = g.position.clone();
      dir.y = 0;
      if (dir.lengthSq() < 0.0004) {
        const a = (i / RING_N) * Math.PI * 2;
        dir.set(Math.sin(a), 0, Math.cos(a));
      }
      dir.normalize();
      dir.y = -0.45 - (i % 5) * 0.06;
      return dir;
    });
    this.phase = 'deal';
    this.t = 0;
    this.dealIndex = 0;
    this.rig.visible = true;
    this.bindPointer();
    this.startLoop();
    return this.untilDeal();
  }

  revealAt(index: number) {
    if (index < 0 || index >= this.drawn.length) return false;
    this.revealed.add(index);
    if (this.flipT[index] === undefined) this.flipT[index] = 0;
    if (this.phase !== 'deal' && this.phase !== 'leave') this.phase = 'table';
    return true;
  }

  async appendCard(card: TarotCard, revealed = true, hostIndex: number | null = null) {
    if (!this.backTex) await this.boot();
    const front = await composeFront(card);
    this.fronts.push(front);
    const mesh = makeCard(front, this.backTex!);
    const slot = new THREE.Vector3();
    const host = (typeof hostIndex === 'number' && this.drawn[hostIndex])
      || this.drawn[Math.max(0, this.drawn.length - 1)];
    if (host) clarifierOffset(host.slot, slot);
    else slotOf(this.layout, this.drawn.length + 1, this.drawn.length, this.chestY, slot);
    mesh.position.copy(slot);
    this.rig.add(mesh);
    const i = this.drawn.length;
    this.drawn.push({ mesh, card, slot });
    this.inspectBlend.push(0);
    this.hoverBlend.push(0);
    this.flipT.push(revealed ? 1 : 0);
    if (revealed) this.revealed.add(i);
    this.phase = 'table';
  }

  async dismiss() {
    if (this.phase === 'off') return;
    this.inspectIndex = null;
    this.leaveFrom = this.drawn.map((d) => d.mesh.position.clone());
    this.leaveScale = this.drawn.map((d) => d.mesh.scale.x);
    this.phase = 'leave';
    this.t = 0;
    return this.untilOff();
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
    if (this.phase === 'off' || !this.rig.visible) return;
    if (this.dressing) return;
    this.chestY = this.readChestY();
    this.t += dt;
    this.spin += dt * this.spinSpeed();
    this.followAvatar();
    this.updateRing(dt);
    if (this.phase === 'deal' || this.phase === 'table' || this.phase === 'leave') this.updateDrawn(dt);
    this.updateDust(dt);
    this.updateLamp();
    this.billboard();
    if (this.phase === 'rise' && this.t >= RISE) this.toShuffle();
    else if (this.phase === 'shuffle' && this.t >= SHUFFLE) this.toCut();
    else if (this.phase === 'deal') this.tickDeal();
    else if (this.phase === 'leave' && this.t >= LEAVE) this.finishLeave();
  }

  peek(): DrawnView | null {
    return this.hover;
  }

  get open() {
    return this.phase !== 'off' && this.phase !== 'leave';
  }

  get currentPhase() {
    return this.phase;
  }

  dispose() {
    this.stopLoop();
    this.unbindPointer();
    this.dropDrawnMeshes();
    this.detach();
    disposeGpu(this.rig);
    disposeTarotTextures();
    this.phase = 'off';
    this.finishDeal();
    this.finishOff();
  }

  private untilDeal() {
    return new Promise<void>((resolve) => this.dealWait.push(resolve));
  }

  private untilOff() {
    return new Promise<void>((resolve) => this.offWait.push(resolve));
  }

  private finishDeal() {
    const q = this.dealWait.splice(0);
    for (const fn of q) fn();
  }

  private finishOff() {
    const q = this.offWait.splice(0);
    for (const fn of q) fn();
  }

  private attach(root: THREE.Object3D, avatar: Avatar) {
    this.detach();
    this.root = root;
    this.avatar = avatar;
    this.rig.scale.setScalar(1);
    const scene = this.stage.threeScene;
    if (scene && this.rig.parent !== scene) scene.add(this.rig);
  }

  private detach() {
    this.rig?.removeFromParent();
    this.root = null;
    this.avatar = null;
  }

  private followAvatar() {
    const root = this.root || this.stage.avatarRoot;
    if (!root) return;
    root.getWorldPosition(this.tmp);
    this.rig.position.set(this.tmp.x, 0, this.tmp.z);
  }

  private readChestY() {
    const bone = this.avatar?.bone('chest') || this.avatar?.bone('spine');
    if (!bone || !this.root) return 1.12;
    bone.getWorldPosition(this.tmp);
    return this.tmp.y;
  }

  private spinSpeed() {
    if (this.phase === 'shuffle') {
      const u = clamp01(this.t / SHUFFLE);
      return 0.55 + Math.sin(u * Math.PI) * 2.6;
    }
    if (this.phase === 'rise') return 0.35;
    if (this.phase === 'cut') return 0.12;
    if (this.phase === 'fan') return 0;
    if (this.phase === 'deal') return 0.18;
    if (this.phase === 'table') return 0.05;
    return 0.08;
  }

  private async boot() {
    if (!this.root) {
      const root = this.stage.avatarRoot;
      const avatar = this.stage.currentAvatar;
      if (root && avatar) this.attach(root, avatar);
    }
    if (!this.rig.parent && this.stage.threeScene) {
      this.stage.threeScene.add(this.rig);
    }
    await this.ensureRing();
  }

  private async ensureRing() {
    if (this.ring.length === RING_N) return;
    for (const g of this.ring) {
      g.removeFromParent();
      disposeGpu(g);
    }
    this.ring = [];
    this.backTex = await loadBackTexture('/assets/tarot/back.png');
    for (let i = 0; i < RING_N; i++) {
      const g = makeCard(this.backTex, this.backTex);
      g.visible = false;
      this.ring.push(g);
      this.rig.add(g);
    }
    this.rollRingMeta();
  }

  private rollRingMeta() {
    this.ringMeta = Array.from({ length: RING_N }, (_, i) => ({
      rad: RING_R * (0.78 + ((i * 17) % 11) / 40 + Math.random() * 0.12),
      yOff: ((i % 7) - 3) * 0.034 + (Math.random() - 0.5) * 0.04,
      wobble: 0.55 + (i % 5) * 0.13,
      lean: 0.22 + (i % 4) * 0.08,
      twist: (i % 2 === 0 ? 1 : -1) * (0.08 + (i % 3) * 0.04),
    }));
  }

  private async dressRing() {
    this.dressing = true;
    try {
      await this.ensureRing();
      this.rollRingMeta();
      if (!this.backTex) this.backTex = await loadBackTexture('/assets/tarot/back.png');
      for (const g of this.ring) {
        g.visible = true;
        g.scale.setScalar(1);
      }
    } finally {
      this.dressing = false;
    }
  }

  private dropDrawnMeshes() {
    for (const d of this.drawn) {
      if (this.ring.includes(d.mesh)) continue;
      d.mesh.removeFromParent();
      disposeGpu(d.mesh);
    }
    this.drawn = [];
    this.fronts = [];
  }

  private writeInspectSlot(out: THREE.Vector3) {
    const cam = this.stage.threeCamera;
    if (!cam) {
      out.set(0.16, this.chestY * 0.72, 0.42);
      return;
    }
    this.ndc.set(0.16, 0.08, 0.5).unproject(cam);
    this.tmp2.copy(this.ndc).sub(cam.position);
    const dist = this.tmp2.length() || 1;
    out.copy(cam.position).addScaledVector(this.tmp2, INSPECT_DIST / dist);
    this.rig.worldToLocal(out);
  }

  private ringPos(i: number, y: number, radius: number, out: THREE.Vector3) {
    const meta = this.ringMeta[i];
    const n = Math.max(1, RING_N);
    const a = this.spin + (i / n) * Math.PI * 2;
    const amp = Math.max(0.35, radius / RING_R);
    const rx = 1.22 * amp * ((meta?.rad ?? RING_R) / RING_R);
    const ry = 0.16 * amp;
    const rz = 0.30 * amp;
    const bob = Math.sin(this.t * (meta?.wobble ?? 1) + i * 0.7) * 0.05;
    out.set(
      Math.sin(a) * rx,
      y + (meta?.yOff ?? 0) + Math.cos(a * 2) * ry + bob,
      0.52 + Math.cos(a) * rz,
    );
  }

  private fanPos(i: number, out: THREE.Vector3) {
    const n = Math.max(1, this.fanN);
    const span = Math.min(1.72, 0.13 * n);
    const u = n === 1 ? 0.5 : i / (n - 1);
    const a = -span / 2 + span * u;
    const arc = 0.58;
    out.set(
      Math.sin(a) * arc,
      this.chestY - 0.18 + Math.cos(a) * 0.04,
      0.52 + Math.cos(a) * 0.22,
    );
  }

  private toShuffle() {
    this.phase = 'shuffle';
    this.t = 0;
  }

  private toCut() {
    this.phase = 'cut';
    this.t = 0;
    if (!this.readySent) {
      this.readySent = true;
      this.handler.onShuffleReady?.();
    }
  }

  private skinDrawn(cards: TarotCard[]) {
    if (!this.backTex) return;
    const n = cards.length;
    for (let i = 0; i < n; i++) {
      const srcIdx = Math.min(RING_N - 1, cards[i].fan_index ?? ((i * 5 + 3) % RING_N));
      const src = this.ring[srcIdx] || this.ring[0];
      const front = this.fronts[i] || this.backTex;
      const mesh = makeCard(front, this.backTex);
      mesh.position.copy(src.position);
      mesh.quaternion.copy(src.quaternion);
      mesh.scale.copy(src.scale);
      this.rig.add(mesh);
      src.visible = false;
      this.hiddenRing.add(srcIdx);
      const slot = new THREE.Vector3();
      if (cards[i].clarifier && this.drawn.length) {
        clarifierOffset(this.drawn[this.drawn.length - 1].slot, slot);
      } else {
        slotOf(this.layout, n, i, this.chestY, slot);
      }
      this.drawn.push({ mesh, card: cards[i], slot });
      mesh.userData.tarotIndex = i;
    }
  }

  private applyFlipHover(mesh: THREE.Object3D, k: number) {
    const flip = (mesh.userData.flip as THREE.Object3D | undefined) || null;
    if (!flip || flip === mesh) return;
    const t = clamp01(k);
    flip.position.y = t * HOVER_LIFT;
    flip.scale.setScalar(1 + t * HOVER_GROW);
  }

  private hitPads(roots: THREE.Object3D[]) {
    const pads: THREE.Object3D[] = [];
    for (const root of roots) {
      const hit = root.getObjectByName('tarot-hit');
      pads.push(hit || root);
    }
    return pads;
  }

  private setHover(view: DrawnView | null) {
    this.hoverMiss = 0;
    if (this.hover?.index === (view?.index ?? -1)) return;
    this.hover = view;
    this.handler.onFocus?.(view, 'hover');
  }

  private writeSlot(item: { mesh: THREE.Group; card: TarotCard; slot: THREE.Vector3 }, n: number) {
    if (item.card.clarifier) {
      const base = String(item.card.position || '').split('·')[0];
      const host = this.drawn.find((d) => !d.card.clarifier && d.card.position === base);
      if (host) {
        clarifierOffset(host.slot, item.slot);
        return;
      }
    }
    const main = Math.max(1, this.drawn.filter((d) => !d.card.clarifier).length);
    const idx = item.card.clarifier ? n - 1 : (item.card.index ?? this.drawn.indexOf(item));
    slotOf(this.layout, main, Math.max(0, idx), this.chestY, item.slot);
  }

  private tickDeal() {
    const n = this.drawn.length;
    if (!n) {
      this.phase = 'table';
      this.t = 0;
      this.finishDeal();
      return;
    }
    const elapsed = this.t;
    const done = Math.min(n, Math.floor(elapsed / DEAL_STAGGER) + 1);
    if (done > this.dealIndex) this.dealIndex = done;
    if (elapsed >= DEAL_STAGGER * Math.max(0, n - 1) + DEAL_ONE + 0.08) {
      this.phase = 'table';
      this.t = 0;
      this.finishDeal();
    }
  }

  private cardFace(i: number) {
    const cur = this.flipT[i] ?? (this.revealed.has(i) ? 1 : 0);
    if (this.phase === 'deal') {
      const landed = clamp01((this.t - i * DEAL_STAGGER) / DEAL_ONE) >= 0.98;
      if (!landed) return 0;
    }
    return easeInOut(clamp01(cur));
  }

  private finishLeave() {
    this.phase = 'off';
    this.t = 0;
    this.rig.visible = false;
    this.stopLoop();
    this.unbindPointer();
    for (const d of this.drawn) {
      d.mesh.removeFromParent();
      disposeGpu(d.mesh);
    }
    this.drawn = [];
    this.hiddenRing.clear();
    this.pickedFan.clear();
    this.revealed.clear();
    for (const g of this.ring) {
      g.visible = true;
      g.scale.setScalar(1);
    }
    this.hover = null;
    this.hoverBlend = [];
    this.hoverMiss = 0;
    this.inspectIndex = null;
    this.inspectBlend = [];
    this.handler.onFocus?.(null, 'inspect');
    this.finishDeal();
    this.finishOff();
  }

  private updateRing(dt: number) {
    const rise = this.phase === 'rise' ? easeOut(clamp01(this.t / RISE)) : 1;
    const y0 = 0.08;
    const y1 = this.chestY;
    const scattering = this.phase === 'deal' || this.phase === 'table' || this.phase === 'leave';
    const scatterU = this.phase === 'deal'
      ? easeInOut(clamp01(this.t / SCATTER))
      : (scattering ? 1 : 0);

    for (let i = 0; i < this.ring.length; i++) {
      const g = this.ring[i];
      if (this.hiddenRing.has(i)) {
        g.visible = false;
        continue;
      }
      if (scattering) {
        const from = this.scatterFrom[i] || g.position;
        const dir = this.scatterDir[i] || new THREE.Vector3(0, -1, 0);
        const u = scatterU;
        g.position.copy(from).addScaledVector(dir, u * 1.85);
        g.position.y += Math.sin(u * Math.PI) * 0.08;
        g.scale.setScalar(Math.max(0, 1 - u));
        g.rotation.x = 0.12 + u * 1.1;
        g.rotation.z = u * (i % 2 === 0 ? 1.4 : -1.4);
        g.visible = u < 0.97;
        continue;
      }
      if (this.phase === 'fan' && i < this.fanN) {
        this.fanPos(i, g.position);
        const mid = (this.fanN - 1) / 2;
        const want = this.fanHover === i ? 1 : 0;
        const cur = this.hoverBlend[i] ?? 0;
        this.hoverBlend[i] = cur + (want - cur) * (1 - Math.exp(-dt * HOVER_EASE));
        g.scale.setScalar(0.94);
        this.applyFlipHover(g, this.hoverBlend[i]);
        g.rotation.set(
          0.52,
          Math.PI * 0.94,
          (i - mid) * 0.09,
        );
        g.visible = true;
        continue;
      }
      this.applyFlipHover(g, 0);
      const y = THREE.MathUtils.lerp(y0, y1, rise);
      const rad = RING_R * (0.42 + 0.58 * rise) * (this.phase === 'cut' ? 0.94 : 1);
      const s = 0.18 + 0.82 * rise;
      this.ringPos(i, y, rad, g.position);
      g.scale.setScalar(s);
      const a = this.spin + (i / RING_N) * Math.PI * 2;
      const meta = this.ringMeta[i];
      const shuffle = this.phase === 'shuffle';
      const tumble = shuffle ? Math.sin(this.t * 4.2 + i) * 0.45 : 0;
      const show = shuffle
        ? (0.5 + 0.5 * Math.sin(this.t * 2.2 + i * 0.8)) * Math.PI
        : (i % 4 === 0 ? 0.22 : 0.04);
      g.rotation.set(
        0.14 + tumble,
        show,
        (meta?.twist ?? 0) + (shuffle ? Math.sin(this.t * 3.1 + i) * 0.28 : 0.04),
      );
      g.visible = this.phase !== 'off';
    }
  }

  private updateDrawn(dt: number) {
    const n = this.drawn.length;
    const inspecting = this.inspectIndex !== null;
    const scale0 = cardScale(n);
    for (let i = 0; i < n; i++) {
      const item = this.drawn[i];
      const mesh = item.mesh;
      const want = this.inspectIndex === i ? 1 : 0;
      const blend = this.inspectBlend[i] ?? 0;
      this.inspectBlend[i] = blend + (want - blend) * (1 - Math.exp(-dt * 9));
      const k = easeInOut(clamp01(this.inspectBlend[i]));
      const hoverHere = this.hover?.index === i && this.inspectIndex !== i;
      const wantH = hoverHere ? 1 : 0;
      const curH = this.hoverBlend[i] ?? 0;
      this.hoverBlend[i] = curH + (wantH - curH) * (1 - Math.exp(-dt * HOVER_EASE));
      const dim = inspecting && this.inspectIndex !== i ? 0.84 : 1;
      mesh.renderOrder = k > 0.15 ? 40 : 2;
      mesh.traverse((obj) => {
        const face = obj.userData.tarotFace as string | undefined;
        obj.renderOrder = mesh.renderOrder + (face === 'front' ? 1 : 0);
        if (obj.name === 'tarot-hit') return;
        const m = obj as THREE.Mesh;
        if (!m.isMesh) return;
        if (face === 'front' || face === 'back') {
          setPaperLook(m, k);
          return;
        }
        const mats = Array.isArray(m.material) ? m.material : [m.material];
        for (const mat of mats) {
          if (!mat) continue;
          mat.depthTest = k < 0.35;
          dressRim(mat, k);
        }
      });

      const target = this.revealed.has(i) ? 1 : 0;
      const cur = this.flipT[i] ?? 0;
      const flipSpeed = this.inspectIndex === i ? 16 : (6 / FLIP_ONE);
      this.flipT[i] = cur + (target - cur) * (1 - Math.exp(-dt * flipSpeed));
      if (Math.abs(target - this.flipT[i]) < 0.002) this.flipT[i] = target;

      if (this.phase === 'leave') {
        const u = easeInOut(clamp01(this.t / LEAVE));
        const from = this.leaveFrom[i] || mesh.position;
        mesh.position.copy(from);
        mesh.position.y -= u * 0.55;
        mesh.scale.setScalar((this.leaveScale[i] ?? 1) * (1 - u));
        continue;
      }

      if (this.phase === 'deal') {
        const start = i * DEAL_STAGGER;
        const u = easeInOut(clamp01((this.t - start) / DEAL_ONE));
        const srcIdx = Math.min(RING_N - 1, item.card.fan_index ?? ((i * 5 + 3) % RING_N));
        this.ringPos(srcIdx, this.chestY, RING_R, this.tmp3);
        this.writeSlot(item, n);
        mesh.position.lerpVectors(this.tmp3, item.slot, u);
        mesh.position.y += Math.sin(u * Math.PI) * 0.16;
        mesh.scale.setScalar(THREE.MathUtils.lerp(0.92, scale0, u));
        this.applyFlipHover(mesh, this.hoverBlend[i] * u);
        continue;
      }

      this.writeSlot(item, n);
      this.tmp3.copy(item.slot);
      this.tmp3.y += (this.hoverBlend[i] ?? 0) > 0.08 ? 0 : Math.sin(this.t * 1.3 + i) * 0.01;
      const homeScale = scale0 * dim;
      this.applyFlipHover(mesh, k > 0.15 ? 0 : this.hoverBlend[i]);
      if (k < 0.002) {
        mesh.position.copy(this.tmp3);
        mesh.scale.setScalar(homeScale);
        continue;
      }
      this.writeInspectSlot(this.dockPos);
      mesh.position.lerpVectors(this.tmp3, this.dockPos, k);
      mesh.scale.setScalar(THREE.MathUtils.lerp(homeScale, INSPECT_SCALE, k));
    }
  }

  private billboard() {
    const cam = this.stage.threeCamera;
    if (!cam) return;
    if (this.phase === 'off' || this.phase === 'rise' || this.phase === 'shuffle' || this.phase === 'cut'
      || this.phase === 'fan' || this.phase === 'leave') return;
    cam.getWorldQuaternion(this.camQ);
    this.rig.getWorldQuaternion(this.parentQ).invert();
    for (let i = 0; i < this.drawn.length; i++) {
      const item = this.drawn[i];
      const face = this.cardFace(i);
      item.mesh.quaternion.copy(this.camQ).premultiply(this.parentQ);
      const flip = (item.mesh.userData.flip as THREE.Object3D | undefined) || item.mesh;
      flip.rotation.y = Math.PI * (1 - face);
      flip.rotation.z = (item.card.reversed && face > 0.55)
        ? THREE.MathUtils.lerp(0, Math.PI, clamp01((face - 0.55) / 0.45))
        : 0;
    }
  }

  private updateDust(dt: number) {
    const mat = this.dust.pts.material as THREE.PointsMaterial;
    const live = this.phase === 'shuffle' || this.phase === 'deal' || this.phase === 'rise' || this.phase === 'cut';
    const target = live ? 0.55 : (this.phase === 'fan' ? 0.22 : 0);
    mat.opacity = THREE.MathUtils.lerp(mat.opacity, target, 1 - Math.exp(-dt * 4));
    const arr = this.dust.pos;
    for (let i = 0; i < this.dust.n; i++) {
      const seed = this.dust.seeds[i];
      const a = this.spin * 1.4 + seed * Math.PI * 2;
      const r = RING_R * (0.7 + seed * 0.5);
      arr[i * 3] = Math.sin(a) * r;
      arr[i * 3 + 1] = this.chestY + Math.sin(this.t * 2 + seed * 6) * 0.12;
      arr[i * 3 + 2] = Math.cos(a) * r;
    }
    (this.dust.pts.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
  }

  private updateLamp() {
    if (this.phase === 'table' || this.phase === 'deal' || this.inspectIndex !== null) {
      this.lamp.intensity = 0;
    } else if (this.phase === 'shuffle' || this.phase === 'cut' || this.phase === 'fan') {
      this.lamp.position.set(0, this.chestY + 0.46, 0.68);
      this.lamp.distance = 1.7;
      this.lamp.intensity = this.phase === 'fan' ? 0.26 : 0.18;
    } else {
      this.lamp.intensity = this.phase === 'off' ? 0 : 0.16;
    }
  }

  private bindPointer() {
    if (this.bound) return;
    const el = this.stage.canvas;
    if (!el) return;
    this.bound = true;
    el.addEventListener('pointermove', this.onMove);
    el.addEventListener('pointerleave', this.onLeave);
    el.addEventListener('pointerdown', this.onDown);
    window.addEventListener('pointerup', this.onUp);
    window.addEventListener('pointercancel', this.onUp);
    window.addEventListener('keydown', this.onKey);
  }

  private unbindPointer() {
    const el = this.stage.canvas;
    if (!this.bound) return;
    this.bound = false;
    el?.removeEventListener('pointermove', this.onMove);
    el?.removeEventListener('pointerleave', this.onLeave);
    el?.removeEventListener('pointerdown', this.onDown);
    window.removeEventListener('pointerup', this.onUp);
    window.removeEventListener('pointercancel', this.onUp);
    window.removeEventListener('keydown', this.onKey);
    if (el) el.style.cursor = '';
  }

  private onKey = (ev: KeyboardEvent) => {
    if (ev.key !== 'Escape') return;
    if (this.inspectIndex === null) return;
    ev.preventDefault();
    this.inspect(null);
  };

  private onLeave = () => {
    this.hoverMiss = HOVER_MISS;
    if (this.phase === 'fan') this.fanHover = -1;
    if (this.phase === 'table' || this.phase === 'deal') this.setHover(null);
    const el = this.stage.canvas;
    if (el && this.inspectIndex === null && this.phase !== 'cut') el.style.cursor = '';
  };

  private onMove = (ev: PointerEvent) => {
    const hit = this.hitAny(ev);
    const el = this.stage.canvas;
    if (el) {
      const live = this.phase === 'cut' || this.phase === 'fan' || this.phase === 'table';
      const over = !!(hit || this.hover || this.fanHover >= 0);
      el.style.cursor = (over || this.inspectIndex !== null || (live && this.phase === 'cut')) ? 'pointer' : '';
    }
    if (this.phase === 'fan') {
      if (hit && hit.kind === 'ring') {
        this.fanHover = hit.index;
        this.hoverMiss = 0;
      } else if (this.fanHover >= 0) {
        this.hoverMiss += 1;
        if (this.hoverMiss >= HOVER_MISS) this.fanHover = -1;
      }
      return;
    }
    if (this.phase !== 'table' && this.phase !== 'deal') return;
    const view = hit && hit.kind === 'drawn' ? this.viewOf(hit.index) : null;
    if (view) {
      this.setHover(view);
      return;
    }
    if (!this.hover) return;
    this.hoverMiss += 1;
    if (this.hoverMiss >= HOVER_MISS) this.setHover(null);
  };

  private onDown = (ev: PointerEvent) => {
    if (ev.button !== 0) return;
    const hit = this.hitAny(ev);
    this.press = hit
      ? { x: ev.clientX, y: ev.clientY, index: hit.index, kind: hit.kind }
      : { x: ev.clientX, y: ev.clientY, index: -1, kind: 'drawn' };
    if (hit || this.inspectIndex !== null || this.phase === 'cut') ev.stopPropagation();
  };

  private onUp = (ev: PointerEvent) => {
    if (!this.press) return;
    const press = this.press;
    this.press = null;
    if (ev.button !== 0 && ev.type === 'pointerup') return;
    const moved = Math.hypot(ev.clientX - press.x, ev.clientY - press.y);
    if (moved > 10) return;
    if (this.phase === 'cut') {
      this.handler.onCut?.(`${ev.clientX},${ev.clientY},${performance.now()}`);
      return;
    }
    if (this.phase === 'fan' && press.kind === 'ring' && press.index >= 0) {
      this.handler.onPick?.(press.index);
      return;
    }
    if ((this.phase === 'table' || this.phase === 'deal') && press.kind === 'drawn' && press.index >= 0) {
      if (!this.revealed.has(press.index)) {
        this.handler.onReveal?.(press.index);
        return;
      }
      if (this.phase === 'table') this.handler.onAsk?.(press.index);
      return;
    }
    if (this.phase === 'table' && this.inspectIndex !== null) this.inspect(null);
  };

  private hitAny(ev: PointerEvent): { kind: 'ring' | 'drawn'; index: number } | null {
    const cam = this.stage.threeCamera;
    const el = this.stage.canvas;
    if (!cam || !el) return null;
    if (this.phase !== 'cut' && this.phase !== 'fan' && this.phase !== 'table' && this.phase !== 'deal') return null;
    const rec = el.getBoundingClientRect();
    this.pointer.x = ((ev.clientX - rec.left) / rec.width) * 2 - 1;
    this.pointer.y = -((ev.clientY - rec.top) / rec.height) * 2 + 1;
    this.ray.setFromCamera(this.pointer, cam);
    this.ray.far = 24;
    if (this.phase === 'table' || this.phase === 'deal') {
      const hits = this.ray.intersectObjects(this.hitPads(this.drawn.map((d) => d.mesh)), false);
      const found: number[] = [];
      for (const h of hits) {
        const idx = this.drawn.findIndex((d) => belongs(h.object, d.mesh));
        if (idx < 0 || found.includes(idx)) continue;
        found.push(idx);
      }
      if (this.hover && found.includes(this.hover.index)) {
        return { kind: 'drawn', index: this.hover.index };
      }
      const back = found.find((i) => !this.revealed.has(i));
      if (back !== undefined) return { kind: 'drawn', index: back };
      if (found.length) return { kind: 'drawn', index: found[0] };
      return null;
    }
    const visible = this.ring.filter((g, i) => !this.hiddenRing.has(i) && g.visible);
    const hits = this.ray.intersectObjects(this.hitPads(visible), false);
    if (this.phase === 'fan' && this.fanHover >= 0) {
      const keep = hits.find((h) => {
        const idx = this.ring.findIndex((g) => belongs(h.object, g));
        return idx === this.fanHover;
      });
      if (keep) return { kind: 'ring', index: this.fanHover };
    }
    if (!hits.length) {
      if (this.phase === 'cut') return { kind: 'ring', index: 0 };
      return null;
    }
    const obj = hits[0].object;
    const idx = this.ring.findIndex((g) => belongs(obj, g));
    if (idx < 0) return this.phase === 'cut' ? { kind: 'ring', index: 0 } : null;
    return { kind: 'ring', index: idx };
  }
}

function belongs(obj: THREE.Object3D, root: THREE.Object3D) {
  let n: THREE.Object3D | null = obj;
  while (n) {
    if (n === root) return true;
    n = n.parent;
  }
  return false;
}

function disposeGpu(root: THREE.Object3D) {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry?.dispose();
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) {
      if (mat) mat.dispose();
    }
  });
}

let plugin: TarotPlugin | null = null;

export function installTarot(stage: Stage) {
  if (plugin) return plugin;
  plugin = new TarotPlugin(stage);
  const root = stage.avatarRoot;
  const avatar = stage.currentAvatar;
  if (root && avatar) plugin.onAvatarReady(root, avatar, null);
  stage.use(plugin);
  return plugin;
}

export function getTarotPlugin() {
  return plugin;
}

export function uninstallTarot(stage: Stage) {
  if (!plugin) return;
  plugin.dispose();
  stage.unuse('tarot');
  plugin = null;
}
