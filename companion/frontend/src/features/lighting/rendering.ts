import * as THREE from 'three';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { FullScreenQuad } from 'three/examples/jsm/postprocessing/Pass.js';
import type { LightingProfile } from './preferences';

const keyPosition = new THREE.Vector3(1.2, 2.2, 2.5);
const keyRadius = Math.hypot(keyPosition.x, keyPosition.z);

export function applyCharacterLights(
  key: THREE.DirectionalLight,
  rim: THREE.DirectionalLight,
  ambient: THREE.AmbientLight,
  base: { key: number; rim: number; amb: number },
  level: number,
  profile?: LightingProfile,
) {
  const contrast = (profile?.contrast ?? 0) / 100;
  const angle = THREE.MathUtils.degToRad(profile?.direction ?? 26);
  key.position.copy(keyPosition);
  if (profile && profile.direction !== 26) {
    key.position.set(Math.sin(angle) * keyRadius, keyPosition.y, Math.cos(angle) * keyRadius);
  }
  key.color.set(profile?.color ?? '#ffffff');
  key.intensity = base.key * level * (1 + contrast * 0.3);
  ambient.intensity = base.amb * level * (1 - contrast * 0.75);
  rim.intensity = base.rim * level * (1 + contrast * 0.4);
}

export class CharacterLighting {
  private gradient?: THREE.DataTexture;
  private originalGradients = new Map<THREE.MeshToonMaterial, THREE.Texture | null>();
  private outlineRoot: THREE.Object3D | null = null;
  private mask?: THREE.WebGLRenderTarget;
  private quad?: FullScreenQuad;
  private width = new THREE.Vector2();

  attach(root: THREE.Object3D | null, profile?: LightingProfile) {
    this.clear();
    if (!root || !profile) return;
    if (profile.outline) this.outlineRoot = root;
    if (!profile.toon) return;
    root.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh) return;
      const surfaces = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of surfaces as THREE.MeshToonMaterial[]) {
        if (!material.isMeshToonMaterial || material.transparent || this.originalGradients.has(material)) continue;
        if (!this.gradient) {
          this.gradient = new THREE.DataTexture(
            new Uint8Array([168, 168, 168, 174, 192, 222, 247, 255]), 8, 1, THREE.RedFormat,
        );
          this.gradient.minFilter = this.gradient.magFilter = THREE.LinearFilter;
          this.gradient.needsUpdate = true;
        }
        this.originalGradients.set(material, material.gradientMap);
        material.gradientMap = this.gradient;
        material.needsUpdate = true;
      }
    });
  }

  renderOutline(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera) {
    const root = this.outlineRoot;
    if (!root?.visible || root.parent !== scene) return;

    const output = renderer.getRenderTarget();
    const size = output ? this.width.set(output.width, output.height) : renderer.getDrawingBufferSize(this.width);
    const scale = Math.min(1, 1080 / Math.max(size.x, size.y));
    const mask = this.mask ??= new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
    });
    mask.setSize(Math.max(1, Math.round(size.x * scale)), Math.max(1, Math.round(size.y * scale)));

    // Render character coverage with the original materials so alpha-tested and blended textures
    // keep their actual shape. The screen pass draws only outside that combined coverage.
    const hidden = scene.children.filter((object) => object.visible && object !== root && !(object as THREE.Light).isLight);
    const background = scene.background;
    const clearAlpha = renderer.getClearAlpha();
    const autoClear = renderer.autoClear;
    const shadowAutoUpdate = renderer.shadowMap.autoUpdate;
    const shadowNeedsUpdate = renderer.shadowMap.needsUpdate;
    try {
      hidden.forEach((object) => { object.visible = false; });
      scene.background = null;
      renderer.setClearAlpha(0);
      renderer.autoClear = false;
      renderer.shadowMap.autoUpdate = false;
      renderer.shadowMap.needsUpdate = false;
      renderer.setRenderTarget(mask);
      renderer.clear(true, true, false);
      renderer.render(scene, camera);
    } finally {
      renderer.setRenderTarget(output);
      renderer.setClearAlpha(clearAlpha);
      renderer.autoClear = autoClear;
      renderer.shadowMap.autoUpdate = shadowAutoUpdate;
      renderer.shadowMap.needsUpdate = shadowNeedsUpdate;
      scene.background = background;
      hidden.forEach((object) => { object.visible = true; });
    }

    const quad = this.quad ??= new FullScreenQuad(makeOutlineMaterial());
    const material = quad.material as THREE.ShaderMaterial;
    const radius = 1.2 * renderer.getPixelRatio();
    material.uniforms.coverage.value = mask.texture;
    material.uniforms.stepUv.value.set(radius / size.x, radius / size.y);
    try {
      renderer.autoClear = false;
      quad.render(renderer);
    } finally {
      renderer.autoClear = autoClear;
    }
  }

  clear() {
    for (const [material, gradient] of this.originalGradients) {
      material.gradientMap = gradient;
      material.needsUpdate = true;
    }
    this.originalGradients.clear();
    this.gradient?.dispose();
    this.gradient = undefined;
    this.outlineRoot = null;
    this.mask?.dispose();
    this.mask = undefined;
    this.quad?.material.dispose();
    // FullScreenQuad uses shared geometry. Only this effect's material is owned here.
    this.quad = undefined;
  }
}

function makeOutlineMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      coverage: { value: null },
      stepUv: { value: new THREE.Vector2() },
      ink: { value: new THREE.Color('#303047') },
    },
    vertexShader: `
      varying vec2 screenUv;
      void main() {
        screenUv = uv;
        gl_Position = vec4(position.xy, 0.0, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D coverage;
      uniform vec2 stepUv;
      uniform vec3 ink;
      varying vec2 screenUv;

      float alphaAt(vec2 offset) {
        vec2 uv = screenUv + offset * stepUv;
        return texture2D(coverage, uv).a;
      }

      void main() {
        float center = alphaAt(vec2(0.0));
        if (center >= 0.25) discard;
        float right = alphaAt(vec2(1.0, 0.0));
        float left = alphaAt(vec2(-1.0, 0.0));
        float up = alphaAt(vec2(0.0, 1.0));
        float down = alphaAt(vec2(0.0, -1.0));
        float axial = max(max(right, left), max(up, down));
        float diagonal = max(
          max(alphaAt(vec2(0.707, 0.707)), alphaAt(vec2(-0.707, 0.707))),
          max(alphaAt(vec2(0.707, -0.707)), alphaAt(vec2(-0.707, -0.707)))
        );
        float outer = smoothstep(0.4, 0.95, max(axial, diagonal));
        float gap = max(min(left, right), min(up, down));
        float edge = outer * (1.0 - smoothstep(0.02, 0.25, center))
                           * (1.0 - smoothstep(0.25, 0.65, gap));
        if (edge <= 0.0) discard;
        gl_FragColor = vec4(ink, edge * 0.58);
        #include <colorspace_fragment>
      }
    `,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  });
}

export class CharacterLightingPass extends RenderPass {
  constructor(scene: THREE.Scene, camera: THREE.Camera, private lighting: CharacterLighting) {
    super(scene, camera);
  }

  override render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    super.render(renderer, writeBuffer, readBuffer, 0, false);
    this.lighting.renderOutline(renderer, this.scene, this.camera);
  }
}