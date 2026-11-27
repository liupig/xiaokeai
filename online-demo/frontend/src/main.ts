import * as THREE from 'three';
import { createLiutingDrape } from './liuting-drape';
import { loadPreviewPmx } from './preview-pmx';
import { loadYuexiaoFinishes, shadeMagnoliaSkin } from './yuexiao-finishes';
import { loadMagnoliaMaterials } from '../../../companion/frontend/src/engine/magnoliaMaterials';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
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
controls.minPolarAngle = THREE.MathUtils.degToRad(35);
controls.maxPolarAngle = THREE.MathUtils.degToRad(105);

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
  chest: ['Spine2', 'mixamorigSpine2', 'Spine1', 'Chest'],
  head: ['Head', 'mixamorigHead'],
  leftUpperArm: ['LeftArm', 'mixamorigLeftArm', 'UpperArm.L'],
  rightUpperArm: ['RightArm', 'mixamorigRightArm', 'UpperArm.R'],
  leftLowerArm: ['LeftForeArm', 'mixamorigLeftForeArm', 'Forearm.L'],
  rightLowerArm: ['RightForeArm', 'mixamorigRightForeArm', 'Forearm.R'],
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
      const found = root.getObjectByName(name) ?? root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name));
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
        for (const name of Object.keys(mesh.morphTargetDictionary!)) {
          if (name !== 'QingyiOriginalHair' && name !== 'QingyiLiutingHair') names.add(name);
        }
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
  from: THREE.Spherical; to: THREE.Spherical;
  fromTarget: THREE.Vector3; toTarget: THREE.Vector3;
  start: number;
} | null = null;
const orbit = new THREE.Spherical();
controls.addEventListener('start', () => { camAnim = null; });

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
  const fromPos = camera.position.clone();
  const fromTarget = controls.target.clone();
  // Consume any remaining drag/pan inertia before handing off to a preset.
  // Restore the displayed pose immediately so this flush never reaches a frame.
  controls.enableDamping = false;
  controls.update();
  controls.enableDamping = true;
  camera.position.copy(fromPos);
  controls.target.copy(fromTarget);
  if (instant) {
    camera.position.copy(p.pos);
    controls.target.copy(p.target);
    camAnim = null;
  } else {
    const from = new THREE.Spherical().setFromVector3(fromPos.sub(fromTarget));
    const to = new THREE.Spherical().setFromVector3(p.pos.clone().sub(p.target));
    const turn = to.theta - from.theta;
    to.theta = from.theta + Math.atan2(Math.sin(turn), Math.cos(turn));
    camAnim = {
      from, to, fromTarget, toTarget: p.target, start: performance.now(),
    };
  }
  controls.update();
}

function updateCamera() {
  if (camAnim) {
    const { from, to, fromTarget, toTarget, start } = camAnim;
    const t = Math.min((performance.now() - start) / 900, 1);
    const k = easeInOut(t);
    orbit.set(
      THREE.MathUtils.lerp(from.radius, to.radius, k),
      THREE.MathUtils.lerp(from.phi, to.phi, k),
      THREE.MathUtils.lerp(from.theta, to.theta, k),
    );
    controls.target.lerpVectors(fromTarget, toTarget, k);
    camera.position.setFromSpherical(orbit).add(controls.target);
    if (t === 1) camAnim = null;
  }
  controls.update();
  // Keep the orbit pivot and the lens above the stage when panning or dollying.
  const floor = 0.06;
  if (controls.target.y < floor) {
    camera.position.y += floor - controls.target.y;
    controls.target.y = floor;
  }
  if (camera.position.y < floor) {
    orbit.setFromVector3(camera.position.sub(controls.target));
    orbit.phi = Math.acos((floor - controls.target.y) / orbit.radius);
    camera.position.setFromSpherical(orbit).add(controls.target);
    camera.lookAt(controls.target);
  }
}

// ---------- 加载模型（?model=xxx，支持 .vrm / .glb / .pmx）----------
const requestedModel = new URLSearchParams(location.search).get('model');
const qingyiTurnaround = requestedModel === 'qingyi-turnaround';
const qingyiDelivery = requestedModel === 'qingyi-delivery' || qingyiTurnaround;
const qingyiRebuilt = requestedModel === 'qingyi-rebuilt';
const qingyiPreview = requestedModel === 'qingyi';
const lookParams = new URLSearchParams(location.search);
const requestedOutfit = lookParams.get('outfit');
const photoOutfit = requestedOutfit === 'yuexiao-photo';
const straplessOutfit = requestedOutfit === 'yuexiao-strapless';
const moonOutfit = qingyiDelivery && !qingyiTurnaround && (photoOutfit || straplessOutfit || requestedOutfit === 'yuexiao'
  || (!requestedOutfit && (!lookParams.has('hair') || lookParams.get('hair') === 'yuexiao')));
const costumeFile = moonOutfit ? (photoOutfit ? 'yuexiao-photo' : straplessOutfit ? 'yuexiao-strapless' : 'yuexiao') : 'lanxu';
const costumeLabels = {
  yuexiao: '小可爱 · 双视图定稿',
  'yuexiao-strapless': '小可爱',
  'yuexiao-photo': '小可爱 · 真人照片版',
  lanxu: '兰汀短裳',
};
const rawParam = qingyiTurnaround ? 'qingyi-turnaround.glb' : qingyiDelivery ? `qingyi-jade/${costumeFile}.pmx` : qingyiRebuilt ? 'qingyi-rebuilt.glb' : qingyiPreview ? 'qingyi.glb' : 'xinyuehu/model.pmx';
if (qingyiPreview || qingyiRebuilt || qingyiDelivery) {
  const label = qingyiTurnaround ? '清漪（多视角材质测试）' : qingyiDelivery ? `${moonOutfit ? '' : '清漪 · '}${costumeLabels[costumeFile]}（${straplessOutfit ? '本版作者：liupig · ' : ''}底模：鸣潮／白泽）` : qingyiRebuilt ? '清漪（重建测试版）' : '清漪（原型）';
  document.getElementById('hint')!.textContent = `鼠标拖动旋转视角 · 滚轮缩放 · ${label}`;
}
const modelFile = /\.(vrm|glb|pmx)$/i.test(rawParam) ? rawParam : `${rawParam}.vrm`;
const modelExt = modelFile.toLowerCase().split('.').pop();
if (qingyiTurnaround) {
  const portraitFill = new THREE.DirectionalLight(0xfff3e5, 0.75);
  portraitFill.position.set(-1, 1.65, 3);
  scene.add(portraitFill);
}

// ?motion=xxx.vmd：播放 MMD 专业动作文件（放在 public/motions/ 下），
// 播放期间程序化身体动画让位给 VMD 动作
const motionParam = null;
let vmdMotionActive = false;
let liutingDrape: ReturnType<typeof createLiutingDrape> | undefined;
let liutingWorn = false;

// ---------- MMD 动作管理：运行时加载 / 切换 / 停止 ----------
let mmdMesh: THREE.SkinnedMesh | null = null;
let mmdPhysics: MMDPhysics | null = null;
function simulateInModelSpace<T>(mesh: THREE.SkinnedMesh, run: () => T): T {
  const parent = mesh.parent;
  const pos = mesh.position.clone(), rot = mesh.quaternion.clone(), scale = mesh.scale.clone();
  try {
    mesh.parent = null;
    mesh.position.set(0, 0, 0);
    mesh.quaternion.identity();
    mesh.scale.setScalar(1);
    mesh.updateMatrixWorld(true);
    return run();
  } finally {
    mesh.parent = parent;
    mesh.position.copy(pos);
    mesh.quaternion.copy(rot);
    mesh.scale.copy(scale);
    mesh.updateMatrixWorld(true);
  }
}

function resetPhysics() {
  if (!mmdPhysics) return;
  const physics = mmdPhysics;
  const ammo = (window as any).Ammo;
  simulateInModelSpace(physics.mesh, () => {
    physics.reset();
    const zero = new ammo.btVector3(0, 0, 0);
    try {
      for (const { body, params } of physics.bodies) {
        if (!(params as { type: number }).type) continue;
        const rigid = body as { setLinearVelocity(v: object): void; setAngularVelocity(v: object): void; clearForces(): void };
        rigid.setLinearVelocity(zero);
        rigid.setAngularVelocity(zero);
        rigid.clearForces();
      }
    } finally { ammo.destroy(zero); }
  });
}
let mmdHelper: MMDAnimationHelper | null = null;
let motionRequest = 0;
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

function loadClip(file: string, mesh: THREE.SkinnedMesh, request: number): Promise<THREE.AnimationClip | null> {
  const cached = clipCache.get(file);
  if (cached) return Promise.resolve(cached);
  return new Promise((resolve) => {
    const loader = new MMDLoader();
    loader.loadVMD(
      `/motions/${file}`,
      (vmd) => {
        if (request !== motionRequest) return resolve(null);
        // MMDLoader adds the mesh's local bone positions to VMD translations.
        // Compile against the saved bind pose even when switching mid-stride.
        restorePose();
        const builder = loader.animationBuilder as { build(data: object, model: THREE.SkinnedMesh): THREE.AnimationClip };
        const clip = builder.build(vmd, mesh);
        clipCache.set(file, clip);
        resolve(clip);
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
  stopMotion();
  action = null;
  const request = motionRequest;
  const clip = await loadClip(file, mmdMesh, request);
  if (request !== motionRequest) return;
  if (!clip) { stopMotion(); return; }
  restorePose();
  liutingDrape?.reset();
  mmdHelper = new MMDAnimationHelper();
  // physics: false —— 物理由主循环自己管理（修复了高刷屏加速问题）
  mmdHelper.add(mmdMesh, { animation: clip, physics: false });
  mmdHelper.update(1 / 60); // 先推进一帧摆到动作起始姿势
  resetPhysics();
  vmdMotionActive = true;
}

function stopMotion() {
  ++motionRequest;
  document.querySelector('#motion-list .active')?.classList.remove('active');
  if (!mmdHelper || !mmdMesh) return;
  mmdHelper.objects.get(mmdMesh)?.mixer?.stopAllAction();
  mmdHelper.remove(mmdMesh);
  mmdHelper = null;
  vmdMotionActive = false;
  restorePose();
  resetPhysics();
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
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => [])
      .then((files: (string | { file: string; label?: string })[]) => {
        if (!files.length) { motionSec.hidden = true; return; }
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
            const playback = playMotion(f);
            btn.classList.add('active');
            await playback;
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
    `心月狐模型加载失败：请检查 /models/${modelFile} 及其贴图。` +
    String(err);
}

async function setupHairWardrobe(mesh: THREE.SkinnedMesh) {
  const head = mesh.skeleton.getBoneByName('頭');
  if (!head) return;
  liutingDrape = createLiutingDrape(mesh.skeleton);
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  const folded = materials.filter(material => material.name.startsWith('Lingyun_'));
  const lining = materials.find(material => material.name === "QingyiHairLining");
  const crown = materials.find(material => material.name === 'Liuting_Crown');
  const headJewels = materials.filter(material => material.name.startsWith('Fengguan_'));
  const moonHair = materials.filter(material => material.name.startsWith('MoonHair_'));
  const originals = materials
    .filter(material => /^(Hair_|Cloth_Hairpin$)/.test(material.name));
  const hairColors = materials.filter(material => material.name.startsWith('Hair_') || material === lining)
    .map(material => {
      const toon = material as THREE.MeshToonMaterial;
      const palette = materials.find(mat => mat.name === 'Liuting_' + toon.name) as THREE.MeshToonMaterial | undefined;
      return { toon, ink: toon.color.clone(), glow: toon.emissive.clone(), map: toon.map, palette };
    });
  const styles = new Map([['liuting', '烟柳低绾'], ['lingyun', '青篁半绾'], ['long', '墨色侧髻长发'], ['low', '偏分低盘髻'], ['high', '高挽云髻'], ['braid', '垂肩长辫'], ['original', '原发型']]);
  if (moonHair.length) styles.set('yuexiao',photoOutfit ? '蝶钗银粉卷发' : '花钗烟粉长卷发');
  const outfits = document.createElement('div');
  outfits.className = 'group';
  const outfitLabel = document.createElement('label');
  outfitLabel.className = 'group-title';
  outfitLabel.htmlFor = 'qingyi-outfit';
  outfitLabel.textContent = '衣装';
  const outfitSelect = document.createElement('select');
  outfitSelect.id = outfitLabel.htmlFor;
  for (const [file, label] of Object.entries(costumeLabels)) {
    outfitSelect.add(new Option(label, file));
  }
  outfitSelect.value = costumeFile;
  outfitSelect.onchange = () => {
    const url = new URL(location.href);
    url.searchParams.set('outfit',outfitSelect.value);
    url.searchParams.set('hair',outfitSelect.value === 'lanxu' ? 'liuting' : 'yuexiao');
    location.assign(url.href);
  };
  outfits.append(outfitLabel,outfitSelect);
  document.getElementById('panel')!.append(outfits);
  const group = document.createElement('div');
  group.className = 'group';
  const label = document.createElement('label');
  label.className = 'group-title';
  label.htmlFor = 'qingyi-hair';
  label.textContent = '发型';
  const select = document.createElement('select');
  select.id = label.htmlFor;
  for (const [key, name] of styles) select.add(new Option(name, key));
  group.append(label, select);
  document.getElementById('panel')!.append(group);
  const cache = new Map<string, Promise<THREE.Object3D>>();
  let active = 'original';
  let revision = 0;
  async function change(key: string) {
    const request = ++revision;
    let chosen: THREE.Object3D | undefined;
    try {
      if (key === 'low' || key === 'high' || key === 'braid') {
        if (!cache.has(key)) {
          cache.set(key, new GLTFLoader().loadAsync('/models/qingyi-jade/' + key + '-hair.glb').then(gltf => gltf.scene));
        }
        chosen = await cache.get(key);
      }
    } catch {
      cache.delete(key);
      if (request === revision) select.value = active;
      return;
    }
    if (revision !== request) return;
    liutingWorn = key === 'liuting';
    if (!liutingWorn) liutingDrape?.reset();
    for (const child of head!.children) if (child.userData.qingyiHair) child.visible = false;
    if (chosen) {
      chosen.userData.qingyiHair = true;
      if (chosen.parent !== head) head!.add(chosen);
      chosen.visible = true;
    }
    if (lining) lining.visible = key === 'long' || key === 'liuting';
    if (crown) crown.visible = liutingWorn;
    folded.forEach(material => { material.visible = key === 'lingyun'; });
    originals.forEach(material => {
      material.visible = !chosen && key !== 'lingyun' && key !== 'yuexiao' && !(liutingWorn && material.name === 'Cloth_Hairpin');
    });
    headJewels.forEach(material => { material.visible = liutingWorn; });
    moonHair.forEach(material => { material.visible = key === 'yuexiao'; });
    const restore = mesh.morphTargetDictionary?.QingyiOriginalHair;
    const liuting = mesh.morphTargetDictionary?.QingyiLiutingHair;
    if (restore !== undefined && mesh.morphTargetInfluences) mesh.morphTargetInfluences[restore] = key === 'original' ? 1 : 0;
    if (liuting !== undefined && mesh.morphTargetInfluences) mesh.morphTargetInfluences[liuting] = key === 'liuting' ? 1 : 0;
    for (const { toon, ink, glow, map, palette } of hairColors) {
      if (key === 'original') toon.color.setRGB(1, 1, 1);
      else if (key === 'liuting' && palette) toon.color.copy(palette.color);
      else if (key === 'liuting') toon.color.setRGB(0.50, 0.48, 0.50);
      else toon.color.copy(ink);
      toon.map = key === 'liuting' && palette ? palette.map : map;
      toon.emissive.copy(key === 'liuting' && palette ? palette.emissive : glow);
    }
    active = key;
    select.value = key;
    try { localStorage.setItem('qingyi-hair', key); } catch {}
  }
  select.onchange = () => { void change(select.value); };
  let preferred = 'lingyun';
  try { preferred = localStorage.getItem('qingyi-hair') || preferred; } catch {}
  if (moonOutfit) preferred = 'yuexiao';
  const requested = new URLSearchParams(location.search).get('hair');
  if (requested && styles.has(requested)) preferred = requested;
  await change(styles.has(preferred) ? preferred : 'lingyun');
}
if (modelExt === 'pmx') {
  const wardrobeRevision = moonOutfit && !photoOutfit
    ? [straplessOutfit ? 'magnolia-pbr-2' : 'sleeve-fit-1', lookParams.get('v')].filter(Boolean).join('-') : null;
  const modelRequests = new THREE.LoadingManager();
  if (wardrobeRevision) {
    modelRequests.setURLModifier(url => /\/yuexiao(?:-[^/?]+)?\.(?:pmx|jpg|png)$/i.test(url)
      ? `${url}?v=${encodeURIComponent(wardrobeRevision)}` : url);
  }
  loadPreviewPmx(new MMDLoader(modelRequests),
    `/models/${modelFile}`,
    async (mmd, updateMorphs) => {
      // MMD 单位约 8cm，缩放到米制
      if (qingyiDelivery) {
        const materials = Array.isArray(mmd.material) ? mmd.material : [mmd.material];
        for (const material of materials as THREE.MeshToonMaterial[]) {
          if (material.map) material.map.colorSpace = THREE.SRGBColorSpace;
          material.emissive.multiplyScalar(0.12);
          // The face atlas is fully opaque. MMD's custom blend leaves fine
          // triangle seams on its MSAA silhouette and across the cheeks.
          if (material.name === 'Face_') material.blending = THREE.NoBlending;
        }
      }
      if (qingyiDelivery && straplessOutfit && Array.isArray(mmd.material)) {
        mmd.material = mmd.material.map(base => ['Up_Skin', 'QingyiTorso', 'Down_Skin'].includes(base.name)
          ? shadeMagnoliaSkin(base as THREE.MeshToonMaterial) : base);
        if (lookParams.get('pbr') !== 'off') {
          const room = new RoomEnvironment();
          const generator = new THREE.PMREMGenerator(renderer);
          const reflection = generator.fromScene(room, .03);
          room.dispose();
          generator.dispose();
          const surfaces = await loadMagnoliaMaterials(mmd, `/models/${modelFile}`, reflection.texture);
          surfaces?.enable(true);
          if (!surfaces) reflection.dispose();
        }
      } else if (qingyiDelivery && Array.isArray(mmd.material)) {
        let jewelReflections: THREE.Texture | undefined;
        const finish = !photoOutfit && mmd.material.some(m => m.name === 'Moon_Brocade' || m.name === 'Moon_MagnoliaSatin')
          ? await loadYuexiaoFinishes(modelRequests, new Set(mmd.material.map(m => m.name))) : undefined;
        mmd.material = mmd.material.map((base: THREE.Material) => {
          if (/^(Fengguan_|Lanxu_|Moon_|MoonHair_)/.test(base.name)) {
            if (!jewelReflections) {
              const rig = new RoomEnvironment();
              const generator = new THREE.PMREMGenerator(renderer);
              jewelReflections = generator.fromScene(rig, 0.025).texture;
              generator.dispose();
              rig.dispose();
            }
            if (base.name.startsWith('Moon_') || base.name.startsWith('MoonHair_')) {
              const source = base as THREE.MeshToonMaterial;
              const costume = finish?.(source, jewelReflections);
              if (costume) return costume;
              const metal = /_(Gold|Silver|Engraving|ChasedMetal|SandalGold)$/.test(base.name);
              const carving = base.name === 'Moon_Carving';
              const lock = /^MoonHair_(Silk|Fringe|Tress)$/.test(base.name);
              const hairCard = base.name === 'MoonHair_Fibres';
              const groom = hairCard || (!photoOutfit && /^MoonHair_(Tress|Fringe)$/.test(base.name));
              const biasInset = base.name === 'Moon_IllusionBias';
              const petalWrap = !photoOutfit && base.name === 'Moon_Petal';
              const gauze = base.name === 'Moon_Gauze' || base.name === 'Moon_Veil' || biasInset || petalWrap;
              const fibres = base.name.endsWith('_Down') || /^MoonHair_(Wisps|FrontFall)$/.test(base.name);
              const softCloth = photoOutfit && /^Moon_(Silk|Brocade|Petal|Gauze|Illusion)$/.test(base.name);
              const drawnSilk = !photoOutfit && /^Moon_(Silk|Brocade|Petal|PearlHem|Veil)$/.test(base.name);
              const organza = !photoOutfit && (base.name === 'Moon_Gauze' || base.name === 'Moon_Veil');
              const stone = /_(Opal|Glass|IrisGlass|Pearl|Moonstone|Celadon|LilacEnamel|SandalPearl)$/.test(base.name);
              return new THREE.MeshPhysicalMaterial({
                name: base.name, color: source.color, map: source.map, side: THREE.DoubleSide,
                emissiveMap: drawnSilk || organza ? source.map : null, emissive: drawnSilk || organza ? 0xa59daa : 0x000000,
                emissiveIntensity: organza ? 0.48 : drawnSilk ? 0.64 : 0,
                metalness: metal ? 0.72 : carving ? 0.24 : groom ? 0 : 0.025, roughness: metal ? 0.28 : carving ? 0.42 : stone ? 0.26 : softCloth || fibres ? 0.82 : groom ? 0.53 : drawnSilk || lock ? 0.64 : 0.56,
                anisotropy: groom ? 0.52 : drawnSilk ? 0.22 : 0, anisotropyRotation: groom || drawnSilk ? Math.PI / 2 : 0,
                iridescence: organza ? 0.13 : 0, iridescenceIOR: 1.28, iridescenceThicknessRange: [90, 250],
                sheen: organza ? 0.58 : softCloth ? 0.16 : source.map ? 0.30 : 0, sheenColor: 0xdac4ce, sheenRoughness: 0.55,
                clearcoat: stone ? 0.32 : 0, envMap: jewelReflections,
                envMapIntensity: metal ? 0.72 : stone || carving ? 0.53 : groom ? 0.30 : 0.23,
                transparent: gauze, opacity: gauze ? source.opacity : 1, depthWrite: !gauze || petalWrap,
                alphaTest: hairCard ? 0.28 : fibres ? 0.38 : 0, alphaToCoverage: fibres || hairCard,
              });
            }
            if (base.name.startsWith('Lanxu_')) {
              const source = base as THREE.MeshToonMaterial;
              const gilt = base.name === 'Lanxu_GiltCord';
              const gem = base.name === 'Lanxu_Jade' || base.name === 'Lanxu_SeedPearls';
              const satin = !!source.map;
              return new THREE.MeshPhysicalMaterial({
                name: base.name, color: source.color, map: source.map, side: THREE.DoubleSide,
                metalness: gilt ? 0.72 : 0, roughness: gilt ? 0.28 : gem ? 0.23 : 0.64,
                sheen: satin ? 0.32 : 0, sheenColor: 0xb0c9bb, sheenRoughness: 0.68,
                clearcoat: gem ? 0.35 : 0, envMap: jewelReflections,
                envMapIntensity: satin ? 0.23 : 0.70,
              });
            }
            const metal = ['Fengguan_Gold', 'Fengguan_Wire', 'Fengguan_Recess'].includes(base.name);
            const pearl = base.name === 'Fengguan_Pearl';
            const stone = base.name === 'Fengguan_Carving';
            const toon = base as THREE.MeshToonMaterial;
            return new THREE.MeshPhysicalMaterial({
              name: base.name, color: toon.color, map: toon.map,
              metalness: metal ? 0.74 : stone ? 0.055 : pearl ? 0.14 : 0.20,
              roughness: base.name === 'Fengguan_Wire' ? 0.24 : stone ? 0.46 : metal ? 0.32 : 0.25,
              clearcoat: metal ? 0.08 : stone ? 0.10 : 0.23, clearcoatRoughness: stone ? 0.34 : 0.22,
              envMap: jewelReflections, envMapIntensity: metal ? 0.70 : stone ? 0.30 : 0.57,
              emissive: stone ? 0x17160e : 0x000000, emissiveMap: stone ? toon.map : null,
            });
          }
          if (!base.name.startsWith('Lingyun_')) return base;
          const toon = base as THREE.MeshToonMaterial;
          const metal = base.name === 'Lingyun_Pale_gold';
          const tapered = base.name === 'Lingyun_Feathered_fringe' || base.name === 'Lingyun_Loose_lengths';
          if (tapered && toon.map) {
            // Keep opaque roots from repeating at the transparent ends.
            toon.map.wrapT = THREE.ClampToEdgeWrapping;
            if (base.name === 'Lingyun_Feathered_fringe') toon.map.wrapS = THREE.ClampToEdgeWrapping;
            toon.map.needsUpdate = true;
          }
          return new THREE.MeshStandardMaterial({
            name: base.name, map: toon.map, color: toon.color, side: base.side,
            roughness: metal ? 0.32 : 0.70, metalness: metal ? 0.25 : 0.0,
            alphaTest: tapered ? 0.30 : 0, alphaToCoverage: tapered,
            emissiveMap: toon.map, emissive: toon.map ? 0x595156 : 0x121011,
          });
        });
      }
      mmd.scale.setScalar(0.08);
      mmd.updateMatrixWorld(true);
      // MMD 卡通材质对光照敏感，压低亮度避免过曝
      keyLight.intensity = 1.0;
      rimLight.intensity = 0.5;
      scene.children.forEach((c) => {
        if ((c as THREE.AmbientLight).isAmbientLight) (c as THREE.AmbientLight).intensity = 0.45;
      });
      if (qingyiDelivery) {
        keyLight.color.setHex(0xfff3e7);
        keyLight.intensity = 1.26;
        rimLight.color.setHex(0xc0c9ec);
        rimLight.intensity = 0.67;
        const fill = scene.children.find(c => c instanceof THREE.AmbientLight) as THREE.AmbientLight;
        fill.color.setHex(0xffeee7);
        fill.intensity = 0.64;
      }
      const av = makeMeshAvatar(mmd, MMD_BONES, MMD_MORPHS);
      avatar = av;
      mmdMesh = mmd;
      if (qingyiDelivery) await setupHairWardrobe(mmd);
      snapshotPose(mmd); // 记录初始姿势，供停止动作后恢复

      const magnolia = costumeFile === 'yuexiao-strapless' && qingyiDelivery;
      if ((!qingyiDelivery || magnolia) && lookParams.get('physics') !== 'off') try {
        const ammo = (window as any).Ammo;
        if (typeof ammo === 'function') (window as any).Ammo = await ammo();
        const ud = mmd.geometry.userData.MMD;
        let bodies = ud.rigidBodies, joints = ud.constraints;
        if (magnolia) {
          // This preview PMX also carries the donor wardrobe. Solve the visible outfit's own rig.
          const first = bodies.findIndex((r: { name: string }) => r.name.startsWith('MX_'));
          if (first < 0) throw Error('玉兰抹胸模型缺少物理绑定');
          bodies = bodies.slice(first);
          joints = joints.filter((j: { rigidBodyIndex1: number; rigidBodyIndex2: number }) =>
            j.rigidBodyIndex1 >= first && j.rigidBodyIndex2 >= first)
            .map((j: { rigidBodyIndex1: number; rigidBodyIndex2: number }) => ({
              ...j, rigidBodyIndex1: j.rigidBodyIndex1-first, rigidBodyIndex2: j.rigidBodyIndex2-first
            }));
        }
        mmdPhysics = simulateInModelSpace(mmd, () => new MMDPhysics(mmd, bodies, joints));
      } catch (err) {
        console.warn('MMD 物理初始化失败，继续以无物理模式运行：', err);
      }

      // 手臂预先放到自然姿势，避免布料从 T-pose 大幅甩动。
      // 先通过 base() 记录原始角度，动画循环里 base+down 的写法才不会叠加两次
      for (const [key, rig] of [['leftUpperArm', av.armL], ['rightUpperArm', av.armR]] as const) {
        const b = av.bone(key);
        if (b) b.rotation[rig.axis] = av.base(b)[rig.axis] + rig.down;
      }
      mmd.updateMatrixWorld(true);

      const simulation = mmdPhysics;
      const strips = magnolia && simulation ? simulation.bodies
        .filter(({ bone, params }) => (params as { type: number }).type !== 0 && bone.name.startsWith('MX_'))
        .map(({ bone }) => ({ bone, bind: initPose.get(bone)!, shown: bone.quaternion.clone() })) : [];
      const target = new THREE.Quaternion();
      const stepSimulation = (step: number) => {
        if (!simulation) return;
        // Only the angular deflection deforms these strips. Keep their authored
        // lengths when a fast hand movement briefly stretches a Bullet constraint.
        for (const { bone, bind } of strips) {
          bone.position.copy(bind.pos);
          bone.quaternion.copy(bind.quat);
        }
        mmd.updateMatrixWorld(true);
        simulation.update(step);
        for (const { bone, bind, shown } of strips) {
          target.copy(bone.quaternion);
          const angle = bind.quat.angleTo(target);
          if (!Number.isFinite(angle)) target.copy(bind.quat);
          else if (angle > .42) target.slerp(bind.quat, 1 - .42 / angle);
          shown.slerp(target, 1-Math.exp(-18*step));
          bone.position.copy(bind.pos);
          bone.quaternion.copy(shown);
        }
        mmd.updateMatrixWorld(true);
      };
      if (simulation) simulateInModelSpace(mmd, () => {
        simulation.reset();
        for (let i = 0; i < 45; i++) stepSimulation(1/65);
      });

      // MMDPhysics 每次调用最少模拟 1/65 秒，在高刷新率屏幕（如 165Hz）上
      // 每帧真实时间不足 1/65 秒，物理会被加速 2~3 倍。
      // 因此累积真实时间，攒够一个物理步长才推进一次
      const PHY_STEP = 1 / 65;
      let phyAcc = 0;
      av.update = (dt: number) => {
        if (mmdHelper) mmdHelper.update(dt); // VMD 动作 + IK，每帧平滑推进
        updateMorphs?.();
        if (!simulation) return;
        phyAcc = Math.min(phyAcc + dt, PHY_STEP * 3);
        if (phyAcc < PHY_STEP) return;
        simulateInModelSpace(mmd, () => {
          while (phyAcc >= PHY_STEP) {
            stepSimulation(PHY_STEP);
            phyAcc -= PHY_STEP;
          }
        });
      };

      if (motionParam) await playMotion(motionParam);

      finishSetup(mmd);
    },
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
  stopMotion();
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

  updateCamera();

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
        if (liutingWorn) liutingDrape?.update(dt, headRx, headRy);
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
