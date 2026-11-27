import * as THREE from 'three';

interface Finish {
  materials: string[];
  map: string;
  tint: [number, number, number];
  fill: number;
  roughness: number;
  metalness: number;
  bump: number;
  anisotropy: number;
  sheen: number;
  sheenTint: string;
  sheenRough: number;
  coat: number;
  coatRough: number;
  specular: number;
  env: number;
  film: number;
  opacity?: number;
  transmission?: number;
  thickness?: number;
  studioResponse?: boolean;
  lacquerBase?: [number,number,number];
}

export interface MagnoliaMaterials {
  enable(on: boolean): void;
  dispose(): void;
}

function skinFinish(base: THREE.MeshToonMaterial, mask: THREE.Texture, body: boolean) {
  const skin = base.clone();
  skin.onBeforeCompile = shader => {
    shader.uniforms.skinZones = { value: mask };
    shader.fragmentShader = (body ? '#define MAGNOLIA_BODY_SKIN\n' : '') + 'uniform sampler2D skinZones;\n' +
      shader.fragmentShader.replace('#include <opaque_fragment>', `
      #if defined(USE_MAP) && NUM_DIR_LIGHTS > 0
        vec4 zones = texture2D(skinZones, vMapUv);
        vec3 V = normalize(vViewPosition);
        #ifdef MAGNOLIA_BODY_SKIN
          // Retain the painted diffuse, with a broad form shadow under side light.
          float keyFacing = dot(normal, directionalLights[0].direction);
          outgoingLight *= 1.0 - .27 * zones.b * (1.0-smoothstep(-.45,.85,keyFacing));
          vec3 softReflection = vec3(0.0);
        #endif
        for (int i = 0; i < NUM_DIR_LIGHTS; ++i) {
          vec3 L = directionalLights[i].direction;
          float rim = pow(1.0 - max(dot(V, normal), 0.0), 1.7);
          float wrap = smoothstep(-0.70, 0.10, -dot(normal, L));
          #ifdef MAGNOLIA_BODY_SKIN
            float nl = max(dot(normal,L),0.0);
            float nv = max(dot(normal,V),.01);
            vec3 H = normalize(L+V);
            float nh = max(dot(normal,H),0.0);
            float a = max(zones.g*zones.g,.12);
            float a2 = a*a;
            float denom = nh*nh*(a2-1.0)+1.0;
            float D = a2 / (3.141593 * denom*denom);
            float visibility = .5/max(nl*sqrt(a2+(1.0-a2)*nv*nv)
                                    +nv*sqrt(a2+(1.0-a2)*nl*nl),.001);
            float fresnel = .028+.972*pow(1.0-max(dot(V,H),0.0),5.0);
            // A broad reflection on the two upper planes. The painted mask
            // follows the body; its brightness follows the actual light and view.
            softReflection += directionalLights[i].color * nl * (.38+.62*pow(nh,6.0));
            outgoingLight += directionalLights[i].color * (
              vec3(.13,.046,.034)*zones.r*rim*wrap +
              vec3(1.0,.94,.92)*zones.b*D*visibility*fresnel*nl);
          #else
          outgoingLight += directionalLights[i].color * (
            vec3(.105,.030,.023) * zones.r * rim * wrap +
            vec3(.027,.021,.022) * zones.b * pow(max(dot(normal, normalize(L+V)),0.0),mix(42.,12.,zones.g))
          );
          #endif
        }
        #ifdef MAGNOLIA_BODY_SKIN
          float headroom = 1.0-smoothstep(.72,1.05,max(max(outgoingLight.r,outgoingLight.g),outgoingLight.b));
          outgoingLight += vec3(.182,.148,.136)*softReflection*(1.0-zones.a)*headroom;
        #endif
      #endif
      #include <opaque_fragment>`);
  };
  skin.customProgramCacheKey = () => body ? 'magnolia-body-skin-v1' : 'magnolia-skin-zones-v1';
  return skin;
}

function clothOrJewel(base: THREE.MeshToonMaterial, r: Finish, detail: THREE.Texture | undefined,
                     environment: THREE.Texture | null) {
  const name = base.name;
  const gauze = name === 'Moon_Gauze' || name === 'Moon_Veil';
  const card = name === 'MoonHair_Fibres';
  const transmission = r.transmission ?? 0;
  const opacity = base.opacity * (r.opacity ?? 1);
  const m = new THREE.MeshPhysicalMaterial({
    name, map: base.map, color: base.color.clone().multiply(new THREE.Color(...r.tint)),
    emissive: base.map ? 0xffffff : base.color, emissiveMap: base.map, emissiveIntensity: r.fill,
    roughness: r.roughness, roughnessMap: detail ?? null, metalness: r.metalness,
    metalnessMap: r.metalness > 0 ? detail ?? null : null,
    bumpMap: r.bump ? detail ?? null : null, bumpScale: r.bump,
    anisotropy: r.anisotropy, anisotropyRotation: Math.PI/2,
    sheen: r.sheen, sheenColor: r.sheenTint, sheenRoughness: r.sheenRough,
    clearcoat: r.coat, clearcoatRoughness: r.coatRough, specularIntensity: r.specular,
    iridescence: r.film, iridescenceIOR: 1.28, iridescenceThicknessRange: [110,210],
    envMap: environment, envMapIntensity: r.env, side: THREE.DoubleSide,
    ior: 1.49, transparent: !card && (transmission > 0 || gauze || name === 'Moon_Petal' || opacity < 1),
    opacity, depthWrite: !transmission && !gauze && name !== 'MoonHair_Filament',
    alphaTest: card ? .34 : name.endsWith('_Nail') ? Math.max(base.alphaTest,.01) : 0,
  });
  if (transmission) {
    // The accessory petals are open shells and often smaller than a pixel
    // at stage distance. Use thin-surface coverage and the PMREM reflection.
    m.forceSinglePass = true;
    m.onBeforeCompile = shader => {
      shader.uniforms.magnoliaTransmission = { value: transmission };
      shader.fragmentShader = 'uniform float magnoliaTransmission;\n' +
        shader.fragmentShader.replace('#include <opaque_fragment>', `
        float facing = abs(dot(normalize(vViewPosition), normal));
        diffuseColor.a *= 1.0 - magnoliaTransmission * (1.0 - pow(1.0-facing,5.0));
        #include <opaque_fragment>`);
    };
    m.customProgramCacheKey = () => 'magnolia-thin-crystal-v1';
  } else if (r.lacquerBase) {
    const pigment = new THREE.Color(...r.lacquerBase);
    m.onBeforeCompile = shader => {
      shader.uniforms.lacquerPigment = { value: pigment };
      shader.fragmentShader = 'uniform vec3 lacquerPigment;\n' + shader.fragmentShader.replace(
        '#include <map_fragment>', '#include <map_fragment>\n diffuseColor.rgb = mix(diffuseColor.rgb, lacquerPigment, .48);');
    };
    m.customProgramCacheKey = () => 'magnolia-nail-lacquer-v1';
  } else if (r.studioResponse && detail) {
    // On the woven atlas B carries the baked studio diffuse correction, not metal.
    m.onBeforeCompile = shader => {
      shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>',
        '#include <roughnessmap_fragment>\n diffuseColor.rgb *= 0.4 + 1.4 * texelRoughness.b;');
    };
    m.customProgramCacheKey = () => 'magnolia-woven-v1';
  }
  return m;
}

/** All extra maps and the manifest travel beside the PMX. The original MMD slots
 * remain available for material comparisons and for older model imports. */
export async function loadMagnoliaMaterials(mesh: THREE.SkinnedMesh, modelUrl: string,
    environment: THREE.Texture | null): Promise<MagnoliaMaterials | null> {
  if (!Array.isArray(mesh.material) || !mesh.material.some(m => m.name === 'Moon_MagnoliaSatin')) return null;
  const original = mesh.material;
  const folder = new URL('.', new URL(modelUrl, location.href));
  const maps = new Map<string, THREE.Texture>();
  const made: THREE.Material[] = [];
  const dispose = () => {
    mesh.material = original;
    made.forEach(material => material.dispose());
    maps.forEach(texture => texture.dispose());
  };
  try {
    const response = await fetch(new URL('xiaokeai-pbr.json', folder), { cache: 'no-cache' });
    if (response.status === 404) return null;
    if (!response.ok) throw Error(String(response.status));
    const profile = await response.json();
    if (profile.version !== 1 || !Array.isArray(profile.finishes)) throw Error('Unknown PBR profile');
    const names = new Set(original.map(m => m.name));
    const recipes = new Map<string,Finish>();
    for (const r of profile.finishes as Finish[]) {
      for (const n of r.materials) if (names.has(n)) recipes.set(n,r);
    }
    const files = new Set(Array.from(recipes.values(), r => r.map).filter(Boolean));
    const skinZones = new Map<string,string>();
    for (const [slot, file] of Object.entries(profile.skinZones ?? {Face_: 'skin-zones'})) {
      if (names.has(slot) && typeof file === 'string') {
        skinZones.set(slot,file);
        files.add(file);
      }
    }
    const loader = new THREE.TextureLoader();
    const loads = await Promise.allSettled([...files].map(async file => {
      if (!/^[a-z0-9-]+$/.test(file)) throw Error('Invalid material map name');
      const texture = await loader.loadAsync(new URL('textures/yuexiao-'+file+'-finish.png',folder).href);
      texture.colorSpace = THREE.NoColorSpace;
      texture.flipY = false;
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      maps.set(file,texture);
    }));
    const failed = loads.find(load => load.status === 'rejected');
    if (failed?.status === 'rejected') throw failed.reason;
    const enhanced = original.map(base => {
      const r = recipes.get(base.name);
      const skin = skinZones.get(base.name);
      const mat = skin ? skinFinish(base as THREE.MeshToonMaterial, maps.get(skin)!,base.name !== 'Face_') :
        r ? clothOrJewel(base as THREE.MeshToonMaterial,r,maps.get(r.map),environment) : base;
      if (mat !== base) { mat.visible = base.visible; made.push(mat); }
      return mat;
    });
    return { enable: on => { mesh.material = on ? enhanced : original; }, dispose };
  } catch (error) {
    dispose();
    console.warn('未加载模型附带的 PBR 材质',error);
    return null;
  }
}
