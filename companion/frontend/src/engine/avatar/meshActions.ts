import * as THREE from 'three';
import type { ArmRig, BoneKey } from '../types';

const CLIP_ALIASES: Record<string, string[]> = {
  greet: ['wave', 'hello', 'greet'],
  think: ['think'],
  talk: ['talk', 'speak'],
  bow: ['bow'],
  clap: ['clap', 'applause'],
  heart: ['heart'],
  shy: ['shy'],
  comfort: ['comfort'],
  tease: ['tease'],
  look: ['look'],
  stretch: ['stretch'],
  cute: ['cute'],
};

const PROCEDURAL_ACTIONS = new Set([
  'greet', 'think', 'talk', 'bow', 'clap', 'heart', 'shy',
  'comfort', 'tease', 'look', 'stretch', 'cute',
]);

type BoneResolver = (key: BoneKey) => THREE.Object3D | null;

export class MeshActionController {
  active = false;

  private readonly mixer?: THREE.AnimationMixer;
  private clipAction: THREE.AnimationAction | null = null;
  private fallback = '';
  private time = 0;

  constructor(
    root: THREE.Object3D,
    private readonly clips: THREE.AnimationClip[],
    private readonly bone: BoneResolver,
    private readonly base: (obj: THREE.Object3D) => THREE.Euler,
    private readonly armL: ArmRig,
    private readonly armR: ArmRig,
  ) {
    if (clips.length) {
      this.mixer = new THREE.AnimationMixer(root);
      this.mixer.addEventListener('finished', (event) => {
        if (event.action === this.clipAction) this.active = false;
      });
    }
  }

  play(name: string): boolean {
    const aliases = CLIP_ALIASES[name] ?? [];
    const clip = this.clips.find((item) => {
      const clipName = item.name.toLowerCase();
      return aliases.some((alias) => clipName.includes(alias));
    });
    this.clipAction?.fadeOut(0.15);
    this.clipAction = null;
    this.mixer?.stopAllAction();
    this.time = 0;
    this.fallback = clip ? '' : name;
    this.active = clip ? !!this.mixer : PROCEDURAL_ACTIONS.has(name);
    if (clip && this.mixer) {
      this.clipAction = this.mixer.clipAction(clip);
      this.clipAction.reset()
        .setLoop(THREE.LoopOnce, 1)
        .fadeIn(0.2)
        .play();
      this.clipAction.clampWhenFinished = true;
    }
    return this.active;
  }

  update(dt: number) {
    this.mixer?.update(dt);
    if (!this.active || !this.fallback) return;
    this.time += dt;
    const p = Math.min(1, this.time / 2);
    const envelope = Math.sin(Math.PI * p);
    this.applyFallback(this.fallback, p, envelope);
    if (p >= 1) {
      this.active = false;
      this.fallback = '';
    }
  }

  private applyFallback(name: string, p: number, envelope: number) {
    const head = this.bone('head');
    const spine = this.bone('spine');
    const left = this.bone('leftUpperArm');
    const right = this.bone('rightUpperArm');
    if (head) {
      const base = this.base(head);
      head.rotation.set(base.x, base.y, base.z);
      if (name === 'think') head.rotation.z += 0.2 * envelope;
      else if (name === 'shy') head.rotation.x += 0.18 * envelope;
      else if (name === 'look') head.rotation.y += 0.35 * envelope;
      else head.rotation.x += 0.16 * Math.sin(p * Math.PI * 4) * envelope;
    }
    if (spine && name === 'bow') {
      const base = this.base(spine);
      spine.rotation.x = base.x + 0.45 * envelope;
    }
    const both = name === 'clap' || name === 'heart' || name === 'cute' || name === 'stretch';
    if (left && (both || name === 'think')) {
      const base = this.base(left);
      left.rotation[this.armL.axis] = base[this.armL.axis]
        + this.armL.down + this.armL.up * envelope * (both ? 0.85 : 0.45);
    }
    if (right) {
      const base = this.base(right);
      const wave = name === 'greet' ? Math.sin(p * Math.PI * 8) * 0.22 * envelope : 0;
      const amount = both || name === 'greet' || name === 'tease' ? 0.9 : 0.25;
      right.rotation[this.armR.axis] = base[this.armR.axis]
        + this.armR.down + this.armR.up * amount * envelope + wave;
    }
  }
}
