import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const view = document.querySelector<HTMLElement>('#view')!;
const status = document.querySelector<HTMLElement>('#status')!;
const renderer = new THREE.WebGLRenderer({ canvas: view.querySelector('canvas')!, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
const scene = new THREE.Scene();
scene.background = new THREE.Color('#302f33');
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.02, 10);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1.38, 0.005);
controls.enablePan = false;
controls.minZoom = 0.75;
controls.maxZoom = 3;
controls.minPolarAngle = 0.35;
controls.maxPolarAngle = 2.6;
scene.add(new THREE.HemisphereLight(0xfffaf4, 0xc9c0b9, 0.94));
function lightRig(lamps: number[][]) {
  const group = new THREE.Group();
  for (const [x, y, z, power] of lamps) {
    const light = new THREE.DirectionalLight(0xfffaf6, power);
    light.target.position.copy(controls.target);
    light.position.copy(controls.target).add(new THREE.Vector3(x, y, z));
    group.add(light, light.target);
  }
  scene.add(group);
  return group;
}
const studio = lightRig([[-1.8, 2.1, 2.2, 2.1], [1.8, 0.65, 1.4, 0.52], [1.3, 1.8, -2, 1.0]]);
const balanced = lightRig([[-1.0, 2.1, 1.7, 1.32], [1.0, 2.1, 1.7, 1.32], [0, 1.8, -2, 1]]);
const render = () => renderer.render(scene, camera);
controls.addEventListener('change', () => {
  if (balanced.visible && Math.abs(controls.getAzimuthalAngle()) > 0.015) {
    balanced.visible = false;
    studio.visible = true;
  }
  render();
});
function setAngle(degrees: number) {
  const radians = THREE.MathUtils.degToRad(degrees);
  balanced.visible = degrees === 0;
  studio.visible = !balanced.visible;
  camera.position.copy(controls.target).add(new THREE.Vector3(-1.15 * Math.sin(radians), 0.024, 1.15 * Math.cos(radians)));
  controls.update();
  render();
}
function resize() {
  const { width, height } = view.getBoundingClientRect();
  const aspect = width / Math.max(height, 1);
  const half = 0.5 * Math.max(0.52, 0.59 / aspect);
  camera.left = -half * aspect;
  camera.right = half * aspect;
  camera.top = half;
  camera.bottom = -half;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  render();
}
setAngle(0);
new ResizeObserver(resize).observe(view);
resize();
let version = 1;
const shapes = new Map<number, THREE.Object3D>();
function applyShape() {
  for (const [key, mesh] of shapes) mesh.visible = key === version;
  render();
}
function mark(group: string, button?: HTMLButtonElement) {
  document.querySelectorAll<HTMLButtonElement>(group).forEach(b => b.setAttribute('aria-pressed', String(b === button)));
}
for (const b of document.querySelectorAll<HTMLButtonElement>('[data-shape]')) {
  b.onclick = () => { version = Number(b.dataset.shape); mark('[data-shape]', b); applyShape(); };
}
for (const b of document.querySelectorAll<HTMLButtonElement>('[data-angle]')) {
  b.onclick = () => { setAngle(Number(b.dataset.angle)); mark('[data-angle]', b); };
}
controls.addEventListener('start', () => mark('[data-angle]'));
new GLTFLoader().load('/models/qingyi-jade/xiaokeai-torso-base.glb?rev=smooth-03', gltf => {
  gltf.scene.traverse(o => {
    if (!(o instanceof THREE.Mesh)) return;
    if (o.name === 'Previous') shapes.set(0, o);
    if (o.name === 'Sculpt') shapes.set(1, o);
  });
  if (shapes.size !== 2) { status.textContent = '底模形态缺失'; return; }
  scene.add(gltf.scene);
  applyShape();
  status.hidden = true;
}, undefined, () => { status.textContent = '底模载入失败，请刷新重试'; });
