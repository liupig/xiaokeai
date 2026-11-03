import * as THREE from 'three';
import { stage } from '../../engine/stage';
import { faceMark } from './cards';
import { artUrl } from './copy';

const CARD_W = 0.172;
const CARD_H = 0.258;
const GEO = new THREE.PlaneGeometry(CARD_W, CARD_H);

export interface TavernBoard {
  phase: string;
  truth: string;
  hand: { id: string; face: string }[];
  selected: string[];
  seats: { id: string; alive: boolean; cards: number }[];
  pile: number;
  pileFrom: string;
  /** 这一手的序号。变了才重新飞一次，避免每帧重播。 */
  pileSeq?: number;
  /** 只有 KE 自己打出的牌才有牌面，飞的时候翻过去。别人的牌始终是牌背。 */
  pileFaces?: string[];
  reveal: string[];
  focus: string;
  faces?: string[];
}

interface Slot {
  key: string;
  art: string;
  faceUp: boolean;
  x: number;
  y: number;
  z: number;
  rotZ: number;
  scale: number;
  pick?: string;
  /** 钉在桌面上，不跟角色走。 */
  fixed?: boolean;
  nx?: number;
  ny?: number;
  /** 新牌从这里飞出来，再落到 nx/ny。 */
  bornNx?: number;
  bornNy?: number;
  /** 从 KE 手里这张牌的位置起飞。 */
  bornId?: string;
  /** 正在从手里飘到落点。 */
  glide?: boolean;
  /** 朝镜头再近一点，选中的牌压在其余牌前面。 */
  near?: number;
  /** 按当前镜头把这一排排开，排不下就缩小，不重叠。 */
  fit?: { center: number; index: number; count: number; max: number; base: number };
  extraScale?: number;
  /** 从牌背翻到正面。 */
  flipIn?: boolean;
  hot?: boolean;
}

const texCache = new Map<string, THREE.Texture>();

function cornerOf(url: string, faceUp: boolean) {
  if (!faceUp) return '';
  const file = decodeURIComponent((url.split('?')[0].split('/').pop() || '')).replace(/\.jpe?g$/i, '');
  if (!file || file === 'back') return '';
  return faceMark(file);
}

function paintCorners(g: CanvasRenderingContext2D, w: number, h: number, text: string) {
  const size = Math.max(28, Math.round(w * 0.078));
  g.font = `600 ${size}px "Microsoft YaHei", "Segoe UI", sans-serif`;
  g.textBaseline = 'top';
  const pad = Math.round(w * 0.045);
  const width = g.measureText(text).width + size * 0.85;
  const height = size * 1.45;
  const plate = (x: number, y: number, flip: boolean) => {
    g.save();
    g.translate(x, y);
    if (flip) g.rotate(Math.PI);
    g.fillStyle = 'rgba(12, 8, 16, 0.78)';
    g.fillRect(0, 0, width, height);
    g.fillStyle = '#f3d48a';
    g.fillText(text, size * 0.32, size * 0.2);
    g.restore();
  };
  plate(pad, pad, false);
  plate(w - pad, h - pad, true);
}

function textureOf(url: string, mark = '') {
  const key = `${url}|${mark}`;
  const hit = texCache.get(key);
  if (hit) return hit;
  const tex = new THREE.Texture();
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.generateMipmaps = false;
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  texCache.set(key, tex);
  const img = new Image();
  img.onload = () => {
    const face = document.createElement('canvas');
    face.width = img.naturalWidth || 768;
    face.height = img.naturalHeight || 1152;
    const g = face.getContext('2d');
    if (!g) return;
    g.drawImage(img, 0, 0, face.width, face.height);
    if (mark) paintCorners(g, face.width, face.height, mark);
    tex.image = face;
    tex.needsUpdate = true;
  };
  img.src = url;
  return tex;
}

function tintCard(card: THREE.Group, hot: boolean) {
  const hex = hot ? 0xffffff : 0x6a645c;
  const front = card.getObjectByName('front') as THREE.Mesh | undefined;
  const back = card.getObjectByName('back') as THREE.Mesh | undefined;
  for (const mesh of [front, back]) {
    const mat = mesh?.material as THREE.MeshBasicMaterial | undefined;
    if (mat && mat.color.getHex() !== hex) mat.color.setHex(hex);
  }
}

function paper(map: THREE.Texture) {
  return new THREE.MeshBasicMaterial({
    map,
    color: 0xa69f93,
    toneMapped: false,
    side: THREE.FrontSide,
  });
}

function gold() {
  return new THREE.MeshBasicMaterial({ color: 0x8a7040, toneMapped: false });
}

function makeRim(w: number, h: number, t: number) {
  const g = new THREE.Group();
  const mat = gold();
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
  flip.name = 'flip';
  const t = 0.0022;
  const fm = new THREE.Mesh(GEO, paper(front));
  fm.name = 'front';
  fm.position.z = t / 2;
  const bm = new THREE.Mesh(GEO, paper(back));
  bm.name = 'back';
  bm.rotation.y = Math.PI;
  bm.position.z = -t / 2;
  flip.add(fm, bm, makeRim(CARD_W, CARD_H, t));
  g.add(flip);
  g.userData.flip = flip;
  g.frustumCulled = false;
  g.traverse((obj) => { obj.frustumCulled = false; });
  return g;
}

function paintMap(group: THREE.Group, name: string, tex: THREE.Texture) {
  const mesh = group.getObjectByName(name) as THREE.Mesh | undefined;
  const mat = mesh?.material as THREE.MeshBasicMaterial | undefined;
  if (!mat || mat.map === tex) return;
  mat.map = tex;
  mat.needsUpdate = true;
}

function disposeObj(obj: THREE.Object3D) {
  obj.traverse((node) => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) mat?.dispose();
  });
}

class TavernPlugin {
  readonly id = 'tavern';
  private rig = new THREE.Group();
  private desk = new THREE.Group();
  private cards = new Map<string, THREE.Group>();
  private slots: Slot[] = [];
  private back: THREE.Texture = textureOf(artUrl('back'));
  private onPick: (id: string) => void = () => {};
  private bound = false;
  private pointer = new THREE.Vector2();
  private ray = new THREE.Raycaster();
  private camQ = new THREE.Quaternion();
  private parentQ = new THREE.Quaternion();
  private tmp = new THREE.Vector3();
  private ndc = new THREE.Vector3();
  private dir = new THREE.Vector3();
  private root: THREE.Object3D | null = null;
  private chestY = 1.12;
  private backUrl = '';
  private last: TavernBoard | null = null;

  constructor() {
    this.rig.name = 'tavern-rig';
    this.desk.name = 'tavern-desk';
    this.rig.visible = false;
    this.desk.visible = false;
    this.onDown = this.onDown.bind(this);
    this.onMove = this.onMove.bind(this);
  }

  setPick(fn: (id: string) => void) {
    this.onPick = fn;
  }

  show(board: TavernBoard) {
    this.last = board;
    this.ensureBack();
    this.slots = layout(board);
    this.rig.visible = true;
    this.desk.visible = true;
    this.ensure();
    this.bind();
    this.attach();
  }

  hide() {
    this.slots = [];
    this.rig.visible = false;
    this.desk.visible = false;
    this.dropSpare(new Set());
    this.unbind();
  }

  onAvatarReady = (root: THREE.Object3D) => {
    this.root = root;
    if (stage.threeScene && this.rig.parent !== stage.threeScene) stage.threeScene.add(this.rig);
  };

  onAvatarUnload = () => {
    this.root = null;
    this.rig.removeFromParent();
  };

  onFrame = (dt: number) => {
    try {
    this.follow();
    for (const slot of this.slots) {
      const card = this.cards.get(slot.key);
      if (!card) continue;
      const home = slot.fixed ? this.desk : this.rig;
      if (card.parent !== home) home.add(card);
      let tx = slot.x;
      let ty = this.chestY + slot.y;
      let tz = slot.z;
      if (slot.fit && stage.threeCamera) {
        const fit = spread(stage.threeCamera, slot.fit.base, slot.fit.count, slot.fit.max);
        const mid = (slot.fit.count - 1) / 2;
        slot.nx = slot.fit.center + (slot.fit.index - mid) * fit.step;
        slot.scale = fit.scale + (slot.extraScale || 0);
      }
      if (slot.fixed && slot.nx != null && slot.ny != null) {
        this.placeView(slot.nx, slot.ny, 1.35, this.tmp);
        tx = this.tmp.x;
        ty = this.tmp.y;
        tz = this.tmp.z;
      }
      if (slot.near && stage.threeCamera) {
        const e = stage.threeCamera.matrixWorld.elements;
        tx += -e[8] * slot.near;
        ty += -e[9] * slot.near;
        tz += -e[10] * slot.near;
      }
      const flight = card.userData.flight as { from: THREE.Vector3; t: number } | undefined;
      if (flight && flight.t < 1) {
        flight.t = Math.min(1, flight.t + dt / 0.9);
        const ease = 1 - (1 - flight.t) ** 3;
        this.tmp.set(tx, ty, tz);
        card.position.lerpVectors(flight.from, this.tmp, ease);
        const cam = stage.threeCamera;
        if (cam) {
          const e = cam.matrixWorld.elements;
          const arc = Math.sin(Math.PI * flight.t) * 0.18;
          card.position.x += e[4] * arc;
          card.position.y += e[5] * arc;
          card.position.z += e[6] * arc;
        }
        if (flight.t >= 1) delete card.userData.flight;
      } else {
        const dist = Math.hypot(tx - card.position.x, ty - card.position.y, tz - card.position.z);
        const rate = dist > 0.22 ? 3.4 : 9;
        const fly = 1 - Math.exp(-dt * rate);
        card.position.x += (tx - card.position.x) * fly;
        card.position.y += (ty - card.position.y) * fly;
        card.position.z += (tz - card.position.z) * fly;
      }
      const s = card.scale.x + (slot.scale - card.scale.x) * (1 - Math.exp(-dt * 8));
      card.scale.setScalar(s);
      this.faceCamera(card, slot.rotZ);
      const flip = card.userData.flip as THREE.Group;
      const want = slot.faceUp ? 0 : Math.PI;
      const turning = card.userData.flight ? 4 : (slot.flipIn ? 1.35 : 8);
      const spin = 1 - Math.exp(-dt * turning);
      flip.rotation.y += (want - flip.rotation.y) * spin;
      tintCard(card, slot.hot !== false);
    }
    } catch {
      /* 一帧算坏了就跳过，别把整张舞台的渲染掐掉。 */
    }
  };

  dispose() {
    this.hide();
    this.rig.removeFromParent();
    this.desk.removeFromParent();
    for (const card of this.cards.values()) {
      card.removeFromParent();
      disposeObj(card);
    }
    this.cards.clear();
    for (const tex of texCache.values()) tex.dispose();
    texCache.clear();
  }

  private ensureBack() {
    const url = artUrl('back');
    if (url === this.backUrl && this.back) return;
    this.backUrl = url;
    this.back = textureOf(url);
  }

  restyle() {
    if (!this.last) return;
    for (const tex of texCache.values()) tex.dispose();
    texCache.clear();
    this.backUrl = '';
    this.show(this.last);
  }

  private ensure() {
    const keep = new Set(this.slots.map((s) => s.key));
    const births = new Map<string, THREE.Vector3>();
    for (const slot of this.slots) {
      if (!slot.glide || this.cards.has(slot.key) || !slot.bornId) continue;
      const src = this.cards.get(`hand:${slot.bornId}`);
      if (src) births.set(slot.key, src.position.clone());
    }
    this.dropSpare(keep);
    for (const slot of this.slots) {
      let card = this.cards.get(slot.key);
      if (!card) {
        card = makeCard(textureOf(slot.art, cornerOf(slot.art, slot.faceUp)), this.back);
        const remembered = births.get(slot.key);
        let born: THREE.Vector3 | null = remembered || null;
        if (!born && slot.glide && slot.bornNx != null && slot.bornNy != null) {
          this.placeView(slot.bornNx, slot.bornNy, 1.35, this.tmp);
          born = this.tmp.clone();
        }
        if (slot.fixed && slot.nx != null && slot.ny != null) {
          this.placeView(slot.nx, slot.ny, 1.35, this.tmp);
          card.position.copy(born || this.tmp);
          this.desk.add(card);
        } else if (born) {
          card.position.copy(born);
          this.desk.add(card);
        } else {
          card.position.set(slot.x, this.chestY + slot.y - 0.2, slot.z);
          this.rig.add(card);
        }
        const flip = card.userData.flip as THREE.Group;
        if (slot.flipIn || !slot.bornId) flip.rotation.y = Math.PI;
        if (born && slot.glide) {
          card.userData.flight = { from: born.clone(), t: 0 };
          if (slot.bornId) flip.rotation.y = 0;
        }
        card.scale.setScalar(slot.bornId ? 0.5 : slot.scale * 0.86);
        this.cards.set(slot.key, card);
      }
      paintMap(card, 'front', textureOf(slot.art, cornerOf(slot.art, slot.faceUp)));
      paintMap(card, 'back', this.back);
      card.userData.pick = slot.pick || '';
      card.visible = true;
    }
  }

  private dropSpare(keep: Set<string>) {
    for (const [key, card] of this.cards) {
      if (keep.has(key)) continue;
      card.removeFromParent();
      disposeObj(card);
      this.cards.delete(key);
    }
  }

  /** 钉在镜头前方的固定桌面，角色和镜头一起走时牌留在画面原处。 */
  private placeView(nx: number, ny: number, dist: number, out: THREE.Vector3) {
    const cam = stage.threeCamera;
    if (!cam) {
      out.set(nx, 1.1 + ny, dist);
      return;
    }
    cam.updateMatrixWorld();
    const e = cam.matrixWorld.elements;
    const rx = e[0];
    const ry = e[1];
    const rz = e[2];
    const ux = e[4];
    const uy = e[5];
    const uz = e[6];
    const fx = -e[8];
    const fy = -e[9];
    const fz = -e[10];
    const vFov = (cam.fov * Math.PI) / 180;
    const halfH = Math.tan(vFov / 2) * dist;
    const halfW = halfH * (cam.aspect || 1);
    out.set(
      cam.position.x + fx * dist + rx * nx * halfW + ux * ny * halfH,
      cam.position.y + fy * dist + ry * nx * halfW + uy * ny * halfH,
      cam.position.z + fz * dist + rz * nx * halfW + uz * ny * halfH,
    );
  }

  private faceCamera(card: THREE.Group, tilt: number) {
    const cam = stage.threeCamera;
    if (!cam) return;
    cam.getWorldQuaternion(this.camQ);
    const parent = card.parent;
    if (parent) parent.getWorldQuaternion(this.parentQ).invert();
    else this.parentQ.identity();
    card.quaternion.copy(this.camQ).premultiply(this.parentQ);
    card.rotateZ(tilt);
  }

  private follow() {
    const root = this.root || stage.avatarRoot;
    if (root) {
      this.root = root;
      root.getWorldPosition(this.tmp);
      this.rig.position.set(this.tmp.x, 0, this.tmp.z);
      const bone = stage.currentAvatar?.bone('chest') || stage.currentAvatar?.bone('spine');
      if (bone) {
        bone.getWorldPosition(this.tmp);
        this.chestY = this.tmp.y;
      }
    }
    this.attach();
  }

  private attach() {
    const scene = stage.threeScene;
    if (!scene) return;
    if (this.rig.parent !== scene) scene.add(this.rig);
    if (this.desk.parent !== scene) scene.add(this.desk);
  }

  private bind() {
    if (this.bound) return;
    const el = stage.canvas;
    if (!el) return;
    this.bound = true;
    el.addEventListener('pointerdown', this.onDown);
    el.addEventListener('pointermove', this.onMove);
  }

  private unbind() {
    if (!this.bound) return;
    this.bound = false;
    const el = stage.canvas;
    el?.removeEventListener('pointerdown', this.onDown);
    el?.removeEventListener('pointermove', this.onMove);
    if (el) el.style.cursor = '';
  }

  private hit(ev: PointerEvent) {
    const el = stage.canvas;
    const cam = stage.threeCamera;
    if (!el || !cam || !this.rig.visible) return '';
    const rect = el.getBoundingClientRect();
    this.pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    this.ray.setFromCamera(this.pointer, cam);
    const hits = this.ray.intersectObjects([...this.rig.children, ...this.desk.children], true);
    for (const hit of hits) {
      let node: THREE.Object3D | null = hit.object;
      while (node) {
        const pick = node.userData.pick as string | undefined;
        if (pick) return pick;
        node = node.parent;
      }
    }
    return '';
  }

  private onDown(ev: PointerEvent) {
    const id = this.hit(ev);
    if (id) this.onPick(id);
  }

  private onMove(ev: PointerEvent) {
    const el = stage.canvas;
    if (!el) return;
    el.style.cursor = this.hit(ev) ? 'pointer' : '';
  }
}

function row(face: string, y: number, z: number, scale: number): Slot[] {
  const out: Slot[] = [];
  const n = 6;
  const span = 0.86;
  for (let i = 0; i < n; i++) {
    const u = i / (n - 1);
    out.push({
      key: `lobby:${face}:${i + 1}`,
      art: artUrl(`${face}:${i + 1}`),
      faceUp: true,
      x: -span / 2 + span * u,
      y,
      z: z + i * 0.004,
      rotZ: (u - 0.5) * -0.08,
      scale,
    });
  }
  return out;
}

const VIEW_DIST = 1.35;

/** 按此刻的镜头量牌有多宽，再留一条缝。一排放不下就缩小。 */
function spread(cam: THREE.PerspectiveCamera, scale: number, count: number, maxSpan: number) {
  const halfH = Math.tan(((cam.fov || 30) * Math.PI) / 360) * VIEW_DIST;
  const halfW = Math.max(0.05, halfH * Math.max(0.6, cam.aspect || 1));
  const widthOf = (s: number) => (CARD_W * s * 1.12) / halfW;
  let next = scale;
  let step = widthOf(next) * 1.08;
  const need = Math.max(count - 1, 1);
  if (count > 1 && step * need > maxSpan) {
    next = scale * (maxSpan / (step * need));
    step = widthOf(next) * 1.08;
  }
  return { step, scale: next };
}

function viewFan(
  key: string, n: number, nx: number, ny: number, scale: number,
  artOf: (i: number) => string, faceUp: boolean, pickOf?: (i: number) => string,
  maxSpan = 1.2,
): Slot[] {
  const count = Math.max(0, Math.min(n, 5));
  const out: Slot[] = [];
  for (let i = 0; i < count; i++) {
    out.push({
      key: `${key}:${i}`,
      art: artOf(i),
      faceUp,
      x: 0,
      y: 0,
      z: 0,
      nx,
      ny,
      rotZ: 0,
      scale,
      fixed: true,
      pick: pickOf?.(i),
      fit: { center: nx, index: i, count, max: maxSpan, base: scale },
    });
  }
  return out;
}

/** 落牌在画面上半，手牌贴在出牌按钮上方。ny 越大越靠上。 */
const PILE_NY = 0.3;
const HAND_NY = -0.17;

const SEAT_AT: Record<string, [number, number]> = {
  you: [0, HAND_NY],
  qin: [-0.78, 0.08],
  bar: [0.78, 0.08],
  her: [0, 0.46],
};

function layout(board: TavernBoard): Slot[] {
  if (!board.phase || board.phase === 'idle') {
    const wildY = -0.46;
    const faces = board.faces && board.faces.length === 3 ? board.faces : ['loli', 'girl', 'lady'];
    return [
      ...row(faces[0], 0.2, 0.78, 0.62),
      ...row(faces[1], -0.02, 0.86, 0.62),
      ...row(faces[2], -0.24, 0.94, 0.62),
      {
        key: 'lobby:mei', art: artUrl('mei'), faceUp: true,
        x: -0.28, y: wildY, z: 1.05, rotZ: 0.04, scale: 0.74,
      },
      {
        key: 'lobby:ying', art: artUrl('ying'), faceUp: true,
        x: 0, y: wildY, z: 1.08, rotZ: 0, scale: 0.74,
      },
      {
        key: 'lobby:back', art: artUrl('back'), faceUp: true,
        x: 0.28, y: wildY, z: 1.05, rotZ: -0.04, scale: 0.74,
      },
    ];
  }
  if (board.phase === 'over') return [];
  const slots: Slot[] = [];
  const pile = Math.min(board.pile, 3);
  const from = SEAT_AT[board.pileFrom] || SEAT_AT.you;
  const faces = board.pileFrom === 'you' ? (board.pileFaces || []) : [];
  const seq = board.pileSeq || 0;
  for (let i = 0; i < pile; i++) {
    const face = faces[i] || '';
    slots.push({
      key: `pile:${seq}:${i}`,
      art: face ? artUrl(face) : artUrl('back'),
      faceUp: false,
      x: 0,
      y: 0,
      z: 0,
      nx: 0,
      ny: PILE_NY,
      rotZ: 0,
      scale: 0.4,
      fixed: true,
      hot: true,
      glide: true,
      bornId: face,
      bornNx: from[0],
      bornNy: from[1],
      fit: { center: 0, index: i, count: pile, max: 0.72, base: 0.4 },
    });
  }
  if (board.reveal.length) {
    slots.push(...viewFan(
      'reveal', board.reveal.length, 0, PILE_NY, 0.5,
      (i) => artUrl(board.reveal[i]), true,
      undefined,
      1.05,
    ).map((slot, i) => {
      slot.key = `reveal:${board.reveal[i]}:${i}`;
      slot.flipIn = true;
      slot.hot = true;
      return slot;
    }));
  }
  const hand = board.hand;
  slots.push(...viewFan(
    'hand', hand.length, 0, HAND_NY, 0.5,
    (i) => artUrl(hand[i].id), true,
    (i) => hand[i].id,
    1.2,
  ).map((slot, i) => {
    slot.key = `hand:${hand[i].id}`;
    slot.hot = true;
    if (board.selected.includes(hand[i].id)) {
      slot.ny = (slot.ny || 0) + 0.1;
      slot.extraScale = 0.04;
      slot.near = 0.14;
      slot.hot = true;
    }
    return slot;
  }));
  return slots;
}

let plugin: TavernPlugin | null = null;

export function mountTavern(onPick: (id: string) => void) {
  if (!plugin) {
    plugin = new TavernPlugin();
    stage.use(plugin);
    const root = stage.avatarRoot;
    if (root) plugin.onAvatarReady(root);
  }
  plugin.setPick(onPick);
}

export function syncTavern(board: TavernBoard) {
  plugin?.show(board);
}

export function refreshCardArt() {
  plugin?.restyle();
}

export function unmountTavern() {
  if (!plugin) return;
  plugin.dispose();
  stage.unuse('tavern');
  plugin = null;
}
