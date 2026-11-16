import { watch } from 'vue';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { stage, type StagePlugin } from '../../engine/stage';
import { stageLife } from './stageLife';

const MODELS: Record<string, string> = {
  car: '/assets/life/vehicles/sedan.glb',
  fuel_car: '/assets/life/vehicles/sedan.glb',
  camper: '/assets/life/vehicles/van.glb',
};

function release(root: THREE.Object3D) {
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry?.dispose();
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (!material) continue;
      const mat = material as THREE.MeshStandardMaterial;
      mat.map?.dispose();
      material.dispose();
    }
  });
}

/** A disposable stage plugin: only owns its model and never changes the avatar. */
export function installLifeVehicles() {
  const loader = new GLTFLoader();
  const group = new THREE.Group();
  group.name = 'life-vehicle';
  let current: THREE.Object3D | null = null;
  let generation = 0;
  let elapsed = 0;
  let wheels: THREE.Object3D[] = [];
  const plugin: StagePlugin = {
    id: 'life-vehicles',
    onFrame(dt) {
      if (!current || !stageLife.active || !MODELS[stageLife.activityArt]) return;
      if (stage.threeScene && group.parent !== stage.threeScene) stage.threeScene.add(group);
      elapsed = Math.min(elapsed + Math.min(dt, 0.1), 1.5);
      const remaining = 1 - elapsed / 1.5;
      group.position.x = 1.05 + remaining * remaining * 1.1;
      if (elapsed < 1.5) wheels.forEach(wheel => { wheel.rotation.x -= dt * 4; });
    },
  };
  stage.use(plugin);
  function clear() {
    if (current) { group.remove(current); release(current); current = null; }
    group.removeFromParent();
    wheels = [];
  }
  const stop = watch(() => [stageLife.active, stageLife.activityArt] as const, async ([active, activity]) => {
    const id = ++generation;
    clear();
    stageLife.vehicleStatus = '';
    const url = active ? MODELS[activity] : undefined;
    if (!url) return;
    stageLife.vehicleStatus = 'loading';
    try {
      const gltf = await loader.loadAsync(url);
      if (id !== generation) { release(gltf.scene); return; }
      current = gltf.scene;
      const bounds = new THREE.Box3().setFromObject(current);
      const size = bounds.getSize(new THREE.Vector3());
      const scale = 1.5 / Math.max(size.x, size.y, size.z, 0.01);
      current.scale.setScalar(scale);
      current.rotation.y = -0.65;
      current.position.y = -bounds.min.y * scale;
      current.traverse(node => { if (node.name.toLowerCase().startsWith('wheel')) wheels.push(node); });
      group.add(current);
      group.position.set(2.15, 0, 0.1);
      if (stage.threeScene) stage.threeScene.add(group);
      stage.playShot('full');
      elapsed = 0;
      stageLife.vehicleStatus = 'ready';
    } catch {
      if (id === generation) stageLife.vehicleStatus = 'failed';
    }
  }, { immediate: true });
  return () => { generation++; stop(); clear(); stage.unuse('life-vehicles'); stageLife.vehicleStatus = ''; };
}
