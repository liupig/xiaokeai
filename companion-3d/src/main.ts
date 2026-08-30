import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MMDLoader, MMDPhysics, MMDAnimationHelper } from 'three-stdlib';
import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

// ---------- 基础场景 ----------
const app = document.getElementById('app')!;
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x141420);
scene.fog = new THREE.Fog(0x141420, 6, 14);

const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 50);
camera.position.set(0, 1.3, 3.6);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0.95, 0);
controls.minDistance = 0.35;
controls.maxDistance = 8;

// 灯光：主光 + 环境光 + 蓝色轮廓光
const keyLight = new THREE.DirectionalLight(0xffffff, 1.8);
keyLight.position.set(1.2, 2.2, 2.5);
scene.add(keyLight);
scene.add(new THREE.AmbientLight(0x9999bb, 0.9));
const rimLight = new THREE.DirectionalLight(0x7788ff, 1.0);
rimLight.position.set(-2, 1.6, -2.5);
scene.add(rimLight);

// 地面
const ground = new THREE.Mesh(
  new THREE.CircleGeometry(2.4, 64),
  new THREE.MeshStandardMaterial({ color: 0x232342, roughness: 0.95 })
);
ground.rotation.x = -Math.PI / 2;
scene.add(ground);

// ---------- 角色抽象层：同时支持 VRM（二次元）和 GLB（写实 ARKit）----------
type BoneKey =
  | 'hips' | 'spine' | 'chest' | 'head'
  | 'leftUpperArm' | 'rightUpperArm' | 'rightLowerArm';

type ExprKey = 'aa' | 'blink' | 'happy' | 'angry' | 'sad' | 'relaxed';
type Axis = 'x' | 'y' | 'z';

// 写实 GLB（RPM / Avaturn / MetaPerson 等）的 ARKit 形态键映射
const GLB_MORPHS: Record<ExprKey, { name: string; scale: number }[]> = {
  aa: [
    { name: 'viseme_aa', scale: 1 },
    { name: 'jawOpen', scale: 0.6 },
    { name: 'mouthOpen', scale: 0.8 },
  ],
  blink: [
    { name: 'eyeBlinkLeft', scale: 1 },
    { name: 'eyeBlinkRight', scale: 1 },
    { name: 'eyesClosed', scale: 1 },
  ],
  happy: [
    { name: 'mouthSmileLeft', scale: 1 },
    { name: 'mouthSmileRight', scale: 1 },
    { name: 'mouthSmile', scale: 1 },
    { name: 'cheekSquintLeft', scale: 0.5 },
    { name: 'cheekSquintRight', scale: 0.5 },
  ],
  angry: [
    { name: 'browDownLeft', scale: 1 },
    { name: 'browDownRight', scale: 1 },
    { name: 'mouthFrownLeft', scale: 0.4 },
    { name: 'mouthFrownRight', scale: 0.4 },
    { name: 'noseSneerLeft', scale: 0.4 },
    { name: 'noseSneerRight', scale: 0.4 },
  ],
  sad: [
    { name: 'mouthFrownLeft', scale: 0.8 },
    { name: 'mouthFrownRight', scale: 0.8 },
    { name: 'browInnerUp', scale: 1 },
    { name: 'eyeSquintLeft', scale: 0.3 },
    { name: 'eyeSquintRight', scale: 0.3 },
  ],
  relaxed: [
    { name: 'mouthSmileLeft', scale: 0.35 },
    { name: 'mouthSmileRight', scale: 0.35 },
    { name: 'eyeSquintLeft', scale: 0.4 },
    { name: 'eyeSquintRight', scale: 0.4 },
  ],
};

// GLB（Mixamo/RPM 命名）骨骼映射
const GLB_BONES: Record<BoneKey | 'leftLowerArm', string[]> = {
  hips: ['Hips', 'mixamorigHips'],
  spine: ['Spine', 'mixamorigSpine'],
  chest: ['Spine2', 'mixamorigSpine2', 'Spine1'],
  head: ['Head', 'mixamorigHead'],
  leftUpperArm: ['LeftArm', 'mixamorigLeftArm'],
  rightUpperArm: ['RightArm', 'mixamorigRightArm'],
  leftLowerArm: ['LeftForeArm', 'mixamorigLeftForeArm'],
  rightLowerArm: ['RightForeArm', 'mixamorigRightForeArm'],
};

// MMD（PMX，日文标准命名）形态键映射
const MMD_MORPHS: Record<ExprKey, { name: string; scale: number }[]> = {
  aa: [{ name: 'あ', scale: 1 }],
  blink: [{ name: 'まばたき', scale: 1 }, { name: '瞬き', scale: 1 }],
  happy: [
    { name: 'にこり', scale: 0.6 },
    { name: '笑い目', scale: 0.8 },
    { name: 'にっこり', scale: 1 },
    { name: '口角上げ左', scale: 1 },
    { name: '口角上げ右', scale: 1 },
  ],
  angry: [
    { name: '怒り', scale: 1 },
    { name: 'キリッ', scale: 0.6 },
    { name: '口角下げ左', scale: 0.7 },
    { name: '口角下げ右', scale: 0.7 },
  ],
  sad: [
    { name: '困る', scale: 1 },
    { name: '悲しい目', scale: 0.8 },
    { name: '悲しい', scale: 0.8 },
    { name: '口角下げ左', scale: 0.5 },
    { name: '口角下げ右', scale: 0.5 },
  ],
  relaxed: [
    { name: 'なごみ', scale: 1 },
    { name: 'じと目', scale: 0.5 },
    { name: '笑い目', scale: 0.4 },
    { name: '口角上げ左', scale: 0.3 },
    { name: '口角上げ右', scale: 0.3 },
  ],
};

// MMD（PMX）骨骼映射
const MMD_BONES: Record<BoneKey | 'leftLowerArm', string[]> = {
  hips: ['下半身'],
  spine: ['上半身'],
  chest: ['上半身2', '上半身'],
  head: ['頭'],
  leftUpperArm: ['左腕'],
  rightUpperArm: ['右腕'],
  leftLowerArm: ['左ひじ'],
  rightLowerArm: ['右ひじ'],
};

// 每根被程序驱动的骨骼记录：静止姿势欧拉角 + 摆臂旋转轴与方向
interface ArmRig {
  axis: Axis;      // 绕哪个局部轴旋转能让手臂上下摆
  down: number;    // 从静止姿势放下手臂需要叠加的角度（带符号）
  up: number;      // 挥手抬起时叠加的角度（带符号）
}

interface Avatar {
  isVRM: boolean;
  bone(key: BoneKey): THREE.Object3D | null;
  beginFrame(): void; // 每帧表情写入前调用，清空上一帧的形态键
  setExpr(key: ExprKey, v: number): void;
  morphNames(): string[]; // 模型自带的全部表情形态键名
  setMorph(name: string, v: number): void; // 直接按名字驱动任意形态键
  update(dt: number): void;
  base(obj: THREE.Object3D): THREE.Euler;
  armL: ArmRig;
  armR: ArmRig;
}

let avatar: Avatar | null = null;
let headY = 1.35;

// 记录骨骼初始欧拉角，动画时在其基础上叠加
function makeBaseTracker() {
  const map = new Map<THREE.Object3D, THREE.Euler>();
  return (obj: THREE.Object3D) => {
    if (!map.has(obj)) map.set(obj, obj.rotation.clone());
    return map.get(obj)!;
  };
}

// 自动测量：绕哪个轴、哪个方向旋转上臂能让手臂放下，以及当前手臂下垂角度
function measureArm(
  root: THREE.Object3D,
  upper: THREE.Object3D,
  lower: THREE.Object3D
): ArmRig {
  const armDir = () => {
    root.updateMatrixWorld(true);
    return lower.getWorldPosition(new THREE.Vector3())
      .sub(upper.getWorldPosition(new THREE.Vector3()))
      .normalize();
  };
  const dir0 = armDir();
  const drop0 = Math.asin(THREE.MathUtils.clamp(-dir0.y, -1, 1)); // 当前低于水平的角度

  let best: { axis: Axis; sign: number; dy: number } = { axis: 'z', sign: 1, dy: 0 };
  for (const axis of ['x', 'y', 'z'] as Axis[]) {
    const orig = upper.rotation[axis];
    upper.rotation[axis] = orig + 0.15;
    const dy = armDir().y - dir0.y;
    upper.rotation[axis] = orig;
    if (Math.abs(dy) > Math.abs(best.dy)) best = { axis, sign: dy < 0 ? 1 : -1, dy };
  }
  root.updateMatrixWorld(true);

  const targetDrop = 1.15; // 目标下垂约 66°
  const down = best.sign * Math.max(0, targetDrop - drop0);
  const up = best.sign * -(drop0 + 0.35); // 抬到水平以上约 20°
  console.log('[measureArm]', upper.name, { axis: best.axis, sign: best.sign, dy: best.dy, drop0, down, up });
  return { axis: best.axis, down, up };
}

function makeVRMAvatar(vrm: VRM): Avatar {
  const base = makeBaseTracker();
  const la = vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
  const ll = vrm.humanoid.getNormalizedBoneNode('leftLowerArm');
  const ra = vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
  const rl = vrm.humanoid.getNormalizedBoneNode('rightLowerArm');
  const armL = la && ll ? measureArm(vrm.scene, la, ll) : { axis: 'z' as Axis, down: 1.15, up: -0.35 };
  const armR = ra && rl ? measureArm(vrm.scene, ra, rl) : { axis: 'z' as Axis, down: -1.15, up: 0.35 };
  return {
    isVRM: true,
    bone: (key) => vrm.humanoid.getNormalizedBoneNode(key),
    beginFrame: () => {},
    setExpr: (key, v) => vrm.expressionManager?.setValue(key, v),
    morphNames: () =>
      vrm.expressionManager?.expressions.map((e) => e.expressionName) ?? [],
    setMorph: (name, v) => vrm.expressionManager?.setValue(name, v),
    update: (dt) => vrm.update(dt),
    base,
    armL,
    armR,
  };
}

// 通用网格适配器：GLB（ARKit）和 MMD（PMX）共用，传入各自的骨骼/形态键映射表
function makeMeshAvatar(
  root: THREE.Object3D,
  BONES: Record<BoneKey | 'leftLowerArm', string[]>,
  MORPHS: Record<ExprKey, { name: string; scale: number }[]>
): Avatar {
  const base = makeBaseTracker();
  const morphMeshes: THREE.Mesh[] = [];
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.isMesh && mesh.morphTargetDictionary) morphMeshes.push(mesh);
  });
  const findBone = (names: string[]) => {
    for (const name of names) {
      const found = root.getObjectByName(name);
      if (found) return found;
    }
    return null;
  };
  const boneCache = new Map<BoneKey, THREE.Object3D | null>();
  const la = findBone(BONES.leftUpperArm);
  const ll = findBone(BONES.leftLowerArm);
  const ra = findBone(BONES.rightUpperArm);
  const rl = findBone(BONES.rightLowerArm);
  const armL = la && ll ? measureArm(root, la, ll) : { axis: 'z' as Axis, down: 0, up: -1 };
  const armR = ra && rl ? measureArm(root, ra, rl) : { axis: 'z' as Axis, down: 0, up: 1 };
  // 收集所有会被表情系统触碰的形态键索引，每帧统一清零后按最大值合成，
  // 避免多个表情共用同一形态键时相互覆盖
  const usedIndices: { mesh: THREE.Mesh; idx: number }[] = [];
  for (const entries of Object.values(MORPHS)) {
    for (const { name } of entries) {
      for (const mesh of morphMeshes) {
        const idx = mesh.morphTargetDictionary![name];
        if (idx !== undefined) usedIndices.push({ mesh, idx });
      }
    }
  }
  return {
    isVRM: false,
    bone: (key) => {
      if (!boneCache.has(key)) boneCache.set(key, findBone(BONES[key]));
      return boneCache.get(key)!;
    },
    beginFrame: () => {
      for (const { mesh, idx } of usedIndices) mesh.morphTargetInfluences![idx] = 0;
    },
    setExpr: (key, v) => {
      for (const { name, scale } of MORPHS[key]) {
        for (const mesh of morphMeshes) {
          const idx = mesh.morphTargetDictionary![name];
          if (idx !== undefined) {
            mesh.morphTargetInfluences![idx] = Math.max(mesh.morphTargetInfluences![idx], v * scale);
          }
        }
      }
    },
    morphNames: () => {
      const names = new Set<string>();
      for (const mesh of morphMeshes) {
        for (const name of Object.keys(mesh.morphTargetDictionary!)) names.add(name);
      }
      return [...names];
    },
    setMorph: (name, v) => {
      for (const mesh of morphMeshes) {
        const idx = mesh.morphTargetDictionary![name];
        if (idx !== undefined) mesh.morphTargetInfluences![idx] = v;
      }
    },
    update: () => {},
    base,
    armL,
    armR,
  };
}

// ---------- 状态 ----------
// 表情库手动开启的形态键：name -> 目标值（1 开 / 0 关，动画循环里平滑过渡）
const manualTargets = new Map<string, number>();
const manualCurrent = new Map<string, number>();

let talking = false;
let currentEmotion = 'neutral';
const EMOTIONS: ExprKey[] = ['happy', 'angry', 'sad', 'relaxed'];
const emotionWeights: Record<string, number> = { happy: 0, angry: 0, sad: 0, relaxed: 0 };

let blinkTimer = 2.5;
let blinkProgress = -1;

let action: { name: string; time: number; duration: number } | null = null;

// ---------- 镜头预设 ----------
type CamPreset = 'close' | 'half' | 'full';
let camAnim: {
  fromPos: THREE.Vector3; toPos: THREE.Vector3;
  fromTarget: THREE.Vector3; toTarget: THREE.Vector3;
  t: number;
} | null = null;

function setCamera(preset: CamPreset, instant = false) {
  const presets: Record<CamPreset, { pos: THREE.Vector3; target: THREE.Vector3 }> = {
    full: {
      pos: new THREE.Vector3(0, headY * 0.62, headY * 2.5),
      target: new THREE.Vector3(0, headY * 0.55, 0),
    },
    half: {
      pos: new THREE.Vector3(0, headY - 0.03, headY * 1.0),
      target: new THREE.Vector3(0, headY - 0.14, 0),
    },
    close: {
      pos: new THREE.Vector3(0, headY + 0.02, 0.6 + headY * 0.18),
      target: new THREE.Vector3(0, headY - 0.02, 0),
    },
  };
  const p = presets[preset];
  if (instant) {
    camera.position.copy(p.pos);
    controls.target.copy(p.target);
    camAnim = null;
  } else {
    camAnim = {
      fromPos: camera.position.clone(), toPos: p.pos,
      fromTarget: controls.target.clone(), toTarget: p.target,
      t: 0,
    };
  }
}

// ---------- 加载模型（?model=xxx，支持 .vrm / .glb / .pmx）----------
const rawParam = new URLSearchParams(location.search).get('model') ?? 'qingxiao/model.pmx';
const modelFile = /\.(vrm|glb|pmx)$/i.test(rawParam) ? rawParam : `${rawParam}.vrm`;
const modelExt = modelFile.toLowerCase().split('.').pop();

// ?motion=xxx.vmd：播放 MMD 专业动作文件（放在 public/motions/ 下），
// 播放期间程序化身体动画让位给 VMD 动作
const motionParam = new URLSearchParams(location.search).get('motion');
let vmdMotionActive = false;

// ---------- MMD 动作管理：运行时加载 / 切换 / 停止 ----------
let mmdMesh: THREE.SkinnedMesh | null = null;
let mmdPhysics: MMDPhysics | null = null;
let mmdHelper: MMDAnimationHelper | null = null;
const clipCache = new Map<string, THREE.AnimationClip>();
// 模型加载完成时的初始姿势，停止动作后恢复
const initPose = new Map<THREE.Bone, { pos: THREE.Vector3; quat: THREE.Quaternion }>();

function snapshotPose(mesh: THREE.SkinnedMesh) {
  for (const b of mesh.skeleton.bones) {
    initPose.set(b, { pos: b.position.clone(), quat: b.quaternion.clone() });
  }
}

function restorePose() {
  if (!mmdMesh) return;
  for (const [b, p] of initPose) {
    b.position.copy(p.pos);
    b.quaternion.copy(p.quat);
  }
  mmdMesh.updateMatrixWorld(true);
}

function loadClip(file: string): Promise<THREE.AnimationClip | null> {
  const cached = clipCache.get(file);
  if (cached) return Promise.resolve(cached);
  return new Promise((resolve) => {
    new MMDLoader().loadAnimation(
      `/motions/${file}`,
      mmdMesh!,
      (c) => {
        clipCache.set(file, c as THREE.AnimationClip);
        resolve(c as THREE.AnimationClip);
      },
      undefined,
      (e) => {
        console.warn('VMD 动作加载失败：', file, e);
        resolve(null);
      }
    );
  });
}

async function playMotion(file: string) {
  if (!mmdMesh) return;
  const clip = await loadClip(file);
  if (!clip) return;
  stopMotion();
  mmdHelper = new MMDAnimationHelper();
  // physics: false —— 物理由主循环自己管理（修复了高刷屏加速问题）
  mmdHelper.add(mmdMesh, { animation: clip, physics: false });
  mmdHelper.update(1 / 60); // 先推进一帧摆到动作起始姿势
  mmdPhysics?.reset(); // 避免姿势跳变导致布料乱甩
  vmdMotionActive = true;
}

function stopMotion() {
  if (!vmdMotionActive && !mmdHelper) return;
  mmdHelper = null;
  vmdMotionActive = false;
  restorePose();
  mmdPhysics?.reset();
}

function finishSetup(root: THREE.Object3D) {
  scene.add(root);
  (window as any).__avatar = avatar;
  (window as any).__scene = scene;
  (window as any).__cam = camera;
  (window as any).__headY = () => headY;

  // 根据模型头部实际高度设置镜头
  const head = avatar!.bone('head');
  if (head) headY = head.getWorldPosition(new THREE.Vector3()).y + 0.06;
  setCamera('full', true);

  buildLibraryUI();
  document.getElementById('loading')!.classList.add('hidden');
}

// ---------- 表情库 + 动作库抽屉 ----------
function buildLibraryUI() {
  const av = avatar!;
  const toggle = document.getElementById('lib-toggle')!;
  const drawer = document.getElementById('drawer')!;
  toggle.classList.remove('hidden');
  toggle.addEventListener('click', () => {
    drawer.classList.toggle('hidden');
    toggle.classList.toggle('active', !drawer.classList.contains('hidden'));
  });

  // --- 表情库：列出模型全部形态键，点击开/关，可任意组合 ---
  const morphList = document.getElementById('morph-list')!;
  const search = document.getElementById('morph-search') as HTMLInputElement;
  const morphButtons: { name: string; btn: HTMLButtonElement }[] = [];
  for (const name of av.morphNames()) {
    const btn = document.createElement('button');
    btn.textContent = name;
    btn.addEventListener('click', () => {
      const on = btn.classList.toggle('active');
      manualTargets.set(name, on ? 1 : 0);
      if (!manualCurrent.has(name)) manualCurrent.set(name, 0);
    });
    morphList.appendChild(btn);
    morphButtons.push({ name, btn });
  }
  document.getElementById('morph-count')!.textContent = `${morphButtons.length} 个`;
  search.addEventListener('input', () => {
    const q = search.value.trim();
    for (const { name, btn } of morphButtons) {
      btn.style.display = name.includes(q) ? '' : 'none';
    }
  });
  document.getElementById('morph-reset')!.addEventListener('click', () => {
    for (const { btn } of morphButtons) btn.classList.remove('active');
    for (const name of manualTargets.keys()) manualTargets.set(name, 0);
  });

  // --- 动作库：列出 public/motions/motions.json 里的全部 VMD，可切换 / 停止 ---
  const motionSec = document.getElementById('sec-motion')!;
  if (modelExt === 'pmx') {
    fetch('/motions/motions.json')
      .then((r) => (r.ok ? r.json() : ['dance.vmd']))
      .catch(() => ['dance.vmd'])
      .then((files: (string | { file: string; label?: string })[]) => {
        const list = document.getElementById('motion-list')!;
        const stopBtn = document.createElement('button');
        stopBtn.textContent = '停止动作（回到闲置）';
        stopBtn.addEventListener('click', () => {
          list.querySelectorAll('button').forEach((b) => b.classList.remove('active'));
          stopMotion();
        });
        list.appendChild(stopBtn);
        for (const item of files) {
          const f = typeof item === 'string' ? item : item.file;
          const btn = document.createElement('button');
          btn.textContent =
            (typeof item === 'object' && item.label) || f.replace(/\.vmd$/i, '');
          btn.addEventListener('click', async () => {
            list.querySelectorAll('button').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            await playMotion(f);
          });
          list.appendChild(btn);
          if (motionParam === f) btn.classList.add('active');
        }
      });
  } else {
    motionSec.style.display = 'none';
  }
}

function onLoadError(err: unknown) {
  document.getElementById('loading')!.textContent =
    `模型加载失败：/models/${modelFile}。请把 .vrm / .glb / .pmx 放到 companion-3d/public/models/，` +
    `或用 ?model=文件名 指定。` + String(err);
}

if (modelExt === 'pmx') {
  new MMDLoader().load(
    `/models/${modelFile}`,
    async (mmd) => {
      // MMD 单位约 8cm，缩放到米制
      mmd.scale.setScalar(0.08);
      mmd.updateMatrixWorld(true);
      // MMD 卡通材质对光照敏感，压低亮度避免过曝
      keyLight.intensity = 1.0;
      rimLight.intensity = 0.5;
      scene.children.forEach((c) => {
        if ((c as THREE.AmbientLight).isAmbientLight) (c as THREE.AmbientLight).intensity = 0.45;
      });
      const av = makeMeshAvatar(mmd, MMD_BONES, MMD_MORPHS);
      avatar = av;
      mmdMesh = mmd;
      snapshotPose(mmd); // 记录初始姿势，供停止动作后恢复

      // 手臂预先放到自然姿势，避免布料从 T-pose 大幅甩动。
      // 先通过 base() 记录原始角度，动画循环里 base+down 的写法才不会叠加两次
      for (const [key, rig] of [['leftUpperArm', av.armL], ['rightUpperArm', av.armR]] as const) {
        const b = av.bone(key);
        if (b) b.rotation[rig.axis] = av.base(b)[rig.axis] + rig.down;
      }
      mmd.updateMatrixWorld(true);

      // 初始化 ammo.js 物理：头发、飘带、裙摆的真实摆动
      try {
        const AmmoInit = (window as any).Ammo;
        if (typeof AmmoInit === 'function') {
          (window as any).Ammo = await AmmoInit();
        }
        const ud = (mmd.geometry as THREE.BufferGeometry).userData.MMD;
        mmdPhysics = new MMDPhysics(mmd, ud.rigidBodies, ud.constraints);
        mmdPhysics.warmup(60); // 预跑几十步让布料在起始姿势下稳定
      } catch (e) {
        console.warn('MMD 物理初始化失败，继续以无物理模式运行：', e);
      }

      // MMDPhysics 每次调用最少模拟 1/65 秒，在高刷新率屏幕（如 165Hz）上
      // 每帧真实时间不足 1/65 秒，物理会被加速 2~3 倍。
      // 因此累积真实时间，攒够一个物理步长才推进一次
      const PHY_STEP = 1 / 65;
      let phyAcc = 0;
      av.update = (dt: number) => {
        if (mmdHelper) mmdHelper.update(dt); // VMD 动作 + IK，每帧平滑推进
        if (!mmdPhysics) return;
        phyAcc += dt;
        if (phyAcc < PHY_STEP) return;
        mmdPhysics.update(Math.min(phyAcc, 1 / 30));
        phyAcc = 0;
      };

      if (motionParam) await playMotion(motionParam);

      finishSetup(mmd);
    },
    undefined,
    onLoadError
  );
} else {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));

  loader.load(
    `/models/${modelFile}`,
    (gltf) => {
      let root: THREE.Object3D;
      if (modelExt === 'vrm') {
        const vrm = gltf.userData.vrm as VRM;
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        if (typeof (VRMUtils as any).combineSkeletons === 'function') {
          (VRMUtils as any).combineSkeletons(gltf.scene);
        }
        VRMUtils.rotateVRM0(vrm); // VRM 0.x 模型转为面向镜头
        avatar = makeVRMAvatar(vrm);
        root = vrm.scene;
        if (vrm.lookAt) vrm.lookAt.target = camera;
      } else {
        avatar = makeMeshAvatar(gltf.scene, GLB_BONES, GLB_MORPHS);
        root = gltf.scene;
      }
      finishSetup(root);
    },
    undefined,
    onLoadError
  );
}

// ---------- UI 事件 ----------
function bindGroup(attr: string, onSelect: (value: string, btn: HTMLButtonElement) => void, toggle = true) {
  document.querySelectorAll<HTMLButtonElement>(`button[${attr}]`).forEach((btn) => {
    btn.addEventListener('click', () => {
      if (toggle) {
        btn.parentElement!.querySelectorAll('button').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
      }
      onSelect(btn.getAttribute(attr)!, btn);
    });
  });
}

bindGroup('data-cam', (v) => setCamera(v as CamPreset));
bindGroup('data-emo', (v) => { currentEmotion = v; });
bindGroup('data-act', (v) => {
  const durations: Record<string, number> = { wave: 2.6, nod: 1.4, shake: 1.6 };
  action = { name: v, time: 0, duration: durations[v] ?? 1.5 };
}, false);

const talkBtn = document.getElementById('btn-talk') as HTMLButtonElement;
talkBtn.addEventListener('click', () => {
  talking = !talking;
  talkBtn.textContent = talking ? '停止说话' : '开始说话';
  talkBtn.classList.toggle('active', talking);
});

// ---------- 动画循环 ----------
const clock = new THREE.Clock();

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

// 动作的淡入淡出包络，避免姿势突变
function envelope(p: number) {
  const fadeIn = Math.min(1, p / 0.15);
  const fadeOut = Math.min(1, (1 - p) / 0.15);
  return Math.min(fadeIn, fadeOut);
}

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;

  // 镜头过渡动画
  if (camAnim) {
    camAnim.t += dt / 0.9;
    const k = easeInOut(Math.min(camAnim.t, 1));
    camera.position.lerpVectors(camAnim.fromPos, camAnim.toPos, k);
    controls.target.lerpVectors(camAnim.fromTarget, camAnim.toTarget, k);
    if (camAnim.t >= 1) camAnim = null;
  }
  controls.update();

  if (avatar) {
    const av = avatar;
    av.beginFrame();

    // --- 说话口型：多个正弦波叠加模拟自然开合 ---
    const mouth = talking
      ? Math.max(0, 0.32 + 0.28 * Math.sin(t * 11) + 0.2 * Math.sin(t * 23 + 1.3))
      : 0;
    av.setExpr('aa', mouth);

    // --- 眨眼 ---
    blinkTimer -= dt;
    if (blinkTimer <= 0 && blinkProgress < 0) {
      blinkProgress = 0;
      blinkTimer = 2 + Math.random() * 4;
    }
    if (blinkProgress >= 0) {
      blinkProgress += dt;
      const v = blinkProgress < 0.08
        ? blinkProgress / 0.08
        : Math.max(0, 1 - (blinkProgress - 0.08) / 0.12);
      av.setExpr('blink', v);
      if (blinkProgress > 0.22) {
        blinkProgress = -1;
        av.setExpr('blink', 0);
      }
    }

    // --- 表情平滑过渡 ---
    for (const e of EMOTIONS) {
      const target = currentEmotion === e ? 0.85 : 0;
      emotionWeights[e] = THREE.MathUtils.lerp(emotionWeights[e], target, 1 - Math.exp(-8 * dt));
      av.setExpr(e, emotionWeights[e]);
    }

    // --- 表情库手动叠加（平滑淡入淡出，可任意组合）---
    for (const [name, target] of manualTargets) {
      const cur = manualCurrent.get(name) ?? 0;
      const nv = THREE.MathUtils.lerp(cur, target, 1 - Math.exp(-10 * dt));
      if (target === 0 && nv < 0.01) {
        manualTargets.delete(name);
        manualCurrent.delete(name);
        av.setMorph(name, 0);
      } else {
        manualCurrent.set(name, nv);
        av.setMorph(name, nv);
      }
    }

    // --- 程序化身体动画（VMD 动作播放期间由 MMDAnimationHelper 接管，跳过）---
    if (!vmdMotionActive) {
      // 呼吸 + 身体轻微摆动（在骨骼初始姿势上叠加）
      const spine = av.bone('spine');
      const chest = av.bone('chest');
      const hips = av.bone('hips');
      if (spine) spine.rotation.x = av.base(spine).x + 0.015 * Math.sin(t * 1.5);
      if (chest) chest.rotation.x = av.base(chest).x + 0.02 * Math.sin(t * 1.5 + 0.4);
      if (hips) hips.rotation.y = av.base(hips).y + 0.03 * Math.sin(t * 0.5);

      // 头部：闲置摆动 + 点头/摇头动作
      const head = av.bone('head');
      let headRx = 0.02 * Math.sin(t * 0.7 + 1);
      let headRy = 0.04 * Math.sin(t * 0.5);

      // 手臂：默认下垂，挥手时抬起
      const la = av.bone('leftUpperArm');
      const ra = av.bone('rightUpperArm');
      const rl = av.bone('rightLowerArm');
      let raOffset = av.armR.down;
      let rlOffset = 0;
      if (la) {
        la.rotation[av.armL.axis] =
          av.base(la)[av.armL.axis] + av.armL.down + 0.02 * Math.sin(t * 1.5 + 0.4);
      }

      if (action) {
        action.time += dt;
        const p = Math.min(action.time / action.duration, 1);
        const e = envelope(p);
        if (action.name === 'wave') {
          raOffset = THREE.MathUtils.lerp(av.armR.down, av.armR.up, e);
          rlOffset = e * 0.55 * Math.sin(t * 13);
        } else if (action.name === 'nod') {
          headRx += e * 0.3 * Math.sin(p * Math.PI * 4);
        } else if (action.name === 'shake') {
          headRy += e * 0.4 * Math.sin(p * Math.PI * 4);
        }
        if (p >= 1) action = null;
      }

      if (ra) {
        ra.rotation[av.armR.axis] =
          av.base(ra)[av.armR.axis] + raOffset + 0.02 * Math.sin(t * 1.5);
      }
      if (rl) rl.rotation[av.armR.axis] = av.base(rl)[av.armR.axis] + rlOffset;
      if (head) {
        const hb = av.base(head);
        head.rotation.set(hb.x + headRx, hb.y + headRy, hb.z);
      }
    }

    av.update(dt);
  }

  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
