import * as THREE from 'three';
import recipes from './yuexiao-finishes.json';

export function shadeMagnoliaSkin(material: THREE.MeshToonMaterial) {
  material.onBeforeCompile = shader => {
    shader.vertexShader = 'varying vec3 vMagnoliaRest;\n' + shader.vertexShader.replace(
      '#include <begin_vertex>', '#include <begin_vertex>\n vMagnoliaRest = position;');
    shader.fragmentShader = 'varying vec3 vMagnoliaRest;\n' + shader.fragmentShader.replace(
      '#include <opaque_fragment>', `
      #if NUM_DIR_LIGHTS > 0
        float area = smoothstep(16.95, 17.47, vMagnoliaRest.y)
          * (1.0 - smoothstep(18.89, 19.30, vMagnoliaRest.y))
          * (1.0 - smoothstep(1.12, 1.53, abs(vMagnoliaRest.x)))
          * smoothstep(-0.20, 0.54, vMagnoliaRest.z);
        vec3 pearl = vec3(0.0);
        float facing = max(0.0, dot(normal, directionalLights[0].direction));
        for (int i = 0; i < NUM_DIR_LIGHTS; ++i) {
          vec3 halfAngle = normalize(directionalLights[i].direction + normalize(vViewPosition));
          float glint = pow(max(0.0, dot(halfAngle, normal)), 21.0);
          pearl += 0.036 * glint * directionalLights[i].color;
        }
        outgoingLight = mix(outgoingLight, outgoingLight * (0.89 + 0.15*facing) + pearl, area);
      #endif
      #include <opaque_fragment>`);
  };
  material.customProgramCacheKey = () => 'magnolia-wrapped-skin';
  return material;
}

export async function loadYuexiaoFinishes(manager: THREE.LoadingManager, materialNames: Set<string>) {
  const loader = new THREE.TextureLoader(manager);
  const maps = new Map<string, THREE.Texture>();
  const active = recipes.filter(r => r.materials.some(name => materialNames.has(name)));
  await Promise.all([...new Set(active.map(r => r.map).filter(Boolean))].map(async name => {
    try {
      const map = await loader.loadAsync(`/models/qingyi-jade/textures/yuexiao-${name}-finish.png`);
      map.flipY = false;
      map.colorSpace = THREE.NoColorSpace;
      map.wrapS = map.wrapT = THREE.RepeatWrapping;
      maps.set(name, map);
    } catch (error) {
      console.warn('Unable to load costume surface', name, error);
    }
  }));
  return (source: THREE.MeshToonMaterial, envMap: THREE.Texture) => {
    const recipe = recipes.find(r => r.materials.includes(source.name));
    if (!recipe) return;
    const detail = maps.get(recipe.map) ?? null;
    const chiffon = source.name === 'Moon_Gauze' || source.name === 'Moon_Veil';
    const wrap = source.name === 'Moon_Petal';
    const opacity = source.opacity * (recipe.opacity ?? 1);
    const material = new THREE.MeshPhysicalMaterial({
      name: source.name, side: THREE.DoubleSide, map: source.map,
      color: source.color.clone().multiply(new THREE.Color(...recipe.tint as [number, number, number])),
      emissive: source.map ? 0xffffff : source.color, emissiveMap: source.map, emissiveIntensity: recipe.fill,
      bumpMap: detail, bumpScale: recipe.bump, roughnessMap: detail, roughness: recipe.roughness,
      metalnessMap: recipe.metalness ? detail : null, metalness: recipe.metalness,
      anisotropy: recipe.anisotropy, anisotropyRotation: Math.PI/2,
      sheen: recipe.sheen, sheenColor: recipe.sheenTint, sheenRoughness: recipe.sheenRough,
      clearcoat: recipe.coat, clearcoatRoughness: recipe.coatRough, ior: 1.48,
      specularIntensity: recipe.specular,
      iridescence: recipe.film, iridescenceIOR: 1.28, iridescenceThicknessRange: [100, 210],
      envMap, envMapIntensity: recipe.env,
      transparent: chiffon || wrap || opacity < 1, opacity, depthWrite: !chiffon,
    });
    if (source.name === 'MoonHair_Fibres') {
      material.alphaTest = 0.34;
      material.alphaToCoverage = true;
    }
    if (recipe.map === 'fibre' || recipe.map === 'mantle' || recipe.map === 'parted-fringe') {
      // A second reflection from tilted cuticles follows the shaft as the
      // head turns. The existing physical lobe supplies the sharper glint.
      material.onBeforeCompile = shader => {
        shader.fragmentShader = shader.fragmentShader.replace('#include <lights_fragment_end>', `
          #include <lights_fragment_end>
          #if NUM_DIR_LIGHTS > 0 && defined(USE_ANISOTROPY)
            vec3 shaft = normalize(material.anisotropyT + 0.13 * normal);
            for (int i = 0; i < NUM_DIR_LIGHTS; ++i) {
              vec3 lightDir = directionalLights[i].direction;
              vec3 halfDir = normalize(lightDir + geometryViewDir);
              float axisDot = clamp(dot(shaft, halfDir), -1.0, 1.0);
              float band = pow(max(0.0, 1.0 - axisDot * axisDot), 24.0);
              float lit = smoothstep(-0.16, 0.72, dot(normal, lightDir));
              reflectedLight.directSpecular += directionalLights[i].color * vec3(1.0,0.85,0.91)
                * (0.090 * band * lit) * mix(vec3(0.5), diffuseColor.rgb, 0.35);
            }
          #endif
        `);
      };
      material.customProgramCacheKey = () => 'yuexiao-hair-cuticle';
    }
    if (recipe.studioResponse && detail) {
      material.onBeforeCompile = shader => {
        shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>',
          '#include <roughnessmap_fragment>\n diffuseColor.rgb *= 0.4 + 1.4 * texelRoughness.b;');
      };
      material.customProgramCacheKey = () => 'yuexiao-cloth-reflectance';
    }
    if (chiffon) {
      // The wardrobe renders straight to an sRGB canvas. Its fixed-function
      // alpha blend mixes display values. Match linear-light thread coverage
      // over the dark stage and pale lining, keeping one transparent draw.
      material.onBeforeCompile = shader => {
        shader.fragmentShader = shader.fragmentShader.replace('#include <colorspace_fragment>', `
          vec3 gauzeRadiance = max(gl_FragColor.rgb, vec3(0.0));
          #include <colorspace_fragment>
          float coverage = gl_FragColor.a;
          vec3 overDark = sRGBTransferOETF(vec4(mix(vec3(0.0072), gauzeRadiance, coverage), 1.0)).rgb;
          vec3 overLight = sRGBTransferOETF(vec4(mix(vec3(0.5705), gauzeRadiance, coverage), 1.0)).rgb;
          float slope = clamp(dot(overLight - overDark, vec3(0.2126, 0.7152, 0.0722)) / 0.70, 0.0, 1.0);
          gl_FragColor.a = 1.0 - slope;
          gl_FragColor.rgb = max(overDark - vec3(0.08 * slope), vec3(0.0)) / max(gl_FragColor.a, 0.0001);
        `);
      };
      material.customProgramCacheKey = () => 'yuexiao-chiffon-coverage';
    }
    return material;
  };
}
